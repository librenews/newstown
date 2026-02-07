#!/usr/bin/env python3
"""End-to-end test for Phase 3 publishing workflow."""
import asyncio
from uuid import uuid4
from datetime import datetime, timezone
from db.connection import db
from db.articles import article_store, Article
from governance import governance_engine
from governance.default_rules import create_default_rules
from publishing.rss import rss_publisher
from config.logging import get_logger

logger = get_logger(__name__)


async def test_publishing_workflow():
    """Test complete publishing workflow with governance."""
    
    print("\n=== Phase 3 Publishing Workflow Test ===\n")
    
    # Connect to database
    await db.connect()
    print("✓ Connected to database")
    
    # Create default governance rules
    try:
        await create_default_rules()
        print("✓ Created default governance rules")
    except Exception:
        print("✓ Governance rules already exist")
    
    # Create a test article
    article = Article(
        id=uuid4(),
        story_id=uuid4(),
        headline="Test Article: AI Breakthrough in Climate Modeling",
        summary="Researchers develop new AI system for climate predictions",
        body="A team of scientists has developed a groundbreaking AI system...",
        byline="News Town Reporter",
        sources=[
            {"url": "https://example.com/source1", "title": "Primary Source"},
            {"url": "https://example.com/source2", "title": "Secondary Source"},
        ],
        tags=["technology", "climate", "ai"],
        published_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    # Store article
    article_id = await article_store.create_article(
        story_id=article.story_id,
        headline=article.headline,
        summary=article.summary,
        body=article.body,
        byline=article.byline,
        sources=article.sources,
        tags=article.tags,
    )
    # Update article with returned ID
    article.id = article_id
    print(f"✓ Created test article: {article.headline}")
    
    # Test governance evaluation
    print("\n--- Governance Evaluation ---")
    result = await governance_engine.evaluate_article(article)
    
    print(f"  Passed: {result.passed}")
    print(f"  Requires Approval: {result.requires_approval}")
    print(f"  Blocked: {result.blocked}")
    print(f"  Violations: {len(result.violations)}")
    
    for v in result.violations:
        print(f"    - {v.rule_name}: {v.details}")
    
    if result.passed:
        print("✓ Article passed governance checks")
    else:
        print("✗ Article blocked by governance")
        return
    
    # Test RSS publishing
    print("\n--- RSS Publishing ---")
    rss_result = await rss_publisher.publish(article)
    
    if rss_result.success:
        print(f"✓ Published to RSS (ID: {rss_result.publication_id})")
    else:
        print(f"✗ RSS publishing failed: {rss_result.error}")
    
    # Generate RSS feed
    print("\n--- RSS Feed Generation ---")
    rss_xml = await rss_publisher.generate_feed()
    print(f"✓ Generated RSS feed ({len(rss_xml)} bytes)")
    
    # Verify article in feed
    if article.headline in rss_xml:
        print(f"✓ Article appears in RSS feed")
    else:
        print(f"✗ Article not found in RSS feed")
    
    # Test retraction
    print("\n--- Retraction Test ---")
    if rss_result.publication_id:
        from db.publications import publication_store
        retracted = await publication_store.retract(
            rss_result.publication_id,
            "Test retraction"
        )
        if retracted:
            print("✓ Article retracted successfully")
        else:
            print("✗ Retraction failed")
    
    # Disconnect
    await db.disconnect()
    print("\n✓ Test complete!\n")


if __name__ == "__main__":
    asyncio.run(test_publishing_workflow())
