"""Ingestion services."""
from ingestion.search import search_service, SearchService, SearchResult

# Try to import entity extractor - may fail on Python 3.12 due to spaCy/Pydantic incompatibility
try:
    from ingestion.entities import entity_extractor, EntityExtractor, Entity
except (ImportError, TypeError) as e:
    # Create dummy placeholders for when spaCy is unavailable
    print(f"Warning: Entity extraction unavailable due to: {e}")
    entity_extractor = None
    EntityExtractor = None
    Entity = None

__all__ = [
    "search_service",
    "SearchService",
    "SearchResult",
    "entity_extractor",
    "EntityExtractor",
    "Entity",
]
