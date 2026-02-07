"""Base agent framework for News Town."""
import asyncio
from abc import ABC, abstractmethod
from typing import Optional, Any
from uuid import UUID, uuid4
from datetime import datetime
from enum import Enum
from db import db, event_store, task_queue, Task, TaskStatus
from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)


class AgentRole(str, Enum):
    """Agent roles in the newsroom."""
    CHIEF = "chief"
    SCOUT = "scout"
    REPORTER = "reporter"
    EDITOR = "editor"
    PUBLISHER = "publisher"


class AgentStatus(str, Enum):
    """Agent status."""
    IDLE = "idle"
    WORKING = "working"
    OFFLINE = "offline"


class BaseAgent(ABC):
    """Base class for all agents."""

    def __init__(self, role: AgentRole):
        self.role = role
        self.agent_id: UUID = uuid4()
        self.status = AgentStatus.IDLE
        self.task_count = 0
        self.success_count = 0
        self._running = False

    async def register(self) -> None:
        """Register agent in database."""
        await db.execute(
            """
            INSERT INTO agents (id, role, status, last_heartbeat)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (id) DO UPDATE
            SET last_heartbeat = $4, status = $3
            """,
            self.agent_id,
            self.role.value,
            self.status.value,
            datetime.utcnow(),
        )
        
        logger.info(
            "Agent registered",
            agent_id=str(self.agent_id),
            role=self.role.value,
        )

    async def heartbeat(self) -> None:
        """Send heartbeat to indicate agent is alive."""
        await db.execute(
            """
            UPDATE agents
            SET last_heartbeat = $2, status = $3
            WHERE id = $1
            """,
            self.agent_id,
            datetime.utcnow(),
            self.status.value,
        )

    async def log_event(
        self,
        story_id: UUID,
        event_type: str,
        data: dict[str, Any],
    ) -> int:
        """Log an event for a story."""
        return await event_store.append(
            story_id=story_id,
            event_type=event_type,
            data=data,
            agent_id=self.agent_id,
        )

    @abstractmethod
    async def handle_task(self, task: Task) -> dict[str, Any]:
        """Handle a task - must be implemented by subclasses."""
        pass

    async def process_task(self, task: Task) -> None:
        """Process a task with error handling."""
        self.status = AgentStatus.WORKING
        await self.heartbeat()
        
        try:
            logger.info(
                "Processing task",
                agent_id=str(self.agent_id),
                task_id=str(task.id),
                stage=task.stage.value,
            )
            
            # Handle the task
            output = await self.handle_task(task)
            
            # Mark task as completed
            await task_queue.complete(task.id, output)
            
            # Log completion event
            await self.log_event(
                task.story_id,
                f"task.completed.{task.stage.value}",
                {"task_id": str(task.id), "output": output},
            )
            
            self.task_count += 1
            self.success_count += 1
            
            logger.info(
                "Task completed successfully",
                agent_id=str(self.agent_id),
                task_id=str(task.id),
            )
            
        except Exception as e:
            logger.error(
                "Task failed",
                agent_id=str(self.agent_id),
                task_id=str(task.id),
                error=str(e),
                exc_info=True,
            )
            
            # Mark task as failed
            await task_queue.fail(task.id, str(e))
            
            # Log failure event
            await self.log_event(
                task.story_id,
                f"task.failed.{task.stage.value}",
                {"task_id": str(task.id), "error": str(e)},
            )
            
            self.task_count += 1
        
        finally:
            self.status = AgentStatus.IDLE
            await self.heartbeat()

    async def run(self) -> None:
        """Main agent loop - poll for tasks and process them."""
        self._running = True
        await self.register()
        
        logger.info(
            "Agent started",
            agent_id=str(self.agent_id),
            role=self.role.value,
        )
        
        heartbeat_counter = 0
        
        while self._running:
            try:
                # Claim a task
                task = await task_queue.claim(self.agent_id, self.role.value)
                
                if task:
                    await self.process_task(task)
                else:
                    # No tasks available - wait
                    await asyncio.sleep(settings.task_poll_interval_seconds)
                
                # Periodic heartbeat
                heartbeat_counter += 1
                if heartbeat_counter >= settings.agent_heartbeat_interval_seconds:
                    await self.heartbeat()
                    heartbeat_counter = 0
                    
            except Exception as e:
                logger.error(
                    "Agent loop error",
                    agent_id=str(self.agent_id),
                    error=str(e),
                    exc_info=True,
                )
                await asyncio.sleep(5)

    async def stop(self) -> None:
        """Stop the agent."""
        self._running = False
        self.status = AgentStatus.OFFLINE
        await self.heartbeat()
        
        logger.info(
            "Agent stopped",
            agent_id=str(self.agent_id),
            role=self.role.value,
        )
