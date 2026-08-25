"""Topic model for subject-driven monitoring isolation."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.models.enums import TopicRole


class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    created_by = relationship("User", back_populates="created_topics")
    user_topics = relationship("UserTopic", back_populates="topic", cascade="all, delete-orphan")
    sources = relationship("MonitoredSource", back_populates="topic", cascade="all, delete-orphan")
    keywords = relationship("Keyword", back_populates="topic", cascade="all, delete-orphan")
    posts = relationship("Post", back_populates="topic", cascade="all, delete-orphan")


class UserTopic(Base):
    __tablename__ = "user_topics"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True)
    role = Column(
        SqlEnum(TopicRole, values_callable=lambda roles: [role.value for role in roles],
                native_enum=False, create_constraint=True),
        nullable=False,
    )

    user = relationship("User", back_populates="user_topics")
    topic = relationship("Topic", back_populates="user_topics")