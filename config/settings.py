"""Configuration settings for News Town."""
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Environment
    environment: Literal["development", "production", "test"] = "development"
    
    # API Keys
    openai_api_key: str
    anthropic_api_key: str
    
    # LLM Configuration
    openai_model: str = "gpt-4-turbo-preview"
    claude_model: str = "claude-3-haiku-20240307"  # Use Haiku as it has broader availability
    
    # Database
    database_url: str = "postgresql://newsroom:newsroom@localhost:5432/newstown"

    # Search Providers
    brave_api_key: str = ""  # Optional
    
    # Email Publishing (Phase 3)
    sendgrid_api_key: str = ""  # Optional, for email newsletters
    email_from_address: str = "news@newstown.example.com"
    email_from_name: str = "News Town"

    # Social Media Publishing (Phase 4)
    bluesky_handle: str = ""  # Optional
    bluesky_app_password: str = ""  # Optional

    # System
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Agent Configuration
    max_concurrent_agents: int = 10
    task_poll_interval_seconds: int = 15
    agent_heartbeat_interval_seconds: int = 30

    # Story Detection
    min_newsworthiness_score: float = 0.6
    max_stories_per_day: int = 20

    # Governance
    min_sources_required: int = 2
    require_fact_verification: bool = True
    auto_publish_enabled: bool = False

    # Phase 4: Local AI & Embeddings
    embedding_model: str = "BAAI/bge-small-en-v1.5"  # "BAAI/bge-large-en-v1.5" for prod
    local_llm_base_url: str = ""  # e.g., "http://localhost:11434/v1" for Ollama
    local_llm_model: str = "llama3"  # Model name to send to local server


# Global settings instance
settings = Settings()
