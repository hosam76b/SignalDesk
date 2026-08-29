"""Single-post retrieval with multi-modal media extraction status."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, normalize_role
from app.db.session import get_db
from app.models import Post, User, UserTopic

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
