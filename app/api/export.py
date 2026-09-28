"""Export Data tab API: filter, preview, then stream a filtered dataset out.

Three-step flow, because the download is a `StreamingResponse` and the progress
bar has to read state that the response body is still producing:

1. ``POST /preview``  -- count the matching rows and break them down.
2. ``POST /jobs``     -- freeze the resolved filters into a job (this is the
   authorisation moment: the topic scope is baked in here, while the
   request-scoped session is still alive).
3. ``GET /jobs/{id}/download`` -- stream the file, updating the job as rows go
   out, while the client polls ``GET /jobs/{id}`` for the percentage.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import SessionLocal, get_db
from app.models.post import Post
from app.models.source import MonitoredSource
from app.models.topic import Topic, UserTopic
from app.models.user import User
from app.services.export_service import (
    AI_STATUS_OPTIONS,
    DEFAULT_COLUMN_KEYS,
    DEFAULT_RANGE_DAYS,
    EXPORT_CHUNK_ROWS,
    EXPORT_COLUMNS,
    EXPORT_FORMATS,
    EXPORT_MAX_ROWS,
    EXPORT_MEDIA_TYPES,
    PDF_MAX_DETAIL_ROWS,
    ExportColumnError,
    ExportFilters,
    accessible_topic_ids,
    build_export_spool,
    count_matching_posts,
    export_jobs,
    export_row_total,
    iter_export_chunks,
    iter_spooled_chunks,
    resolve_columns,
    resolve_date_window,
    summarize_matching_posts,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/export", tags=["Data Export"])


def open_export_session() -> Session:
    """Open a dedicated session for streaming an export body.

    Deliberately *not* the request-scoped ``get_db`` session: FastAPI 0.104
    closes ``yield`` dependencies before the response body is streamed, so a
    generator that touched that session would fail on an already-closed
    connection. The job's filters were authorised up front in the request
    handler; this session only reads rows.
    """
    return SessionLocal()


class ExportRequest(BaseModel):
    """The filter set shared by /preview and /jobs."""

    date_from: datetime | None = None
    date_to: datetime | None = None
    ai_status: str = "all"
    topic_id: int | None = Field(default=None, ge=1)
    source_id: int | None = Field(default=None, ge=1)
    search: str = Field(default="", max_length=500)
    columns: list[str] | None = Field(default=None, max_length=64)
    format: str = "csv"
    lang: str = "ar"
    limit: int = Field(default=EXPORT_MAX_ROWS, ge=1, le=EXPORT_MAX_ROWS)

    @field_validator("ai_status")
    @classmethod
    def _known_ai_status(cls, value: str) -> str:
        normalized = (value or "all").strip().lower()
        if normalized not in AI_STATUS_OPTIONS:
            raise ValueError(f"ai_status must be one of {', '.join(AI_STATUS_OPTIONS)}")
        return normalized

    @field_validator("format")
    @classmethod
    def _known_format(cls, value: str) -> str:
        normalized = (value or "csv").strip().lower()
        if normalized not in EXPORT_FORMATS:
            raise ValueError(f"format must be one of {', '.join(EXPORT_FORMATS)}")
        return normalized

    @field_validator("lang")
    @classmethod
    def _known_lang(cls, value: str) -> str:
        return "ar" if (value or "ar").strip().lower() == "ar" else "en"


class ExportJobRequest(ExportRequest):
    """Export parameters for a download. Kept as a named alias for readability."""


def _build_filters(payload: ExportRequest, current_user: User, db: Session) -> ExportFilters:
    date_from, date_to, _defaulted = resolve_date_window(payload.date_from, payload.date_to)
    try:
        columns = resolve_columns(payload.columns)
    except ExportColumnError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    scope = accessible_topic_ids(db, current_user)
    if scope is not None and payload.topic_id is not None and payload.topic_id not in scope:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this topic",
        )
    return ExportFilters(
        format=payload.format,
        lang=payload.lang,
        date_from=date_from,
        date_to=date_to,
        ai_status=payload.ai_status,
        topic_id=payload.topic_id,
        source_id=payload.source_id,
        search=payload.search or "",
        columns=columns,
        limit=payload.limit,
        allowed_topic_ids=scope,
        requested_by=getattr(current_user, "email", "") or "",
    )


def _effective(filters: ExportFilters) -> dict[str, Any]:
    return {
        "date_from": filters.date_from_bound.isoformat(),
        "date_to": filters.date_to_bound.isoformat(),
        "ai_status": filters.ai_status,
        "topic_id": filters.topic_id,
        "source_id": filters.source_id,
        "search": filters.search or None,
        "limit": filters.effective_limit,
        "columns": [column.key for column in filters.columns],
    }


@router.get("/options")
def export_options(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Catalogue for the Export tab: columns, statuses, formats, topics, sources."""
    scope = accessible_topic_ids(db, current_user)
    topic_query = db.query(Topic.id, Topic.title).order_by(Topic.title)
    if scope is not None:
        topic_query = topic_query.filter(Topic.id.in_(scope or (-1,)))
    sources = (
        db.query(MonitoredSource.id, MonitoredSource.name, MonitoredSource.platform)
        .order_by(MonitoredSource.name)
        .all()
    )
    return {
        "columns": [
            {
                "key": column.key,
                "label_ar": column.label_ar,
                "label_en": column.label_en,
                "group": column.group,
                "default": column.default,
            }
            for column in EXPORT_COLUMNS
        ],
        "default_columns": list(DEFAULT_COLUMN_KEYS),
        "ai_statuses": list(AI_STATUS_OPTIONS),
        "formats": [
            {"value": value, "media_type": EXPORT_MEDIA_TYPES[value]} for value in EXPORT_FORMATS
        ],
        "topics": [{"id": topic_id, "title": title} for topic_id, title in topic_query.all()],
        "sources": [
            {"id": source_id, "name": name, "platform": platform} for source_id, name, platform in sources
        ],
        "limits": {
            "max_rows": EXPORT_MAX_ROWS,
            "chunk_rows": EXPORT_CHUNK_ROWS,
            "pdf_max_detail_rows": PDF_MAX_DETAIL_ROWS,
            "default_range_days": DEFAULT_RANGE_DAYS,
        },
    }


