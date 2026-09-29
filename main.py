"""
Main FastAPI application entry point.
Initializes database, includes authentication and user management endpoints.
"""

import logging
import asyncio
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.core.rate_limit import limiter
from app.core.self_check import self_check
from app.db.init_db import init_db
from app.db.session import SessionLocal, current_sqlite_pragmas
from app.services.ai_queue import ai_queue
from app.services.ai_service import ai_service
from app.api import auth as auth_routes
from app.api import users as users_routes
from app.api import scraper as scraper_routes
from app.api import ai_analysis as ai_routes
from app.api import data_export as data_export_routes
from app.api import export as export_routes
from app.api import webhooks as webhook_routes
from app.api import dashboard as dashboard_routes
from app.api import monitoring as monitoring_routes
from app.api import topics as topics_routes
from app.api import audit as audit_routes
from app.api import analytics as analytics_routes
from app.api import knowledge as knowledge_routes
from app.api import approvals as approvals_routes
from app.api import profile as profile_routes
from app.api import posts as posts_routes
from app.api import ingestion as ingestion_routes
from app.api import spider as spider_routes
from app.api import setup as setup_routes
from app.api import system as system_routes
from config import settings

# Import all models to register them with SQLAlchemy
import app.models  # noqa: F401

# Setup logging
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _api_documentation_urls() -> tuple[str | None, str | None, str | None]:
    if not settings.api_openapi_enabled:
        return None, None, None
    if not settings.api_docs_enabled:
        return settings.api_openapi_url, None, None
    return settings.api_openapi_url, settings.api_docs_url, settings.api_redoc_url


openapi_url, docs_url, redoc_url = _api_documentation_urls()


