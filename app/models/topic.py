"""Topic model for subject-driven monitoring isolation."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.session import Base


class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    created_by = relationship("User", back_populates="created_topics")
    user_topics = relationship("UserTopic", back_populates="topic", cascade="all, delete-orphan")
    permissions = relationship("TopicPermission", back_populates="topic", cascade="all, delete-orphan")
    prompt_templates = relationship("PromptTemplate", back_populates="topic", cascade="all, delete-orphan")
    sources = relationship("MonitoredSource", back_populates="topic", cascade="all, delete-orphan")
    keywords = relationship("Keyword", back_populates="topic", cascade="all, delete-orphan")
    posts = relationship("Post", back_populates="topic", cascade="all, delete-orphan")
    knowledge_documents = relationship("KnowledgeDocument", back_populates="topic", cascade="all, delete-orphan")


class UserTopic(Base):
    __tablename__ = "user_topics"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True)
    role = Column(String(50), nullable=False)

    user = relationship("User", back_populates="user_topics")
    topic = relationship("Topic", back_populates="user_topics")


class TopicPermission(Base):
    __tablename__ = "topic_permissions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), default="observer", nullable=False)
    can_view = Column(Integer, default=1, nullable=False)
    can_configure_prompts = Column(Integer, default=0, nullable=False)
    can_trigger_ai = Column(Integer, default=0, nullable=False)
    can_export = Column(Integer, default=0, nullable=False)

    user = relationship("User", back_populates="topic_permissions")
    topic = relationship("Topic", back_populates="permissions")


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    template = Column(Text, nullable=False)
    variables = Column(Text, nullable=True)
    provider = Column(String(50), default="ollama", nullable=False)
    model_name = Column(String(255), default="qwen2.5:7b", nullable=False)
    is_active = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    topic = relationship("Topic", back_populates="prompt_templates")
    created_by = relationship("User", back_populates="prompt_templates")