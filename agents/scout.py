"""Scout agent - monitors feeds and detects newsworthy content."""
import feedparser
from typing import Any
from uuid import uuid4
from agents.base import BaseAgent, AgentRole
from db import Task, event_store, task_queue, TaskStage
from config.logging import get_logger

logger = get_logger(__name__)


class ScoutAgent(BaseAgent):
    """Scout agent that monitors RSS feeds for newsworthy content."""

    def __init__(self, feeds: list[str]):
        super().__init__(AgentRole.SCOUT)
        self.feeds = feeds

    async def handle_task(self, task: Task) -> dict[str, Any]:
        """
        Scouts don't process tasks from the queue.
        They proactively scan feeds and create stories.
        """
        return {"status": "scout_task_not_applicable"}

    def calculate_newsworthiness(self, entry: dict) -> float:
        """Calculate newsworthiness score for a feed entry."""
        score = 0.0
        
        # Has title and description
        if entry.get("title") and entry.get("summary"):
            score += 0.3
        
        # Recent (less than 24 hours old)
        # TODO: Implement time-based scoring
        score += 0.2
        
        # Has links/sources
        if entry.get("link"):
            score += 0.2
        
        # Length indicates substance
        summary = entry.get("summary", "")
        if len(summary) > 200:
            score += 0.2
        
        # TODO: Add semantic novelty check against existing stories
        # TODO: Add entity extraction
        # TODO: Add impact estimation
        
        return min(score, 1.0)

    async def scan_feed(self, feed_url: str) -> None:
        """Scan a single RSS feed for newsworthy content."""
        logger.info("Scanning feed", feed_url=feed_url)
        
        # Import services here to avoid circular imports if any
        from ingestion.embeddings import embedding_service
        from ingestion import entity_extractor
        from db.memory import memory_store
        
        try:
            feed = feedparser.parse(feed_url)
            
            for entry in feed.entries[:10]:  # Limit to recent 10 entries
                score = self.calculate_newsworthiness(entry)
                
                if score < 0.6:
                    continue
                
                title = entry.get("title", "")
                summary = entry.get("summary", "")[:500]
                content_for_embedding = f"{title}. {summary}"
                
                # Check for duplicates using embeddings
                try:
                    embedding = embedding_service.embed(content_for_embedding)
                    similar_stories = await memory_store.find_similar_stories(
                        embedding, threshold=0.85, limit=1
                    )
                except Exception as e:
                    logger.error("Embedding generation failed", error=str(e))
                    embedding = []
                    similar_stories = []
                
                if similar_stories:
                    # Duplicate found - link to existing story
                    existing_story = similar_stories[0]
                    story_id = existing_story["story_id"]
                    is_duplicate = True
                    logger.info(
                        "Duplicate story detected",
                        new_title=title,
                        existing_story_id=str(story_id),
                        similarity=existing_story["similarity"]
                    )
                else:
                    # New story
                    story_id = uuid4()
                    is_duplicate = False
                
                # Log detection event
                await self.log_event(
                    story_id,
                    "story.detected",
                    {
                        "source": feed_url,
                        "title": title,
                        "url": entry.get("link"),
                        "summary": summary,
                        "score": score,
                        "published": entry.get("published"),
                        "is_duplicate": is_duplicate,
                    },
                )
                
                # If new, save to memory for future deduplication
                if not is_duplicate and embedding:
                    # Extract entities for metadata
                    entities_meta = {}
                    if entity_extractor:
                        try:
                            extracted = entity_extractor.extract(f"{title}. {summary}")
                            entities_meta = {
                                "people": [e.text for e in extracted if e.label_ == "PERSON"],
                                "orgs": [e.text for e in extracted if e.label_ == "ORG"],
                                "gpe": [e.text for e in extracted if e.label_ == "GPE"],
                            }
                        except Exception as e:
                            logger.warning("Entity extraction failed", error=str(e))

                    await memory_store.add(
                        story_id=story_id,
                        content=content_for_embedding,
                        embedding=embedding,
                        memory_type="summary",
                        metadata={
                            "source": feed_url, 
                            "url": entry.get("link"),
                            "entities": entities_meta
                        }
                    )
                
                if not is_duplicate:
                    logger.info(
                        "New story detected",
                        story_id=str(story_id),
                        title=title,
                        score=score,
                    )
                
        except Exception as e:
            logger.error("Feed scan failed", feed_url=feed_url, error=str(e))

    async def run(self) -> None:
        """Override run to proactively scan feeds."""
        await self.register()
        self._running = True
        
        logger.info(
            "Scout started",
            agent_id=str(self.agent_id),
            feed_count=len(self.feeds),
        )
        
        while self._running:
            for feed_url in self.feeds:
                await self.scan_feed(feed_url)
            
            # Wait before next scan
            import asyncio
            await asyncio.sleep(300)  # Scan every 5 minutes
            await self.heartbeat()
