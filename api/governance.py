"""FastAPI endpoints for governance operations."""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime
from db.articles import article_store
from db.governance import (
    governance_rule_store,
    approval_request_store,
    audit_log_store,
    ApprovalRequest,
    GovernanceRule,
    AuditLogEntry,
)
from governance import governance_engine
from config.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["governance"])


# Request/Response Models

class EvaluateResponse(BaseModel):
    """Response from governance evaluation."""
    article_id: str
    passed: bool
    violations: List[dict]
    requires_approval: bool
    blocked: bool


class ApprovalResponse(BaseModel):
    """Approval request details."""
    id: str
    article_id: str
    requested_at: datetime
    reason: str
    status: str
    rule_violations: Optional[List[dict]] = None


class ApprovalActionRequest(BaseModel):
    """Request to approve/reject."""
    reviewed_by: str = Field(..., description="Name/ID of reviewer")
    notes: Optional[str] = Field(None, description="Optional notes")


# Endpoints

@router.post("/governance/evaluate/{article_id}", response_model=EvaluateResponse)
async def evaluate_article(article_id: UUID):
    """
    Evaluate an article against governance rules.
    
    Returns pass/fail status and any violations.
    """
    # Get article
    article = await article_store.get(article_id)
    if not article:
        raise HTTPException(status_code=404, detail=f"Article {article_id} not found")
    
    # Evaluate
    result = await governance_engine.evaluate_article(article)
    
    # If requires approval, create request
    if result.requires_approval and not result.blocked:
        await governance_engine.request_approval(article, result.violations)
    
    return EvaluateResponse(
        article_id=str(article_id),
        passed=result.passed,
        violations=[
            {
                "rule_name": v.rule_name,
                "rule_type": v.rule_type,
                "severity": v.severity,
                "details": v.details,
            }
            for v in result.violations
        ],
        requires_approval=result.requires_approval,
        blocked=result.blocked,
    )


@router.get("/approvals/pending", response_model=List[ApprovalResponse])
async def get_pending_approvals():
    """Get all pending approval requests."""
    approvals = await approval_request_store.get_pending()
    
    return [
        ApprovalResponse(
            id=str(a.id),
            article_id=str(a.article_id),
            requested_at=a.requested_at,
            reason=a.reason,
            status=a.status,
            rule_violations=a.rule_violations,
        )
        for a in approvals
    ]


@router.post("/approvals/{approval_id}/approve")
async def approve_article(approval_id: UUID, request: ApprovalActionRequest):
    """
    Approve an article for publishing.
    
    - **reviewed_by**: Name or ID of reviewer
    - **notes**: Optional notes
    """
    success = await approval_request_store.approve(
        approval_id,
        reviewed_by=request.reviewed_by,
        notes=request.notes,
    )
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Approval request {approval_id} not found or already processed"
        )
    
    # Log approval
    await audit_log_store.log(
        event_type="approval.granted",
        entity_type="approval",
        entity_id=approval_id,
        details={
            "reviewed_by": request.reviewed_by,
            "notes": request.notes,
        },
        user_id=request.reviewed_by,
        severity="info",
    )
    
    logger.info(
        "Article approved",
        approval_id=str(approval_id),
        reviewed_by=request.reviewed_by,
    )
    
    return {
        "approval_id": str(approval_id),
        "status": "approved",
        "reviewed_by": request.reviewed_by,
    }


@router.post("/approvals/{approval_id}/reject")
async def reject_article(approval_id: UUID, request: ApprovalActionRequest):
    """
    Reject an article.
    
    - **reviewed_by**: Name or ID of reviewer
    - **notes**: Optional reason for rejection
    """
    success = await approval_request_store.reject(
        approval_id,
        reviewed_by=request.reviewed_by,
        notes=request.notes,
    )
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Approval request {approval_id} not found or already processed"
        )
    
    # Log rejection
    await audit_log_store.log(
        event_type="approval.rejected",
        entity_type="approval",
        entity_id=approval_id,
        details={
            "reviewed_by": request.reviewed_by,
            "notes": request.notes,
        },
        user_id=request.reviewed_by,
        severity="warning",
    )
    
    logger.info(
        "Article rejected",
        approval_id=str(approval_id),
        reviewed_by=request.reviewed_by,
    )
    
    return {
        "approval_id": str(approval_id),
        "status": "rejected",
        "reviewed_by": request.reviewed_by,
    }


@router.get("/audit/log")
async def get_audit_log(
    limit: int = Query(100, ge=1, le=500),
    severity: Optional[str] = Query(None, description="Filter by severity"),
):
    """
    Get audit log entries.
    
    - **limit**: Max entries (1-500)
    - **severity**: Optional filter (info, warning, error, critical)
    """
    entries = await audit_log_store.get_recent(limit=limit, severity=severity)
    
    return {
        "entries": [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "entity_type": e.entity_type,
                "entity_id": str(e.entity_id) if e.entity_id else None,
                "details": e.details,
                "user_id": e.user_id,
                "severity": e.severity,
                "timestamp": e.timestamp,
            }
            for e in entries
        ],
        "count": len(entries),
    }


@router.get("/governance/rules")
async def get_governance_rules():
    """Get all enabled governance rules."""
    rules = await governance_rule_store.get_enabled()
    
    return {
        "rules": [
            {
                "id": str(r.id),
                "rule_type": r.rule_type,
                "name": r.name,
                "description": r.description,
                "condition": r.condition,
                "action": r.action,
                "priority": r.priority,
                "enabled": r.enabled,
            }
            for r in rules
        ],
        "count": len(rules),
    }
