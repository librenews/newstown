"""Reporter agent - researches and writes stories."""
from typing import Any
from agents.base import BaseAgent, AgentRole
from db import Task, TaskStage
from config.logging import get_logger
from config.settings import settings
import anthropic

logger = get_logger(__name__)


class ReporterAgent(BaseAgent):
    """Reporter agent that researches and drafts articles."""

    def __init__(self):
        super().__init__(AgentRole.REPORTER)
        # Use ChatService abstraction
        from agents.llm import chat_service
        self.chat_service = chat_service

    async def handle_task(self, task: Task) -> dict[str, Any]:
        """Handle research or draft tasks."""
        
        if task.stage == TaskStage.RESEARCH:
            return await self.research(task)
        elif task.stage == TaskStage.DRAFT:
            return await self.draft(task)
        elif task.stage == TaskStage.EDIT:
            return await self.revise(task)
        else:
            raise ValueError(f"Reporter cannot handle stage: {task.stage}")

    async def research(self, task: Task) -> dict[str, Any]:
        """Research a story using a two-phase (Discovery & Deep Dive) strategy."""
        detection_data = task.input.get("detection_data", {})
        
        title = detection_data.get("title", "")
        summary = detection_data.get("summary", "")
        original_url = detection_data.get("url", "")
        
        logger.info(
            "Phase 4.5 Research started",
            story_id=str(task.story_id),
            title=title,
        )
        
        from ingestion import search_service, entity_extractor
        from ingestion.embeddings import embedding_service
        from db.human_oversight import human_prompt_store, source_store
        from db.memory import memory_store
        
        # Phase 1: Discovery & Initial Extraction
        initial_entities_list = entity_extractor.extract(f"{title}. {summary}") if entity_extractor else []
        
        # LLM entity refinement
        refined_entities = await self._refine_entities(
            title=title, 
            summary=summary, 
            initial_entities=initial_entities_list
        )
        
        # Contextual Memory Retrieval
        historical_context = []
        try:
            embedding = embedding_service.embed(f"{title}. {summary}")
            similar_memories = await memory_store.find_similar_stories(embedding, limit=3)
            for memory in similar_memories:
                if str(memory["story_id"]) != str(task.story_id):
                    historical_context.append(memory)
        except Exception: pass

        # Discovery Search
        discovery_results = await search_service.search(title, num_results=5)
        
        # Phase 2: Deep Dive (Investigative Questions)
        investigative_questions = await self._generate_investigative_questions(
            title=title,
            summary=summary,
            entities=refined_entities,
            discovery_snippets=[r.snippet for r in discovery_results[:3]]
        )
        
        deep_results = []
        for query in investigative_questions[:2]: # Multi-hop: deep dive into specific leads
            results = await search_service.search(query, num_results=2)
            deep_results.extend(results)

        # Merge and Corroborate
        all_results = discovery_results + deep_results
        unique_results = {}
        for r in all_results:
            if r.url != original_url: unique_results[r.url] = r

        sources = [{
            "url": original_url,
            "title": title,
            "snippet": summary[:200],
            "type": "original"
        }]
        
        for r in unique_results.values():
            sources.append({
                "url": r.url,
                "title": r.title,
                "snippet": r.snippet,
                "type": "corroboration",
                "reliability_score": self._score_reliability(r.url) 
            })

        # Facts & Prompts (Phase 2 logic continues...)
        verified = len(sources) >= 3 # Higher threshold for 4.5
        facts = [{"claim": f"Core topic: {title}", "source": original_url, "verified": verified}]

        await self.log_event(task.story_id, "research.enhanced_completed", {
            "discovery_count": len(discovery_results),
            "deep_dive_count": len(deep_results),
            "entities_refined": len(refined_entities.get("people", [])) + len(refined_entities.get("organizations", []))
        })
        
        return {
            "facts": facts,
            "sources": sources,
            "entities": refined_entities,
            "verified": verified,
            "investigative_leads": investigative_questions,
            "historical_context": historical_context
        }

    async def _refine_entities(self, title: str, summary: str, initial_entities: list) -> dict:
        """Use LLM to refine, deduplicate and disambiguate entities."""
        entity_text = ", ".join([f"{e.text} ({e.label_})" for e in initial_entities])
        prompt = f"""Story: {title}
Context: {summary}
Initial Entities identified: {entity_text}

Task: Refine this list. Deduplicate, fix miscategorizations, and verify relevance.
Return JSON: {{"people": [], "organizations": [], "locations": [], "key_events": []}}
"""
        try:
            content = await self.chat_service.generate(
                system="You are a meticulous data journalist.",
                messages=[{"role": "user", "content": prompt}]
            )
            # Standard JSON extraction
            start, end = content.find("{"), content.rfind("}") + 1
            if start != -1 and end != -1:
                return json.loads(content[start:end])
        except Exception: pass
        return {"people": [], "organizations": [], "locations": []}

    async def _generate_investigative_questions(self, title: str, summary: str, entities: dict, discovery_snippets: list) -> list:
        """Generate specific queries for Phase 2 'Deep Dive' research."""
        context = "\n".join(discovery_snippets)
        prompt = f"""Story: {title}
Known Context: {summary}
Early findings: {context}
Entities: {entities}

Task: Generate 3 specific search queries to find missing details or corroboration for this story.
Return JSON list: ["query 1", "query 2", "query 3"]
"""
        try:
            content = await self.chat_service.generate(
                system="You are an investigative reporter.",
                messages=[{"role": "user", "content": prompt}]
            )
            start, end = content.find("["), content.rfind("]") + 1
            if start != -1 and end != -1:
                return json.loads(content[start:end])
        except Exception: pass
        return [f"{title} official statement", f"{title} background"]

    def _score_reliability(self, url: str) -> float:
        """Score source reliability based on domain patterns."""
        reliability = 0.5
        if any(d in url for d in [".gov", ".edu", "reuters.com", "apnews.com", "nytimes.com", "bbc.co.uk"]):
            reliability = 0.9
        elif any(d in url for d in ["twitter.com", "facebook.com", "reddit.com", "blogspot.com"]):
            reliability = 0.3
        return reliability

    async def _answer_prompt(self, question: str, context: dict[str, Any]) -> str:
        """Answer a human prompt using research context."""
        sources_text = "\n".join([
            f"- {s.get('title', 'Untitled')}: {s.get('snippet', s.get('full_content', 'No content'))[:150]}"
            for s in context["sources"][:5]
        ])
        
        context_text = ""
        if context.get("historical_context"):
            context_text = "\nHistorical Context:\n" + "\n".join([
                f"- {h['content'][:150]}..." for h in context["historical_context"][:2]
            ])
        
        prompt = f"""You are a research assistant.
Story: {context['title']}
Context: {context['summary']}

Question: {question}

Sources:
{sources_text}
{context_text}

Answer the question based on findings.
"""
        try:
            return await self.chat_service.generate(
                system="You are a helpful research assistant.",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
            )
        except Exception:
            return "Unable to answer."

    async def draft(self, task: Task) -> dict[str, Any]:
        """Draft an article."""
        detection_data = task.input.get("detection_data", {})
        research_data = task.input.get("research_data", {})
        
        logger.info(
            "Drafting article",
            story_id=str(task.story_id),
            title=detection_data.get("title"),
        )
        
        sources = research_data.get("sources", [])
        entities = research_data.get("entities", {})
        facts = research_data.get("facts", [])
        verified = research_data.get("verified", False)
        historical_context = research_data.get("historical_context", [])
        
        # Build context string
        context_section = ""
        if historical_context:
            context_section = "\nHistorical Context/Related Stories:\n" + "\n".join([
                f"- {item['content']}" for item in historical_context
            ])
        
        prompt = f"""Title: {detection_data.get('title')}
Original Summary: {detection_data.get('summary')}
Source URL: {detection_data.get('url')}

Research Findings:
- Verified: {verified}
- Number of independent sources: {len(sources)}
- People: {', '.join(entities.get('people', [])[:5]) or 'None'}
- Orgs: {', '.join(entities.get('organizations', [])[:5]) or 'None'}

Key facts:
{chr(10).join(f"- {fact['claim']}" for fact in facts[:5])}

Additional sources:
{chr(10).join(f"- {s['title']}: {s['snippet'][:100]}..." for s in sources[1:4])}
{context_section}

Write a clear, factual news article (200-400 words).
Include a headline and article body.
Cite sources appropriately.
If historical context is provided, mention it to add depth (e.g., "This follows...").
"""
        
        try:
            article_text = await self.chat_service.generate(
                system="You are a reporter writing a news article.",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
            )
            
            await self.log_event(
                task.story_id,
                "draft.completed",
                {
                    "word_count": len(article_text.split()),
                    "provider": self.chat_service.provider,
                },
            )
            
            return {
                "article": article_text,
                "headline": detection_data.get("title"),
                "word_count": len(article_text.split()),
            }
            
        except Exception as e:
            logger.error("Draft generation failed", error=str(e))
            raise

    async def revise(self, task: Task) -> dict[str, Any]:
        """Revise an article based on editor feedback."""
        draft = task.input.get("draft", {})
        feedback = task.input.get("feedback", "")
        original_article = draft.get("article", "")
        headline = draft.get("headline", "")
        
        logger.info(
            "Revising article",
            story_id=str(task.story_id),
            headline=headline,
        )
        
        prompt = f"""Original Article:
{original_article}

Editor's Feedback:
{feedback}

Rewrite the article to address the feedback.
Keep the same general structure unless requested otherwise.
"""
        
        try:
            revised_text = await self.chat_service.generate(
                system="You are a reporter modifying an article based on feedback.",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
            )
            
            await self.log_event(
                task.story_id,
                "revision.completed",
                {
                    "word_count": len(revised_text.split()),
                    "provider": self.chat_service.provider,
                },
            )
            
            return {
                "article": revised_text,
                "headline": headline,
                "word_count": len(revised_text.split()),
                "is_revision": True
            }
            
        except Exception as e:
            logger.error("Revision failed", error=str(e))
            raise
