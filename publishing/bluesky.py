"""Bluesky/AT Protocol publisher."""
from typing import Dict, Any, Optional
from atproto import Client, client_utils
from db.articles import Article
from db.publications import publication_store, Publication
from publishing import Publisher, PublishResult
from config.settings import settings
from config.logging import get_logger

logger = get_logger(__name__)


class BlueskyPublisher(Publisher):
    """Publish articles to Bluesky using the AT Protocol."""

    def __init__(self, handle: Optional[str] = None, app_password: Optional[str] = None):
        self.handle = handle or settings.bluesky_handle
        self.app_password = app_password or settings.bluesky_app_password
        self.client = None

    @property
    def channel_name(self) -> str:
        return "bluesky"

    async def _ensure_client(self) -> Client:
        """Lazily initialize and authenticate the Bluesky client."""
        if not self.client:
            if not self.handle or not self.app_password:
                raise ValueError("Bluesky handle and app password are required")
            
            self.client = Client()
            # Login is synchronous in atproto 0.0.52
            self.client.login(self.handle, self.app_password)
            logger.info("Authenticated with Bluesky", handle=self.handle)
        
        return self.client

    async def publish(self, article: Article) -> PublishResult:
        """Publish article to Bluesky."""
        try:
            client = await self._ensure_client()
            
            # Create a rich text post with the headline and link
            # Bluesky has a 300 character limit for posts.
            # We'll post the headline and a link to the article if available.
            
            headline = article.headline
            if len(headline) > 250:
                headline = headline[:247] + "..."
            
            # Format post
            text = f"{headline}\n\n"
            
            # Build the post with facets (links)
            builder = client_utils.TextBuilder()
            builder.text(headline + "\n\n")
            
            # Add link if we have one in metadata or otherwise
            # For now, let's assume we might have a canonical URL in metadata
            article_url = article.metadata.get("canonical_url") or article.metadata.get("url")
            
            if article_url:
                builder.link("Read more on News Town", article_url)
            else:
                builder.text("#NewsTown #AgenticNews")

            # Post to Bluesky
            # Note: client.send_post is synchronous in some versions, but we'll try to use it
            response = client.send_post(builder)
            
            post_uri = response.uri
            post_cid = response.cid
            
            logger.info(
                "Article published to Bluesky",
                article_id=str(article.id),
                uri=post_uri,
            )
            
            # Record publication
            pub_id = await publication_store.create(
                article_id=article.id,
                channel=self.channel_name,
                metadata={
                    "uri": post_uri,
                    "cid": post_cid,
                    "handle": self.handle
                }
            )
            
            return PublishResult(
                success=True,
                publication_id=pub_id,
                metadata={"uri": post_uri, "cid": post_cid}
            )

        except Exception as e:
            logger.error("Bluesky publish failed", error=str(e), article_id=str(article.id))
            return PublishResult(success=False, error=str(e))

    async def retract(self, publication: Publication) -> bool:
        """Delete a post from Bluesky."""
        try:
            client = await self._ensure_client()
            
            uri = publication.metadata.get("uri")
            if not uri:
                logger.warning("No URI found for publication, cannot retract", publication_id=str(publication.id))
                return False
            
            # Delete post
            client.delete_post(uri)
            
            logger.info("Bluesky post deleted", uri=uri)
            
            # Mark as retracted in database
            return await publication_store.retract(
                publication.id,
                f"Deleted from Bluesky: {uri}"
            )
            
        except Exception as e:
            logger.error("Bluesky retraction failed", error=str(e), publication_id=str(publication.id))
            return False


# Global instance
bluesky_publisher = None
if settings.bluesky_handle and settings.bluesky_app_password:
    bluesky_publisher = BlueskyPublisher()
