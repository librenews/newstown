"""Main entry point for News Town."""
import asyncio
import signal
from config.logging import configure_logging, get_logger
from config.settings import settings
from db import db
from db.migrate import run_migrations
from chief import Chief
from agents.scout import ScoutAgent
from agents.reporter import ReporterAgent

logger = get_logger(__name__)


class NewsTown:
    """Main News Town application."""

    def __init__(self):
        self.agents = []
        self.running = False

    async def start(self):
        """Start the News Town system."""
        configure_logging()
        logger.info("Starting News Town", environment=settings.environment)
        
        # Connect to database
        await db.connect()
        
        # Run migrations
        logger.info("Running migrations")
        await run_migrations()
        
        # Create agents
        logger.info("Creating agents")
        
        # Create Chief
        chief = Chief()
        self.agents.append(chief)
        
        # Create Scout agents (monitoring different feeds)
        tech_feeds = [
            "https://news.ycombinator.com/rss",
            "https://www.techmeme.com/feed.xml",
        ]
        scout = ScoutAgent(feeds=tech_feeds)
        self.agents.append(scout)
        
        # Create Reporter agents
        for _ in range(2):
            reporter = ReporterAgent()
            self.agents.append(reporter)
        
        # Start all agents
        logger.info(f"Starting {len(self.agents)} agents")
        self.running = True
        
        tasks = [agent.run() for agent in self.agents]
        await asyncio.gather(*tasks)

    async def stop(self):
        """Stop the News Town system."""
        if not self.running:
            return
        
        logger.info("Stopping News Town")
        self.running = False
        
        # Stop all agents
        for agent in self.agents:
            await agent.stop()
        
        # Disconnect from database
        await db.disconnect()
        
        logger.info("News Town stopped")


async def main():
    """Main entry point."""
    town = NewsTown()
    
    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    
    def handle_signal():
        logger.info("Received shutdown signal")
        asyncio.create_task(town.stop())
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)
    
    try:
        await town.start()
    except Exception as e:
        logger.error("Fatal error", error=str(e), exc_info=True)
    finally:
        await town.stop()


if __name__ == "__main__":
    asyncio.run(main())
