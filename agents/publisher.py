"""Publisher agent - orchestrates multi-channel publishing."""
from typing import Any, List
from uuid import UUID
from agents.base import BaseAgent, AgentRole
from db import Task, TaskStage
from db.articles import article_store
from db.publications import publication_store
from publishing.rss import rss_publisher
from publishing.email import email_publisher
from config.logging import get_logger

logger = get_logger(__name__)


class PublisherAgent(BaseAgent):
    """Publisher agent that distributes articles to various channels."""

    def __init__(self):
        super().__init__(AgentRole.PUBLISHER)

    async def handle_task(self, task: Task) -> dict[str, Any]:
        """Handle publishing tasks."""
        
        if task.stage == TaskStage.PUBLISH:
            return await self.publish(task)
        else:
            raise ValueError(f"Publisher cannot handle stage: {task.stage}")

    async def publish(self, task: Task) -> dict[str, Any]:
        """Publish an article to specified channels."""
        article_id = task.input.get("article_id")
        channels = task.input.get("channels", ["rss"])  # Default to RSS
        
        if not article_id:
            raise ValueError("article_id required for publishing")
        
        logger.info(
            "Publishing article",
            article_id=str(article_id),
            channels=channels,
        )
        
        # Get article
        article = await article_store.get(UUID(article_id))
        if not article:
            raise ValueError(f"Article {article_id} not found")
        
        # Publish to each channel
        results = {}
        for channel in channels:
            try:
                if channel == "rss":
                    result = await rss_publisher.publish(article)
                    results[channel] = {
                        "success": result.success,
                        "publication_id": str(result.publication_id) if result.publication_id else None,
                        "error": result.error,
                    }
                    
                elif channel == "email":
                    # Email requires recipients
                    recipients = task.input.get("recipients", [])
                    if not recipients:
                        results[channel] = {
                            "success": False,
                            "error": "No recipients specified for email"
                        }
                        continue
                    
                    if email_publisher:
                        batch_results = await email_publisher.send_batch(article, recipients)
                        success_count = sum(1 for r in batch_results.values() if r.success)
                        results[channel] = {
                            "success": success_count > 0,
                            "sent": success_count,
                            "total": len(recipients),
                        }
                    else:
                        results[channel] = {
                            "success": False,
                            "error": "Email publisher not configured (missing SendGrid API key)"
                        }
                
                else:
                    results[channel] = {
                        "success": False,
                        "error": f"Unknown channel: {channel}"
                    }
                    
            except Exception as e:
                logger.error(
                    "Channel publishing failed",
                    channel=channel,
                    error=str(e),
                    exc_info=True,
                )
                results[channel] = {
                    "success": False,
                    "error": str(e),
                }
        
        # Log publication event
        await self.log_event(
            task.story_id,
            "article.published",
            {
                "article_id": str(article_id),
                "channels": channels,
                "results": results,
            },
        )
        
        # Count successes
        success_count = sum(1 for r in results.values() if r.get("success"))
        
        logger.info(
            "Publishing complete",
            article_id=str(article_id),
            success_count=success_count,
            total_channels=len(channels),
        )
        
        return {
            "article_id": str(article_id),
            "channels": channels,
            "results": results,
            "success_count": success_count,
        }
