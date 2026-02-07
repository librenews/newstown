"""Chief agent - central orchestrator for News Town."""
import asyncio
from typing import Any
from uuid import UUID
from agents.base import BaseAgent, AgentRole
from db import db, event_store, task_queue, Task, TaskStage
from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)


class Chief(BaseAgent):
    """
    Central orchestrator that manages story pipelines.
    
    The Chief doesn't write articles - it manages workflow:
    - Converts detections into story pipelines
    - Creates tasks for other agents
    - Monitors progress
    - Handles stuck work
    - Processes human prompts (Phase 2)
    """

    def __init__(self):
        super().__init__(AgentRole.CHIEF)

    async def handle_task(self, task: Task) -> dict[str, Any]:
        """Chief doesn't process tasks from queue - runs its own loop."""
        return {"status": "chief_task_not_applicable"}

    async def process_new_detections(self) -> int:
        """Convert story detections into pipelines."""
        # Find stories that have been detected but not yet processed
        rows = await db.fetch("""
            WITH detected_stories AS (
                SELECT DISTINCT story_id
                FROM story_events
                WHERE event_type = 'story.detected'
            ),
            created_stories AS (
                SELECT DISTINCT story_id
                FROM story_events
                WHERE event_type = 'story.created'
            )
            SELECT d.story_id
            FROM detected_stories d
            LEFT JOIN created_stories c ON d.story_id = c.story_id
            WHERE c.story_id IS NULL
            LIMIT 10
        """)
        
        count = 0
        for row in rows:
            story_id = row["story_id"]
            
            # Get detection data
            events = await event_store.get_story_events(story_id)
            detection_event = next(
                (e for e in events if e.event_type == "story.detected"),
                None
            )
            
            if not detection_event:
                continue
            
            score = detection_event.data.get("score", 0)
            
            # Check if score meets threshold
            if score < settings.min_newsworthiness_score:
                await self.log_event(
                    story_id,
                    "story.rejected",
                    {"reason": "low_score", "score": score}
                )
                continue
            
            # Create story pipeline
            await self.log_event(
                story_id,
                "story.created",
                {
                    "score": score,
                    "title": detection_event.data.get("title"),
                }
            )
            
            # Create research task
            await task_queue.create(
                story_id=story_id,
                stage=TaskStage.RESEARCH,
                priority=int(score * 10),
                input_data={"detection_data": detection_event.data},
            )
            
            logger.info(
                "Story pipeline created",
                story_id=str(story_id),
                score=score,
            )
            
            count += 1
        
        return count

    async def advance_stories(self) -> int:
        """Move stories through pipeline stages."""
        # Find stories with completed research but no draft task
        rows = await db.fetch("""
            WITH research_completed AS (
                SELECT DISTINCT story_id
                FROM story_events
                WHERE event_type = 'task.completed.research'
            ),
            draft_tasks AS (
                SELECT DISTINCT story_id
                FROM story_tasks
                WHERE stage = 'draft'
            )
            SELECT r.story_id
            FROM research_completed r
            LEFT JOIN draft_tasks d ON r.story_id = d.story_id
            WHERE d.story_id IS NULL
            LIMIT 10
        """)
        
        count = 0
        for row in rows:
            story_id = row["story_id"]
            
            # Get research results
            events = await event_store.get_story_events(story_id)
            research_event = next(
                (e for e in reversed(events) if e.event_type == "task.completed.research"),
                None
            )
            detection_event = next(
                (e for e in events if e.event_type == "story.detected"),
                None
            )
            
            if not research_event or not detection_event:
                continue
            
            # Create draft task
            await task_queue.create(
                story_id=story_id,
                stage=TaskStage.DRAFT,
                priority=5,
                input_data={
                    "detection_data": detection_event.data,
                    "research_data": research_event.data.get("output", {}),
                },
            )
            
            logger.info("Draft task created", story_id=str(story_id))
            count += 1
        
        return count

    async def recover_stalled_tasks(self) -> int:
        """Handle tasks that have been active too long."""
        # Find tasks active for more than 30 minutes
        rows = await db.fetch("""
            SELECT id, story_id, stage, assigned_agent
            FROM story_tasks
            WHERE status = 'active'
              AND started_at < now() - INTERVAL '30 minutes'
        """)
        
        count = 0
        for row in rows:
            task_id = row["id"]
            
            # Reset task to pending
            await db.execute("""
                UPDATE story_tasks
                SET status = 'pending',
                    assigned_agent = NULL,
                    started_at = NULL
                WHERE id = $1
            """, task_id)
            
            logger.warning(
                "Task recovered",
                task_id=str(task_id),
                agent=str(row["assigned_agent"]),
            )
            
            count += 1
        
        return count

    async def process_human_prompts(self) -> int:
        """Process pending human prompts by creating high-priority research tasks."""
        from db.human_oversight import human_prompt_store
        
        prompts = await human_prompt_store.get_pending_prompts()
        
        count = 0
        for prompt in prompts:
            # Get story events to find detection data
            events = await event_store.get_story_events(prompt.story_id)
            detection_event = next(
                (e for e in events if e.event_type == "story.detected"),
                None
            )
            
            if not detection_event:
                logger.warning(
                    "Cannot process prompt - no detection event found",
                    story_id=str(prompt.story_id),
                    prompt_id=prompt.id,
                )
                continue
            
            # Create a high-priority research task for this prompt
            await task_queue.create(
                story_id=prompt.story_id,
                stage=TaskStage.RESEARCH,
                priority=10,  # High priority for human requests
                input_data={
                    "detection_data": detection_event.data,
                    "human_prompt_id": prompt.id,
                    "human_prompt_text": prompt.prompt_text,
                },
            )
            
            logger.info(
                "Created research task for human prompt",
                story_id=str(prompt.story_id),
                prompt_id=prompt.id,
                prompt_text=prompt.prompt_text[:50] + "..." if len(prompt.prompt_text) > 50 else prompt.prompt_text,
            )
            
            count += 1
        
        return count

    async def run(self) -> None:
        """Main Chief loop."""
        await self.register()
        self._running = True
        
        logger.info("Chief started", agent_id=str(self.agent_id))
        
        while self._running:
            try:
                # Process human prompts FIRST (highest priority)
                prompt_count = await self.process_human_prompts()
                if prompt_count > 0:
                    logger.info(f"Processed {prompt_count} human prompts")
                
                # Process new detections
                new_count = await self.process_new_detections()
                if new_count > 0:
                    logger.info(f"Created {new_count} new story pipelines")
                
                # Advance stories through pipeline
                advanced_count = await self.advance_stories()
                if advanced_count > 0:
                    logger.info(f"Advanced {advanced_count} stories")
                
                # Recover stalled work
                recovered_count = await self.recover_stalled_tasks()
                if recovered_count > 0:
                    logger.warning(f"Recovered {recovered_count} stalled tasks")
                
                # Send heartbeat
                await self.heartbeat()
                
                # Wait before next cycle
                await asyncio.sleep(settings.task_poll_interval_seconds)
                
            except Exception as e:
                logger.error("Chief loop error", error=str(e), exc_info=True)
                await asyncio.sleep(5)
