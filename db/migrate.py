"""Database migration utilities."""
import asyncio
from pathlib import Path
from config.logging import get_logger
from db.connection import db

logger = get_logger(__name__)


async def run_migrations() -> None:
    """Run database migrations."""
    logger.info("Running database migrations")
    
    schema_path = Path(__file__).parent / "schema.sql"
    
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    
    schema_sql = schema_path.read_text()

    # Configure vector dimension based on selected model
    # distinct from production/development environment
    from ingestion.embeddings import embedding_service
    dim = embedding_service.dimension
    logger.info(f"Configuring schema with vector dimension: {dim}")
    
    # Replace default dimension with actual model dimension
    schema_sql = schema_sql.replace("vector(1536)", f"vector({dim})")
    
    async with db.acquire() as conn:
        await conn.execute(schema_sql)
    
    logger.info("Migrations completed successfully")


async def reset_database() -> None:
    """Drop and recreate all tables (development only)."""
    logger.warning("Resetting database - all data will be lost")
    
    async with db.acquire() as conn:
        # Drop functions
        await conn.execute("DROP FUNCTION IF EXISTS claim_task(uuid,text) CASCADE")
        
        # Drop tables
        await conn.execute("DROP MATERIALIZED VIEW IF EXISTS stories CASCADE")
        await conn.execute("DROP TABLE IF EXISTS article_reviews CASCADE")
        await conn.execute("DROP TABLE IF EXISTS publications CASCADE")
        await conn.execute("DROP TABLE IF EXISTS publishing_schedule CASCADE")
        await conn.execute("DROP TABLE IF EXISTS approval_requests CASCADE")
        await conn.execute("DROP TABLE IF EXISTS governance_rules CASCADE")
        await conn.execute("DROP TABLE IF EXISTS audit_log CASCADE")
        await conn.execute("DROP TABLE IF EXISTS articles CASCADE")
        await conn.execute("DROP TABLE IF EXISTS story_sources CASCADE")
        await conn.execute("DROP TABLE IF EXISTS human_prompts CASCADE")
        await conn.execute("DROP TABLE IF EXISTS story_memory CASCADE")
        await conn.execute("DROP TABLE IF EXISTS agents CASCADE")
        await conn.execute("DROP TABLE IF EXISTS story_tasks CASCADE")
        await conn.execute("DROP TABLE IF EXISTS story_events CASCADE")
        await conn.execute("DROP EXTENSION IF EXISTS vector CASCADE")
    
    logger.info("Database reset complete")
    
    # Re-run migrations
    await run_migrations()


if __name__ == "__main__":
    async def main():
        await db.connect()
        try:
            await run_migrations()
        finally:
            await db.disconnect()
    
    asyncio.run(main())
