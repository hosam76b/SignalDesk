"""Dynamic Spider & Topic Discovery Engine endpoints.

Exposes a configurable, asynchronous web spider that feeds accepted articles
directly into the Phase 1 relevance filter and Phase 2 local-LLM analysis pipeline.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin_user, get_current_user
from app.db.session import get_db
from app.models.topic import Topic
from app.models.user import User
from app.services.spider_service import spider_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/spider", tags=["Spider"])


class SpiderRunRequest(BaseModel):
    """Runtime parameters for a spider execution."""

    topic_id: int = Field(..., ge=1)
    search_topics: list[str] = Field(default_factory=list)
    target_keywords: list[str] = Field(default_factory=list)
    seed_urls: list[str] | None = None
    relevance_threshold: float = 30.0
    max_depth: int = Field(default=1, ge=1, le=3)
    proxy_enabled: bool = False

    @field_validator("relevance_threshold")
    @classmethod
    def _validate_threshold(cls, value: float) -> float:
        if not 0 <= value <= 100:
            raise ValueError("relevance_threshold must be between 0 and 100")
        return value


class SpiderRunResponse(BaseModel):
    run_id: str
    status: str
    message: str


class SpiderAddTopicRequest(BaseModel):
    """Dynamic topic/keyword injection into an active or queued run."""

    run_id: str
    search_topics: list[str] = Field(default_factory=list)
    target_keywords: list[str] = Field(default_factory=list)


class SpiderStopRequest(BaseModel):
    run_id: str


class SpiderStatusResponse(BaseModel):
    run_id: str
    status: str
    topic_id: int
    pages_crawled: int
    accepted: int
    discarded: int
    active_keywords: list[str]
    search_topics: list[str] = Field(default_factory=list)
    target_keywords: list[str] = Field(default_factory=list)
    seed_urls: list[str] = Field(default_factory=list)
    relevance_threshold: float = 30.0
    max_depth: int = 1
    proxy_enabled: bool = False
    errors: list[dict]
    started_at: str
    finished_at: str | None


class SpiderActiveStatusResponse(BaseModel):
    is_running: bool
    active_runs: int
    total_runs: int
    last_run_id: str | None
    last_status: str | None


@router.post(
    "/run",
    response_model=SpiderRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a dynamic spider run for a topic",
)
async def run_spider(
    payload: SpiderRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> SpiderRunResponse:
    """Launch an asynchronous crawl scoped to ``topic_id`` using the given keyword matrix."""
    if not db.query(Topic).filter(Topic.id == payload.topic_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    if not (payload.search_topics or payload.target_keywords or payload.seed_urls):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide at least one search topic, keyword, or seed URL",
        )

    # Seed URLs are fetched by the crawler with follow_redirects=True, so they
    # must clear the outbound policy before the run starts. Validating here
    # rather than inside the crawl keeps a bad seed from surfacing as a run
    # failure after it has already been stored.
    seed_urls = payload.seed_urls or []
    if seed_urls:
        from app.core.ssrf import UnsafeURLError, validate_url
        from config import settings

        try:
            seed_urls = [
                validate_url(
                    url,
                    allow_private=bool(getattr(settings, "allow_private_outbound_urls", False)),
                    allow_blocked_ports=bool(getattr(settings, "allow_blocked_ports_outbound", False)),
                )
                for url in seed_urls
            ]
        except UnsafeURLError as exc:
            logger.warning("Rejected spider seed URL: %s", exc)
            raise HTTPException(status_code=400, detail=f"Seed URL rejected: {exc}") from exc

    run = spider_orchestrator.create_run(
        topic_id=payload.topic_id,
        search_topics=payload.search_topics,
        target_keywords=payload.target_keywords,
        seed_urls=seed_urls,
        relevance_threshold=payload.relevance_threshold,
        max_depth=payload.max_depth,
        proxy_enabled=payload.proxy_enabled,
    )

    asyncio.create_task(spider_orchestrator.execute(run.run_id, seed_urls))
    message = (
        "Spider run started"
        if seed_urls
        else "Spider run started; discovering pages from the open web using the active keywords"
    )
    return SpiderRunResponse(run_id=run.run_id, status=run.status, message=message)


@router.post(
    "/add-topic",
    response_model=SpiderStatusResponse,
    summary="Inject a new topic/keywords into a running spider batch",
)
async def add_topic(
    payload: SpiderAddTopicRequest,
    current_user: User = Depends(get_current_admin_user),
) -> SpiderStatusResponse:
    """Append keywords to the active filtering matrix of an ongoing or queued run."""
    run = await spider_orchestrator.add_topic(
        payload.run_id, payload.search_topics, payload.target_keywords
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spider run not found")
    return SpiderStatusResponse(**run.to_status())


@router.post(
    "/stop",
    response_model=SpiderStatusResponse,
    summary="Stop an active or queued spider run",
)
async def stop_run(
    payload: SpiderStopRequest,
    current_user: User = Depends(get_current_admin_user),
) -> SpiderStatusResponse:
    """Request the run to halt after its current in-flight page batch finishes."""
    run = spider_orchestrator.request_stop(payload.run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spider run not found")
    return SpiderStatusResponse(**run.to_status())


@router.get(
    "/status/{run_id}",
    response_model=SpiderStatusResponse,
    summary="Get the live status of a spider run",
)
async def get_status(
    run_id: str,
    current_user: User = Depends(get_current_admin_user),
) -> SpiderStatusResponse:
    run = spider_orchestrator.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spider run not found")
    return SpiderStatusResponse(**run.to_status())


@router.get(
    "/runs",
    response_model=list[SpiderStatusResponse],
    summary="List recent spider runs",
)
async def list_runs(
    current_user: User = Depends(get_current_admin_user),
) -> list[SpiderStatusResponse]:
    return [SpiderStatusResponse(**item) for item in spider_orchestrator.list_runs()]


@router.get(
    "/active-status",
    response_model=SpiderActiveStatusResponse,
    summary="Lightweight spider activity indicator for any authenticated user",
)
async def get_active_status(
    current_user: User = Depends(get_current_user),
) -> SpiderActiveStatusResponse:
    return SpiderActiveStatusResponse(**spider_orchestrator.get_active_summary())
