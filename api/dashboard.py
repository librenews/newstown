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

        # Quality stats overview
        avg_score = await conn.fetchval("SELECT AVG(score) FROM article_reviews")
        avg_v_score = await conn.fetchval("SELECT AVG(verification_score) FROM article_reviews")
        avg_s_score = await conn.fetchval("SELECT AVG(style_score) FROM article_reviews")
    
    return {
        "stats": {
            "total_articles": total_articles or 0,
            "articles_today": articles_today or 0,
            "total_stories": total_stories or 0,
            "active_pipelines": active_pipelines or 0,
            "total_publications": total_publications or 0,
            "rss_publications": rss_pubs or 0,
            "pending_approvals": pending_approvals or 0,
            "avg_quality_score": round(avg_score or 0, 2),
            "avg_verification": round(avg_v_score or 0, 2),
            "avg_style": round(avg_s_score or 0, 2),
        },
        "recent_articles": [dict(row) for row in recent_articles] if recent_articles else [],
        "recent_activity": [dict(row) for row in recent_activity] if recent_activity else [],
        "agent_activity": [dict(row) for row in agent_activity] if agent_activity else [],
        "last_updated": datetime.now().isoformat(),
    }


async def get_extended_quality_stats() -> Dict[str, Any]:
    """Gather detailed newsroom quality analytics."""
    async with db.acquire() as conn:
        # Common violations (we store them in JSON metadata)
        # We'll need to parse this if we want specific counts, 
        # but for now let's get rejection rate
        total_reviews = await conn.fetchval("SELECT COUNT(*) FROM article_reviews")
        rejected_reviews = await conn.fetchval("SELECT COUNT(*) FROM article_reviews WHERE decision = 'REJECT'")
        rejection_rate = (rejected_reviews / total_reviews * 100) if total_reviews > 0 else 0

        # Revision throughput
        # Average number of revisions for completed stories
        avg_revisions = await conn.fetchval("""
            SELECT AVG(rev_count) FROM (
                SELECT story_id, COUNT(*) as rev_count 
                FROM story_tasks 
                WHERE stage = 'edit' 
                GROUP BY story_id
            ) sub
        """)

        # Quality trends (last 7 days)
        trends = await conn.fetch("""
            SELECT 
                DATE_TRUNC('day', created_at) as day,
                AVG(score) as avg_score,
                COUNT(*) as volume
            FROM article_reviews
            WHERE created_at > NOW() - INTERVAL '7 days'
            GROUP BY day
            ORDER BY day ASC
        """)

    return {
        "rejection_rate": round(rejection_rate, 1),
        "total_reviews": total_reviews,
        "avg_revisions": round(avg_revisions or 0, 1),
        "trends": [dict(row) for row in trends]
    }


@router.get("/api/quality")
async def quality_metrics(user: dict = Depends(get_current_user)):
    """API endpoint for detailed quality analytics."""
    return await get_extended_quality_stats()


@router.get("/api/performance")
async def performance_metrics(user: dict = Depends(get_current_user)):
    """API endpoint for agent performance tracking."""
    # Simplified performance metric: success vs failure in tasks
    rows = await db.fetch("""
        SELECT 
            role,
            COUNT(*) FILTER (WHERE status = 'completed') as successes,
            COUNT(*) FILTER (WHERE status = 'failed') as failures
        FROM agents a
        JOIN story_tasks t ON t.assigned_agent = a.id
        GROUP BY role
    """)
    return [dict(row) for row in rows]


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
