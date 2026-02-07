"""Pytest configuration and fixtures for News Town tests."""
import pytest
import asyncio
import os
from uuid import uuid4
from typing import AsyncGenerator

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", "postgresql://localhost/newstown_test")
os.environ["LOG_LEVEL"] = "WARNING"  # Reduce noise in tests
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["ANTHROPIC_API_KEY"] = "test-key"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def db():
    """Provide a clean database for each test."""
    from db.connection import db as database
    from db.migrate import reset_database
    
    # Connect to test database
    await database.connect()
    
    # Reset to clean state
    await reset_database()
    
    yield database
    
    # Cleanup
    await database.disconnect()


@pytest.fixture
def sample_story_id():
    """Generate a sample story ID."""
    return uuid4()


@pytest.fixture
def sample_detection_event():
    """Sample story detection event data."""
    return {
        "source": "https://news.ycombinator.com/rss",
        "title": "Tech Company Announces Major Layoffs",
        "url": "https://example.com/article",
        "summary": "TechCorp announced it will lay off 400 employees across multiple offices.",
        "score": 0.85,
        "published": "2026-02-07T12:00:00Z",
    }


@pytest.fixture
def sample_research_data():
    """Sample research results."""
    return {
        "facts": [
            {
                "claim": "TechCorp laying off 400 employees",
                "source": "https://example.com/article",
                "verified": True,
                "source_count": 3,
            }
        ],
        "sources": [
            {
                "url": "https://example.com/article",
                "title": "TechCorp Layoffs",
                "snippet": "Company announces layoffs",
                "type": "original",
            },
            {
                "url": "https://news.com/techcorp",
                "title": "TechCorp Restructure",
                "snippet": "Layoffs confirmed",
                "type": "corroboration",
            },
        ],
        "entities": {
            "people": ["CEO John Smith"],
            "organizations": ["TechCorp", "SEC"],
            "locations": ["San Francisco"],
        },
        "verified": True,
        "source_count": 3,
    }


@pytest.fixture
def mock_llm_response():
    """Mock LLM response for drafting."""
    return """# TechCorp Announces Major Restructuring

TechCorp announced today that it will lay off approximately 400 employees as part of a broader restructuring effort. The layoffs will affect multiple offices, with the San Francisco headquarters expected to see the largest impact.

CEO John Smith stated in a press release that the decision was made to streamline operations and focus on core business areas. The company filed notice with the SEC yesterday.

This marks the second round of layoffs at TechCorp this year, following a similar reduction in workforce earlier this quarter.
"""


@pytest.fixture
def mock_search_results():
    """Mock search results."""
    from ingestion.search import SearchResult
    
    return [
        SearchResult(
            title="TechCorp Layoffs Confirmed",
            url="https://news.com/techcorp-layoffs",
            snippet="TechCorp has confirmed plans to lay off 400 workers",
            source="news.com",
        ),
        SearchResult(
            title="Breaking: TechCorp Restructure",
            url="https://tech.blog/techcorp",
            snippet="Company announces major restructuring with job cuts",
            source="tech.blog",
        ),
    ]


# Test markers
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test (slower)"
    )
    config.addinivalue_line(
        "markers", "requires_api: mark test as requiring external API keys"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow"
    )
