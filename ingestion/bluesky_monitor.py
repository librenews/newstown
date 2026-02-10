"""Bluesky monitor for detecting newsworthy content."""
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from atproto import Client
from config.settings import settings
from config.logging import get_logger

logger = get_logger(__name__)


class BlueskyMonitor:
    """Monitor Bluesky for newsworthy signals."""

    def __init__(self, handle: Optional[str] = None, app_password: Optional[str] = None):
        self.handle = handle or settings.bluesky_handle
        self.app_password = app_password or settings.bluesky_app_password
        self.client = None

    async def _ensure_client(self) -> Client:
        """Lazily initialize and authenticate the Bluesky client."""
        if not self.client:
            if not self.handle or not self.app_password:
                # Monitoring can sometimes be done without auth for public data,
                # but search usually requires a session.
                raise ValueError("Bluesky credentials required for monitoring")
            
            self.client = Client()
            self.client.login(self.handle, self.app_password)
            logger.info("Monitor authenticated with Bluesky", handle=self.handle)
        
        return self.client

    async def search_signals(self, queries: List[str], limit: int = 10) -> List[Dict[str, Any]]:
        """Search Bluesky for posts matching queries."""
        try:
            client = await self._ensure_client()
            all_signals = []
            
            for query in queries:
                logger.debug("Searching Bluesky", query=query)
                # search_posts is synchronous in atproto 0.0.52
                response = client.app.bsky.feed.search_posts(params={'q': query, 'limit': limit})
                
                for post in response.posts:
                    signal = {
                        "id": post.uri,
                        "text": post.record.text,
                        "author": post.author.handle,
                        "created_at": post.record.created_at,
                        "uri": post.uri,
                        "cid": post.cid,
                        "type": "bluesky_post",
                        "query": query
                    }
                    all_signals.append(signal)
            
            # Deduplicate by URI
            unique_signals = {s["uri"]: s for s in all_signals}.values()
            return list(unique_signals)

        except Exception as e:
            logger.error("Bluesky search failed", error=str(e))
            return []

    async def get_trending_signals(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get trending signals from Bluesky.
        Note: True 'trending' is complex, but we can look at popular tags or a broad search.
        """
        # For now, let's search for broad news-related keywords
        news_keywords = ["breaking", "news", "urgent", "report", "exclusive"]
        return await self.search_signals(news_keywords, limit=limit)


# Global instance
bluesky_monitor = None
if settings.bluesky_handle and settings.bluesky_app_password:
    bluesky_monitor = BlueskyMonitor()
else:
    logger.warning("Bluesky monitor NOT initialized - missing credentials")
