"""Integration tests for end-to-end workflows."""
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from db import event_store, task_queue, TaskStage
from chief import Chief
from agents.reporter import ReporterAgent


@pytest.mark.integration
@pytest.mark.asyncio
async def test_story_detection_to_research_pipeline(db, sample_story_id, sample_detection_event):
    """Test complete pipeline: detection → research task creation."""
    # Setup: Create a story detection event
    await event_store.append(
        story_id=sample_story_id,
        event_type="story.detected",
        data=sample_detection_event,
    )
    
    # Chief processes detections
    chief = Chief()
    await chief.register()
    
    processed_count = await chief.process_new_detections()
    
    # Should create one story and task
    assert processed_count == 1
    
    # Verify story.created event exists
    events = await event_store.get_story_events(sample_story_id)
    event_types = [e.event_type for e in events]
    assert "story.created" in event_types
    
    # Verify research task was created
    tasks = await task_queue.get_story_tasks(sample_story_id)
    assert len(tasks) == 1
    assert tasks[0].stage == TaskStage.RESEARCH


@pytest.mark.integration
@pytest.mark.asyncio
async def test_research_to_draft_pipeline(db, sample_story_id, sample_detection_event):
    """Test pipeline: research completion → draft task creation."""
    # Setup: Story detected and created
    await event_store.append(sample_story_id, "story.detected", sample_detection_event)
    await event_store.append(sample_story_id, "story.created", {"score": 0.85})
    
    # Research task completed
    await event_store.append(
        sample_story_id,
        "task.completed.research",
        {
            "output": {
                "facts": [],
                "sources": [],
                "entities": {},
            }
        },
    )
    
    # Chief advances story
    chief = Chief()
    await chief.register()
    
    advanced_count = await chief.advance_stories()
    
    assert advanced_count == 1
    
    # Verify draft task was created
    tasks = await task_queue.get_story_tasks(sample_story_id)
    draft_tasks = [t for t in tasks if t.stage == TaskStage.DRAFT]
    assert len(draft_tasks) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reporter_research_task(db, sample_story_id, sample_detection_event, mock_search_results):
    """Test reporter completing a research task."""
    # Create research task
    task_id = await task_queue.create(
        story_id=sample_story_id,
        stage=TaskStage.RESEARCH,
        input_data={"detection_data": sample_detection_event},
    )
    
    # Mock search service
    with patch("agents.reporter.search_service") as mock_search:
        mock_search.search = AsyncMock(return_value=mock_search_results)
        
        # Create reporter and claim task
        reporter = ReporterAgent()
        await reporter.register()
        
        claimed_task = await task_queue.claim(reporter.agent_id, "reporter")
        assert claimed_task is not None
        
        # Process the task
        await reporter.process_task(claimed_task)
        
        # Verify task completed
        task = await task_queue.get_task(task_id)
        assert task.status.value == "completed"
        
        # Verify research output
        output = task.output
        assert "sources" in output
        assert "entities" in output
        assert "verified" in output


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reporter_draft_task(db, sample_story_id, sample_detection_event, sample_research_data, mock_llm_response):
    """Test reporter completing a draft task."""
    # Create draft task
    task_id = await task_queue.create(
        story_id=sample_story_id,
        stage=TaskStage.DRAFT,
        input_data={
            "detection_data": sample_detection_event,
            "research_data": sample_research_data,
        },
    )
    
    # Mock Claude API
    with patch.object(ReporterAgent, "llm") as mock_llm:
        mock_response = AsyncMock()
        mock_response.content = [AsyncMock(text=mock_llm_response)]
        mock_llm.messages.create = AsyncMock(return_value=mock_response)
        
        # Create reporter and process
        reporter = ReporterAgent()
        reporter.llm = mock_llm
        await reporter.register()
        
        claimed_task = await task_queue.claim(reporter.agent_id, "reporter")
        await reporter.process_task(claimed_task)
        
        # Verify task completed
        task = await task_queue.get_task(task_id)
        assert task.status.value == "completed"
        
        # Verify draft output
        output = task.output
        assert "article" in output
        assert len(output["article"]) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stalled_task_recovery(db, sample_story_id):
    """Test that Chief recovers stalled tasks."""
    # Create a task and claim it
    task_id = await task_queue.create(
        story_id=sample_story_id,
        stage=TaskStage.RESEARCH,
    )
    
    agent_id = uuid4()
    await task_queue.claim(agent_id, "reporter")
    
    # Manually backdate the started_at to simulate stall
    await db.execute(
        "UPDATE story_tasks SET started_at = now() - INTERVAL '31 minutes' WHERE id = $1",
        task_id,
    )
    
    # Chief should recover it
    chief = Chief()
    await chief.register()
    
    recovered_count = await chief.recover_stalled_tasks()
    assert recovered_count == 1
    
    # Task should be pending again
    task = await task_queue.get_task(task_id)
    assert task.status == "pending"
    assert task.assigned_agent is None
