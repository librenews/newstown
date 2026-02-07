"""Tests for human oversight features."""
import pytest
from uuid import uuid4
from db.human_oversight import human_prompt_store, source_store


@pytest.mark.asyncio
async def test_create_human_prompt(db, sample_story_id):
    """Test creating a human prompt."""
    prompt_id = await human_prompt_store.create_prompt(
        story_id=sample_story_id,
        prompt_text="Is there evidence of fiscal inconsistency?",
        created_by="analyst@example.com",
    )
    
    assert prompt_id is not None
    assert isinstance(prompt_id, int)


@pytest.mark.asyncio
async def test_create_prompt_with_context(db, sample_story_id):
    """Test creating a prompt with additional context."""
    context = {
        "source_document": "Q4_2024_Report.pdf",
        "page": 15,
        "section": "Financial Statements"
    }
    
    prompt_id = await human_prompt_store.create_prompt(
        story_id=sample_story_id,
        prompt_text="Verify revenue numbers",
        created_by="editor",
        context=context,
    )
    
    # Retrieve prompt
    prompts = await human_prompt_store.get_pending_prompts(sample_story_id)
    
    assert len(prompts) == 1
    assert prompts[0].id == prompt_id
    assert prompts[0].prompt_text == "Verify revenue numbers"
    assert prompts[0].context["page"] == 15
    assert prompts[0].status == "pending"


@pytest.mark.asyncio
async def test_get_pending_prompts(db):
    """Test retrieving pending prompts across stories."""
    story1 = uuid4()
    story2 = uuid4()
    
    await human_prompt_store.create_prompt(story1, "Question 1", "user1")
    await human_prompt_store.create_prompt(story2, "Question 2", "user2")
    await human_prompt_store.create_prompt(story1, "Question 3", "user1")
    
    # Get all pending
    all_prompts = await human_prompt_store.get_pending_prompts()
    assert len(all_prompts) == 3
    
    # Get for specific story
    story1_prompts = await human_prompt_store.get_pending_prompts(story1)
    assert len(story1_prompts) == 2
    assert all(p.story_id == story1 for p in story1_prompts)


@pytest.mark.asyncio
async def test_mark_prompt_answered(db, sample_story_id):
    """Test marking a prompt as answered with response."""
    prompt_id = await human_prompt_store.create_prompt(
        story_id=sample_story_id,
        prompt_text="What is the timeline?",
        created_by="user",
    )
    
    response = {
        "answer": "The event occurred on March 15, 2024",
        "confidence": 0.95,
        "sources": ["source1.com", "source2.com"]
    }
    
    await human_prompt_store.mark_answered(prompt_id, response)
    
    # Get prompt history
    history = await human_prompt_store.get_prompt_history(sample_story_id)
    
    assert len(history) == 1
    assert history[0].status == "answered"
    assert history[0].response["answer"] == "The event occurred on March 15, 2024"
    assert history[0].response["confidence"] == 0.95


@pytest.mark.asyncio
async def test_mark_prompt_processing(db, sample_story_id):
    """Test marking a prompt as being processed."""
    prompt_id = await human_prompt_store.create_prompt(
        story_id=sample_story_id,
        prompt_text="Test question",
        created_by="user",
    )
    
    await human_prompt_store.mark_processing(prompt_id)
    
    # Should not appear in pending
    pending = await human_prompt_store.get_pending_prompts(sample_story_id)
    assert len(pending) == 0
    
    # Should appear in history
    history = await human_prompt_store.get_prompt_history(sample_story_id)
    assert len(history) == 1
    assert history[0].status == "processing"


@pytest.mark.asyncio
async def test_add_url_source(db, sample_story_id):
    """Test adding a URL source to a story."""
    source_id = await source_store.add_url_source(
        story_id=sample_story_id,
        url="https://example.com/article",
        added_by="researcher",
        metadata={"title": "Important Article", "date": "2024-03-15"}
    )
    
    assert source_id is not None
    
    # Retrieve sources
    sources = await source_store.get_story_sources(sample_story_id)
    assert len(sources) == 1
    assert sources[0].source_type == "url"
    assert sources[0].source_url == "https://example.com/article"
    assert sources[0].source_metadata["title"] == "Important Article"


@pytest.mark.asyncio
async def test_add_text_source(db, sample_story_id):
    """Test adding pasted text as a source."""
    text_content = """
    Important context from internal memo:
    The board meeting was held on March 10.
    All members voted unanimously.
    """
    
    source_id = await source_store.add_text_source(
        story_id=sample_story_id,
        content=text_content,
        added_by="editor",
        metadata={"type": "memo", "confidential": True}
    )
    
    sources = await source_store.get_story_sources(sample_story_id)
    assert len(sources) == 1
    assert sources[0].source_type == "text"
    assert "board meeting" in sources[0].source_content
    assert sources[0].source_metadata["confidential"] is True


@pytest.mark.asyncio
async def test_add_document_source(db, sample_story_id):
    """Test adding a document source."""
    doc_content = "PDF content extracted here..."
    
    source_id = await source_store.add_document_source(
        story_id=sample_story_id,
        content=doc_content,
        filename="financial_report_q4.pdf",
        added_by="analyst",
    )
    
    sources = await source_store.get_story_sources(sample_story_id)
    assert len(sources) == 1
    assert sources[0].source_type == "document"
    assert sources[0].source_content == doc_content
    assert sources[0].source_metadata["filename"] == "financial_report_q4.pdf"


@pytest.mark.asyncio
async def test_get_story_sources_multiple_types(db, sample_story_id):
    """Test retrieving multiple source types for a story."""
    await source_store.add_url_source(sample_story_id, "https://url1.com", "user1")
    await source_store.add_text_source(sample_story_id, "Some text", "user2")
    await source_store.add_document_source(sample_story_id, "Doc content", "doc.pdf", "user3")
    
    sources = await source_store.get_story_sources(sample_story_id)
    
    assert len(sources) == 3
    
    types = {s.source_type for s in sources}
    assert types == {"url", "text", "document"}


@pytest.mark.asyncio
async def test_mark_source_processed(db, sample_story_id):
    """Test marking a source as processed."""
    source_id = await source_store.add_url_source(
        sample_story_id,
        "https://example.com",
        "user"
    )
    
    # Initially not processed
    sources = await source_store.get_story_sources(sample_story_id)
    assert sources[0].processed is False
    
    # Mark as processed
    await source_store.mark_processed(source_id)
    
    # Verify
    sources = await source_store.get_story_sources(sample_story_id)
    assert sources[0].processed is True
    
    # Test processed_only filter
    processed_sources = await source_store.get_story_sources(sample_story_id, processed_only=True)
    assert len(processed_sources) == 1


@pytest.mark.asyncio
async def test_multiple_sources_ordering(db, sample_story_id):
    """Test that sources are returned in reverse chronological order."""
    import asyncio
    
    await source_store.add_text_source(sample_story_id, "First", "user")
    await asyncio.sleep(0.1)
    await source_store.add_text_source(sample_story_id, "Second", "user")
    await asyncio.sleep(0.1)
    await source_store.add_text_source(sample_story_id, "Third", "user")
    
    sources = await source_store.get_story_sources(sample_story_id)
    
    # Should be in reverse order (newest first)
    assert sources[0].source_content == "Third"
    assert sources[1].source_content == "Second"
    assert sources[2].source_content == "First"
