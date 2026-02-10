"""Controlled E2E verification for the Editor flow."""
import asyncio
import json
import uuid
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import db, event_store, task_queue, TaskStage, TaskStatus
from chief.orchestrator import Chief
from agents.reporter import ReporterAgent
from agents.editor import EditorAgent
from config.logging import configure_logging, get_logger

logger = get_logger(__name__)

async def verify_pipeline():
    configure_logging()
    await db.connect()
    
    story_id = uuid.uuid4()
    print(f"\n🚀 Starting E2E Verification | Story ID: {story_id}")
    
    # 1. DETECT
    print("\n--- [STAGE 1: DETECTION] ---")
    await event_store.append(
        story_id=story_id,
        event_type="story.detected",
        data={
            "title": "Quantum Computing Breakthrough in Silicon Valley",
            "url": "https://tech.example.com/quantum",
            "summary": "Scientists have achieved stable qubits at room temperature using a new silicon-based approach, potentially accelerating quantum adoption.",
            "score": 0.9,
            "source": "manual_e2e"
        }
    )
    print("✅ Story detection event injected.")
    
    # Instance agents
    chief = Chief()
    reporter = ReporterAgent()
    editor = EditorAgent()
    
    # Register agents (simulated)
    chief.agent_id = uuid.uuid4()
    reporter.agent_id = uuid.uuid4()
    editor.agent_id = uuid.uuid4()
    
    # 2. CHIEF: DETECT -> RESEARCH
    print("\n--- [STAGE 2: CHIEF ORCHESTRATION (RESEARCH)] ---")
    await chief.process_new_detections()
    
    tasks = await task_queue.get_story_tasks(story_id)
    research_task = next((t for t in tasks if t.stage == TaskStage.RESEARCH), None)
    if research_task:
        print(f"✅ Research task created: {research_task.id}")
    else:
        print("❌ Research task NOT created!")
        return

    # 3. REPORTER: RESEARCH
    print("\n--- [STAGE 3: REPORTER RESEARCH] ---")
    # We'll use the actual agent logic but mock the search to be fast/cheap
    from unittest.mock import AsyncMock, patch
    with patch("ingestion.search_service.search") as mock_search, \
         patch("ingestion.entity_extractor.extract") as mock_extract, \
         patch("ingestion.embeddings.embedding_service.embed") as mock_embed:
        
        mock_search.return_value = [] # Fast return
        mock_extract.return_value = []
        mock_embed.return_value = [0.1] * 384
        
        # Claim and process
        # We manually claim to avoid background polling issues
        async with db.acquire() as conn:
            await conn.execute(
                "UPDATE story_tasks SET assigned_agent = $1, status = 'active', started_at = now() WHERE id = $2",
                reporter.agent_id, research_task.id
            )
        
        # Create a fresh task object from DB for the agent
        task = await task_queue.get_task(research_task.id)
        await reporter.process_task(task)
        print("✅ Reporter research completed.")

    # 4. CHIEF: RESEARCH -> DRAFT
    print("\n--- [STAGE 4: CHIEF ORCHESTRATION (DRAFT)] ---")
    await chief.advance_stories()
    
    tasks = await task_queue.get_story_tasks(story_id)
    draft_task = next((t for t in tasks if t.stage == TaskStage.DRAFT), None)
    if draft_task:
        print(f"✅ Draft task created: {draft_task.id}")
    else:
        print("❌ Draft task NOT created!")
        return

    # 5. REPORTER: DRAFT
    print("\n--- [STAGE 5: REPORTER DRAFTING] ---")
    # Mock ChatService for speed/cost
    with patch("agents.llm.ChatService.generate") as mock_gen:
        mock_gen.return_value = "# Quantum Revolution\n\nThe silicon valley team has achieved room temperature stability..."
        
        async with db.acquire() as conn:
            await conn.execute(
                "UPDATE story_tasks SET assigned_agent = $1, status = 'active', started_at = now() WHERE id = $2",
                reporter.agent_id, draft_task.id
            )
        
        task = await task_queue.get_task(draft_task.id)
        await reporter.process_task(task)
        print("✅ Reporter draft completed.")

    # 6. CHIEF: DRAFT -> REVIEW (Editor)
    print("\n--- [STAGE 6: CHIEF ORCHESTRATION (REVIEW)] ---")
    await chief.advance_stories()
    
    tasks = await task_queue.get_story_tasks(story_id)
    review_task = next((t for t in tasks if t.stage == TaskStage.REVIEW), None)
    if review_task:
        print(f"✅ Review task created: {review_task.id}")
    else:
        print("❌ Review task NOT created!")
        return

    # 7. EDITOR: REVIEW
    print("\n--- [STAGE 7: EDITOR REVIEW] ---")
    # Mock ChatService/Search for speed
    with patch("agents.llm.ChatService.generate") as mock_gen, \
         patch("ingestion.search_fallback.FallbackSearch.search", new_callable=AsyncMock) as mock_search:
        
        mock_search.return_value = []
        
        # Mock analysis then claim verification (2 claims)
        mock_gen.side_effect = [
            json.dumps({"score": 0.9, "claims": ["c1", "c2"], "tone": "Objective", "style_issues": [], "grammar_issues": []}), # analyze
            json.dumps({"supported": True, "reason": "Consistent with search"}), # verify claim 1
            json.dumps({"supported": True, "reason": "Consistent with search"}), # verify claim 2
        ]
        
        async with db.acquire() as conn:
            await conn.execute(
                "UPDATE story_tasks SET assigned_agent = $1, status = 'active', started_at = now() WHERE id = $2",
                editor.agent_id, review_task.id
            )
            
        task = await task_queue.get_task(review_task.id)
        await editor.process_task(task)
        print("✅ Editor review completed.")

    # 8. CHIEF: REVIEW -> PUBLISH
    print("\n--- [STAGE 8: CHIEF ORCHESTRATION (PUBLISH)] ---")
    await chief.advance_stories()
    
    tasks = await task_queue.get_story_tasks(story_id)
    publish_task = next((t for t in tasks if t.stage == TaskStage.PUBLISH), None)
    if publish_task:
        print(f"✅ Publish task created: {publish_task.id}")
        
        # Verify article exists
        from db.articles import article_store
        article = await article_store.get_story_article(story_id)
        if article:
            print(f"✅ Final Article Generated: {article.headline}")
        else:
            print("❌ Article record NOT found!")
    else:
        edit_task = next((t for t in tasks if t.stage == TaskStage.EDIT), None)
        if edit_task:
            print("🔶 Rejection Path Taken (Revision Requested)")
            print(f"Feedback: {edit_task.input.get('feedback')}")
        else:
            print("❌ Publish task NOT created!")
        return

    print("\n✨ E2E VERIFICATION SUCCESSFUL! ✨")
    print(f"Full pipeline verified for Story: {story_id}")
    
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(verify_pipeline())
