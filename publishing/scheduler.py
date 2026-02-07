"""Publishing scheduler - background task for scheduled publications."""
import asyncio
from datetime import datetime
from typing import Optional
from uuid import UUID
from db.articles import article_store
from db.publications import schedule_store
from publishing.rss import rss_publisher
from publishing.email import email_publisher
from config.logging import get_logger

logger = get_logger(__name__)


class PublishingScheduler:
    """Background scheduler for publishing articles at scheduled times."""
    
    def __init__(self, poll_interval: int = 60):
        """
        Initialize scheduler.
        
        Args:
            poll_interval: How often to check for pending publications (seconds)
        """
        self.poll_interval = poll_interval
        self.running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the scheduler background task."""
        if self.running:
            logger.warning("Scheduler already running")
            return
        
        self.running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Publishing scheduler started", poll_interval=self.poll_interval)
    
    async def stop(self):
        """Stop the scheduler."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Publishing scheduler stopped")
    
    async def _run(self):
        """Main scheduler loop."""
        while self.running:
            try:
                await self._process_pending()
            except Exception as e:
                logger.error("Scheduler error", error=str(e), exc_info=True)
            
            # Wait before next check
            await asyncio.sleep(self.poll_interval)
    
    async def _process_pending(self):
        """Process all pending scheduled publications."""
        # Get pending publications that are due
        pending = await schedule_store.get_pending()
        
        if not pending:
            return
        
        logger.info(f"Processing {len(pending)} scheduled publications")
        
        for schedule in pending:
            try:
                await self._publish_scheduled(schedule)
            except Exception as e:
                logger.error(
                    "Failed to publish scheduled article",
                    schedule_id=str(schedule.id),
                    error=str(e),
                    exc_info=True,
                )
                
                # Mark as failed
                await schedule_store.mark_failed(
                    schedule.id,
                    error_message=str(e),
                )
    
    async def _publish_scheduled(self, schedule):
        """Publish a single scheduled article."""
        # Get article
        article = await article_store.get(schedule.article_id)
        if not article:
            await schedule_store.mark_failed(
                schedule.id,
                error_message=f"Article {schedule.article_id} not found",
            )
            return
        
        logger.info(
            "Publishing scheduled article",
            article_id=str(article.id),
            channels=schedule.channels,
            scheduled_for=schedule.scheduled_for,
        )
        
        # Publish to each channel
        results = {}
        for channel in schedule.channels:
            try:
                if channel == "rss":
                    result = await rss_publisher.publish(article)
                    results[channel] = result.success
                
                elif channel == "email":
                    # Email needs recipients - skip for scheduled
                    logger.warning("Email channel requires recipients, skipping")
                    results[channel] = False
                
                else:
                    logger.warning(f"Unknown channel: {channel}")
                    results[channel] = False
                    
            except Exception as e:
                logger.error(f"Channel {channel} failed", error=str(e))
                results[channel] = False
        
        # Mark as published if at least one channel succeeded
        if any(results.values()):
            await schedule_store.mark_published(schedule.id)
            logger.info(
                "Scheduled publication complete",
                article_id=str(article.id),
                results=results,
            )
        else:
            await schedule_store.mark_failed(
                schedule.id,
                error_message="All channels failed",
            )


# Global scheduler instance
scheduler = PublishingScheduler()
