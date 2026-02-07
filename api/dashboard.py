"""Dashboard routes for News Town monitoring."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Any
from datetime import datetime, timedelta
from db.connection import db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


async def get_dashboard_stats() -> Dict[str, Any]:
    """Gather all dashboard statistics."""
    
    # Article stats
    total_articles = await db.fetchval("SELECT COUNT(*) FROM articles")
    articles_today = await db.fetchval(
        "SELECT COUNT(*) FROM articles WHERE published_at > NOW() - INTERVAL '24 hours'"
    )
    
    # Story stats  
    total_stories = await db.fetchval("SELECT COUNT(DISTINCT story_id) FROM story_events")
    
    # Publication stats
    total_publications = await db.fetchval("SELECT COUNT(*) FROM publications WHERE status = 'published'")
    rss_pubs = await db.fetchval("SELECT COUNT(*) FROM publications WHERE channel = 'rss' AND status = 'published'")
    email_pubs = await db.fetchval("SELECT COUNT(*) FROM publications WHERE channel = 'email' AND status = 'published'")
    
    # Governance stats
    total_rules = await db.fetchval("SELECT COUNT(*) FROM governance_rules")
    enabled_rules = await db.fetchval("SELECT COUNT(*) FROM governance_rules WHERE enabled = true")
    pending_approvals = await db.fetchval("SELECT COUNT(*) FROM approval_requests WHERE status = 'pending'")
    
    # Recent articles
    recent_articles = await db.fetch(
        """
        SELECT id, headline, byline, published_at
        FROM articles
        ORDER BY published_at DESC
        LIMIT 10
        """
    )
    
    # Recent activity (from audit log)
    recent_activity = await db.fetch(
        """
        SELECT event_type, severity, timestamp, details
        FROM audit_log
        ORDER BY timestamp DESC
        LIMIT 20
        """
    )
    
    # Agent activity (from story events)
    agent_activity = await db.fetch(
        """
        SELECT agent_id, event_type, occurred_at
        FROM story_events
        WHERE occurred_at > NOW() - INTERVAL '1 hour'
        ORDER BY occurred_at DESC
        LIMIT 50
        """
    )
    
    return {
        "stats": {
            "total_articles": total_articles or 0,
            "articles_today": articles_today or 0,
            "total_stories": total_stories or 0,
            "total_publications": total_publications or 0,
            "rss_publications": rss_pubs or 0,
            "email_publications": email_pubs or 0,
            "total_rules": total_rules or 0,
            "enabled_rules": enabled_rules or 0,
            "pending_approvals": pending_approvals or 0,
        },
        "recent_articles": [dict(row) for row in recent_articles] if recent_articles else [],
        "recent_activity": [dict(row) for row in recent_activity] if recent_activity else [],
        "agent_activity": [dict(row) for row in agent_activity] if agent_activity else [],
        "last_updated": datetime.now().isoformat(),
    }


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render main dashboard page."""
    stats = await get_dashboard_stats()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, **stats}
    )


@router.get("/api/stats")
async def live_stats():
    """API endpoint for live stats (for auto-refresh)."""
    return await get_dashboard_stats()
