"""Test Scout agent deduplication logic."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import ingestion.embeddings  # Explicit import to ensure module is loaded
from agents.scout import ScoutAgent

@pytest.fixture
def mock_embedding_service():
    with patch("ingestion.embeddings.embedding_service") as mock:
        mock.embed.return_value = [0.1, 0.2, 0.3]  # Dummy vector
        yield mock

@pytest.fixture
def mock_entity_extractor():
    with patch("ingestion.entity_extractor") as mock:
        mock.extract.return_value = []
        yield mock

@pytest.fixture
def mock_memory_store():
    with patch("db.memory.memory_store") as mock:
        mock.find_similar_stories = AsyncMock()
        mock.add = AsyncMock()
        yield mock

@pytest.fixture
def scout():
    return ScoutAgent(feeds=["http://example.com/rss"])

@pytest.mark.asyncio
async def test_scout_detects_new_story(scout, mock_embedding_service, mock_memory_store, mock_entity_extractor):
    """Test that a new story is detected and saved to memory."""
    # Setup
    mock_memory_store.find_similar_stories.return_value = []  # No duplicates
    
    # Mock feedparser
    with patch("feedparser.parse") as mock_parse:
        mock_entry = {
            "title": "New Tech Invention",
            "summary": "Scientists discover new physics.",
            "link": "http://example.com/story1",
            "published": "Mon, 07 Feb 2026 12:00:00 GMT"
        }
        mock_parse.return_value.entries = [mock_entry]
        
        # Run
        with patch.object(scout, "log_event", new_callable=AsyncMock) as mock_log:
            await scout.scan_feed("http://example.com/rss")
            
            # Verify
            assert mock_embedding_service.embed.called
            assert mock_memory_store.find_similar_stories.called
            assert mock_memory_store.add.called  # Should add to memory
            
            # Check log event
            args, kwargs = mock_log.call_args
            event_data = args[2]
            assert event_data["is_duplicate"] is False
            assert event_data["title"] == "New Tech Invention"

@pytest.mark.asyncio
async def test_scout_detects_duplicate_story(scout, mock_embedding_service, mock_memory_store, mock_entity_extractor):
    """Test that a duplicate story is identified and linked."""
    # Setup
    existing_id = uuid4()
    mock_memory_store.find_similar_stories.return_value = [
        {"story_id": existing_id, "similarity": 0.95, "content": "Old content"}
    ]
    
    # Mock feedparser
    with patch("feedparser.parse") as mock_parse:
        mock_entry = {
            "title": "New Tech Invention (Updated)",
            "summary": "Scientists discover new physics.",
            "link": "http://example.com/story1-update",
            "published": "Mon, 07 Feb 2026 13:00:00 GMT"
        }
        mock_parse.return_value.entries = [mock_entry]
        
        # Run
        with patch.object(scout, "log_event", new_callable=AsyncMock) as mock_log:
            await scout.scan_feed("http://example.com/rss")
            
            # Verify
            assert mock_embedding_service.embed.called
            assert mock_memory_store.find_similar_stories.called
            assert not mock_memory_store.add.called  # Should NOT add duplicate to memory
            
            # Check log event use existing ID
            args, kwargs = mock_log.call_args
            story_id_arg = args[0]
            event_data = args[2]
            
            assert str(story_id_arg) == str(existing_id)
            assert event_data["is_duplicate"] is True
