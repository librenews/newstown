"""Human oversight database operations."""
import json
from typing import Optional, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel
from db.connection import db
from config.logging import get_logger

logger = get_logger(__name__)


class HumanPrompt(BaseModel):
    """Human prompt/question for agents."""
    id: int
    story_id: UUID
    prompt_text: str
    context: dict[str, Any] = {}
    created_by: Optional[str] = None
    created_at: datetime
    status: str = "pending"
    response: Optional[dict[str, Any]] = None


class StorySource(BaseModel):
    """Human-provided source."""
    id: int
    story_id: UUID
    source_type: str  # 'url', 'document', 'text'
    source_url: Optional[str] = None
    source_content: Optional[str] = None
    source_metadata: dict[str, Any] = {}
    added_by: Optional[str] = None
    added_at: datetime
    processed: bool = False


class HumanPromptStore:
    """Manage human prompts/questions."""
    
    async def create_prompt(
        self,
        story_id: UUID,
        prompt_text: str,
        created_by: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> int:
        """Create a new human prompt for a story."""
        prompt_id = await db.fetchval(
            """
            INSERT INTO human_prompts (story_id, prompt_text, context, created_by)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            story_id,
            prompt_text,
            json.dumps(context or {}),
            created_by,
        )
        
        logger.info(
            "Human prompt created",
            prompt_id=prompt_id,
            story_id=str(story_id),
            created_by=created_by,
        )
        
        return prompt_id
    
    async def get_pending_prompts(
        self,
        story_id: Optional[UUID] = None,
    ) -> list[HumanPrompt]:
        """Get pending prompts, optionally filtered by story."""
        if story_id:
            query = """
                SELECT * FROM human_prompts
                WHERE story_id = $1 AND status = 'pending'
                ORDER BY created_at ASC
            """
            rows = await db.fetch(query, story_id)
        else:
            query = """
                SELECT * FROM human_prompts
                WHERE status = 'pending'
                ORDER BY created_at ASC
            """
            rows = await db.fetch(query)
        
        prompts = []
        for row in rows:
            row_dict = dict(row)
            if isinstance(row_dict['context'], str):
                row_dict['context'] = json.loads(row_dict['context'])
            if row_dict['response'] and isinstance(row_dict['response'], str):
                row_dict['response'] = json.loads(row_dict['response'])
            prompts.append(HumanPrompt(**row_dict))
        
        return prompts
    
    async def mark_answered(
        self,
        prompt_id: int,
        response: dict[str, Any],
    ) -> None:
        """Mark a prompt as answered with the response."""
        await db.execute(
            """
            UPDATE human_prompts
            SET status = 'answered',
                response = $2::JSONB
            WHERE id = $1
            """,
            prompt_id,
            json.dumps(response),
        )
        
        logger.info("Prompt answered", prompt_id=prompt_id)
    
    async def mark_processing(self, prompt_id: int) -> None:
        """Mark a prompt as being processed."""
        await db.execute(
            "UPDATE human_prompts SET status = 'processing' WHERE id = $1",
            prompt_id,
        )
    
    async def get_prompt_history(self, story_id: UUID) -> list[HumanPrompt]:
        """Get all prompts for a story."""
        rows = await db.fetch(
            """
            SELECT * FROM human_prompts
            WHERE story_id = $1
            ORDER BY created_at DESC
            """,
            story_id,
        )
        
        prompts = []
        for row in rows:
            row_dict = dict(row)
            if isinstance(row_dict['context'], str):
                row_dict['context'] = json.loads(row_dict['context'])
            if row_dict['response'] and isinstance(row_dict['response'], str):
                row_dict['response'] = json.loads(row_dict['response'])
            prompts.append(HumanPrompt(**row_dict))
        
        return prompts


class SourceStore:
    """Manage human-provided sources."""
    
    async def add_url_source(
        self,
        story_id: UUID,
        url: str,
        added_by: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> int:
        """Add a URL source to a story."""
        source_id = await db.fetchval(
            """
            INSERT INTO story_sources (story_id, source_type, source_url, source_metadata, added_by)
            VALUES ($1, 'url', $2, $3, $4)
            RETURNING id
            """,
            story_id,
            url,
            json.dumps(metadata or {}),
            added_by,
        )
        
        logger.info(
            "URL source added",
            source_id=source_id,
            story_id=str(story_id),
            url=url,
        )
        
        return source_id
    
    async def add_text_source(
        self,
        story_id: UUID,
        content: str,
        added_by: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> int:
        """Add a pasted text source to a story."""
        source_id = await db.fetchval(
            """
            INSERT INTO story_sources (story_id, source_type, source_content, source_metadata, added_by)
            VALUES ($1, 'text', $2, $3, $4)
            RETURNING id
            """,
            story_id,
            content,
            json.dumps(metadata or {}),
            added_by,
        )
        
        logger.info("Text source added", source_id=source_id, story_id=str(story_id))
        
        return source_id
    
    async def add_document_source(
        self,
        story_id: UUID,
        content: str,
        filename: str,
        added_by: Optional[str] = None,
    ) -> int:
        """Add a document source to a story."""
        metadata = {"filename": filename}
        
        source_id = await db.fetchval(
            """
            INSERT INTO story_sources (story_id, source_type, source_content, source_metadata, added_by)
            VALUES ($1, 'document', $2, $3, $4)
            RETURNING id
            """,
            story_id,
            content,
            json.dumps(metadata),
            added_by,
        )
        
        logger.info(
            "Document source added",
            source_id=source_id,
            story_id=str(story_id),
            filename=filename,
        )
        
        return source_id
    
    async def get_story_sources(
        self,
        story_id: UUID,
        processed_only: bool = False,
    ) -> list[StorySource]:
        """Get all sources for a story."""
        if processed_only:
            query = """
                SELECT * FROM story_sources
                WHERE story_id = $1 AND processed = true
                ORDER BY added_at DESC
            """
        else:
            query = """
                SELECT * FROM story_sources
                WHERE story_id = $1
                ORDER BY added_at DESC
            """
        
        rows = await db.fetch(query, story_id)
        
        sources = []
        for row in rows:
            row_dict = dict(row)
            if isinstance(row_dict['source_metadata'], str):
                row_dict['source_metadata'] = json.loads(row_dict['source_metadata'])
            sources.append(StorySource(**row_dict))
        
        return sources
    
    async def mark_processed(self, source_id: int) -> None:
        """Mark a source as processed."""
        await db.execute(
            "UPDATE story_sources SET processed = true WHERE id = $1",
            source_id,
        )
        
        logger.info("Source marked as processed", source_id=source_id)


# Global instances
human_prompt_store = HumanPromptStore()
source_store = SourceStore()
