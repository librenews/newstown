"""Publishing system for News Town - Phase 3."""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from uuid import UUID
from db.articles import Article
from db.publications import Publication

__all__ = ["Publisher", "PublishResult"]


class PublishResult:
    """Result of a publish operation."""
    
    def __init__(
        self,
        success: bool,
        publication_id: Optional[UUID] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.success = success
        self.publication_id = publication_id
        self.error = error
        self.metadata = metadata or {}


class Publisher(ABC):
    """Base class for all publishers (RSS, email, social, etc)."""
    
    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Channel identifier (e.g., 'rss', 'email', 'twitter')."""
        pass
    
    @abstractmethod
    async def publish(self, article: Article) -> PublishResult:
        """
        Publish an article to this channel.
        
        Args:
            article: The article to publish
            
        Returns:
            PublishResult with success status and metadata
        """
        pass
    
    @abstractmethod
    async def retract(self, publication: Publication) -> bool:
        """
        Retract a previously published article.
        
        Args:
            publication: The publication to retract
            
        Returns:
            True if successfully retracted
        """
        pass
    
    async def validate_article(self, article: Article) -> bool:
        """
        Validate that an article can be published to this channel.
        
        Override in subclasses for channel-specific validation.
        """
        # Basic validation
        if not article.headline:
            return False
        if not article.body:
            return False
        return True
