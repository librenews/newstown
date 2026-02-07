"""Initialize default governance rules for News Town."""
import asyncio
from db.governance import governance_rule_store
from config.logging import get_logger

logger = get_logger(__name__)


async def create_default_rules():
    """Create default governance rules if they don't exist."""
    
    # Rule 1: Source Count
    await governance_rule_store.create(
        rule_type="source_count",
        name="Minimum Source Requirement",
        description="Articles must have at least 2 independent sources",
        condition={"min_sources": 2},
        action="require_approval",
        priority=10,
    )
    
    # Rule 2: Approval for Sensitive Topics
    await governance_rule_store.create(
        rule_type="approval_required",
        name="Sensitive Topic Approval",
        description="Articles on politics, health, or finance require human approval",
        condition={
            "sensitive_tags": ["politics", "health", "finance", "medical", "election"]
        },
        action="require_approval",
        priority=8,
    )
    
    # Rule 3: Topic Restrictions
    await governance_rule_store.create(
        rule_type="topic_restriction",
        name="Blocked Topics",
        description="Certain topics are not allowed",
        condition={
            "blocked_topics": []  # Empty by default, configure as needed
        },
        action="block",
        priority=15,
    )
    
    # Rule 4: Content Moderation
    await governance_rule_store.create(
        rule_type="moderation",
        name="Content Safety Check",
        description="Articles are screened for harmful content",
        condition={
            "check_hate_speech": True,
            "check_violence": True,
        },
        action="block",
        priority=20,  # Highest priority
    )
    
    logger.info("Default governance rules created")


if __name__ == "__main__":
    # Run as script to initialize rules
    asyncio.run(create_default_rules())
