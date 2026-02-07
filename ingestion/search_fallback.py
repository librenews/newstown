"""Multi-provider search with automatic fallback."""
import asyncio
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import httpx
from config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SearchResult:
    """Unified search result across providers."""
    title: str
    url: str
    snippet: str
    provider: str  # Which provider returned this result


class SearchProvider(ABC):
    """Base class for search providers."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        pass
    
    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """Execute search and return results."""
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """Check if provider is currently available."""
        pass


class BraveSearchProvider(SearchProvider):
    """Brave Search API provider."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.search.brave.com/res/v1/web/search"
        self._rate_limited_until: Optional[float] = None
    
    @property
    def name(self) -> str:
        return "Brave"
    
    async def is_available(self) -> bool:
        """Check if not rate limited."""
        if self._rate_limited_until:
            import time
            if time.time() < self._rate_limited_until:
                return False
            self._rate_limited_until = None
        return bool(self.api_key)
    
    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """Search using Brave API."""
        if not await self.is_available():
            raise RuntimeError("Brave API not available (rate limited)")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    self.base_url,
                    params={"q": query, "count": max_results},
                    headers={"X-Subscription-Token": self.api_key},
                )
                
                if response.status_code == 429:
                    # Rate limited - mark as unavailable for 60 seconds
                    import time
                    self._rate_limited_until = time.time() + 60
                    logger.warning("Brave API rate limited", retry_after=60)
                    raise RuntimeError("Rate limited")
                
                response.raise_for_status()
                data = response.json()
                
                results = []
                for item in data.get("web", {}).get("results", [])[:max_results]:
                    results.append(SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("description", ""),
                        provider=self.name
                    ))
                
                logger.info("Brave search completed", query=query, results=len(results))
                return results
                
            except httpx.HTTPError as e:
                logger.error("Brave search failed", error=str(e), query=query)
                raise


class DuckDuckGoSearchProvider(SearchProvider):
    """DuckDuckGo HTML scraping provider (no API key needed)."""
    
    @property
    def name(self) -> str:
        return "DuckDuckGo"
    
    async def is_available(self) -> bool:
        """DuckDuckGo is always available (no rate limits on basic usage)."""
        return True
    
    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """Search using DuckDuckGo HTML."""
        try:
            from duckduckgo_search import DDGS
            
            results = []
            with DDGS() as ddgs:
                search_results = list(ddgs.text(query, max_results=max_results))
                
                for item in search_results:
                    results.append(SearchResult(
                        title=item.get("title", ""),
                        url=item.get("href", ""),
                        snippet=item.get("body", ""),
                        provider=self.name
                    ))
            
            logger.info("DuckDuckGo search completed", query=query, results=len(results))
            return results
            
        except Exception as e:
            logger.error("DuckDuckGo search failed", error=str(e), query=query)
            raise


class FallbackSearch:
    """Search with automatic fallback across multiple providers."""
    
    def __init__(self, providers: List[SearchProvider]):
        self.providers = providers
    
    async def search(
        self, 
        query: str, 
        max_results: int = 5,
        max_retries: int = 2
    ) -> List[SearchResult]:
        """
        Search with automatic fallback.
        
        Tries each provider in order until one succeeds.
        Implements retry logic with exponential backoff.
        """
        last_error = None
        
        for provider in self.providers:
            # Check if provider is available
            if not await provider.is_available():
                logger.debug(
                    "Skipping unavailable provider",
                    provider=provider.name
                )
                continue
            
            # Try this provider with retries
            for attempt in range(max_retries):
                try:
                    logger.info(
                        "Attempting search",
                        provider=provider.name,
                        attempt=attempt + 1,
                        query=query
                    )
                    
                    results = await provider.search(query, max_results)
                    
                    if results:
                        logger.info(
                            "Search successful",
                            provider=provider.name,
                            result_count=len(results)
                        )
                        return results
                    
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "Search attempt failed",
                        provider=provider.name,
                        attempt=attempt + 1,
                        error=str(e)
                    )
                    
                    # Exponential backoff before retry
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        logger.debug("Retrying after backoff", wait_seconds=wait_time)
                        await asyncio.sleep(wait_time)
        
        # All providers failed
        error_msg = f"All search providers failed. Last error: {last_error}"
        logger.error(error_msg, query=query)
        raise RuntimeError(error_msg)


# Global instance - will be initialized with config
_fallback_search: Optional[FallbackSearch] = None


def get_search() -> FallbackSearch:
    """Get or create the global fallback search instance."""
    global _fallback_search
    
    if _fallback_search is None:
        from config.settings import settings
        
        providers = []
        
        # Add Brave if API key available
        if settings.brave_api_key:
            providers.append(BraveSearchProvider(settings.brave_api_key))
        
        # Always add DuckDuckGo as fallback
        providers.append(DuckDuckGoSearchProvider())
        
        if not providers:
            raise RuntimeError("No search providers configured")
        
        _fallback_search = FallbackSearch(providers)
        logger.info(
            "Search providers initialized",
            providers=[p.name for p in providers]
        )
    
    return _fallback_search
