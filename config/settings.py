"""Configuration management for News Town."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql://localhost/newstown"

    # AI Providers
    openai_api_key: str
    anthropic_api_key: str

    # Search Providers
    brave_api_key: str = ""  # Optional
    
    # Email Publishing (Phase 3)
    sendgrid_api_key: str = ""  # Optional, for email newsletters
    email_from_address: str = "news@newstown.example.com"
    email_from_name: str = "News Town"

    # System
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    environment: Literal["development", "production", "test"] = "development"

    # Agent Configuration
    max_concurrent_agents: int = 10
    task_poll_interval_seconds: int = 5
    agent_heartbeat_interval_seconds: int = 30

    # Story Detection
    min_newsworthiness_score: float = 0.6
    max_stories_per_day: int = 20

    # Governance
    min_sources_required: int = 2
    require_fact_verification: bool = True
    auto_publish_enabled: bool = False


# Global settings instance
settings = Settings()
