"""
Application configuration management using Pydantic Settings.
Loads environment variables securely from .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Uses pydantic-settings for secure configuration management.
    """

    # Database Configuration
    db_url: str = "postgresql://user:password@localhost:5432/media_monitor"

    # Redis Configuration
    redis_url: str = "redis://127.0.0.1:6379/0"

    # JWT Security Configuration
    secret_key: str = "your-secret-key-change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # API Keys
    ollama_model: str = "qwen2.5:7b"
    ollama_base_url: str = "http://localhost:11434"
    gemini_api_key: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "MediaMonitor/1.0"
    youtube_api_key: str = ""
    apify_api_token: str = ""
    apify_actor_id: str = "apify/facebook-posts-scraper"
    facebook_cookies_file: str = ""
    post_ingested_webhook_url: str = ""

    # Application Configuration
    debug: bool = True
    log_level: str = "INFO"
    app_name: str = "Media Monitoring Platform"
    app_version: str = "1.0.0"

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Returns cached Settings instance.
    Uses lru_cache to ensure single instantiation across application.
    """
    return Settings()


# Global settings instance
settings = get_settings()