@router.post("/preview")
def preview_export(
    payload: ExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Count and break down the rows an export would contain, without exporting."""
    filters = _build_filters(payload, current_user, db)
    total = count_matching_posts(db, filters)
    summary = summarize_matching_posts(db, filters)
    return {
        "total_rows": total,
        "exported_rows": min(total, filters.effective_limit),
        "truncated": total > filters.effective_limit,
        "format": filters.format,
        "effective": _effective(filters),
        **summary,
    }


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def create_export_job(
    payload: ExportJobRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Freeze the authorised filters into a downloadable job.

    Authorisation happens here, on the request session, because the streaming
    body runs after `get_db` has been torn down.
    """
    filters = _build_filters(payload, current_user, db)
    matched = count_matching_posts(db, filters)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    # The job tracks the rows the *file* will hold, not the rows the filter
    # matched, so the progress percentage has the right denominator. The
    # uncapped count is reported alongside it for the truncation notice.
    job = export_jobs.create(filters, export_row_total(matched, filters), stamp)
    return {
        "job_id": job.job_id,
        "filename": job.filename,
        "media_type": job.media_type,
        "total_rows": job.total_rows,
        "matched_rows": matched,
        "truncated": matched > filters.effective_limit,
        "effective": _effective(filters),
        "poll_url": f"/api/v1/export/jobs/{job.job_id}",
        "download_url": f"/api/v1/export/jobs/{job.job_id}/download",
    }


@router.get("/jobs/{job_id}")
def export_job_progress(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Progress for the in-flight download, polled while the body streams.

    Authenticated like the download it describes: the payload names the export
    file and how many records it holds, which is not something an anonymous
    caller should be able to enumerate.
    """
    job = export_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found")
    return job.as_dict()


@router.get("/jobs/{job_id}/download")
def download_export_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream the export as a file attachment.

    Chunked on purpose: rows are pulled in batches and encoded per batch, so a
    50k-row CSV never exists in memory. XLSX and PDF cannot be produced a byte
    at a time, so they are built into a temporary file first -- see
    :func:`build_export_spool` for why that happens here rather than in the
    body generator.
    """
    job = export_jobs.claim(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found or already downloaded")

    def report_progress(rows_written: int) -> None:
        export_jobs.progress(job, rows_written)

    filters = job.filters
    meta: dict[str, Any] = {}
    session = open_export_session()
    spool = None
    try:
        # The PDF's statistical summary must be computed before the document
        # body starts, since ReportLab lays the whole story out in one pass.
        if filters.format == "pdf":
            meta = {
                "total_rows": job.total_rows,
                **summarize_matching_posts(session, filters),
            }
        # XLSX and PDF are built here rather than inside the body generator:
        # by the time a StreamingResponse yields its first chunk the 200 and the
        # Content-Disposition are already on the wire, so a build failure could
        # only ever reach the client as a truncated file. Progress still
        # advances during this call, because the progress poll is a separate
        # request the browser fires while the download is still pending.
        spool = build_export_spool(session, filters, meta, report_progress)
    except Exception as exc:
        session.close()
        export_jobs.fail(job, "Failed to build the export file")
        logger.exception("Export job %s could not be built", job_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build the export file",
        ) from exc

    def body() -> Iterator[bytes]:
        try:
            if spool is None:
                for chunk in iter_export_chunks(session, filters, meta, report_progress):
                    yield chunk
            else:
                for chunk in iter_spooled_chunks(spool):
                    yield chunk
            export_jobs.complete(job)
        except Exception as exc:  # pragma: no cover - defensive
            export_jobs.fail(job, str(exc))
            logger.exception("Export job %s aborted", job_id)
            raise
        finally:
            # A client that disconnects mid-stream leaves the spool file and the
            # session checked out; closing them here is the only thing that
            # reliably returns both to the pool and to the temp directory.
            if spool is not None:
                spool.close()
            session.close()

    headers = {
        "Content-Disposition": f'attachment; filename="{job.filename}"',
        "X-Export-Job-Id": job.job_id,
        "X-Export-Total-Rows": str(job.total_rows),
        "X-Content-Type-Options": "nosniff",
    }
    return StreamingResponse(body(), media_type=job.media_type, headers=headers)
