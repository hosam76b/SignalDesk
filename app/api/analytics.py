"""Analytics endpoints for propagation graph and intelligence tracking."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_topic_user
from app.db.session import get_db
from app.models.user import User
from app.services.alerts import AlertManager
from app.services.propagation_service import analyze_topic_propagation_graph
from app.services.reports import PDFReportService

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics & CIB Tracking"])


@router.get("/topics/{topic_id}/propagation-graph", status_code=status.HTTP_200_OK)
def get_topic_propagation_graph_endpoint(
    topic_id: int,
    cib_window_minutes: int = Query(default=60, ge=1, le=1440),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_topic_user),
) -> dict[str, Any]:
    """
    Retrieve network propagation graph for a specific topic.
    Renders Patient Zero nodes, amplification chains, and CIB clusters.
    """
    return analyze_topic_propagation_graph(db, topic_id, cib_window_minutes=cib_window_minutes)


@router.get("/topics/{topic_id}/reports/executive-pdf")
def export_executive_pdf_report(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_topic_user),
) -> Response:
    """Generate and download a topic-scoped executive PDF report."""
    result = PDFReportService.generate_executive_report(db, topic_id, requester=current_user)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Executive report generation failed"))
    return Response(
        content=result["pdf_bytes"],
        media_type=result["content_type"],
        headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
    )


@router.get("/topics/{topic_id}/alerts")
def get_topic_alerts(
    topic_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_topic_user),
) -> dict[str, Any]:
    """Return real-time alerts generated for a specific topic."""
    return AlertManager.evaluate_topic_alerts(db, topic_id)


@router.patch("/topics/{topic_id}/alerts/{alert_id}")
def update_alert_status(
    topic_id: int,
    alert_id: str,
    status_value: str = Query(default="acknowledged", alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_topic_user),
) -> dict[str, Any]:
    """Update the status for an in-memory alert generated against a topic."""
    allowed = {"unread", "acknowledged", "resolved"}
    normalized = status_value.strip().lower()
    if normalized not in allowed:
        raise HTTPException(status_code=400, detail="Status must be unread, acknowledged, or resolved")

    result = AlertManager.evaluate_topic_alerts(db, topic_id)
    alerts = result.get("alerts", [])
    for alert in alerts:
        if alert.get("id") == alert_id:
            alert["status"] = normalized
            break
    else:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {"success": True, "topic_id": topic_id, "alert_id": alert_id, "status": normalized, "alerts": alerts}

