"""Tests for research pipeline."""
import pytest
from ingestion.entities import Entity, EntityExtractor
from ingestion.search import SearchResult


def test_entity_model():
    """Test entity model creation."""
    entity = Entity(
        text="Apple Inc.",
        label_="ORG",
        start=0,
        end=10,
    )
    
    assert entity.text == "Apple Inc."
    assert entity.label_ == "ORG"
    assert entity.start == 0
    assert entity.end == 10


def test_search_result_model():
    """Test search result model."""
    result = SearchResult(
        title="Test Article",
        url="https://example.com/article",
        snippet="This is a test snippet",
        source="example.com",
    )
    
    assert result.title == "Test Article"
    assert result.url == "https://example.com/article"
    assert result.snippet == "This is a test snippet"
    assert result.source == "example.com"


def test_entity_extraction_with_text():
    """Test entity extraction with sample text."""
    extractor = EntityExtractor()
    
    # This test requires spaCy model to be installed
    if not extractor.nlp:
        pytest.skip("spaCy model not installed")
    
    text = "Apple Inc. announced layoffs in San Francisco. CEO Tim Cook commented."
    entities = extractor.extract(text)
    
    # Should find at least some entities
    assert len(entities) > 0
    
    # Check entity types
    labels = [e.label_ for e in entities]
    assert any(label in ["ORG", "PERSON", "GPE"] for label in labels)


def test_entity_extraction_empty_text():
    """Test entity extraction with empty text."""
    extractor = EntityExtractor()
    
    entities = extractor.extract("")
    assert entities == []
    
    entities = extractor.extract("   ")
    assert entities == []


def test_entity_extraction_by_type():
    """Test filtering entities by type."""
    extractor = EntityExtractor()
    
    if not extractor.nlp:
        pytest.skip("spaCy model not installed")
    
    text = "Microsoft was founded by Bill Gates in Seattle."
    
    people = extractor.get_people(text)
    orgs = extractor.get_organizations(text)
    locations = extractor.get_locations(text)
    
    # Should find at least some of these
    assert isinstance(people, list)
    assert isinstance(orgs, list)
    assert isinstance(locations, list)
