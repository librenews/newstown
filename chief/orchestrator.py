"""Chief agent - central orchestrator for News Town."""
import asyncio
import json
from typing import Any
from uuid import UUID
from agents.base import BaseAgent, AgentRole
from db import db, event_store, task_queue, Task, TaskStage
from db.articles import article_store
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
        count = 0
        count += await self.assign_research_to_draft()
        count += await self.assign_draft_to_review()
        count += await self.process_reviews()
        return count

    async def assign_research_to_draft(self) -> int:
        """Create draft tasks for stories with completed research."""
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

    async def assign_draft_to_review(self) -> int:
        """Create review tasks for stories with completed drafts/revisions."""
        # Find stories with completed draft OR completed revision, but NO active review
        rows = await db.fetch("""
            WITH latest_drafts AS (
                SELECT DISTINCT story_id, MAX(created_at) as last_draft_time
                FROM story_events
                WHERE event_type IN ('draft.completed', 'revision.completed')
                GROUP BY story_id
            ),
            active_reviews AS (
                SELECT DISTINCT story_id
                FROM story_tasks
                WHERE stage = 'review' AND status IN ('pending', 'active')
            ),
            completed_reviews AS (
                SELECT story_id, MAX(created_at) as last_review_time
                FROM story_tasks
                WHERE stage = 'review' AND status = 'completed'
                GROUP BY story_id
            )
            SELECT d.story_id
            FROM latest_drafts d
            LEFT JOIN active_reviews a ON d.story_id = a.story_id
            LEFT JOIN completed_reviews c ON d.story_id = c.story_id
            WHERE a.story_id IS NULL
              AND (c.story_id IS NULL OR d.last_draft_time > c.last_review_time)
            LIMIT 10
        """)
        
        count = 0
        for row in rows:
            story_id = row["story_id"]
            
            # Get latest draft content
            events = await event_store.get_story_events(story_id)
            draft_event = next(
                (e for e in reversed(events) if e.event_type in ["draft.completed", "revision.completed"]),
                None
            )
            
            # Also get task output just in case (the event usually contains metadata, task output contains content)
            # Wait, Reporter.draft returns the content in the output.
            # And BaseAgent logs task.completed.draft with output.
            # So we should look for task.completed.draft or task.completed.edit (for revisions)
            
            task_event = next(
                (e for e in reversed(events) if e.event_type in ["task.completed.draft", "task.completed.edit"]),
                None
            )
            
            if not task_event:
                continue
            
            draft_content = task_event.data.get("output", {})
            
            # Create review task
            await task_queue.create(
                story_id=story_id,
                stage=TaskStage.REVIEW,
                priority=6,
                input_data={"draft": draft_content},
            )
            
            logger.info("Review task created", story_id=str(story_id))
            count += 1
            
        return count

    async def process_reviews(self) -> int:
        """Process completed reviews (Publish or Request Revision)."""
        # Find completed reviews that haven't been acted upon
        rows = await db.fetch("""
            WITH completed_reviews AS (
                SELECT *
                FROM story_tasks
                WHERE stage = 'review' AND status = 'completed'
                  AND completed_at > NOW() - INTERVAL '1 hour'
            )
            SELECT * FROM completed_reviews
            LIMIT 10
        """)
        
        count = 0
        for row in rows:
            task_id = row["id"]
            story_id = row["story_id"]
            output = json.loads(row["output"]) if isinstance(row["output"], str) else row["output"]
            task_input = json.loads(row["input"]) if isinstance(row["input"], str) else row["input"]
            
            decision = output.get("decision")
            
            if decision == "APPROVE":
                # ... existing approval logic ...
                # Check if publish task already exists
                publish_exists = await db.fetchval(
                    "SELECT 1 FROM story_tasks WHERE story_id = $1 AND stage = 'publish'",
                    story_id
                )
                if not publish_exists:
                    draft = task_input.get("draft", {})
                    if not draft:
                        logger.error("Approved review missing draft content", task_id=str(task_id))
                        continue

                    article_body = draft.get("article", "")
                    headline = draft.get("headline", "Untitled")
                    
                    try:
                        article_id = await article_store.create_article(
                            story_id=story_id,
                            headline=headline,
                            body=article_body,
                            summary=None,
                            byline="News Town Reporter",
                        )
                        
                        await task_queue.create(
                            story_id=story_id,
                            stage=TaskStage.PUBLISH,
                            priority=8,
                            input_data={
                                "article_id": str(article_id),
                                "channels": ["rss"]
                            }
                        )
                        logger.info("Publish task created", story_id=str(story_id))
                        count += 1
                        
                    except Exception as e:
                        logger.error("Failed to create article for publishing", error=str(e))
            
            elif decision == "REJECT":
                 # Check how many revisions we've already done
                 revision_count = await db.fetchval("""
                     SELECT COUNT(*) FROM story_tasks 
                     WHERE story_id = $1 AND stage = 'edit'
                 """, story_id)
                 
                 if revision_count >= 3:
                     logger.warning(
                         "Max revisions reached, killing story pipeline",
                         story_id=str(story_id),
                         revisions=revision_count
                     )
                     await self.log_event(
                         story_id,
                         "story.killed",
                         {"reason": "too_many_revisions", "last_feedback": output.get("feedback")}
                     )
                     continue

                 # Create revision task (EDIT stage)
                 # Reporter role will pick this up due to schema update
                 latest_task = await db.fetchrow(
                     "SELECT * FROM story_tasks WHERE story_id = $1 ORDER BY created_at DESC LIMIT 1",
                     story_id
                 )
                 
                 if latest_task and latest_task["id"] == task_id:
                     draft_content = task_input.get("draft", {})
                     
                     await task_queue.create(
                        story_id=story_id,
                        stage=TaskStage.EDIT,
                        priority=7,
                        input_data={
                            "draft": draft_content,
                            "feedback": output.get("feedback", "No feedback provided."),
                            "revision_number": revision_count + 1
                        }
                     )
                     logger.info(
                         "Revision task created", 
                         story_id=str(story_id), 
                         rev_num=revision_count + 1
                     )
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
