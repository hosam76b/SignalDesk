"""Public system status endpoints used by the application shell."""

from fastapi import APIRouter

from app.services.update_service import get_update_status

router = APIRouter(prefix="/api/system", tags=["System"])


@router.get("/update-status")
def update_status() -> dict:
    """Report whether a newer commit is available on the configured repository."""
    return get_update_status()