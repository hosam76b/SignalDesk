"""Analytics endpoints for propagation graph and intelligence tracking."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_topic_user
from app.db.session import get_db
from app.models.user import User
from app.services.alerts import AlertManager
from app.services.propagation_service import analyze_topic_propagation_graph
from app.services.reports import PDFReportService
from app.services.webhook_service import (
    WEBHOOK_EVENT_ALERT_TRIGGERED,
    WEBHOOK_EVENT_REPORT_READY,
    dispatch_event_background,
)

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics & CIB Tracking"])

# In-memory dedup so alert webhooks fire only once per detected alert instance.
_dispatched_alert_ids: set[str] = set()


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
    background_tasks: BackgroundTasks,
    language: str = Query(default="en", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_topic_user),
) -> Response:
    """Generate and download a topic-scoped executive PDF report."""
    result = PDFReportService.generate_executive_report(
        db,
        topic_id,
        requester=current_user,
        language=language,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Executive report generation failed"))
    background_tasks.add_task(
        dispatch_event_background,
        WEBHOOK_EVENT_REPORT_READY,
        {
            "topic_id": topic_id,
            "filename": result["filename"],
            "language": language,
            "requested_by": current_user.email,
        },
    )
    return Response(
        content=result["pdf_bytes"],
        media_type=result["content_type"],
        headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
    )


@router.get("/topics/{topic_id}/alerts")
def get_topic_alerts(
    topic_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_topic_user),
) -> dict[str, Any]:
    """Return real-time alerts generated for a specific topic."""
    result = AlertManager.evaluate_topic_alerts(db, topic_id)
    fresh_alerts: list[dict[str, Any]] = []
    for alert in result.get("alerts", []):
        alert_key = f"{topic_id}:{alert.get('id')}"
        if (
            alert.get("status") == "unread"
            and str(alert.get("severity", "")).lower() in {"high", "critical"}
            and alert_key not in _dispatched_alert_ids
        ):
            _dispatched_alert_ids.add(alert_key)
            fresh_alerts.append(alert)
    if fresh_alerts:
        background_tasks.add_task(
            dispatch_event_background,
            WEBHOOK_EVENT_ALERT_TRIGGERED,
            {"topic_id": topic_id, "alert_count": len(fresh_alerts), "alerts": fresh_alerts},
        )
    return result


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

