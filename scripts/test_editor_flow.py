"""Integration test for Editor flow."""
import asyncio
import json
import uuid
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import db, event_store, task_queue, TaskStage
from config.logging import configure_logging, get_logger

logger = get_logger(__name__)

async def run_test():
    configure_logging()
    await db.connect()
    
    story_id = uuid.uuid4()
    print(f"Starting test with Story ID: {story_id}")
    
    # 1. Inject detection event
    await event_store.append(
        story_id=story_id,
        event_type="story.detected",
        data={
            "title": "New AI Model Demonstrates Reasoning Capabilities",
            "url": "https://example.com/ai-reasoning",
            "summary": "Researchers have released a new AI model that shows advanced reasoning steps before answering, improving accuracy on complex tasks.",
            "score": 8.5, # High enough to be picked up
            "source": "manual_test"
        }
    )
    print("Injected story.detected event")
    
    # Poll for progress
    start_time = datetime.now()
    stages_completed = {
        "research": False,
        "draft": False,
        "review": False,
        "publish": False,
        "revise": False
    }
    
    while (datetime.now() - start_time).seconds < 120: # 2 minute timeout
        events = await event_store.get_story_events(story_id)
        
        # Check research
        if not stages_completed["research"]:
            if any(e.event_type == "task.completed.research" for e in events):
                print("Research completed!")
                stages_completed["research"] = True
                
        # Check draft
        if not stages_completed["draft"]:
            if any(e.event_type == "task.completed.draft" for e in events):
                print("Draft completed!")
                stages_completed["draft"] = True
                
        # Check review
        if not stages_completed["review"]:
            review_event = next((e for e in events if e.event_type == "task.completed.review"), None)
            if review_event:
                print("Review completed!")
                output = review_event.data.get("output", {})
                print(f"Decision: {output.get('decision')}")
                print(f"Score: {output.get('score')}")
                stages_completed["review"] = True
                
                if output.get("decision") == "APPROVE":
                    stages_completed["revise"] = True # No revision needed
                
        # Check publish task creation (via story_tasks table check)
        if stages_completed["review"] and not stages_completed["publish"]:
            tasks = await task_queue.get_story_tasks(story_id)
            if any(t.stage == TaskStage.PUBLISH for t in tasks):
                print("Publish task created!")
                stages_completed["publish"] = True
                break # Success!
                
            # Check for Revision task
            if any(t.stage == TaskStage.EDIT for t in tasks):
                print("Revision task created!")
                stages_completed["revise"] = True
                stages_completed["publish"] = True # Consider test done for now (path taken)
                break

        await asyncio.sleep(5)
        
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(run_test())
