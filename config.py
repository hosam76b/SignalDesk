"""
Application configuration management using Pydantic Settings.
Loads environment variables securely from .env file.
"""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Uses pydantic-settings for secure configuration management.
    """

    # Single source of truth for the port the server listens on.
    # NSSM hands the service this number through AppEnvironmentExtra
    # (SIGNALDESK_PORT=8000) and the very same value is what uvicorn binds
    # via AppParameters (--port). main.py forwards it to the socket self-check,
    # so the probe can never be pointed at a port this process does not serve.
    # Plain PORT is accepted as an alias for non-service runs.
    port: int = Field(
        default=8000,
        validation_alias=AliasChoices("SIGNALDESK_PORT", "PORT"),
    )

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
    ollama_api_key: str = ""
    # Ollama runner tuning. Keep alive long enough to survive the 5-minute
    # scrape interval (Ollama's 5m default unloads the model between cycles and
    # every cycle then pays a full model reload), and give the request an
    # explicit context window and token cap so analysis is never silently
    # truncated by the runner default.
    ollama_keep_alive: str = "30m"
    ollama_num_ctx: int = 8192
    ollama_num_predict: int = 512
    ollama_num_batch: int = 512
    ollama_temperature: float = 0.1
    # Must be >= ai_max_concurrency or the runner serialises requests that the
    # application believes are running in parallel.
    ollama_num_parallel: int = 4
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"
    google_ai_studio_api_key: str = ""
    google_ai_studio_base_url: str = "https://generativelanguage.googleapis.com/v1beta/models"
    google_ai_studio_model: str = "gemini-2.0-flash"
    custom_openai_api_key: str = ""
    custom_openai_base_url: str = "https://api.openai.com/v1"
    custom_openai_model: str = "gpt-4o-mini"
    ai_request_timeout: float = 180.0
    ai_max_concurrency: int = 5
    # Per-provider timeouts. A stalled endpoint must fail fast so the circuit
    # breaker can open instead of blocking a whole batch for ai_request_timeout.
    ai_connect_timeout: float = 10.0
    # Consecutive provider failures that trip the breaker.
    ai_circuit_failure_threshold: int = 3
    # Seconds a tripped breaker stays open before one trial call is allowed.
    ai_circuit_recovery_seconds: float = 30.0
    # Retry the local Ollama server when the selected cloud provider fails or times out.
    ai_fallback_enabled: bool = True
    ai_fallback_provider: str = "ollama"
    ai_vision_enabled: bool = True
    ai_max_images_per_post: int = 2
    knowledge_rag_enabled: bool = True
    knowledge_rag_top_k: int = 3
    knowledge_chunk_chars: int = 700
    # API Keys
    gemini_api_key: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "MediaMonitor/1.0"
    youtube_api_key: str = ""
    apify_api_token: str = ""
    apify_actor_id: str = ""
    # Caps how many dataset items a single actor run may produce. Passed as
    # Apify's `maxItems` so one over-eager actor cannot bill or return an
    # unbounded batch that then has to be normalized, de-duplicated and
    # re-queued. An explicit `maxItems` in a caller's actor_input wins.
    apify_max_items_per_run: int = Field(
        default=25,
        validation_alias=AliasChoices("APIFY_MAX_ITEMS_PER_RUN"),
    )
    apify_facebook_actor_id: str = ""
    # JSON object template for a community Facebook actor. Placeholders:
    # {url} = source URL, {max_items} = apify_max_items_per_run. Used by
    # _build_payload() when set; empty falls back to the official
    # startUrls/maxItems shape.
    apify_facebook_actor_input: str = ""
    apify_instagram_actor_id: str = ""
    apify_x_actor_id: str = ""
    apify_tiktok_actor_id: str = ""
    apify_threads_actor_id: str = ""
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
    # Production-safe defaults. DEBUG=True previously shipped as the default and
    # leaked tracebacks plus an interactive debugger on a network-bound server.
    debug: bool = False
    log_level: str = "INFO"
    app_name: str = "SignalDesk"
    app_version: str = "1.0.0"
    update_check_enabled: bool = True
    update_repository: str = "hosam76b/SignalDesk"
    update_branch: str = "main"
    update_check_interval_seconds: int = 900
    api_docs_enabled: bool = False
    api_openapi_enabled: bool = False
    api_docs_url: str = "/docs"
    api_redoc_url: str = "/redoc"
    api_openapi_url: str = "/openapi.json"
    # Explicit local origins. A wildcard combined with allow_credentials=True
    # makes Starlette reflect any request Origin and pair it with
    # Access-Control-Allow-Credentials: true, which hands authenticated API
    # access to every website the operator visits.
    cors_allow_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    scraping_enabled: bool = True
    scraping_interval_seconds: int = 300
    # Maximum sources scraped concurrently in one cycle.
    scraping_max_concurrency: int = 6
    spider_proxy_url: str = ""

    # AI analysis queue. Bounded so an ingestion spike degrades instead of
    # exhausting memory; overflow posts stay 'pending' in the database and are
    # picked up by the next cycle.
    ai_queue_maxsize: int = 1000
    # Kept small on purpose: one batch is one wave of concurrent provider
    # requests, so a large batch both burns the OpenRouter rate limit and holds
    # a write transaction open long enough to stall dashboard reads on SQLite.
    ai_queue_batch_size: int = 10
    ai_queue_workers: int = 1

    # Reclaim loop. The queue is fed by the scraper, so anything that misses it
    # (queue overflow, a batch that failed, posts that existed before the queue
    # started) would otherwise stay 'pending'/'failed' forever. This polls the
    # database on an interval and feeds those posts back into the same queue,
    # which is the "next cycle" the module docstrings promise.
    ai_reclaim_enabled: bool = True
    ai_reclaim_interval_seconds: int = 15
    # Upper bound on how many posts one reclaim tick may enqueue, so a large
    # backlog cannot be dumped into the queue in a single tick.
    ai_reclaim_batch_size: int = 10

    # Operator throttle. When true the worker accepts nothing and consumes no
    # provider calls, leaving SQLite and the CPU entirely to request handling --
    # useful while regenerating the frontend against a busy database.
    ai_queue_paused: bool = False

    # TTL for the dashboard statistics cache. Dashboard panels are re-read on
    # every page load but the underlying aggregates only move as posts are
    # ingested, so a short cache removes almost all of that work.
    dashboard_cache_ttl_seconds: int = 15

    # -------------------------------------------------------------------------
    # Socket self-check (Windows IOCP recovery)
    # -------------------------------------------------------------------------
    # On Windows the asyncio Proactor's accept() can fail with WinError 64
    # ("The specified network name is no longer available"). When that happens
    # the listener stops accepting, but the process stays alive: background
    # tasks keep running and keep holding the SQLite write lock, so every other
    # writer fails with "database is locked" while the Windows service manager
    # still reports the service as Running. The app is then down but looks
    # healthy, and only a restart recovers it.
    #
    # The self-check below probes the app's own port and exits the process when
    # it cannot get an HTTP response. NSSM ("AppExit Default: Restart") then
    # brings the service back within seconds instead of leaving it dead.
    #
    # self_check_port MUST match the port uvicorn binds (its --port argument).
    self_check_enabled: bool = True
    self_check_port: int = 8000
    # Loopback is correct even when uvicorn binds 0.0.0.0.
    self_check_host: str = "127.0.0.1"
    self_check_interval_seconds: int = 30
    # Short: the probe targets localhost, so a slow answer means the accept
    # loop is stuck rather than the machine being busy.
    self_check_timeout_seconds: float = 5.0
    # Consecutive failures required before exiting. Guards against a single
    # unlucky probe (antivirus, a busy scheduler) causing a restart loop.
    self_check_failure_threshold: int = 3

    # Outbound request policy. Governs user-supplied URLs submitted through
    # quick ingest, spider seeds, and webhook configuration.
    allow_private_outbound_urls: bool = False
    allow_blocked_ports_outbound: bool = False

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


    @property
    def cors_origin_list(self) -> list[str]:
        """Parsed, normalized CORS origins with wildcards rejected."""
        origins: list[str] = []
        for raw in self.cors_allow_origins.split(","):
            origin = raw.strip().rstrip("/")
            if not origin:
                continue
            if origin == "*":
                raise ValueError(
                    "CORS_ALLOW_ORIGINS may not be '*'. Wildcard origins combined "
                    "with allow_credentials=True let any website make "
                    "authenticated cross-origin requests. List the exact origins."
                )
            origins.append(origin)
        return origins

    def assert_secure_defaults(self) -> list[str]:
        """Return a list of unsafe-in-production configuration warnings.

        Called during startup so a misconfigured deployment is visible in the
        log immediately rather than discovered during an incident.
        """
        warnings: list[str] = []
        if self.debug:
            warnings.append("DEBUG is enabled; tracebacks and debug tooling are exposed")
        if self.api_docs_enabled or self.api_openapi_enabled:
            warnings.append("API documentation/OpenAPI endpoints are enabled")
        if self.secret_key == "your-secret-key-change-this-in-production":
            warnings.append(
                "SECRET_KEY is still the built-in default; every JWT is forgeable"
            )
        elif len(self.secret_key) < 32:
            warnings.append("SECRET_KEY is shorter than 32 characters")
        if not self.cors_origin_list:
            warnings.append("No CORS origins are configured")
        return warnings


@lru_cache()
def get_settings() -> Settings:
    """
    Returns cached Settings instance.
    Uses lru_cache to ensure single instantiation across application.
    """
    return Settings()


# Global settings instance
settings = get_settings()
