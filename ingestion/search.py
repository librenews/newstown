"""Search abstraction layer - supports multiple search providers."""
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass
import aiohttp
from config.settings import settings
from config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SearchResult:
    """A single search result."""
    title: str
    url: str
    snippet: str
    source: str  # domain name


class SearchProvider(ABC):
    """Base class for search providers."""

    @abstractmethod
    async def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        """Search for a query and return results."""
        pass


class BraveSearchProvider(SearchProvider):
    """Brave Search API provider."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.search.brave.com/res/v1/web/search"

    async def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        """Search using Brave Search API."""
        if not self.api_key:
            logger.warning("Brave API key not configured, skipping search")
            return []

        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }

        params = {
            "q": query,
            "count": min(num_results, 20),  # Brave max is 20
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.base_url,
                    headers=headers,
                    params=params,
                ) as response:
                    if response.status != 200:
                        logger.error(
                            "Brave search failed",
                            status=response.status,
                            error=await response.text(),
                        )
                        return []

                    data = await response.json()

                    results = []
                    for item in data.get("web", {}).get("results", []):
                        results.append(
                            SearchResult(
                                title=item.get("title", ""),
                                url=item.get("url", ""),
                                snippet=item.get("description", ""),
                                source=item.get("url", "").split("/")[2]
                                if "/" in item.get("url", "")
                                else "",
                            )
                        )

                    logger.info(
                        "Search completed",
                        query=query,
                        result_count=len(results),
                    )

                    return results

        except Exception as e:
            logger.error("Search request failed", query=query, error=str(e))
            return []


class SearchService:
    """
    Search service that can use multiple providers.
    
    Makes it easy to add additional search engines later.
    """

    def __init__(self):
        self.providers: dict[str, SearchProvider] = {}

        # Register Brave Search if API key is available
        if settings.brave_api_key:
            self.providers["brave"] = BraveSearchProvider(settings.brave_api_key)
            logger.info("Brave Search provider registered")

        # Future: Add other providers here
        # if settings.serp_api_key:
        #     self.providers["serp"] = SerpApiProvider(settings.serp_api_key)

    async def search(
        self,
        query: str,
        num_results: int = 5,
        provider: Optional[str] = None,
    ) -> list[SearchResult]:
        """
        Search using specified provider or first available.
        
        Args:
            query: Search query
            num_results: Number of results to return
            provider: Specific provider name, or None for first available
        """
        if not self.providers:
            logger.warning("No search providers configured")
            return []

        # Use specific provider or first available
        if provider and provider in self.providers:
            search_provider = self.providers[provider]
        else:
            search_provider = next(iter(self.providers.values()))

        return await search_provider.search(query, num_results)


# Global search service instance
search_service = SearchService()
