"""
Monitored source database model.
Represents social media platforms and URLs being monitored for content.
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.session import Base


class MonitoredSource(Base):
    """
    Model for social media sources being monitored.

    Attributes:
        id (int): Primary key.
        platform (str): Social media platform - 'facebook', 'x', 'reddit', 'youtube', 'instagram', 'rss'.
        name (str): Friendly name/description of the source.
        url_or_handle (str): URL, account handle, or RSS feed URL.
        is_active (bool): Whether this source is currently being monitored.
        last_scraped_at (datetime): Timestamp of last successful scrape.
        created_at (datetime): When this source was added.
        posts (relationship): Posts from this source.
    """

    __tablename__ = "monitored_sources"
    __table_args__ = (
        UniqueConstraint("url_or_handle", name="uq_monitored_sources_url_or_handle"),
    )

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(
        String(50),
        nullable=False,
        index=True
    )  # 'facebook', 'x', 'reddit', 'youtube', 'instagram', 'rss'
    name = Column(String(255), nullable=False)
    url_or_handle = Column(String(500), nullable=False)
    target_type = Column(String(30), default="url", nullable=False)
    apify_actor_id = Column(String(255), nullable=True)
    status = Column(String(20), default="active", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    approval_status = Column(String(20), default="approved", nullable=False, index=True)
    proposed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    last_scraped_at = Column(DateTime, nullable=True)
    last_error = Column(String(1000), nullable=True)
    last_error_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    posts = relationship("Post", back_populates="source", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<MonitoredSource(id={self.id}, platform='{self.platform}', name='{self.name}')>"

    def __str__(self) -> str:
        return f"{self.platform.upper()}: {self.name} ({self.url_or_handle})"
