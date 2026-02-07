"""Story memory and vector search."""
import json
from typing import List, Optional, Any, Dict
from uuid import UUID
from db.connection import db
from config.logging import get_logger

logger = get_logger(__name__)


class MemoryStore:
    """Store and retrieve story memories (vectors)."""

    async def add(
        self,
        story_id: UUID,
        content: str,
        embedding: List[float],
        memory_type: str = "summary",
        metadata: Dict[str, Any] = None,
    ) -> int:
        """
        Add a memory item with embedding.
        
        Args:
            story_id: Associated story ID
            content: Text content
            embedding: Vector embedding
            memory_type: Type of memory (summary, fact, etc)
            metadata: Additional metadata
            
        Returns:
            ID of the inserted row
        """
        query = """
        INSERT INTO story_memory (story_id, content, embedding, memory_type, metadata)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """
        
        # pgvector expects string representation for list insertion often, 
        # but asyncpg handles list[float] mapping to vector type automatically 
        # in newer versions. If not, we might need str(embedding).
        # Let's try direct list first.
        
        return await db.fetchval(
            query,
            story_id,
            content,
            str(embedding), # Explicit string conversion often safer for generic vector types
            memory_type,
            json.dumps(metadata) if metadata else "{}"
        )

    async def find_similar_stories(
        self,
        embedding: List[float],
        threshold: float = 0.85,
        limit: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Find stories with similar embeddings.
        
        Args:
            embedding: Query vector
            threshold: Similarity threshold (0-1, where 1 is identical)
            limit: Max results
            
        Returns:
            List of {story_id, similarity, content}
        """
        # Cosine distance <=> 0 means identical, 2 means opposite.
        # Similarity = 1 - distance.
        # We want similarity > threshold, so distance < (1 - threshold).
        
        distance_threshold = 1.0 - threshold
        
        query = """
        SELECT 
            story_id,
            content,
            1 - (embedding <=> $1) as similarity
        FROM story_memory
        WHERE (embedding <=> $1) < $2
            AND memory_type = 'summary' -- compare against story summaries
        ORDER BY embedding <=> $1 ASC
        LIMIT $3
        """
        
        rows = await db.fetch(query, str(embedding), distance_threshold, limit)
        
        return [
            {
                "story_id": row["story_id"],
                "similarity": row["similarity"],
                "content": row["content"],
            }
            for row in rows
        ]

# Global instance
memory_store = MemoryStore()
