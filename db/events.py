"""Event sourcing system - core of News Town."""
import json
from typing import Any, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field
from db.connection import db
from config.logging import get_logger

logger = get_logger(__name__)


class Event(BaseModel):
    """Event model."""
    id: Optional[int] = None
    story_id: UUID
    agent_id: Optional[UUID] = None
    event_type: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class EventStore:
    """Event store for append-only event log."""

    async def append(
        self,
        story_id: UUID,
        event_type: str,
        data: dict[str, Any],
        agent_id: Optional[UUID] = None,
    ) -> int:
        """Append an event to the log."""
        event_id = await db.fetchval(
            """
            INSERT INTO story_events (story_id, agent_id, event_type, data)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            story_id,
            agent_id,
            event_type,
            json.dumps(data),  # Serialize dict to JSON string
        )
        
        logger.info(
            "Event appended",
            event_id=event_id,
            story_id=str(story_id),
            type=event_type,
            agent_id=str(agent_id) if agent_id else None,
        )
        
        return event_id

    async def get_story_events(self, story_id: UUID) -> list[Event]:
        """Get all events for a story."""
        rows = await db.fetch(
            """
            SELECT id, story_id, agent_id, event_type, data, created_at
            FROM story_events
            WHERE story_id = $1
            ORDER BY created_at ASC
            """,
            story_id,
        )
        
        # Deserialize JSON data back to dict
        events = []
        for row in rows:
            row_dict = dict(row)
            if isinstance(row_dict['data'], str):
                row_dict['data'] = json.loads(row_dict['data'])
            events.append(Event(**row_dict))
        
        return events

    async def get_recent_events(self, limit: int = 100) -> list[Event]:
        """Get recent events across all stories."""
        rows = await db.fetch(
            """
            SELECT id, story_id, agent_id, event_type, data, created_at
            FROM story_events
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
        
        # Deserialize JSON data back to dict
        events = []
        for row in rows:
            row_dict = dict(row)
            if isinstance(row_dict['data'], str):
                row_dict['data'] = json.loads(row_dict['data'])
            events.append(Event(**row_dict))
        
        return events

    async def count_events_by_type(self, story_id: UUID) -> dict[str, int]:
        """Count events by type for a story."""
        rows = await db.fetch(
            """
            SELECT event_type, COUNT(*) as count
            FROM story_events
            WHERE story_id = $1
            GROUP BY event_type
            """,
            story_id,
        )
        
        return {row["event_type"]: row["count"] for row in rows}


# Global event store instance
event_store = EventStore()
