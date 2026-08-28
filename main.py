"""
Main FastAPI application entry point.
Initializes database, includes authentication and user management endpoints.
"""

import logging
import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.api import auth as auth_routes
from app.api import users as users_routes
from app.api import scraper as scraper_routes
from app.api import ai_analysis as ai_routes
from app.api import data_export as data_export_routes
from app.api import webhooks as webhook_routes
from app.api import dashboard as dashboard_routes
from app.api import monitoring as monitoring_routes
from app.api import topics as topics_routes
from app.api import audit as audit_routes
from app.api import analytics as analytics_routes
from app.api import knowledge as knowledge_routes
from config import settings

# Import all models to register them with SQLAlchemy
import app.models  # noqa: F401

# Setup logging
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


async def _background_scraping_loop() -> None:
    """Continuously ingest active topic sources on a dedicated DB session."""
    interval = max(15, settings.scraping_interval_seconds)
    while True:
        db = SessionLocal()
        try:
            scraper_routes._scraper_state["is_running"] = True
            result = await scraper_routes.scraper.run_scraping_cycle(db)
            scraper_routes._scraper_state["last_run"] = datetime.now(timezone.utc)
            scraper_routes._scraper_state["last_result"] = result
            logger.info(
                "Background scraping cycle completed: %s new posts, %s errors",
                result.get("new_posts_saved", 0),
                len(result.get("errors", [])),
            )
        except Exception:
            logger.exception("Background scraping cycle failed")
        finally:
            scraper_routes._scraper_state["is_running"] = False
            db.close()
        await asyncio.sleep(interval)


# ============================================================================
# FastAPI Application Setup
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources before serving requests and log shutdown."""
    scraping_task = None
    logger.info("=" * 80)
    logger.info(f"🚀 {settings.app_name} v{settings.app_version} starting up...")
    logger.info("=" * 80)
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Log level: {settings.log_level}")
    try:
        init_db()
        if settings.scraping_enabled and "PYTEST_CURRENT_TEST" not in os.environ:
            scraping_task = asyncio.create_task(_background_scraping_loop())
            logger.info(
                "✅ Background scraping enabled; interval=%ss",
                max(15, settings.scraping_interval_seconds),
            )
        logger.info("✅ Application startup complete")
        yield
    except Exception as exc:
        logger.error(f"❌ Application startup failed: {str(exc)}")
        raise
    finally:
        if scraping_task is not None:
            scraping_task.cancel()
            await asyncio.gather(scraping_task, return_exceptions=True)
            logger.info("✅ Background scraping stopped")
        logger.info("=" * 80)
        logger.info(f"🛑 {settings.app_name} shutting down...")
        logger.info("=" * 80)


app = FastAPI(
    title=settings.app_name,
    description="Media Monitoring Platform for Detecting Child Safety/Violence Content",
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(auth_routes.router)
app.include_router(users_routes.router)
app.include_router(scraper_routes.router)
app.include_router(ai_routes.router)
app.include_router(data_export_routes.router)
app.include_router(webhook_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(monitoring_routes.router)
app.include_router(topics_routes.router)
app.include_router(audit_routes.router)
app.include_router(analytics_routes.router)
app.include_router(knowledge_routes.router)


def custom_openapi() -> dict:
    """Generate OpenAPI metadata with JWT bearer authentication for Swagger UI."""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema.setdefault("components", {})["securitySchemes"] = {
        "HTTPBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }
    openapi_schema["security"] = [{"HTTPBearer": []}]
    app.openapi_schema = openapi_schema
    return openapi_schema


app.openapi = custom_openapi


# ============================================================================
# Health Check Endpoints
# ============================================================================

@app.get("/", tags=["Health"])
async def root():
    """Root health check endpoint."""
    return {
        "message": "Media Monitoring Platform Running",
        "app": settings.app_name,
        "version": settings.app_version,
        "status": "operational"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Detailed health check endpoint."""
    return {
        "status": "healthy",
        "database": "connected",
        "cache": "configured"
    }


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )

