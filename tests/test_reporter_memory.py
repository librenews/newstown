"""Test Reporter agent enhancements."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from uuid import uuid4
from db import Task, TaskStage
from agents.reporter import ReporterAgent

@pytest.fixture
def mock_services():
    with patch("ingestion.embeddings.embedding_service") as embed, \
         patch("db.memory.memory_store") as memory, \
         patch("ingestion.search_service") as search, \
         patch("ingestion.entity_extractor") as entity, \
         patch("db.human_oversight.human_prompt_store") as prompts, \
         patch("db.human_oversight.source_store") as sources, \
         patch("agents.llm.chat_service") as chat:
        
        embed.embed.return_value = [0.1, 0.2]
        memory.find_similar_stories = AsyncMock(return_value=[])
        search.search = AsyncMock(return_value=[])
        entity.extract.return_value = []
        prompts.get_pending_prompts = AsyncMock(return_value=[])
        sources.get_story_sources = AsyncMock(return_value=[])
        chat.generate = AsyncMock(return_value="Drafted article content.")
        chat.provider = "mock_provider"
        
        yield {
            "embed": embed,
            "memory": memory,
            "search": search,
            "entity": entity,
            "chat": chat
        }

@pytest.fixture
def reporter(mock_services):
    agent = ReporterAgent()
    agent.log_event = AsyncMock()
    return agent

@pytest.mark.asyncio
async def test_research_contextual_memory(reporter, mock_services):
    """Test that research retrieves and returns historical context."""
    # Setup
    mock_services["memory"].find_similar_stories.return_value = [
        {"story_id": "old-1", "content": "Old Story Content", "similarity": 0.9}
    ]
    
    task = Task(
        id=uuid4(),
        type="research",
        story_id=uuid4(),
        stage=TaskStage.RESEARCH,
        input={"detection_data": {"title": "New Event", "summary": "Something happened."}}
    )
    
    # Run
    result = await reporter.research(task)
    
    # Verify
    assert "historical_context" in result
    assert result["historical_context"][0]["content"] == "Old Story Content"
    mock_services["embed"].embed.assert_called_once()

@pytest.mark.asyncio
async def test_research_entity_first(reporter, mock_services):
    """Test that research performs entity-specific searches."""
    # Setup
    mock_entity = MagicMock()
    mock_entity.text = "Elon Musk"
    mock_entity.label_ = "PERSON"
    mock_services["entity"].extract.return_value = [mock_entity]
    
    task = Task(
        id=uuid4(),
        type="research",
        story_id=uuid4(),
        stage=TaskStage.RESEARCH,
        input={"detection_data": {"title": "Space Launch", "summary": "Rocket goes up."}}
    )
    
    # Run
    await reporter.research(task)
    
    # Verify
    # Should search for "Elon Musk Space Launch"
    calls = mock_services["search"].search.call_args_list
    # Note: calls might be any order, checking if one matches
    entity_search_called = any("Elon Musk" in str(call) for call in calls)
    assert entity_search_called

@pytest.mark.asyncio
async def test_draft_uses_context(reporter, mock_services):
    """Test that draft prompt includes historical context."""
    task = Task(
        id=uuid4(),
        type="draft",
        story_id=uuid4(),
        stage=TaskStage.DRAFT,
        input={
            "detection_data": {"title": "News", "summary": "Summary"},
            "research_data": {
                "historical_context": [{"content": "Previous incident details."}],
                "verified": True
            }
        }
    )
    
    # Run
    await reporter.draft(task)
    
    # Verify prompt contains context
    args, kwargs = mock_services["chat"].generate.call_args
    # Check messages argument (passed as kwarg in code)
    messages = kwargs.get("messages") or (args[1] if len(args) > 1 else [])
    
    prompt_content = messages[0]["content"]
    
    assert "Previous incident details" in prompt_content
    assert "Historical Context" in prompt_content
