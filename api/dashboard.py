"""Dashboard routes for News Town monitoring."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Any
from datetime import datetime, timedelta
from api.auth_routes import get_current_user
from fastapi import Depends
from db.connection import db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


async def get_dashboard_stats() -> Dict[str, Any]:
    """Gather all dashboard statistics."""
    
    async with db.acquire() as conn:
        # Article stats
        total_articles = await conn.fetchval("SELECT COUNT(*) FROM articles")
        articles_today = await conn.fetchval(
            "SELECT COUNT(*) FROM articles WHERE published_at > NOW() - INTERVAL '24 hours'"
        )
        
        # Story stats  
        total_stories = await conn.fetchval("SELECT COUNT(DISTINCT story_id) FROM story_events")
        active_pipelines = await conn.fetchval(
            "SELECT COUNT(DISTINCT story_id) FROM story_tasks WHERE status IN ('pending', 'active')"
        )
        
        # Publication stats
        total_publications = await conn.fetchval("SELECT COUNT(*) FROM publications WHERE status = 'published'")
        rss_pubs = await conn.fetchval("SELECT COUNT(*) FROM publications WHERE channel = 'rss' AND status = 'published'")
        
        # Governance stats
        pending_approvals = await conn.fetchval("SELECT COUNT(*) FROM approval_requests WHERE status = 'pending'")
        
        # Recent articles
        recent_articles = await conn.fetch(
            """
            SELECT id, headline, byline, published_at
            FROM articles
            ORDER BY published_at DESC
            LIMIT 10
            """
        )
        
        # Recent activity (from audit log)
        recent_activity = await conn.fetch(
            """
            SELECT event_type, severity, timestamp, details
            FROM audit_log
            ORDER BY timestamp DESC
            LIMIT 20
            """
        )
        
        # Agent activity
        agent_activity = await conn.fetch(
            """
            SELECT agent_id, event_type, created_at as occurred_at
            FROM story_events
            WHERE created_at > NOW() - INTERVAL '1 hour'
            ORDER BY created_at DESC
            LIMIT 50
            """
        )
    
    return {
        "stats": {
            "total_articles": total_articles or 0,
            "articles_today": articles_today or 0,
            "total_stories": total_stories or 0,
            "active_pipelines": active_pipelines or 0,
            "total_publications": total_publications or 0,
            "rss_publications": rss_pubs or 0,
            "pending_approvals": pending_approvals or 0,
        },
        "recent_articles": [dict(row) for row in recent_articles] if recent_articles else [],
        "recent_activity": [dict(row) for row in recent_activity] if recent_activity else [],
        "agent_activity": [dict(row) for row in agent_activity] if agent_activity else [],
        "last_updated": datetime.now().isoformat(),
    }


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, user: dict = Depends(get_current_user)):
    """Render main dashboard page."""
    stats = await get_dashboard_stats()
    return templates.TemplateResponse(
        "dashboard_v2.html",
        {"request": request, "user": user, **stats}
    )


@router.get("/api/stats")
async def live_stats(user: dict = Depends(get_current_user)):
    """API endpoint for live stats."""
    return await get_dashboard_stats()


@router.get("/api/stories")
async def list_stories(limit: int = 50, user: dict = Depends(get_current_user)):
    """Get active story pipelines."""
    rows = await db.fetch("""
        SELECT 
            s.id,
            (SELECT data->>'title' FROM story_events WHERE story_id = s.id AND event_type = 'story.detected' LIMIT 1) as title,
            (SELECT MAX(created_at) FROM story_events WHERE story_id = s.id) as last_activity,
            (SELECT stage FROM story_tasks WHERE story_id = s.id ORDER BY created_at DESC LIMIT 1) as current_stage,
            (SELECT status FROM story_tasks WHERE story_id = s.id ORDER BY created_at DESC LIMIT 1) as status
        FROM (SELECT DISTINCT story_id as id FROM story_events) s
        ORDER BY last_activity DESC
        LIMIT $1
    """, limit)
    return [dict(row) for row in rows]


@router.get("/api/prompts")
async def list_prompts(user: dict = Depends(get_current_user)):
    """Get pending human prompts."""
    from db.human_oversight import human_prompt_store
    prompts = await human_prompt_store.get_pending_prompts()
    return prompts


@router.post("/api/prompts")
async def create_prompt(story_id: str, prompt_text: str, user: dict = Depends(get_current_user)):
    """Submit a new human prompt."""
    from db.human_oversight import human_prompt_store
    from uuid import UUID
    prompt_id = await human_prompt_store.create_prompt(
        story_id=UUID(story_id),
        prompt_text=prompt_text
    )
    return {"status": "success", "prompt_id": prompt_id}


@router.get("/api/sources")
async def list_sources(story_id: str = None, user: dict = Depends(get_current_user)):
    """Get sources for a story or all recent sources."""
    if story_id:
        from db.human_oversight import source_store
        from uuid import UUID
        sources = await source_store.get_story_sources(UUID(story_id))
        return sources
    else:
        rows = await db.fetch("SELECT * FROM story_sources ORDER BY added_at DESC LIMIT 50")
        return [dict(row) for row in rows]
