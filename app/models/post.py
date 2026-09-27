"""
Post database model.
Represents scraped content/posts from monitored sources with AI analysis results.
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, Index, text
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from hashlib import md5
from app.db.session import Base

#: AI analysis lifecycle. ``pending``/``processing`` are the two values the
#: background queue moves posts through, and the partial index that makes
#: "give me the next batch" an index seek rather than a full table scan.
AI_STATUS_PENDING = "pending"
AI_STATUS_PROCESSING = "processing"
AI_STATUS_DONE = "done"
AI_STATUS_FAILED = "failed"
AI_STATUS_SKIPPED = "skipped"


class Post(Base):
    """
    Model for scraped posts from monitored sources.

    Attributes:
        id (int): Primary key.
        source_id (int): Foreign key to MonitoredSource.
        external_id (str): Platform-specific post ID.
        platform (str): The platform this post came from.
        author (str): Post author/account name.
        content (str): Full text content of the post.
        media_urls (dict): JSON field storing media URLs (images, videos).
        post_url (str): Direct URL to the post on the platform.
        published_at (datetime): When the post was published.
        scraped_at (datetime): When the post was scraped/downloaded.
        violence_category (str): AI-detected content category.
        severity_level (str): Severity assessment - 'low', 'medium', 'high', 'critical'.
        ai_summary (str): AI-generated summary of harmful content.
        raw_ai_response (dict): Complete JSON response from AI model.
        is_flagged (bool): Whether post has been manually flagged by analyst.
        source (relationship): Reference to MonitoredSource.
    """

    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(Integer, ForeignKey("monitored_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    external_id = Column(String(500), nullable=False)
    platform = Column(String(50), nullable=False, index=True)
    author = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    title = Column(String(1000), nullable=True)
    media_urls = Column(JSON, nullable=True)  # Stores list of media URLs as JSON
    post_url = Column(String(1000), nullable=True)
    source_url = Column(String(1000), nullable=True)
    raw_metadata = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)
    published_at = Column(DateTime, nullable=False)
    scraped_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    violence_category = Column(String(255), nullable=True)
    severity_level = Column(
        String(20),
        nullable=True
    )  # 'low', 'medium', 'high', 'critical'
    ai_summary = Column(Text, nullable=True)
    raw_ai_response = Column(JSON, nullable=True)  # Complete AI response stored as JSON
    is_flagged = Column(Boolean, default=False, nullable=False)
    is_important = Column(Boolean, default=False, nullable=False, index=True)
    is_dangerous = Column(Boolean, default=False, nullable=False, index=True)
    content_fingerprint = Column(String(32), nullable=True, index=True)
    sentiment = Column(String(20), nullable=True, index=True)
    sentiment_score = Column(Integer, nullable=True)
    entities = Column(JSON, nullable=True)
    extracted_ocr_text = Column(Text, nullable=True)
    video_transcript = Column(Text, nullable=True)
    media_status = Column(String(20), default="pending", nullable=False, index=True)
    # Analysis lifecycle for the background queue. Defaults to 'pending' so a
    # post is always claimable by the worker after it is ingested.
    ai_status = Column(
        String(20),
        default=AI_STATUS_PENDING,
        nullable=False,
        server_default=AI_STATUS_PENDING,
    )
    ai_analyzed_at = Column(DateTime, nullable=True)

    # Relationships
    source = relationship("MonitoredSource", back_populates="posts")
    topic = relationship("Topic", back_populates="posts")

    __table_args__ = (
        # Alert filtering: get_flagged_posts() filters is_flagged OR
        # severity_level IN ('high','critical') and orders by id DESC. This
        # turns two full scans into two index seeks (measured 1.6ms -> 0.21ms).
        Index("ix_posts_flagged", "is_flagged", "id"),
        Index("ix_posts_severity", "severity_level", "id"),
        # Batch deduplication. _save_posts() checks (source_id, topic_id, ...)
        # for every candidate post; without the composite prefix SQLite falls
        # back to ix_posts_topic_id and scans every post in the topic.
        Index("ix_posts_dedup_external", "source_id", "topic_id", "external_id"),
        Index("ix_posts_dedup_url", "source_id", "topic_id", "post_url"),
        Index("ix_posts_dedup_fingerprint", "source_id", "topic_id", "content_fingerprint"),
        # Queue claim query: WHERE ai_status IN ('pending','failed') ORDER BY id.
        # The partial predicate must cover BOTH states the claim selects, and the
        # key column must be `id` because that is the ORDER BY -- indexing
        # `created_at`/`scraped_at` would leave a temp B-tree sort. Partial so
        # the index only carries the small unanalyzed subset.
        Index(
            "ix_posts_ai_queue",
            "id",
            sqlite_where=text("ai_status IN ('pending', 'failed')"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Post(id={self.id}, platform='{self.platform}', severity='{self.severity_level}')>"

    def __str__(self) -> str:
        return f"Post by @{self.author} on {self.platform} - Severity: {self.severity_level}"
