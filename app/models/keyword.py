"""
Keyword/phrase database model.
Represents keywords and phrases to monitor for in post content.
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.session import Base


class Keyword(Base):
    """
    Model for keywords and phrases to monitor.

    Attributes:
        id (int): Primary key.
        word_or_phrase (str): The keyword or phrase to search for.
        category (str): Category for organizing keywords (e.g., 'violence', 'child-safety', 'other').
        is_active (bool): Whether this keyword is currently active in monitoring.
        created_at (datetime): When this keyword was added.
    """

    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    word_or_phrase = Column(String(500), nullable=False, unique=True, index=True)
    category = Column(String(100), default="general", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    approval_status = Column(String(20), default="approved", nullable=False, index=True)
    proposed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    topic = relationship("Topic", back_populates="keywords")

    def __repr__(self) -> str:
        return f"<Keyword(id={self.id}, word='{self.word_or_phrase}', category='{self.category}')>"

    def __str__(self) -> str:
        return f"{self.word_or_phrase} [{self.category}]"