async def _background_scraping_loop() -> None:
    """Continuously ingest active topic sources on a dedicated DB session.

    Scraping only *enqueues* AI work now; the bounded queue's worker performs
    the provider calls. This loop therefore returns to ``asyncio.sleep`` on a
    network-bound schedule instead of blocking for the whole analysis batch.
    """
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
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Background scraping cycle failed")
        finally:
            scraper_routes._scraper_state["is_running"] = False
            db.close()
        await asyncio.sleep(interval)


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
        for warning in settings.assert_secure_defaults():
            logger.warning("⚠️  SECURITY: %s", warning)

        init_db()

        pragmas = current_sqlite_pragmas()
        if pragmas:
            logger.info("🗄️  SQLite pragmas: %s", pragmas)

        # Start the AI worker before serving traffic so a scrape cycle that
        # lands immediately has somewhere to enqueue. The worker owns its own
        # session and event-loop task, so provider latency can no longer block
        # request handling.
        ai_queue.start()

        # Watches our own listener. If the Windows IOCP accept loop dies the
        # process would otherwise stay alive, keep the SQLite write lock held
        # and serve nothing while the service manager still reports "Running".
        # Started last so it cannot race the socket it is about to probe.
        #
        # The probe target is passed in rather than read from SELF_CHECK_PORT:
        # SIGNALDESK_PORT (NSSM AppEnvironmentExtra -> settings.port) is the
        # same number uvicorn binds, so the two can no longer drift apart and
        # produce a false "the accept loop is dead" verdict on a live server.
        _bind_port = int(getattr(settings, "port", 8000) or 8000)
        self_check.start(port=_bind_port)

        if settings.scraping_enabled and "PYTEST_CURRENT_TEST" not in os.environ:
            scraping_task = asyncio.create_task(_background_scraping_loop())
            logger.info(
                "✅ Background scraping enabled; interval=%ss concurrency=%s",
                max(15, settings.scraping_interval_seconds),
                settings.scraping_max_concurrency,
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
        await self_check.stop()
        await ai_queue.stop()
        logger.info("=" * 80)
        logger.info(f"🛑 {settings.app_name} shutting down...")
        logger.info("=" * 80)


app = FastAPI(
    title=settings.app_name,
    description="SignalDesk - Threat Intelligence & Media Monitoring Platform",
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
    openapi_url=openapi_url,
    docs_url=docs_url,
    redoc_url=redoc_url,
)

# Rate limiting (brute-force protection on auth endpoints)
app.state.limiter = limiter


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Return rate-limit responses with CORS headers for browser clients."""
    response = _rate_limit_exceeded_handler(request, exc)
    # Reflect only an origin that is actually allow-listed. Echoing whatever the
    # client sent, as this handler used to, handed out an
    # Access-Control-Allow-Origin for any site paired with credentials.
    origin = request.headers.get("origin", "")
    if origin and origin.rstrip("/") in _allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    return response


app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS Configuration
#
# Origins are explicit. A wildcard with allow_credentials=True makes Starlette
# reflect the request Origin and pair it with
# Access-Control-Allow-Credentials: true, which was measured here as a
# preflight from https://evil.example.com being answered 200 with
# ACAO: 'https://evil.example.com'.
_allowed_origins = settings.cors_origin_list
logger.info("CORS allowed origins: %s", _allowed_origins or "(none)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    max_age=600,
)


# --- Authenticated media serving -------------------------------------------
MEDIA_UPLOADS_DIR = Path(__file__).resolve().parent / "media_uploads"
MEDIA_UPLOADS_DIR.mkdir(exist_ok=True)
MEDIA_ROOT = MEDIA_UPLOADS_DIR.resolve()

MEDIA_CONTENT_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
    ".mkv": "video/x-matroska", ".m4a": "audio/mp4", ".mp3": "audio/mpeg",
    ".wav": "audio/wav", ".pdf": "application/pdf",
}


def _safe_media_path(relative: str) -> Path | None:
    """Resolve ``relative`` inside the uploads dir, or None if it escapes."""
    if not relative:
        return None
    try:
        candidate = (MEDIA_ROOT / relative).resolve()
    except (OSError, ValueError):
        return None
    if not candidate.is_relative_to(MEDIA_ROOT):
        logger.warning("Blocked media path traversal attempt: %r", relative)
        return None
    # Defence in depth: never serve a non-media file even if it lands inside
    # the uploads directory (a .env dropped there by some other tool).
    if candidate.suffix.lower() not in MEDIA_CONTENT_TYPES:
        return None
    return candidate if candidate.is_file() else None


@app.get("/media/{media_path:path}", include_in_schema=False)
async def serve_media(media_path: str, request: Request):
    """Serve an uploaded media file to authenticated users only.

    This was previously a bare ``StaticFiles`` mount, so every screenshot and
    video clip ingested through Quick Ingest was world-readable to anything
    that could reach the port -- including a LAN host, given the server binds
    0.0.0.0.
    """
    from fastapi import HTTPException as _HTTPException
    from fastapi.security import HTTPBearer

    credentials = await HTTPBearer(auto_error=False)(request)
    if credentials is None:
        return JSONResponse(
            status_code=401,
            content={"detail": "Authentication required to access uploaded media"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Percent-encoded traversal is rejected before decoding, and the decoded
    # path is containment-checked as well.
    if "%2e" in media_path.lower() or "%2f" in media_path.lower() or "%5c" in media_path.lower():
        logger.warning("Blocked encoded media traversal attempt: %r", media_path)
        raise _HTTPException(status_code=404, detail="Not found")

    candidate = _safe_media_path(unquote(media_path))
    if candidate is None:
        raise _HTTPException(status_code=404, detail="Not found")
    return FileResponse(
        candidate,
        media_type=MEDIA_CONTENT_TYPES.get(candidate.suffix.lower()),
        # Uploads are user-supplied; never let a browser sniff or execute them.
        headers={"X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"},
    )

# Include API routers
app.include_router(auth_routes.router)
app.include_router(users_routes.router)
app.include_router(scraper_routes.router)
app.include_router(ai_routes.router)
app.include_router(data_export_routes.router)
app.include_router(export_routes.router)
app.include_router(webhook_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(monitoring_routes.router)
app.include_router(topics_routes.router)
app.include_router(audit_routes.router)
app.include_router(analytics_routes.router)
app.include_router(knowledge_routes.router)
app.include_router(approvals_routes.router)
app.include_router(profile_routes.router)
app.include_router(posts_routes.router)
app.include_router(ingestion_routes.router)
app.include_router(spider_routes.router)
app.include_router(setup_routes.router)
app.include_router(system_routes.router)


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

@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness and readiness detail.

    Deliberately unauthenticated and cheap: it must stay responsive even while
    the AI worker is saturated, which is exactly the condition the audit
    measured the old code against. It reports queue depth so a saturated queue
    is visible without needing to log in.
    """
    return {
        "status": "healthy",
        "database": "connected",
        "cache": "configured",
        "ai_queue": ai_queue.stats(),
        "ai_circuits": ai_service.circuit_status(),
    }


FRONTEND_OUT_DIR = Path(__file__).resolve().parent / "frontend" / "out"
# Pre-resolved build root. Every candidate is checked against this with
# Path.is_relative_to, so percent-encoded traversal (`/%2e%2e/%2e%2e/.env`) and
# plain `../` both resolve to a path outside the build dir and are rejected.
# Without this, the catch-all route served arbitrary files -- including .env
# with every API key and SECRET_KEY -- to unauthenticated callers.
FRONTEND_BUILD_ROOT = FRONTEND_OUT_DIR.resolve()

#: Encoded separators and dot-segments. Uvicorn normalizes literal `../` out of
#: the path before routing but does not decode `%2e%2e`, so an encoded request
#: reaches this handler intact and would otherwise be decoded downstream into a
#: traversal. Rejecting the encoded forms up front means the decode step below
#: can never produce an escaping path.
_ENCODED_TRAVERSAL = re.compile(r"%2e|%2f|%5c|%00", re.IGNORECASE)


def _safe_frontend_asset(path: str) -> Path | None:
    """Return ``path`` resolved inside the build dir, or None if it escapes it."""
    if not path:
        return None
    if _ENCODED_TRAVERSAL.search(path):
        logger.warning("Blocked encoded frontend traversal attempt: %r", path)
        return None
    try:
        candidate = (FRONTEND_BUILD_ROOT / unquote(path)).resolve()
    except (OSError, ValueError):
        # Malformed path (e.g. NUL bytes or a drive-relative path on Windows).
        return None
    if not candidate.is_relative_to(FRONTEND_BUILD_ROOT):
        logger.warning("Blocked frontend path traversal attempt: %r", path)
        return None
    return candidate if candidate.is_file() else None


@app.get("/{path:path}", include_in_schema=False)
async def serve_frontend(path: str):
    """Serve the exported Next.js app and fall back to its SPA entry point."""
    candidate = _safe_frontend_asset(path)
    if candidate is not None:
        return FileResponse(candidate)
    index_file = FRONTEND_BUILD_ROOT / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return {
        "message": "SignalDesk frontend has not been built yet",
        "build_command": "cd frontend; npm run build",
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

