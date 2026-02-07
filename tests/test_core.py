"""Basic tests for News Town."""
import pytest
from unittest.mock import Mock, AsyncMock
from uuid import uuid4
from db.events import Event, EventStore
from db.tasks import Task, TaskStage, TaskStatus, TaskQueue
from agents.base import BaseAgent, AgentRole


class MockAgent(BaseAgent):
    """Mock agent for testing."""
    
    def __init__(self):
        super().__init__(AgentRole.REPORTER)
        self.handled_tasks = []
    
    async def handle_task(self, task: Task) -> dict:
        self.handled_tasks.append(task)
        return {"status": "success"}


@pytest.mark.asyncio
async def test_event_creation():
    """Test event model creation."""
    story_id = uuid4()
    event = Event(
        story_id=story_id,
        event_type="test.event",
        data={"test": "value"}
    )
    
    assert event.story_id == story_id
    assert event.event_type == "test.event"
    assert event.data == {"test": "value"}


@pytest.mark.asyncio
async def test_task_creation():
    """Test task model creation."""
    story_id = uuid4()
    task = Task(
        story_id=story_id,
        stage=TaskStage.RESEARCH,
        priority=7
    )
    
    assert task.story_id == story_id
    assert task.stage == TaskStage.RESEARCH
    assert task.status == TaskStatus.PENDING
    assert task.priority == 7


@pytest.mark.asyncio
async def test_agent_task_processing():
    """Test agent task processing."""
    agent = MockAgent()
    
    task = Task(
        story_id=uuid4(),
        stage=TaskStage.RESEARCH,
    )
    
    # Mock database methods
    agent.heartbeat = AsyncMock()
    agent.log_event = AsyncMock()
    
    # Process task would normally handle the task
    # For now just verify agent can be instantiated
    assert agent.role == AgentRole.REPORTER
    assert agent.status.value == "idle"


def test_agent_roles():
    """Test agent role enum."""
    assert AgentRole.CHIEF.value == "chief"
    assert AgentRole.SCOUT.value == "scout"
    assert AgentRole.REPORTER.value == "reporter"
    assert AgentRole.EDITOR.value == "editor"
    assert AgentRole.PUBLISHER.value == "publisher"


def test_task_stages():
    """Test task stage enum."""
    assert TaskStage.DETECT.value == "detect"
    assert TaskStage.RESEARCH.value == "research"
    assert TaskStage.DRAFT.value == "draft"
    assert TaskStage.EDIT.value == "edit"
    assert TaskStage.REVIEW.value == "review"
    assert TaskStage.PUBLISH.value == "publish"
