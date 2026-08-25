"""
Scraper API Endpoints.
Provides endpoints for triggering scraping operations.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends, Query, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone

from app.db.session import get_db
from app.models.user import User
from app.core.deps import get_current_user, get_current_admin_user
from app.services.scraper_orchestrator import ScraperOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scraper", tags=["Scraper"])

# Global scraper instance
scraper = ScraperOrchestrator()


# ============================================================================
# Pydantic Models
# ============================================================================

class ScrapingResult(BaseModel):
    """Response model for scraping operation."""

    success: bool
    total_sources: int
    total_posts_found: int
    new_posts_saved: int
    errors: list
    duration_seconds: float
    sources_processed: dict

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "success": True,
                "total_sources": 3,
                "total_posts_found": 45,
                "new_posts_saved": 38,
                "errors": [],
                "duration_seconds": 23.5,
                "sources_processed": {
                    "rss": {"sources": 1, "posts_found": 15, "posts_saved": 15},
                    "reddit": {"sources": 1, "posts_found": 20, "posts_saved": 18},
                    "youtube": {"sources": 1, "posts_found": 10, "posts_saved": 5},
                },
            }
        })


class ScraperStatusResponse(BaseModel):
    """Response model for scraper status."""

    status: str
    message: str
    last_run: datetime = None
    is_running: bool

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "status": "idle",
                "message": "Scraper is ready",
                "last_run": "2026-08-21T10:30:00",
                "is_running": False,
            }
        })


# ============================================================================
# Global State
# ============================================================================

_scraper_state = {
    "is_running": False,
    "last_run": None,
    "last_result": None,
}


# ============================================================================
# Scraper Endpoints
# ============================================================================

@router.post(
    "/trigger",
    response_model=ScrapingResult,
    status_code=status.HTTP_200_OK,
    summary="Trigger Manual Scraping Cycle",
)
async def trigger_scraping(
    topic_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Manually trigger a complete scraping cycle.
    
    **Admin only operation.**
    
    Scrapes all active monitored sources dynamically using native platform
    libraries first, then Apify when configured and native ingestion fails.
    
    The request waits for the current cycle to finish.

    Args:
        db (Session): Database session.
        current_user (User): Authenticated administrator.
    
    Returns:
        ScrapingResult: Statistics about the scraping operation.
    
    Raises:
        HTTPException: If user is not admin or scraper is already running.
    
    Example:
        ```
        POST /api/scraper/trigger
        Authorization: Bearer <token>
        
        Response:
        {
            "success": true,
            "total_sources": 3,
            "total_posts_found": 45,
            "new_posts_saved": 38,
            "errors": [],
            "duration_seconds": 23.5,
            "sources_processed": {...}
        }
        ```
    """
    # Check if already running
    if _scraper_state["is_running"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scraping cycle is already running",
        )

    try:
        logger.info(f"🚀 Scraping cycle triggered by {current_user.email}")

        # Mark as running
        _scraper_state["is_running"] = True

        # Execute scraping
        result = await scraper.run_scraping_cycle(db, topic_id=topic_id)

        # Update state
        _scraper_state["is_running"] = False
        _scraper_state["last_run"] = datetime.now(timezone.utc)
        _scraper_state["last_result"] = result

        logger.info(f"✅ Scraping cycle completed: {result['new_posts_saved']} new posts saved")

        return result

    except Exception as e:
        _scraper_state["is_running"] = False
        error_msg = f"Scraping error: {str(e)}"
        logger.error(f"❌ {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg,
        )


@router.get(
    "/status",
    response_model=ScraperStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Scraper Status",
)
async def get_scraper_status(
    current_user: User = Depends(get_current_user),
):
    """
    Get the current status of the scraper.
    
    **Requires authentication.**
    
    Returns information about:
    - Whether scraping is currently running
    - Last scraping execution time
    - Current operational status
    
    Args:
        current_user (User): Authenticated user.
    
    Returns:
        ScraperStatusResponse: Current scraper status.
    
    Example:
        ```
        GET /api/scraper/status
        Authorization: Bearer <token>
        
        Response:
        {
            "status": "idle",
            "message": "Scraper is ready",
            "last_run": "2026-08-21T10:30:00",
            "is_running": false
        }
        ```
    """
    status_str = "running" if _scraper_state["is_running"] else "idle"
    message = (
        "Scraping cycle in progress..."
        if _scraper_state["is_running"]
        else "Scraper is ready"
    )

    return ScraperStatusResponse(
        status=status_str,
        message=message,
        last_run=_scraper_state["last_run"],
        is_running=_scraper_state["is_running"],
    )


@router.get(
    "/last-result",
    response_model=ScrapingResult,
    status_code=status.HTTP_200_OK,
    summary="Get Last Scraping Result",
)
async def get_last_scraping_result(
    current_user: User = Depends(get_current_user),
):
    """
    Get the results from the last scraping cycle.
    
    **Requires authentication.**
    
    Returns statistics from the most recent scraping operation including:
    - Number of posts found
    - Number of new posts saved
    - Processing time
    - Any errors encountered
    
    Args:
        current_user (User): Authenticated user.
    
    Returns:
        ScrapingResult: Statistics from last scraping cycle.
    
    Raises:
        HTTPException: If no scraping has been run yet.
    
    Example:
        ```
        GET /api/scraper/last-result
        Authorization: Bearer <token>
        
        Response:
        {
            "success": true,
            "total_sources": 3,
            "total_posts_found": 45,
            "new_posts_saved": 38,
            ...
        }
        ```
    """
    if _scraper_state["last_result"] is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No scraping results available yet",
        )

    return _scraper_state["last_result"]


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Scraper Health Check",
)
async def scraper_health():
    """
    Health check for the scraper service.
    
    **No authentication required.**
    
    Returns:
        Dict with health status.
    
    Example:
        ```
        GET /api/scraper/health
        
        Response:
        {
            "status": "healthy",
            "services": {
                "rss": "operational",
                "reddit": "operational",
                "youtube": "operational",
                "playwright": "operational"
            }
        }
        ```
    """
    return {
        "status": "healthy",
        "services": {
            "rss": "operational",
            "reddit": "operational",
            "youtube": "operational",
            "playwright": "operational",
        },
        "timestamp": datetime.now(timezone.utc),
    }
