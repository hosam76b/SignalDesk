"""API endpoints for local Ollama content evaluation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.topic import PromptTemplate, Topic
from app.models.keyword import Keyword
from app.models.post import Post
from app.models.user import User
from app.core.deps import get_current_user, get_current_admin_user, get_current_topic_user
from app.services.ai_orchestrator import ai_orchestrator
from app.services.audit_service import record_audit
from app.services.ai_service import analyze_post_content, get_ai_status, ai_service
from app.services.knowledge_context import get_topic_knowledge_context
from app.services.media_processor import build_combined_text

router = APIRouter(prefix="/api/ai", tags=["AI Analysis"])


class AnalysisResponse(BaseModel):
    """Summary of a batch analysis operation."""

    success: bool
    processed: int
    analyzed: int
    updated: int
    failed: int
    risk_flagged: int = 0
    errors: list[dict[str, Any]]
    duration_seconds: float


class FlaggedPostResponse(BaseModel):
    """Safe analyst-facing representation of an evaluated post."""

    id: int
    source: str
    source_id: int
    platform: str
    author: str
    content: str
    post_url: str | None
    published_at: str | None
    scraped_at: str | None
    severity_level: str
    violence_category: str | None
    ai_summary: str | None
    is_flagged: bool


class FlaggedPostsResponse(BaseModel):
    """Paginated flagged-post response."""

    success: bool
    total_count: int
    returned: int
    limit: int
    offset: int
    posts: list[FlaggedPostResponse]


class PromptTemplateCreate(BaseModel):
    topic_id: int
    name: str = Field(min_length=1, max_length=255)
    template: str = Field(min_length=1)
    variables: str | None = None
    provider: str = "ollama"
    model_name: str = "qwen2.5:7b"
    is_active: bool = True


class PromptTemplateRead(BaseModel):
    id: int
    topic_id: int
    name: str
    template: str
    variables: str | None
    provider: str
    model_name: str
    is_active: bool
    created_by_id: int | None

    model_config = {"from_attributes": True}


class AIConnectionConfig(BaseModel):
    provider: str
    model: str
    base_url: str
    api_key: str | None = None


class AIConnectionRead(BaseModel):
    provider: str
    model: str
    base_url: str
    has_api_key: bool
    configured: bool


@router.get("/status")
def get_ai_status_endpoint() -> dict[str, Any]:
    """Expose the optional AI engine availability state to the frontend."""
    return get_ai_status()


@router.get("/config", response_model=AIConnectionRead)
def get_ai_config(_: User = Depends(get_current_admin_user)) -> dict[str, Any]:
    return ai_service.get_config()


@router.put("/config", response_model=AIConnectionRead)
def update_ai_config(payload: AIConnectionConfig, _: User = Depends(get_current_admin_user)) -> dict[str, Any]:
    try:
        return ai_service.configure(payload.provider, payload.model, payload.base_url, payload.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/config/test")
def test_ai_connection(_: User = Depends(get_current_admin_user)) -> dict[str, Any]:
    try:
        return ai_service.test_connection()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider connection failed: {exc}") from exc


@router.get("/config/models")
def fetch_ai_models(_: User = Depends(get_current_admin_user)) -> dict[str, Any]:
    try:
        models = ai_service.fetch_models()
        return {"provider": ai_service.get_config()["provider"], "models": models}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to fetch models: {exc}") from exc


@router.post("/analyze-pending", response_model=AnalysisResponse)
def analyze_pending_posts(
    batch_size: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
) -> AnalysisResponse:
    """Analyze one bounded batch of posts missing AI evaluation."""
    result = ai_orchestrator.process_unanalyzed_posts(db, batch_size=batch_size)
    return AnalysisResponse(**result)


@router.get("/flagged-posts", response_model=FlaggedPostsResponse)
def get_flagged_posts(
    severity: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FlaggedPostsResponse:
    """Retrieve flagged posts and posts with high or critical severity."""
    try:
        result = ai_orchestrator.get_flagged_posts(db, severity, limit, offset)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return FlaggedPostsResponse(**result)


@router.get("/topics/{topic_id}/prompts", response_model=list[PromptTemplateRead])
def list_prompt_templates(topic_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[PromptTemplate]:
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    if current_user.role == "super_admin":
        prompt_templates = db.query(PromptTemplate).filter(PromptTemplate.topic_id == topic_id).all()
    else:
        prompt_templates = db.query(PromptTemplate).filter(PromptTemplate.topic_id == topic_id, PromptTemplate.is_active == 1).all()
        if not prompt_templates and current_user.role not in {"topic_manager", "analyst", "observer"}:
            raise HTTPException(status_code=403, detail="No prompt access")
    return prompt_templates


@router.post("/topics/{topic_id}/prompts", response_model=PromptTemplateRead)
def create_prompt_template(topic_id: int, payload: PromptTemplateCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_topic_user)) -> PromptTemplate:
    if current_user.role not in {"super_admin", "topic_manager"}:
        raise HTTPException(status_code=403, detail="Prompt configuration requires topic manager privileges")
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    template = PromptTemplate(
        topic_id=topic_id,
        created_by_id=current_user.id,
        name=payload.name,
        template=payload.template,
        variables=payload.variables,
        provider=payload.provider,
        model_name=payload.model_name,
        is_active=1 if payload.is_active else 0,
    )
    db.add(template)
    record_audit(
        db,
        user_id=current_user.id,
        topic_id=topic_id,
        action="prompt_updated",
        entity_type="prompt_template",
        details={"name": payload.name},
    )
    db.commit()
    db.refresh(template)
    return template


@router.post("/topics/{topic_id}/prompts/test")
def test_prompt_template(topic_id: int, payload: PromptTemplateCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_topic_user)) -> dict[str, Any]:
    if current_user.role not in {"super_admin", "topic_manager"}:
        raise HTTPException(status_code=403, detail="Prompt testing requires topic manager privileges")
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")

    recent_posts = (
        db.query(Post)
        .filter(Post.topic_id == topic_id)
        .order_by(Post.scraped_at.desc(), Post.id.desc())
        .limit(20)
        .all()
    )
    post_samples: list[str] = []
    for post in recent_posts:
        combined_text = build_combined_text(post)
        if not combined_text:
            continue
        post_samples.append(
            "\n".join([
                f"- ID: {post.id}",
                f"  Platform: {post.platform}",
                f"  Author: {post.author}",
                f"  Published: {post.published_at.isoformat() if post.published_at else 'unknown'}",
                f"  Title: {post.title or ''}",
                f"  Content: {combined_text[:1200]}",
            ])
        )
        if len(post_samples) == 5:
            break

    if not post_samples:
        raise HTTPException(status_code=400, detail="No non-empty posts are available for this topic test")

    keyword_rows = (
        db.query(Keyword)
        .filter(Keyword.topic_id == topic_id, Keyword.is_active.is_(True))
        .order_by(Keyword.id.asc())
        .limit(50)
        .all()
    )
    context = {
        "topic_name": topic.title,
        "posts_content": "\n\n".join(post_samples),
        "keywords": ", ".join(keyword.word_or_phrase for keyword in keyword_rows) or "No active keywords configured.",
        "time_range": "last 24 hours",
        "knowledge_context": get_topic_knowledge_context(db, topic_id) or "No knowledge base documents for this topic.",
    }
    provider = payload.provider or "ollama"
    model_name = payload.model_name or "qwen2.5:7b"
    rendered = payload.template
    for key, value in context.items():
        rendered = rendered.replace(f"{{{key}}}", str(value))
    if "{posts_content}" not in payload.template:
        rendered = (
            f"{rendered}\n\n"
            "[Actual monitored content for this prompt test]\n"
            f"Topic: {context['topic_name']}\n"
            f"Time range: {context['time_range']}\n"
            f"Keywords: {context['keywords']}\n\n"
            f"Posts:\n{context['posts_content']}\n\n"
            f"Knowledge context:\n{context['knowledge_context']}"
        )
    summary = analyze_post_content(rendered)
    if not summary.get("success"):
        raise HTTPException(status_code=502, detail=summary.get("error") or "AI analysis failed")
    status = get_ai_status()
    status["provider"] = provider
    status["model"] = model_name
    return {"success": True, "rendered_prompt": rendered, "ai_status": status, "analysis": summary}
