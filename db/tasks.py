"""Task management system."""
import json
from typing import Optional, Any
from uuid import UUID, uuid4
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from db.connection import db
from config.logging import get_logger

logger = get_logger(__name__)


class TaskStage(str, Enum):
    """Pipeline stages for tasks."""
    DETECT = "detect"
    RESEARCH = "research"
    DRAFT = "draft"
    EDIT = "edit"
    REVIEW = "review"
    PUBLISH = "publish"


class TaskStatus(str, Enum):
    """Task status."""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(BaseModel):
    """Task model."""
    id: UUID = Field(default_factory=uuid4)
    story_id: UUID
    stage: TaskStage
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 5
    assigned_agent: Optional[UUID] = None
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    deadline: Optional[datetime] = None


class TaskQueue:
    """Task queue for agent work coordination."""

    async def create(
        self,
        story_id: UUID,
        stage: TaskStage,
        priority: int = 5,
        input_data: Optional[dict[str, Any]] = None,
        deadline: Optional[datetime] = None,
    ) -> UUID:
        """Create a new task."""
        task_id = await db.fetchval(
            """
            INSERT INTO story_tasks (story_id, stage, priority, input, deadline)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            story_id,
            stage.value,
            priority,
            json.dumps(input_data or {}),  # Serialize to JSON string
            deadline,
        )
        
        logger.info(
            "Task created",
            task_id=str(task_id),
            story_id=str(story_id),
            stage=stage.value,
            priority=priority,
        )
        
        return task_id

    async def claim(self, agent_id: UUID, role: str) -> Optional[Task]:
        """Claim the next available task for an agent role."""
        row = await db.fetchrow(
            "SELECT * FROM claim_task($1, $2)",
            agent_id,
            role,
        )
        
        if not row:
            return None
        
        task = Task(
            id=row["task_id"],
            story_id=row["story_id"],
            stage=TaskStage(row["stage"]),
            status=TaskStatus.ACTIVE,
            assigned_agent=agent_id,
            input=json.loads(row["input"]) if isinstance(row["input"], str) else row["input"],
        )
        
        logger.info(
            "Task claimed",
            task_id=str(task.id),
            agent_id=str(agent_id),
            stage=task.stage.value,
        )
        
        return task

    async def complete(
        self,
        task_id: UUID,
        output_data: dict[str, Any],
    ) -> None:
        """Mark a task as completed."""
        await db.execute(
            """
            UPDATE story_tasks
            SET status = 'completed',
                output = $2,
                completed_at = now()
            WHERE id = $1
            """,
            task_id,
            json.dumps(output_data),  # Serialize to JSON string
        )
        
        logger.info("Task completed", task_id=str(task_id))

    async def fail(
        self,
        task_id: UUID,
        error: str,
    ) -> None:
        """Mark a task as failed."""
        await db.execute(
            """
            UPDATE story_tasks
            SET status = 'failed',
                output = jsonb_build_object('error', $2::TEXT),
                completed_at = now()
            WHERE id = $1
            """,
            task_id,
            error,
        )
        
        logger.warning("Task failed", task_id=str(task_id), error=error)

    async def get_task(self, task_id: UUID) -> Optional[Task]:
        """Get a task by ID."""
        row = await db.fetchrow(
            "SELECT * FROM story_tasks WHERE id = $1",
            task_id,
        )
        
        if not row:
            return None
        
        # Deserialize JSON fields
        row_dict = dict(row)
        if isinstance(row_dict['input'], str):
            row_dict['input'] = json.loads(row_dict['input'])
        if isinstance(row_dict['output'], str):
            row_dict['output'] = json.loads(row_dict['output'])
        return Task(**row_dict)

    async def get_story_tasks(self, story_id: UUID) -> list[Task]:
        """Get all tasks for a story."""
        rows = await db.fetch(
            "SELECT * FROM story_tasks WHERE story_id = $1 ORDER BY created_at",
            story_id,
        )
        
        # Deserialize JSON fields
        tasks = []
        for row in rows:
            row_dict = dict(row)
            if isinstance(row_dict['input'], str):
                row_dict['input'] = json.loads(row_dict['input'])
            if isinstance(row_dict['output'], str):
                row_dict['output'] = json.loads(row_dict['output'])
            tasks.append(Task(**row_dict))
        return tasks


# Global task queue instance
task_queue = TaskQueue()
