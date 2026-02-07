"""FastAPI endpoints for publishing operations."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from db.articles import article_store
from db.publications import publication_store, schedule_store, Publication
from publishing.rss import rss_publisher
from publishing.email import email_publisher
from config.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["publishing"])


# Request/Response Models

class PublishRequest(BaseModel):
    """Request to publish an article."""
    channels: List[str] = Field(..., description="Channels to publish to")
    recipients: Optional[List[str]] = Field(None, description="Email recipients (for email channel)")


class ScheduleRequest(BaseModel):
    """Request to schedule a publication."""
    channels: List[str] = Field(..., description="Channels to publish to")
    scheduled_for: datetime = Field(..., description="When to publish (ISO 8601)")


class PublishResponse(BaseModel):
    """Response from publish operation."""
    article_id: str
    channels: List[str]
    results: dict
    success_count: int


class ScheduleResponse(BaseModel):
    """Response from schedule operation."""
    schedule_id: str
    article_id: str
    channels: List[str]
    scheduled_for: datetime


# Endpoints

@router.post("/articles/{article_id}/publish", response_model=PublishResponse)
async def publish_article(article_id: UUID, request: PublishRequest):
    """
    Publish an article to specified channels.
    
    - **channels**: List of channels (rss, email)
    - **recipients**: Email addresses (required for email channel)
    """
    # Get article
    article = await article_store.get(article_id)
    if not article:
        raise HTTPException(status_code=404, detail=f"Article {article_id} not found")
    
    # Publish to each channel
    results = {}
    
    for channel in request.channels:
        try:
            if channel == "rss":
                result = await rss_publisher.publish(article)
                results[channel] = {
                    "success": result.success,
                    "publication_id": str(result.publication_id) if result.publication_id else None,
                    "error": result.error,
                }
            
            elif channel == "email":
                if not request.recipients:
                    results[channel] = {
                        "success": False,
                        "error": "Recipients required for email channel"
                    }
                    continue
                
                if email_publisher:
                    batch_results = await email_publisher.send_batch(article, request.recipients)
                    success_count = sum(1 for r in batch_results.values() if r.success)
                    results[channel] = {
                        "success": success_count > 0,
                        "sent": success_count,
                        "total": len(request.recipients),
                    }
                else:
                    results[channel] = {
                        "success": False,
                        "error": "Email publisher not configured"
                    }
            
            else:
                results[channel] = {
                    "success": False,
                    "error": f"Unknown channel: {channel}"
                }
                
        except Exception as e:
            logger.error(f"Publishing to {channel} failed", error=str(e))
            results[channel] = {
                "success": False,
                "error": str(e)
            }
    
    success_count = sum(1 for r in results.values() if r.get("success"))
    
    return PublishResponse(
        article_id=str(article_id),
        channels=request.channels,
        results=results,
        success_count=success_count,
    )


@router.post("/articles/{article_id}/schedule", response_model=ScheduleResponse)
async def schedule_publication(article_id: UUID, request: ScheduleRequest):
    """
    Schedule an article for future publication.
    
    - **channels**: List of channels
    - **scheduled_for**: ISO 8601 datetime
    """
    # Verify article exists
    article = await article_store.get(article_id)
    if not article:
        raise HTTPException(status_code=404, detail=f"Article {article_id} not found")
    
    # Validate scheduled time is in future
    if request.scheduled_for <= datetime.now(request.scheduled_for.tzinfo):
        raise HTTPException(status_code=400, detail="scheduled_for must be in the future")
    
    # Create schedule
    schedule_id = await schedule_store.create(
        article_id=article_id,
        channels=request.channels,
        scheduled_for=request.scheduled_for,
    )
    
    logger.info(
        "Publication scheduled",
        article_id=str(article_id),
        schedule_id=str(schedule_id),
        scheduled_for=request.scheduled_for,
    )
    
    return ScheduleResponse(
        schedule_id=str(schedule_id),
        article_id=str(article_id),
        channels=request.channels,
        scheduled_for=request.scheduled_for,
    )


@router.get("/publications")
async def list_publications(
    channel: Optional[str] = Query(None, description="Filter by channel"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
):
    """
    List recent publications.
    
    - **channel**: Optional channel filter (rss, email)
    - **limit**: Max results (1-100)
    """
    if channel:
        publications = await publication_store.list_by_channel(channel, limit=limit)
    else:
        # Would need to implement list_all in store
        raise HTTPException(status_code=400, detail="channel parameter required")
    
    return {
        "publications": [
            {
                "id": str(p.id),
                "article_id": str(p.article_id),
                "channel": p.channel,
                "published_at": p.published_at,
                "status": p.status,
            }
            for p in publications
        ],
        "count": len(publications),
    }


@router.delete("/publications/{publication_id}")
async def retract_publication(publication_id: UUID):
    """
    Retract a publication.
    
    Note: Email retractions cannot recall sent messages.
    """
    # Get publication
    publication = await publication_store.get(publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail=f"Publication {publication_id} not found")
    
    # Retract
    success = await publication_store.retract(
        publication_id,
        reason="Retracted via API",
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Retraction failed")
    
    logger.info("Publication retracted", publication_id=str(publication_id))
    
    return {
        "publication_id": str(publication_id),
        "status": "retracted",
    }


@router.get("/feed.rss")
async def get_rss_feed():
    """
    Get RSS 2.0 feed XML.
    
    Returns recent published articles as RSS feed.
    """
    from fastapi.responses import Response
    
    rss_xml = await rss_publisher.generate_feed()
    
    return Response(
        content=rss_xml,
        media_type="application/rss+xml",
    )
