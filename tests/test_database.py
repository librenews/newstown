"""Database integration tests."""
import pytest
from uuid import uuid4
from db import event_store, task_queue, TaskStage, TaskStatus


@pytest.mark.asyncio
async def test_event_store_append(db, sample_story_id):
    """Test appending events to the event store."""
    event_id = await event_store.append(
        story_id=sample_story_id,
        event_type="test.event",
        data={"test": "value"},
    )
    
    assert event_id is not None
    assert isinstance(event_id, int)


@pytest.mark.asyncio
async def test_event_store_get_story_events(db, sample_story_id):
    """Test retrieving events for a story."""
    # Create multiple events
    await event_store.append(sample_story_id, "event.first", {"order": 1})
    await event_store.append(sample_story_id, "event.second", {"order": 2})
    await event_store.append(sample_story_id, "event.third", {"order": 3})
    
    # Retrieve events
    events = await event_store.get_story_events(sample_story_id)
    
    assert len(events) == 3
    assert events[0].event_type == "event.first"
    assert events[1].event_type == "event.second"
    assert events[2].event_type == "event.third"
    # Events should be ordered by creation time
    assert events[0].data["order"] == 1


@pytest.mark.asyncio
async def test_task_queue_create(db, sample_story_id):
    """Test creating a task in the queue."""
    task_id = await task_queue.create(
        story_id=sample_story_id,
        stage=TaskStage.RESEARCH,
        priority=7,
        input_data={"test": "data"},
    )
    
    assert task_id is not None
    
    # Verify task was created
    task = await task_queue.get_task(task_id)
    assert task is not None
    assert task.stage == TaskStage.RESEARCH
    assert task.priority == 7
    assert task.status == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_task_queue_claim(db, sample_story_id):
    """Test claiming a task from the queue."""
    # Create a research task
    task_id = await task_queue.create(
        story_id=sample_story_id,
        stage=TaskStage.RESEARCH,
    )
    
    # Claim it as a reporter
    agent_id = uuid4()
    claimed_task = await task_queue.claim(agent_id, "reporter")
    
    assert claimed_task is not None
    assert claimed_task.id == task_id
    assert claimed_task.stage == TaskStage.RESEARCH
    assert claimed_task.assigned_agent == agent_id


@pytest.mark.asyncio
async def test_task_queue_claim_wrong_role(db, sample_story_id):
    """Test that agents can only claim tasks for their role."""
    # Create a research task (for reporter)
    await task_queue.create(
        story_id=sample_story_id,
        stage=TaskStage.RESEARCH,
    )
    
    # Try to claim as chief (shouldn't work for research tasks)
    agent_id = uuid4()
    claimed_task = await task_queue.claim(agent_id, "mayor")
    
    assert claimed_task is None


@pytest.mark.asyncio
async def test_task_queue_concurrent_claim(db, sample_story_id):
    """Test that two agents can't claim the same task."""
    import asyncio
    
    # Create one task
    await task_queue.create(
        story_id=sample_story_id,
        stage=TaskStage.RESEARCH,
    )
    
    # Try to claim simultaneously from two agents
    agent1 = uuid4()
    agent2 = uuid4()
    
    results = await asyncio.gather(
        task_queue.claim(agent1, "reporter"),
        task_queue.claim(agent2, "reporter"),
    )
    
    # Exactly one should succeed
    successful_claims = [r for r in results if r is not None]
    assert len(successful_claims) == 1


@pytest.mark.asyncio
async def test_task_queue_complete(db, sample_story_id):
    """Test completing a task."""
    # Create and claim a task
    task_id = await task_queue.create(
        story_id=sample_story_id,
        stage=TaskStage.RESEARCH,
    )
    
    agent_id = uuid4()
    await task_queue.claim(agent_id, "reporter")
    
    # Complete it
    await task_queue.complete(task_id, {"result": "success"})
    
    # Verify status
    task = await task_queue.get_task(task_id)
    assert task.status == TaskStatus.COMPLETED
    assert task.output == {"result": "success"}
    assert task.completed_at is not None


@pytest.mark.asyncio
async def test_task_queue_fail(db, sample_story_id):
    """Test failing a task."""
    # Create and claim a task
    task_id = await task_queue.create(
        story_id=sample_story_id,
        stage=TaskStage.RESEARCH,
    )
    
    agent_id = uuid4()
    await task_queue.claim(agent_id, "reporter")
    
    # Fail it
    await task_queue.fail(task_id, "Something went wrong")
    
    # Verify status
    task = await task_queue.get_task(task_id)
    assert task.status == TaskStatus.FAILED
    assert task.output["error"] == "Something went wrong"


@pytest.mark.asyncio
async def test_task_priority_ordering(db, sample_story_id):
    """Test that higher priority tasks are claimed first."""
    # Create tasks with different priorities
    await task_queue.create(sample_story_id, TaskStage.RESEARCH, priority=3)
    high_priority_id = await task_queue.create(sample_story_id, TaskStage.RESEARCH, priority=9)
    await task_queue.create(sample_story_id, TaskStage.RESEARCH, priority=5)
    
    # Claim a task
    agent_id = uuid4()
    claimed = await task_queue.claim(agent_id, "reporter")
    
    # Should get the highest priority task
    assert claimed.id == high_priority_id
    assert claimed.priority == 9
