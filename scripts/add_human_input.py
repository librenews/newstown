#!/usr/bin/env python
"""Helper script to add human prompts and sources to stories."""
import asyncio
import sys
from uuid import UUID
from db.connection import db_pool
from db.human_oversight import human_prompt_store, source_store


async def add_prompt(story_id_str: str, prompt_text: str, created_by: str = "human"):
    """Add a human prompt to a story."""
    async with db_pool:
        story_id = UUID(story_id_str)
        prompt_id = await human_prompt_store.create_prompt(
            story_id=story_id,
            prompt_text=prompt_text,
            created_by=created_by,
        )
        print(f"✓ Created prompt {prompt_id} for story {story_id}")


async def add_url(story_id_str: str, url: str, added_by: str = "human"):
    """Add a URL source to a story."""
    async with db_pool:
        story_id = UUID(story_id_str)
        source_id = await source_store.add_url_source(
            story_id=story_id,
            url=url,
            added_by=added_by,
        )
        print(f"✓ Added URL source {source_id} for story {story_id}")


async def add_text(story_id_str: str, text: str, added_by: str = "human"):
    """Add a text source to a story."""
    async with db_pool:
        story_id = UUID(story_id_str)
        source_id = await source_store.add_text_source(
            story_id=story_id,
            content=text,
            added_by=added_by,
        )
        print(f"✓ Added text source {source_id} for story {story_id}")


async def list_recent_stories():
    """List recent story IDs for reference."""
    async with db_pool:
        rows = await db_pool.fetch("""
            SELECT DISTINCT story_id, created_at
            FROM story_events
            WHERE event_type = 'story.created'
            ORDER BY created_at DESC
            LIMIT 10
        """)
        
        print("\n📰 Recent Stories:")
        for row in rows:
            print(f"  {row['story_id']} - {row['created_at']}")


def main():
    if len(sys.argv) < 2:
        print("""
Usage:
  python scripts/add_human_input.py prompt <story_id> "<question>"
  python scripts/add_human_input.py url <story_id> <url>
  python scripts/add_human_input.py text <story_id> "<text>"
  python scripts/add_human_input.py list

Examples:
  python scripts/add_human_input.py prompt abc-123 "Is there evidence of fiscal inconsistency?"
  python scripts/add_human_input.py url abc-123 https://example.com/article
  python scripts/add_human_input.py list
        """)
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "list":
        asyncio.run(list_recent_stories())
    elif command == "prompt" and len(sys.argv) >= 4:
        asyncio.run(add_prompt(sys.argv[2], sys.argv[3]))
    elif command == "url" and len(sys.argv) >= 4:
        asyncio.run(add_url(sys.argv[2], sys.argv[3]))
    elif command == "text" and len(sys.argv) >= 4:
        asyncio.run(add_text(sys.argv[2], sys.argv[3]))
    else:
        print("Invalid command. Use 'list', 'prompt', 'url', or 'text'")
        sys.exit(1)


if __name__ == "__main__":
    main()
