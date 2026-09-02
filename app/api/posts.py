"""Single-post retrieval with multi-modal media extraction status."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, normalize_role
from app.db.session import get_db
from app.models import Post, User, UserTopic
from app.services.selected_posts_report import (
    generate_selected_posts_csv,
    generate_selected_posts_json,
    generate_selected_posts_pdf,
    generate_selected_posts_xlsx,
)

router = APIRouter(prefix="/api/v1/posts", tags=["Posts"])


class PostDetailOutput(BaseModel):
    id: int
    topic_id: int
    source_id: int
    platform: str
    author: str
    title: str | None
    content: str
    media_urls: list | None
    post_url: str | None
    published_at: datetime
    scraped_at: datetime
    severity_level: str | None
    sentiment: str | None
    sentiment_score: int | None
    entities: list | dict | None
    is_flagged: bool
    is_important: bool
    is_dangerous: bool
    extracted_ocr_text: str | None
    video_transcript: str | None
    media_status: str

    model_config = ConfigDict(from_attributes=True)


def _assert_topic_access(db: Session, current_user: User, topic_id: int) -> None:
    if normalize_role(current_user.role) == "super_admin":
        return
    assignment = db.query(UserTopic).filter(
        UserTopic.user_id == current_user.id,
        UserTopic.topic_id == topic_id,
    ).first()
    if assignment is None:
        raise HTTPException(status_code=403, detail="You do not have access to this post's topic")


@router.get("/{post_id}", response_model=PostDetailOutput)
def get_post(post_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    post = db.query(Post).filter(Post.id == post_id).first()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    _assert_topic_access(db, current_user, post.topic_id)
    return post


class SelectedPostsExportRequest(BaseModel):
    """Export a specific, user-picked set of posts (e.g. checkboxes in the intelligence feed)."""

    post_ids: list[int] = Field(..., min_length=1, max_length=500)
    lang: str = "en"  # only affects the PDF report; "ar" or "en"


def _load_selected_posts(db: Session, current_user: User, post_ids: list[int]) -> list[Post]:
    posts = db.query(Post).filter(Post.id.in_(post_ids)).all()
    found_ids = {post.id for post in posts}
    missing = [post_id for post_id in post_ids if post_id not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail=f"Posts not found: {missing}")
    for topic_id in {post.topic_id for post in posts}:
        _assert_topic_access(db, current_user, topic_id)
    order = {post_id: index for index, post_id in enumerate(post_ids)}
    posts.sort(key=lambda post: order[post.id])
    return posts


@router.post("/export/pdf")
def export_selected_posts_pdf(
    payload: SelectedPostsExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Export the given post IDs as a bilingual PDF report (matches the active UI language)."""
    posts = _load_selected_posts(db, current_user, payload.post_ids)
    lang = "ar" if payload.lang == "ar" else "en"
    pdf_bytes = generate_selected_posts_pdf(posts, lang, current_user.full_name)
    filename = f"selected_posts_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export/csv")
def export_selected_posts_csv(
    payload: SelectedPostsExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Export the given post IDs as CSV."""
    posts = _load_selected_posts(db, current_user, payload.post_ids)
    return Response(
        content=generate_selected_posts_csv(posts),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="selected_posts_export.csv"'},
    )


@router.post("/export/json")
def export_selected_posts_json(
    payload: SelectedPostsExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Export the given post IDs as JSON."""
    posts = _load_selected_posts(db, current_user, payload.post_ids)
    return Response(
        content=generate_selected_posts_json(posts),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="selected_posts_export.json"'},
    )


@router.post("/export/xlsx")
def export_selected_posts_xlsx(
    payload: SelectedPostsExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Export the given post IDs as a minimal .xlsx workbook."""
    posts = _load_selected_posts(db, current_user, payload.post_ids)
    return Response(
        content=generate_selected_posts_xlsx(posts),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="selected_posts_export.xlsx"'},
    )
