"""
Report database model.
Represents generated monitoring reports with analysis summaries.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.session import Base


class Report(Base):
    """
    Model for generated monitoring reports.

    Attributes:
        id (int): Primary key.
        title (str): Report title/name.
        period_start (datetime): Start of the reporting period.
        period_end (datetime): End of the reporting period.
        generated_by_id (int): Foreign key to User who generated the report.
        summary_text (str): Text summary of findings.
        file_path (str): Path to the generated report file (PDF/HTML).
        created_at (datetime): When the report was generated.
        author (relationship): Reference to User who created this report.
    """

    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    generated_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    summary_text = Column(Text, nullable=True)
    file_path = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationship to User who generated this report
    # back_populates must match the relationship attribute name in User model
    author = relationship("User", back_populates="reports")

    def __repr__(self) -> str:
        return f"<Report(id={self.id}, title='{self.title}', created_at='{self.created_at}')>"

    def __str__(self) -> str:
        return f"{self.title} ({self.period_start.date()} to {self.period_end.date()})"

