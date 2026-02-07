"""Tests for JSONB serialization in events and tasks."""
import pytest
import json
from uuid import uuid4
from db import event_store, task_queue, TaskStage, TaskStatus


@pytest.mark.asyncio
async def test_event_store_jsonb_serialization(db, sample_story_id):
    """Test that event data is properly serialized to JSONB."""
    complex_data = {
        "title": "Test Story",
        "score": 0.85,
        "entities": ["Person A", "Company B"],
        "metadata": {
            "source": "rss",
            "nested": {"key": "value"}
        }
    }
    
    event_id = await event_store.append(
        story_id=sample_story_id,
        event_type="test.jsonb",
        data=complex_data,
    )
    
    assert event_id is not None
    
    # Retrieve and verify data is deserialized correctly
    events = await event_store.get_story_events(sample_story_id)
    assert len(events) == 1
    
    event = events[0]
    assert isinstance(event.data, dict)
    assert event.data["title"] == "Test Story"
    assert event.data["score"] == 0.85
    assert event.data["entities"] == ["Person A", "Company B"]
    assert event.data["metadata"]["nested"]["key"] == "value"


@pytest.mark.asyncio
async def test_event_store_empty_dict(db, sample_story_id):
    """Test appending event with empty dict."""
    event_id = await event_store.append(
        story_id=sample_story_id,
        event_type="test.empty",
        data={},
    )
    
    events = await event_store.get_story_events(sample_story_id)
    assert len(events) == 1
    assert events[0].data == {}


@pytest.mark.asyncio
async def test_task_input_jsonb_serialization(db, sample_story_id):
    """Test that task input data is properly serialized."""
    input_data = {
        "detection_data": {
            "title": "Breaking News",
            "url": "https://example.com",
            "score": 0.9
        },
        "context": ["fact1", "fact2"],
        "metadata": {"priority": "high"}
    }
    
    task_id = await task_queue.create(
        story_id=sample_story_id,
        stage=TaskStage.RESEARCH,
        priority=5,
        input_data=input_data,
    )
    
    # Retrieve task
    task = await task_queue.get_task(task_id)
    
    assert isinstance(task.input, dict)
    assert task.input["detection_data"]["title"] == "Breaking News"
    assert task.input["context"] == ["fact1", "fact2"]
    assert task.input["metadata"]["priority"] == "high"


@pytest.mark.asyncio
async def test_task_output_jsonb_serialization(db, sample_story_id):
    """Test that task output data is properly serialized."""
    task_id = await task_queue.create(
        story_id=sample_story_id,
        stage=TaskStage.RESEARCH,
    )
    
    agent_id = uuid4()
    await task_queue.claim(agent_id, "reporter")
    
    output_data = {
        "facts": ["fact1", "fact2"],
        "sources": [{"url": "https://example.com", "title": "Source"}],
        "verified": True
    }
    
    await task_queue.complete(task_id, output_data)
    
    # Retrieve task
    task = await task_queue.get_task(task_id)
    
    assert isinstance(task.output, dict)
    assert task.output["facts"] == ["fact1", "fact2"]
    assert task.output["verified"] is True
    assert task.output["sources"][0]["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_task_fail_with_error_message(db, sample_story_id):
    """Test that task failure stores error as JSONB."""
    task_id = await task_queue.create(
        story_id=sample_story_id,
        stage=TaskStage.RESEARCH,
    )
    
    agent_id = uuid4()
    await task_queue.claim(agent_id, "reporter")
    
    error_message = "Network timeout after 30 seconds"
    await task_queue.fail(task_id, error_message)
    
    # Retrieve task
    task = await task_queue.get_task(task_id)
    
    assert task.status == TaskStatus.FAILED
    assert isinstance(task.output, dict)
    assert task.output["error"] == error_message


@pytest.mark.asyncio
async def test_task_claimed_input_deserialization(db, sample_story_id):
    """Test that claimed task has properly deserialized input."""
    input_data = {
        "type": "research",
        "urls": ["url1", "url2"],
        "config": {"depth": 2}
    }
    
    await task_queue.create(
        story_id=sample_story_id,
        stage=TaskStage.RESEARCH,
        input_data=input_data,
    )
    
    agent_id = uuid4()
    claimed_task = await task_queue.claim(agent_id, "reporter")
    
    assert isinstance(claimed_task.input, dict)
    assert claimed_task.input["type"] == "research"
    assert claimed_task.input["urls"] == ["url1", "url2"]
    assert claimed_task.input["config"]["depth"] == 2


@pytest.mark.asyncio
async def test_get_story_tasks_deserialization(db, sample_story_id):
    """Test that get_story_tasks properly deserializes all fields."""
    # Create multiple tasks with different data
    task1_id = await task_queue.create(
        story_id=sample_story_id,
        stage=TaskStage.RESEARCH,
        input_data={"task": 1},
    )
    
    task2_id = await task_queue.create(
        story_id=sample_story_id,
        stage=TaskStage.DRAFT,
        input_data={"task": 2},
    )
    
    # Complete one
    agent_id = uuid4()
    await task_queue.claim(agent_id, "reporter")
    await task_queue.complete(task1_id, {"result": "success"})
    
    # Get all tasks
    tasks = await task_queue.get_story_tasks(sample_story_id)
    
    assert len(tasks) == 2
    
    for task in tasks:
        assert isinstance(task.input, dict)
        if task.output:
            assert isinstance(task.output, dict)
    
    completed_task = next(t for t in tasks if t.id == task1_id)
    assert completed_task.output["result"] == "success"
