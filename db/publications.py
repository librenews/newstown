"""Publishing data models and stores for Phase 3."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field
from db.connection import db


class Publication(BaseModel):
    """Published article instance."""
    id: UUID
    article_id: UUID
    channel: str  # 'rss', 'email', 'twitter', 'bluesky', 'web'
    published_at: datetime
    status: str = "published"  # 'published', 'retracted', 'failed'
    metadata: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None
    retracted_at: Optional[datetime] = None
    retraction_reason: Optional[str] = None
    created_at: datetime


class PublishingSchedule(BaseModel):
    """Scheduled publication."""
    id: UUID
    article_id: UUID
    channels: List[str]
    scheduled_for: datetime
    status: str = "pending"  # 'pending', 'published', 'cancelled', 'failed'
    published_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: datetime
    updated_at: datetime


class PublicationStore:
    """Manage published articles."""
    
    async def create(
        self,
        article_id: UUID,
        channel: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UUID:
        """Record a new publication."""
        import json
        
        query = """
            INSERT INTO publications (article_id, channel, metadata)
            VALUES ($1, $2, $3)
            RETURNING id
        """
        result = await db.fetchrow(
            query,
            article_id,
            channel,
            json.dumps(metadata or {}),  # Convert dict to JSON string
        )
        return result["id"]
    
    async def get(self, publication_id: UUID) -> Optional[Publication]:
        """Get a publication by ID."""
        import json
        
        query = "SELECT * FROM publications WHERE id = $1"
        row = await db.fetchrow(query, publication_id)
        if not row:
            return None
        
        row_dict = dict(row)
        # Deserialize JSON fields
        if isinstance(row_dict.get('metadata'), str):
            row_dict['metadata'] = json.loads(row_dict['metadata'])
        if isinstance(row_dict.get('metrics'), str):
            row_dict['metrics'] = json.loads(row_dict['metrics'])
        
        return Publication(**row_dict)
    
    async def list_by_article(self, article_id: UUID) -> List[Publication]:
        """Get all publications for an article."""
        import json
        
        query = """
            SELECT * FROM publications
            WHERE article_id = $1
            ORDER BY published_at DESC
        """
        rows = await db.fetch(query, article_id)
        
        publications = []
        for row in rows:
            row_dict = dict(row)
            if isinstance(row_dict.get('metadata'), str):
                row_dict['metadata'] = json.loads(row_dict['metadata'])
            if isinstance(row_dict.get('metrics'), str):
                row_dict['metrics'] = json.loads(row_dict['metrics'])
            publications.append(Publication(**row_dict))
        
        return publications
    
    async def list_by_channel(
        self,
        channel: str,
        limit: int = 50,
    ) -> List[Publication]:
        """Get recent publications for a channel."""
        import json
        
        query = """
            SELECT * FROM publications
            WHERE channel = $1 AND status = 'published'
            ORDER BY published_at DESC
            LIMIT $2
        """
        rows = await db.fetch(query, channel, limit)
        
        publications = []
        for row in rows:
            row_dict = dict(row)
            if isinstance(row_dict.get('metadata'), str):
                row_dict['metadata'] = json.loads(row_dict['metadata'])
            if isinstance(row_dict.get('metrics'), str):
                row_dict['metrics'] = json.loads(row_dict['metrics'])
            publications.append(Publication(**row_dict))
        
        return publications
    
    async def retract(
        self,
        publication_id: UUID,
        reason: str,
    ) -> bool:
        """Retract a publication."""
        query = """
            UPDATE publications
            SET status = 'retracted',
                retracted_at = NOW(),
                retraction_reason = $2
            WHERE id = $1
            RETURNING id
        """
        result = await db.fetchrow(query, publication_id, reason)
        return result is not None
    
    async def update_metrics(
        self,
        publication_id: UUID,
        metrics: Dict[str, Any],
    ) -> bool:
        """Update publication metrics (views, clicks, etc)."""
        query = """
            UPDATE publications
            SET metrics = $2
            WHERE id = $1
            RETURNING id
        """
        result = await db.fetchrow(query, publication_id, metrics)
        return result is not None


class ScheduleStore:
    """Manage publishing schedule."""
    
    async def create(
        self,
        article_id: UUID,
        channels: List[str],
        scheduled_for: datetime,
    ) -> UUID:
        """Schedule an article for publication."""
        query = """
            INSERT INTO publishing_schedule (article_id, channels, scheduled_for)
            VALUES ($1, $2, $3)
            RETURNING id
        """
        result = await db.fetchrow(query, article_id, channels, scheduled_for)
        return result["id"]
    
    async def get_pending(self) -> List[PublishingSchedule]:
        """Get all pending scheduled publications that are due."""
        query = """
            SELECT * FROM publishing_schedule
            WHERE status = 'pending'
              AND scheduled_for <= NOW()
            ORDER BY scheduled_for ASC
        """
        rows = await db.fetch(query)
        return [PublishingSchedule(**dict(row)) for row in rows]
    
    async def mark_published(self, schedule_id: UUID) -> bool:
        """Mark a scheduled publication as published."""
        query = """
            UPDATE publishing_schedule
            SET status = 'published',
                published_at = NOW(),
                updated_at = NOW()
            WHERE id = $1
            RETURNING id
        """
        result = await db.fetchrow(query, schedule_id)
        return result is not None
    
    async def mark_failed(
        self,
        schedule_id: UUID,
        error_message: str,
    ) -> bool:
        """Mark a scheduled publication as failed."""
        query = """
            UPDATE publishing_schedule
            SET status = 'failed',
                error_message = $2,
                retry_count = retry_count + 1,
                updated_at = NOW()
            WHERE id = $1
            RETURNING id
        """
        result = await db.fetchrow(query, schedule_id, error_message)
        return result is not None
    
    async def cancel(self, schedule_id: UUID) -> bool:
        """Cancel a scheduled publication."""
        query = """
            UPDATE publishing_schedule
            SET status = 'cancelled',
                updated_at = NOW()
            WHERE id = $1 AND status = 'pending'
            RETURNING id
        """
        result = await db.fetchrow(query, schedule_id)
        return result is not None


# Global instances
publication_store = PublicationStore()
schedule_store = ScheduleStore()
