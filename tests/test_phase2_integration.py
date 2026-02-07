"""Integration tests for Phase 2 human oversight features."""
import pytest
from uuid import uuid4
from db import event_store, task_queue, TaskStage
from db.human_oversight import human_prompt_store, source_store
from db.articles import article_store


@pytest.mark.integration
@pytest.mark.asyncio
async def test_human_prompt_creates_task_workflow(db, sample_story_id):
    """Test that creating a prompt leads to task creation (requires Chief)."""
    # Create a story
    await event_store.append(
        story_id=sample_story_id,
        event_type="story.created",
        data={"title": "Test Story"},
    )
    
    # Human adds a prompt
    prompt_id = await human_prompt_store.create_prompt(
        story_id=sample_story_id,
        prompt_text="What are the key financial risks?",
        created_by="analyst",
    )
    
    # Verify prompt is pending
    prompts = await human_prompt_store.get_pending_prompts(sample_story_id)
    assert len(prompts) == 1
    assert prompts[0].status == "pending"
    
    # NOTE: In real workflow, Chief would process this and create a task
    # For now just verify the prompt exists and can be retrieved


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sources_available_for_research(db, sample_story_id):
    """Test that added sources are available when research task is created."""
    # Human adds sources to a story
    await source_store.add_url_source(
        sample_story_id,
        "https://example.com/background",
        "researcher",
    )
    
    await source_store.add_text_source(
        sample_story_id,
        "Important context: The event happened on March 10.",
        "editor",
    )
    
    # Create a research task
    task_id = await task_queue.create(
        story_id=sample_story_id,
        stage=TaskStage.RESEARCH,
        input_data={"detection_data": {"title": "Test Story"}},
    )
    
    # Verify sources can be retrieved
    sources = await source_store.get_story_sources(sample_story_id)
    assert len(sources) == 2
    
    # Agent would check for sources during research
    url_sources = [s for s in sources if s.source_type == "url"]
    text_sources = [s for s in sources if s.source_type == "text"]
    
    assert len(url_sources) == 1
    assert len(text_sources) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_prompt_answer_workflow(db, sample_story_id):
    """Test complete workflow: prompt → processing → answered."""
    # Create prompt
    prompt_id = await human_prompt_store.create_prompt(
        sample_story_id,
        "Is this story verified?",
        "editor",
    )
    
    # Mark as processing (Chief does this)
    await human_prompt_store.mark_processing(prompt_id)
    
    # Check it's no longer pending
    pending = await human_prompt_store.get_pending_prompts(sample_story_id)
    assert len(pending) == 0
    
    # Agent answers the prompt
    response = {
        "answer": "Yes, verified with 3 independent sources",
        "sources": ["source1.com", "source2.com", "source3.com"],
        "confidence": 0.92,
    }
    
    await human_prompt_store.mark_answered(prompt_id, response)
    
    # Verify in history
    history = await human_prompt_store.get_prompt_history(sample_story_id)
    assert len(history) == 1
    assert history[0].status == "answered"
    assert history[0].response["confidence"] == 0.92


@pytest.mark.integration
@pytest.mark.asyncio
async def test_story_to_article_pipeline(db, sample_story_id):
    """Test pipeline from story creation to article publication."""
    # 1. Story detected
    await event_store.append(
        sample_story_id,
        "story.detected",
        {
            "title": "Breaking News Event",
            "url": "https://source.com/story",
            "score": 0.85,
        },
    )
    
    # 2. Research completed
    await event_store.append(
        sample_story_id,
        "research.completed",
        {
            "facts": ["Fact 1", "Fact 2"],
            "sources": [{"url": "https://source.com", "title": "Source"}],
        },
    )
    
    # 3. Draft completed
    await event_store.append(
        sample_story_id,
        "draft.completed",
        {"article": "Draft article text"},
    )
    
    # 4. Article published
    article_id = await article_store.create_article(
        story_id=sample_story_id,
        headline="Breaking News Event",
        body="Final article body with **formatting**.",
        sources=[{"url": "https://source.com", "title": "Source"}],
        tags=["breaking", "news"],
    )
    
    # Verify article
    article = await article_store.get_article(article_id)
    assert article.story_id == sample_story_id
    assert article.headline == "Breaking News Event"
    assert len(article.sources) == 1
    
    # Verify can render
    html = article_store.render_html(article)
    assert "Breaking News Event" in html


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_prompts_single_story(db, sample_story_id):
    """Test handling multiple prompts for the same story."""
    # Add multiple prompts
    prompt1 = await human_prompt_store.create_prompt(
        sample_story_id,
        "Question 1: What is the timeline?",
        "user1",
    )
    
    prompt2 = await human_prompt_store.create_prompt(
        sample_story_id,
        "Question 2: Who are the key players?",
        "user2",
    )
    
    prompt3 = await human_prompt_store.create_prompt(
        sample_story_id,
        "Question 3: What are the implications?",
        "user1",
    )
    
    # All should be pending
    pending = await human_prompt_store.get_pending_prompts(sample_story_id)
    assert len(pending) == 3
    
    # Answer them one by one
    await human_prompt_store.mark_answered(
        prompt1,
        {"answer": "Timeline: March 10-15, 2024"},
    )
    
    await human_prompt_store.mark_answered(
        prompt2,
        {"answer": "Key players: Person A, Company B"},
    )
    
    # One still pending
    pending = await human_prompt_store.get_pending_prompts(sample_story_id)
    assert len(pending) == 1
    assert pending[0].id == prompt3
    
    # Check history shows all
    history = await human_prompt_store.get_prompt_history(sample_story_id)
    assert len(history) == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_source_processing_marks(db, sample_story_id):
    """Test that sources can be marked as processed during workflow."""
    # Add multiple sources
    source1 = await source_store.add_url_source(
        sample_story_id,
        "https://source1.com",
        "user",
    )
    
    source2 = await source_store.add_url_source(
        sample_story_id,
        "https://source2.com",
        "user",
    )
    
    # Agent processes first source
    await source_store.mark_processed(source1)
    
    # Check unprocessed
    all_sources = await source_store.get_story_sources(sample_story_id)
    assert len(all_sources) == 2
    
    processed = await source_store.get_story_sources(sample_story_id, processed_only=True)
    assert len(processed) == 1
    assert processed[0].id == source1
    
    # Process second
    await source_store.mark_processed(source2)
    
    processed = await source_store.get_story_sources(sample_story_id, processed_only=True)
    assert len(processed) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_article_updates_maintain_history(db, sample_story_id):
    """Test that updating articles maintains version history through timestamps."""
    import asyncio
    
    # Create initial article
    article_id = await article_store.create_article(
        story_id=sample_story_id,
        headline="Initial Headline",
        body="Initial body",
        tags=["initial"],
    )
    
    initial_article = await article_store.get_article(article_id)
    initial_published = initial_article.published_at
    initial_updated = initial_article.updated_at
    
    # Wait briefly
    await asyncio.sleep(0.1)
    
    # Update the article
    await article_store.update_article(
        article_id,
        headline="Updated Headline",
        body="Updated body",
        tags=["updated", "revised"],
    )
    
    updated_article = await article_store.get_article(article_id)
    
    # published_at shouldn't change
    assert updated_article.published_at == initial_published
    
    # updated_at should be newer
    assert updated_article.updated_at > initial_updated
    
    # Content should be updated
    assert updated_article.headline == "Updated Headline"
    assert "revised" in updated_article.tags
