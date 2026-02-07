"""RSS feed generator for News Town."""
from typing import List, Optional
from datetime import datetime
from feedgen.feed import FeedGenerator
from db.articles import Article, article_store
from db.publications import publication_store, Publication
from publishing import Publisher, PublishResult
from config.logging import get_logger
from uuid import UUID

logger = get_logger(__name__)


class RSSPublisher(Publisher):
    """Publish articles as RSS 2.0 feed."""
    
    def __init__(
        self,
        feed_title: str = "News Town",
        feed_link: str = "https://newstown.example.com",
        feed_description: str = "Multi-agent news reporting system",
        max_items: int = 50,
    ):
        self.feed_title = feed_title
        self.feed_link = feed_link
        self.feed_description = feed_description
        self.max_items = max_items
    
    @property
    def channel_name(self) -> str:
        return "rss"
    
    async def publish(self, article: Article) -> PublishResult:
        """
        Publish article by adding to RSS feed.
        
        Note: RSS is regenerated on-demand, so this just records
        the publication. Call generate_feed() to create XML.
        """
        try:
            # Validate article
            if not await self.validate_article(article):
                return PublishResult(
                    success=False,
                    error="Article validation failed"
                )
            
            # Create publication record
            pub_id = await publication_store.create(
                article_id=article.id,
                channel=self.channel_name,
                metadata={
                    "feed_title": self.feed_title,
                    "published_to_feed": True,
                }
            )
            
            logger.info(
                "Article added to RSS feed",
                article_id=str(article.id),
                headline=article.headline,
            )
            
            return PublishResult(
                success=True,
                publication_id=pub_id,
                metadata={"channel": self.channel_name}
            )
            
        except Exception as e:
            logger.error("RSS publication failed", error=str(e), exc_info=True)
            return PublishResult(
                success=False,
                error=str(e)
            )
    
    async def retract(self, publication: Publication) -> bool:
        """Retract from RSS feed (mark as retracted)."""
        try:
            success = await publication_store.retract(
                publication.id,
                "Article retracted by publisher"
            )
            
            if success:
                logger.info(
                    "Article retracted from RSS feed",
                    publication_id=str(publication.id),
                )
            
            return success
            
        except Exception as e:
            logger.error("RSS retraction failed", error=str(e))
            return False
    
    async def generate_feed(self) -> str:
        """
        Generate RSS 2.0 XML feed from recent publications.
        
        Returns:
            RSS feed as XML string
        """
        # Get recent published articles
        publications = await publication_store.list_by_channel(
            self.channel_name,
            limit=self.max_items,
        )
        
        # Filter out retracted
        publications = [p for p in publications if p.status == "published"]
        
        # Create feed
        fg = FeedGenerator()
        fg.title(self.feed_title)
        fg.link(href=self.feed_link, rel="alternate")
        fg.description(self.feed_description)
        fg.language("en")
        
        # Add items
        for pub in publications:
            # Get article
            article = await article_store.get_article(pub.article_id)
            if not article:
                continue
            
            # Create feed entry
            fe = fg.add_entry()
            fe.title(article.headline)
            fe.link(href=f"{self.feed_link}/articles/{article.id}")
            fe.description(article.summary or article.body[:200] + "...")
            fe.published(pub.published_at)
            fe.updated(article.updated_at or article.created_at)
            
            # Add author if available
            if article.byline:
                fe.author({"name": article.byline})
            
            # Add content (full article body)
            if article.body:
                fe.content(article.body, type="text")
            
            # Add sources as links
            if article.sources:
                for source in article.sources[:5]:  # Limit to 5 sources
                    if isinstance(source, dict) and source.get('url'):
                        fe.link(
                            href=source['url'],
                            rel="related",
                            title=source.get('title', 'Source')
                        )
            
            # Add categories/tags
            if article.tags:
                for tag in article.tags:
                    fe.category(term=tag)
        
        # Generate RSS 2.0 XML
        rss_str = fg.rss_str(pretty=True)
        
        logger.info(
            "RSS feed generated",
            item_count=len(publications),
            feed_title=self.feed_title,
        )
        
        return rss_str.decode('utf-8')
    
    async def save_feed(self, filepath: str) -> bool:
        """Generate and save RSS feed to file."""
        try:
            rss_xml = await self.generate_feed()
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(rss_xml)
            
            logger.info("RSS feed saved", filepath=filepath)
            return True
            
        except Exception as e:
            logger.error("Failed to save RSS feed", error=str(e))
            return False


# Global instance
rss_publisher = RSSPublisher()
