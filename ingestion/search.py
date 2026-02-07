"""Search abstraction layer - supports multiple search providers with fallback."""
from typing import List
from dataclasses import dataclass
from config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SearchResult:
    """A single search result."""
    title: str
    url: str
    snippet: str
    source: str  # domain name


# Import the fallback search system
from ingestion.search_fallback import get_search as get_fallback_search, SearchResult as FallbackSearchResult


async def search(query: str, num_results: int = 5) -> List[SearchResult]:
    """
    Search using multi-provider fallback system.
    
    Automatically tries Brave, then DuckDuckGo if rate limited.
    """
    try:
        fallback_search = get_fallback_search()
        results = await fallback_search.search(query, max_results=num_results)
        
        # Convert to our SearchResult format
        converted = []
        for r in results:
            source_domain = r.url.split("/")[2] if "/" in r.url else ""
            converted.append(SearchResult(
                title=r.title,
                url=r.url,
                snippet=r.snippet,
                source=source_domain
            ))
        
        return converted
        
    except Exception as e:
        logger.error("Search failed after all fallbacks", query=query, error=str(e))
        return []


# For backwards compatibility
class SearchService:
    """Legacy search service - now uses fallback system."""
    
    async def search(self, query: str, num_results: int = 5, provider=None) -> List[SearchResult]:
        """Search using fallback system."""
        return await search(query, num_results)


# Global instance for backwards compatibility
search_service = SearchService()
