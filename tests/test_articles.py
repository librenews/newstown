"""Tests for article storage and rendering."""
import pytest
from uuid import uuid4
from db.articles import article_store, Article


@pytest.mark.asyncio
async def test_create_article(db, sample_story_id):
    """Test creating a basic article."""
    article_id = await article_store.create_article(
        story_id=sample_story_id,
        headline="Breaking News: Major Development",
        body="This is the article body in **Markdown** format.",
        byline="Reporter Name",
        summary="A brief summary of the article.",
    )
    
    assert article_id is not None


@pytest.mark.asyncio
async def test_create_article_with_sources(db, sample_story_id):
    """Test creating an article with sources."""
    sources = [
        {"url": "https://source1.com", "title": "Source One", "accessed_at": "2024-03-15"},
        {"url": "https://source2.com", "title": "Source Two", "accessed_at": "2024-03-15"},
    ]
    
    article_id = await article_store.create_article(
        story_id=sample_story_id,
        headline="Test Article",
        body="Article content",
        sources=sources,
    )
    
    article = await article_store.get_article(article_id)
    
    assert article is not None
    assert len(article.sources) == 2
    assert article.sources[0]["url"] == "https://source1.com"


@pytest.mark.asyncio
async def test_create_article_with_entities_and_tags(db, sample_story_id):
    """Test creating an article with entities and tags."""
    entities = [
        {"text": "John Doe", "type": "PERSON"},
        {"text": "Acme Corp", "type": "ORG"},
    ]
    
    tags = ["politics", "economy", "breaking-news"]
    
    article_id = await article_store.create_article(
        story_id=sample_story_id,
        headline="Tagged Article",
        body="Content",
        entities=entities,
        tags=tags,
    )
    
    article = await article_store.get_article(article_id)
    
    assert len(article.entities) == 2
    assert article.entities[0]["text"] == "John Doe"
    assert article.tags == ["politics", "economy", "breaking-news"]


@pytest.mark.asyncio
async def test_get_article(db, sample_story_id):
    """Test retrieving an article by ID."""
    article_id = await article_store.create_article(
        story_id=sample_story_id,
        headline="Test Headline",
        body="Test body content",
        byline="Test Author",
        summary="Test summary",
    )
    
    article = await article_store.get_article(article_id)
    
    assert article is not None
    assert article.headline == "Test Headline"
    assert article.body == "Test body content"
    assert article.byline == "Test Author"
    assert article.summary == "Test summary"
    assert article.story_id == sample_story_id


@pytest.mark.asyncio
async def test_get_nonexistent_article(db):
    """Test retrieving an article that doesn't exist."""
    fake_id = uuid4()
    article = await article_store.get_article(fake_id)
    
    assert article is None


@pytest.mark.asyncio
async def test_get_story_article(db, sample_story_id):
    """Test getting the latest article for a story."""
    # Create two articles for same story
    article1_id = await article_store.create_article(
        story_id=sample_story_id,
        headline="First Version",
        body="Original content",
    )
    
    import asyncio
    await asyncio.sleep(0.1)
    
    article2_id = await article_store.create_article(
        story_id=sample_story_id,
        headline="Updated Version",
        body="Updated content",
    )
    
    # Should get the latest one
    article = await article_store.get_story_article(sample_story_id)
    
    assert article is not None
    assert article.id == article2_id
    assert article.headline == "Updated Version"


@pytest.mark.asyncio
async def test_list_recent_articles(db):
    """Test listing recent articles."""
    story1 = uuid4()
    story2 = uuid4()
    story3 = uuid4()
    
    await article_store.create_article(story1, "Article 1", "Body 1")
    await article_store.create_article(story2, "Article 2", "Body 2")
    await article_store.create_article(story3, "Article 3", "Body 3")
    
    articles = await article_store.list_recent_articles(limit=10)
    
    assert len(articles) >= 3
    # Most recent should be first
    assert articles[0].headline == "Article 3"


@pytest.mark.asyncio
async def test_list_recent_articles_limit(db):
    """Test that list_recent_articles respects limit."""
    for i in range(5):
        story_id = uuid4()
        await article_store.create_article(story_id, f"Article {i}", "Body")
    
    articles = await article_store.list_recent_articles(limit=3)
    
    assert len(articles) == 3


@pytest.mark.asyncio
async def test_update_article(db, sample_story_id):
    """Test updating an article."""
    article_id = await article_store.create_article(
        story_id=sample_story_id,
        headline="Original Headline",
        body="Original body",
    )
    
    # Update it
    await article_store.update_article(
        article_id,
        headline="Updated Headline",
        body="Updated body content",
    )
    
    # Retrieve and verify
    article = await article_store.get_article(article_id)
    
    assert article.headline == "Updated Headline"
    assert article.body == "Updated body content"
    # published_at shouldn't change, but updated_at should
    assert article.updated_at > article.published_at


@pytest.mark.asyncio
async def test_update_article_sources(db, sample_story_id):
    """Test updating article sources."""
    article_id = await article_store.create_article(
        story_id=sample_story_id,
        headline="Test",
        body="Body",
        sources=[{"url": "https://old.com"}],
    )
    
    new_sources = [
        {"url": "https://new1.com", "title": "New Source 1"},
        {"url": "https://new2.com", "title": "New Source 2"},
    ]
    
    await article_store.update_article(article_id, sources=new_sources)
    
    article = await article_store.get_article(article_id)
    assert len(article.sources) == 2
    assert article.sources[0]["url"] == "https://new1.com"


def test_render_markdown():
    """Test rendering article as Markdown."""
    article = Article(
        id=uuid4(),
        story_id=uuid4(),
        headline="Test Article",
        byline="John Doe",
        summary="This is a test summary",
        body="Article **content** with *formatting*.",
        sources=[
            {"url": "https://source1.com", "title": "Source 1"},
            {"url": "https://source2.com", "title": "Source 2"},
        ],
        entities=[],
        tags=[],
        metadata={},
        published_at="2024-03-15T10:00:00",
        updated_at="2024-03-15T10:00:00",
    )
    
    markdown = article_store.render_markdown(article)
    
    assert "# Test Article" in markdown
    assert "*By John Doe*" in markdown
    assert "**This is a test summary**" in markdown
    assert "Article **content** with *formatting*." in markdown
    assert "## Sources" in markdown
    assert "[Source 1](https://source1.com)" in markdown


def test_render_html():
    """Test rendering article as HTML."""
    article = Article(
        id=uuid4(),
        story_id=uuid4(),
        headline="Test Article",
        byline="Jane Smith",
        summary=None,
        body="Simple body text.",
        sources=[],
        entities=[],
        tags=[],
        metadata={},
        published_at="2024-03-15T10:00:00",
        updated_at="2024-03-15T10:00:00",
    )
    
    html = article_store.render_html(article)
    
    assert "<title>Test Article</title>" in html
    assert "<h1>Test Article</h1>" in html
    assert "By Jane Smith" in html
    assert "Simple body text" in html


def test_render_html_with_sources():
    """Test HTML rendering includes sources section."""
    article = Article(
        id=uuid4(),
        story_id=uuid4(),
        headline="Test",
        body="Body",
        sources=[
            {"url": "https://example.com", "title": "Example Source"},
        ],
        entities=[],
        tags=[],
        metadata={},
        byline=None,
        summary=None,
        published_at="2024-03-15T10:00:00",
        updated_at="2024-03-15T10:00:00",
    )
    
    html = article_store.render_html(article)
    
    assert "Sources" in html
    assert "https://example.com" in html
    assert "Example Source" in html
