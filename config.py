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
    password_reset_expire_minutes: int = 15
    rate_limit_auth: str = "5/10minute"

    # Email / SMTP Configuration (password reset delivery)
    mail_enabled: bool = False
    mail_username: str = ""
    mail_password: str = ""
    mail_from: str = "no-reply@signaldesk.local"
    mail_from_name: str = "Signaldesk"
    mail_server: str = "smtp.gmail.com"
    mail_port: int = 587
    mail_starttls: bool = True
    mail_ssl_tls: bool = False
    frontend_url: str = "http://localhost:3000"

    # AI Configuration
    ai_provider: str = "ollama"
    ai_model: str = "qwen2.5:7b"
    ollama_enabled: bool = True
    ollama_model: str = "qwen2.5:7b"
    ollama_base_url: str = "http://localhost:11434"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"
    google_ai_studio_api_key: str = ""
    google_ai_studio_base_url: str = "https://generativelanguage.googleapis.com/v1beta/models"
    google_ai_studio_model: str = "gemini-2.0-flash"
    # API Keys
    gemini_api_key: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "MediaMonitor/1.0"
    youtube_api_key: str = ""
    apify_api_token: str = ""
    apify_actor_id: str = "apify/facebook-posts-scraper"
    facebook_cookies_file: str = ""
    meta_access_token: str = ""
    meta_graph_api_version: str = "v21.0"
    meta_app_id: str = ""
    meta_app_secret: str = ""
    post_ingested_webhook_url: str = ""
    telegram_api_id: str = ""
    telegram_api_hash: str = ""
    telegram_session_string: str = ""
    whisper_model: str = "base"
    ocr_enabled: bool = True

    # Application Configuration
    debug: bool = True
    log_level: str = "INFO"
    app_name: str = "Media Monitoring Platform"
    app_version: str = "1.0.0"
    scraping_enabled: bool = True
    scraping_interval_seconds: int = 300

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
