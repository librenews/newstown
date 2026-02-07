"""Tests for Chief orchestration logic."""
import pytest
from uuid import uuid4
from chief import Chief
from db import event_store, task_queue, TaskStage


@pytest.mark.asyncio
async def test_chief_registration(db):
    """Test Chief can register as an agent."""
    chief = Chief()
    await chief.register()
    
    # Should be registered in database
    agents = await db.fetch("SELECT * FROM agents WHERE role = 'chief'")
    assert len(agents) > 0


@pytest.mark.asyncio
async def test_chief_processes_high_score_detection(db, sample_detection_event):
    """Test Chief creates pipeline for high-score detection."""
    story_id = uuid4()
    
    # Create detection with high score
    detection_event = {**sample_detection_event, "score": 0.85}
    await event_store.append(story_id, "story.detected", detection_event)
    
    chief = Chief()
    await chief.register()
    
    count = await chief.process_new_detections()
    
    assert count == 1
    
    # Should create story.created event
    events = await event_store.get_story_events(story_id)
    assert any(e.event_type == "story.created" for e in events)
    
    # Should create research task
    tasks = await task_queue.get_story_tasks(story_id)
    assert len(tasks) == 1
    assert tasks[0].stage == TaskStage.RESEARCH


@pytest.mark.asyncio
async def test_chief_rejects_low_score_detection(db, sample_detection_event):
    """Test Chief rejects detection with low score."""
    story_id = uuid4()
    
    # Create detection with low score (below threshold of 0.6)
    detection_event = {**sample_detection_event, "score": 0.4}
    await event_store.append(story_id, "story.detected", detection_event)
    
    chief = Chief()
    await chief.register()
    
    count = await chief.process_new_detections()
    
    assert count == 0
    
    # Should create story.rejected event
    events = await event_store.get_story_events(story_id)
    assert any(e.event_type == "story.rejected" for e in events)
    
    # Should NOT create any tasks
    tasks = await task_queue.get_story_tasks(story_id)
    assert len(tasks) == 0


@pytest.mark.asyncio
async def test_chief_advances_research_to_draft(db, sample_detection_event):
    """Test Chief creates draft task after research completes."""
    story_id = uuid4()
    
    # Setup: Detection and creation events
    await event_store.append(story_id, "story.detected", sample_detection_event)
    await event_store.append(story_id, "story.created", {})
    
    # Research completed
    await event_store.append(
        story_id,
        "task.completed.research",
        {
            "output": {
                "facts": [],
                "sources": [],
                "entities": {},
            }
        },
    )
    
    chief = Chief()
    await chief.register()
    
    count = await chief.advance_stories()
    
    assert count == 1
    
    # Should create draft task
    tasks = await task_queue.get_story_tasks(story_id)
    draft_tasks = [t for t in tasks if t.stage == TaskStage.DRAFT]
    assert len(draft_tasks) == 1


@pytest.mark.asyncio
async def test_chief_doesnt_duplicate_tasks(db, sample_detection_event):
    """Test Chief doesn't create duplicate tasks for same story."""
    story_id = uuid4()
    
    # Setup
    await event_store.append(story_id, "story.detected", sample_detection_event)
    await event_store.append(story_id, "story.created", {})
    await event_store.append(story_id, "task.completed.research", {"output": {}})
    
    chief = Chief()
    await chief.register()
    
    # Advance twice
    count1 = await chief.advance_stories()
    count2 = await chief.advance_stories()
    
    assert count1 == 1
    assert count2 == 0  # Should not create duplicate
    
    # Should only have one draft task
    tasks = await task_queue.get_story_tasks(story_id)
    draft_tasks = [t for t in tasks if t.stage == TaskStage.DRAFT]
    assert len(draft_tasks) == 1


@pytest.mark.asyncio
async def test_chief_recovers_stalled_tasks(db):
    """Test Chief resets stalled tasks."""
    story_id = uuid4()
    
    # Create task and simulate it being stuck
    task_id = await task_queue.create(story_id, TaskStage.RESEARCH)
    agent_id = uuid4()
    await task_queue.claim(agent_id, "reporter")
    
    # Backdate to 31 minutes ago
    await db.execute(
        "UPDATE story_tasks SET started_at = now() - INTERVAL '31 minutes' WHERE id = $1",
        task_id,
    )
    
    chief = Chief()
    await chief.register()
    
    count = await chief.recover_stalled_tasks()
    
    assert count == 1
    
    # Task should be reset
    task = await task_queue.get_task(task_id)
    assert task.status.value == "pending"
    assert task.assigned_agent is None
