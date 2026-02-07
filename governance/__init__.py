"""Governance engine for News Town - Phase 3."""
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from db.articles import Article
from db.governance import (
    governance_rule_store,
    approval_request_store,
    audit_log_store,
    GovernanceRule,
)
from config.settings import settings
from config.logging import get_logger

logger = get_logger(__name__)


class RuleViolation:
    """Represents a rule violation."""
    
    def __init__(
        self,
        rule_id: UUID,
        rule_name: str,
        rule_type: str,
        severity: str,
        details: str,
    ):
        self.rule_id = rule_id
        self.rule_name = rule_name
        self.rule_type = rule_type
        self.severity = severity
        self.details = details


class GovernanceResult:
    """Result of governance evaluation."""
    
    def __init__(
        self,
        passed: bool,
        violations: List[RuleViolation],
        requires_approval: bool = False,
        blocked: bool = False,
    ):
        self.passed = passed
        self.violations = violations
        self.requires_approval = requires_approval
        self.blocked = blocked


class GovernanceEngine:
    """Evaluate articles against governance rules."""
    
    async def evaluate_article(self, article: Article) -> GovernanceResult:
        """
        Evaluate an article against all enabled governance rules.
        
        Returns:
            GovernanceResult with pass/fail and any violations
        """
        # Get all enabled rules
        rules = await governance_rule_store.get_enabled()
        
        violations = []
        requires_approval = False
        blocked = False
        
        # Evaluate each rule
        for rule in rules:
            violation = await self._evaluate_rule(article, rule)
            
            if violation:
                violations.append(violation)
                
                # Determine action
                if rule.action == "block":
                    blocked = True
                elif rule.action == "require_approval":
                    requires_approval = True
        
        # Article passes if not blocked
        passed = not blocked
        
        # Log evaluation
        await audit_log_store.log(
            event_type="governance.evaluated",
            entity_type="article",
            entity_id=article.id,
            details={
                "passed": passed,
                "violations": len(violations),
                "requires_approval": requires_approval,
                "blocked": blocked,
            },
            severity="warning" if violations else "info",
        )
        
        logger.info(
            "Governance evaluation complete",
            article_id=str(article.id),
            passed=passed,
            violations=len(violations),
            requires_approval=requires_approval,
        )
        
        return GovernanceResult(
            passed=passed,
            violations=violations,
            requires_approval=requires_approval,
            blocked=blocked,
        )
    
    async def _evaluate_rule(
        self,
        article: Article,
        rule: GovernanceRule,
    ) -> Optional[RuleViolation]:
        """Evaluate a single rule against an article."""
        
        if rule.rule_type == "source_count":
            return await self._check_source_count(article, rule)
        
        elif rule.rule_type == "approval_required":
            return await self._check_approval_required(article, rule)
        
        elif rule.rule_type == "topic_restriction":
            return await self._check_topic_restriction(article, rule)
        
        elif rule.rule_type == "moderation":
            return await self._check_moderation(article, rule)
        
        else:
            logger.warning(f"Unknown rule type: {rule.rule_type}")
            return None
    
    async def _check_source_count(
        self,
        article: Article,
        rule: GovernanceRule,
    ) -> Optional[RuleViolation]:
        """Check if article has minimum number of sources."""
        min_sources = rule.condition.get("min_sources", settings.min_sources_required)
        
        source_count = len(article.sources) if article.sources else 0
        
        if source_count < min_sources:
            return RuleViolation(
                rule_id=rule.id,
                rule_name=rule.name,
                rule_type=rule.rule_type,
                severity="high",
                details=f"Article has {source_count} sources, requires {min_sources}",
            )
        
        return None
    
    async def _check_approval_required(
        self,
        article: Article,
        rule: GovernanceRule,
    ) -> Optional[RuleViolation]:
        """Check if article requires human approval."""
        # Check various conditions that might require approval
        requires_approval = False
        reasons = []
        
        # Low source count
        if article.sources and len(article.sources) < 2:
            requires_approval = True
            reasons.append("insufficient sources")
        
        # Sensitive tags
        sensitive_tags = rule.condition.get("sensitive_tags", [])
        if article.tags:
            for tag in article.tags:
                if tag.lower() in [t.lower() for t in sensitive_tags]:
                    requires_approval = True
                    reasons.append(f"sensitive topic: {tag}")
        
        if requires_approval:
            return RuleViolation(
                rule_id=rule.id,
                rule_name=rule.name,
                rule_type=rule.rule_type,
                severity="medium",
                details=f"Approval required: {', '.join(reasons)}",
            )
        
        return None
    
    async def _check_topic_restriction(
        self,
        article: Article,
        rule: GovernanceRule,
    ) -> Optional[RuleViolation]:
        """Check if article topic is restricted."""
        blocked_topics = rule.condition.get("blocked_topics", [])
        
        if article.tags:
            for tag in article.tags:
                if tag.lower() in [t.lower() for t in blocked_topics]:
                    return RuleViolation(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        rule_type=rule.rule_type,
                        severity="critical",
                        details=f"Blocked topic: {tag}",
                    )
        
        return None
    
    async def _check_moderation(
        self,
        article: Article,
        rule: GovernanceRule,
    ) -> Optional[RuleViolation]:
        """Check article content for harmful material."""
        # This would integrate with OpenAI Moderation API
        # For now, just a placeholder
        
        # TODO: Call OpenAI moderation API
        # moderation_result = await openai.moderations.create(
        #     input=article.body
        # )
        
        # if moderation_result.flagged:
        #     return RuleViolation(...)
        
        return None
    
    async def request_approval(
        self,
        article: Article,
        violations: List[RuleViolation],
    ) -> UUID:
        """Create an approval request for an article."""
        reason = f"Article flagged by {len(violations)} governance rule(s)"
        
        rule_violations = [
            {
                "rule_id": str(v.rule_id),
                "rule_name": v.rule_name,
                "rule_type": v.rule_type,
                "severity": v.severity,
                "details": v.details,
            }
            for v in violations
        ]
        
        approval_id = await approval_request_store.create(
            article_id=article.id,
            reason=reason,
            rule_violations=rule_violations,
        )
        
        # Log approval request
        await audit_log_store.log(
            event_type="approval.requested",
            entity_type="article",
            entity_id=article.id,
            details={
                "approval_id": str(approval_id),
                "violations": len(violations),
            },
            severity="warning",
        )
        
        logger.info(
            "Approval requested",
            article_id=str(article.id),
            approval_id=str(approval_id),
        )
        
        return approval_id


# Global instance
governance_engine = GovernanceEngine()
