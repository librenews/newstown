"""Governance data models and stores for Phase 3."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel
from db.connection import db


class GovernanceRule(BaseModel):
    """Publishing governance rule."""
    id: UUID
    rule_type: str  # 'source_count', 'approval_required', 'topic_restriction', 'moderation'
    name: str
    description: Optional[str] = None
    condition: Dict[str, Any]  # rule parameters
    action: str  # 'block', 'require_approval', 'flag', 'warn'
    priority: int = 0
    enabled: bool = True
    created_at: datetime
    updated_at: datetime


class ApprovalRequest(BaseModel):
    """Human approval request."""
    id: UUID
    article_id: UUID
    requested_at: datetime
    reason: str
    rule_violations: Optional[List[Dict[str, Any]]] = None
    status: str = "pending"  # 'pending', 'approved', 'rejected'
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewer_notes: Optional[str] = None
    auto_approved: bool = False


class AuditLogEntry(BaseModel):
    """Audit log entry."""
    id: UUID
    event_type: str
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None
    details: Dict[str, Any]
    user_id: Optional[str] = None
    severity: str = "info"  # 'info', 'warning', 'error', 'critical'
    timestamp: datetime


class GovernanceRuleStore:
    """Manage governance rules."""
    
    async def create(
        self,
        rule_type: str,
        name: str,
        condition: Dict[str, Any],
        action: str,
        description: Optional[str] = None,
        priority: int = 0,
    ) -> UUID:
        """Create a governance rule."""
        query = """
            INSERT INTO governance_rules (rule_type, name, description, condition, action, priority)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
        """
        result = await db.fetchrow(
            query,
            rule_type,
            name,
            description,
            condition,
            action,
            priority,
        )
        return result["id"]
    
    async def get_enabled(self) -> List[GovernanceRule]:
        """Get all enabled rules, ordered by priority."""
        query = """
            SELECT * FROM governance_rules
            WHERE enabled = true
            ORDER BY priority DESC, created_at ASC
        """
        rows = await db.fetch(query)
        return [GovernanceRule(**dict(row)) for row in rows]
    
    async def disable(self, rule_id: UUID) -> bool:
        """Disable a rule."""
        query = """
            UPDATE governance_rules
            SET enabled = false, updated_at = NOW()
            WHERE id = $1
            RETURNING id
        """
        result = await db.fetchrow(query, rule_id)
        return result is not None


class ApprovalRequestStore:
    """Manage approval requests."""
    
    async def create(
        self,
        article_id: UUID,
        reason: str,
        rule_violations: Optional[List[Dict[str, Any]]] = None,
    ) -> UUID:
        """Create an approval request."""
        query = """
            INSERT INTO approval_requests (article_id, reason, rule_violations)
            VALUES ($1, $2, $3)
            RETURNING id
        """
        result = await db.fetchrow(query, article_id, reason, rule_violations or [])
        return result["id"]
    
    async def get_pending(self) -> List[ApprovalRequest]:
        """Get all pending approval requests."""
        query = """
            SELECT * FROM approval_requests
            WHERE status = 'pending'
            ORDER BY requested_at ASC
        """
        rows = await db.fetch(query)
        return [ApprovalRequest(**dict(row)) for row in rows]
    
    async def approve(
        self,
        request_id: UUID,
        reviewed_by: str,
        notes: Optional[str] = None,
    ) -> bool:
        """Approve a request."""
        query = """
            UPDATE approval_requests
            SET status = 'approved',
                reviewed_by = $2,
                reviewed_at = NOW(),
                reviewer_notes = $3
            WHERE id = $1 AND status = 'pending'
            RETURNING id
        """
        result = await db.fetchrow(query, request_id, reviewed_by, notes)
        return result is not None
    
    async def reject(
        self,
        request_id: UUID,
        reviewed_by: str,
        notes: Optional[str] = None,
    ) -> bool:
        """Reject a request."""
        query = """
            UPDATE approval_requests
            SET status = 'rejected',
                reviewed_by = $2,
                reviewed_at = NOW(),
                reviewer_notes = $3
            WHERE id = $1 AND status = 'pending'
            RETURNING id
        """
        result = await db.fetchrow(query, request_id, reviewed_by, notes)
        return result is not None


class AuditLogStore:
    """Manage audit log."""
    
    async def log(
        self,
        event_type: str,
        details: Dict[str, Any],
        entity_type: Optional[str] = None,
        entity_id: Optional[UUID] = None,
        user_id: Optional[str] = None,
        severity: str = "info",
    ) -> UUID:
        """Create an audit log entry."""
        import json
        
        query = """
            INSERT INTO audit_log (event_type, entity_type, entity_id, details, user_id, severity)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
        """
        result = await db.fetchrow(
            query,
            event_type,
            entity_type,
            entity_id,
            json.dumps(details),  # Convert dict to JSON string
            user_id,
            severity,
        )
        return result["id"]
    
    async def get_recent(
        self,
        limit: int = 100,
        severity: Optional[str] = None,
    ) -> List[AuditLogEntry]:
        """Get recent audit log entries."""
        if severity:
            query = """
                SELECT * FROM audit_log
                WHERE severity = $1
                ORDER BY timestamp DESC
                LIMIT $2
            """
            rows = await db.fetch(query, severity, limit)
        else:
            query = """
                SELECT * FROM audit_log
                ORDER BY timestamp DESC
                LIMIT $1
            """
            rows = await db.fetch(query, limit)
        
        return [AuditLogEntry(**dict(row)) for row in rows]
    
    async def get_by_entity(
        self,
        entity_type: str,
        entity_id: UUID,
    ) -> List[AuditLogEntry]:
        """Get audit log for a specific entity."""
        query = """
            SELECT * FROM audit_log
            WHERE entity_type = $1 AND entity_id = $2
            ORDER BY timestamp DESC
        """
        rows = await db.fetch(query, entity_type, entity_id)
        return [AuditLogEntry(**dict(row)) for row in rows]


# Global instances
governance_rule_store = GovernanceRuleStore()
approval_request_store = ApprovalRequestStore()
audit_log_store = AuditLogStore()
