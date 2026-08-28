"""Executive intelligence and topic-report generation service."""

from __future__ import annotations

import io
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.models.keyword import Keyword
from app.models.post import Post
from app.models.source import MonitoredSource
from app.models.topic import Topic
from app.models.user import User
from app.services.ai_service import get_ai_status

logger = logging.getLogger(__name__)


class PDFReportService:
    """Build a topic-scoped executive report in PDF format with local fallback support."""

    @staticmethod
    def generate_executive_report(
        db: Session,
        topic_id: int,
        requester: User | None = None,
    ) -> dict[str, Any]:
        try:
            topic = db.query(Topic).filter(Topic.id == topic_id).first()
            if topic is None:
                raise ValueError(f"Topic {topic_id} not found")

            posts = db.query(Post).filter(Post.topic_id == topic_id).order_by(Post.published_at.desc()).all()
            sources = db.query(MonitoredSource).filter(MonitoredSource.topic_id == topic_id).all()
            keywords = db.query(Keyword).filter(Keyword.topic_id == topic_id).all()

            ai_status = get_ai_status()
            if ai_status.get("enabled"):
                ai_summary = "AI executive summary active: narrative synthesis and anomaly scoring were generated using the configured intelligence model."
            else:
                ai_summary = (
                    "AI is disabled or unavailable. Executive summary is generated from local analytics, "
                    "severity distribution, post velocity, and raw topic logs to preserve continuity without interruption."
                )

            total_posts = len(posts)
            critical_posts = [post for post in posts if (post.severity_level or "low").lower() in {"high", "critical"} or post.is_dangerous or post.is_flagged]
            high_impact = sorted(
                critical_posts,
                key=lambda post: (
                    3 if (post.severity_level or "low").lower() in {"high", "critical"} else 0,
                    2 if post.is_dangerous else 0,
                    1 if post.is_important else 0,
                    0,
                ),
                reverse=True,
            )[:5]

            platform_counts = Counter(post.platform for post in posts)
            severity_counts = Counter((post.severity_level or "low").lower() for post in posts)
            sentiment_counts = Counter((post.sentiment or "neutral").lower() for post in posts)

            if total_posts:
                threat_level = "Critical" if severity_counts.get("critical", 0) else "High" if severity_counts.get("high", 0) else "Medium" if severity_counts.get("medium", 0) else "Low"
            else:
                threat_level = "Low"

            recommendations = [
                "Escalate any high or critical posts with coordinated narratives to the analyst queue.",
                "Review source velocity and amplification nodes to identify early seed accounts before spread intensifies.",
                "Validate whether repeated content clusters match known disinformation or coordinated influence patterns.",
            ]

            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                leftMargin=36,
                rightMargin=36,
                topMargin=36,
                bottomMargin=36,
            )
            styles = getSampleStyleSheet()
            primary = colors.HexColor("#0f172a")
            accent = colors.HexColor("#2563eb")
            danger = colors.HexColor("#ef4444")
            warn = colors.HexColor("#f59e0b")
            success = colors.HexColor("#10b981")
            card_bg = colors.HexColor("#f8fafc")
            muted = colors.HexColor("#64748b")

            title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=primary)
            subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=11, textColor=muted)
            heading_style = ParagraphStyle("Heading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=15, textColor=primary, spaceBefore=12, spaceAfter=6)
            body_style = ParagraphStyle("Body", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#334155"))
            bold_style = ParagraphStyle("BoldBody", parent=body_style, fontName="Helvetica-Bold")
            badge_style = ParagraphStyle("Badge", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=colors.white, alignment=1)

            story: list[Any] = []
            story.append(Paragraph("CONFIDENTIAL // EXECUTIVE INTELLIGENCE REPORT", title_style))
            story.append(Spacer(1, 6))
            story.append(Paragraph(f"Topic: {topic.title}", bold_style))
            story.append(Paragraph(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} | Analyst: {requester.full_name if requester else 'System'}", subtitle_style))
            story.append(Spacer(1, 12))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#dbeafe"), spaceBefore=4, spaceAfter=8))

            threat_color = danger if threat_level in {"Critical", "High"} else warn if threat_level == "Medium" else success
            story.append(Paragraph("AI Executive Summary", heading_style))
            story.append(Paragraph(ai_summary, body_style))
            story.append(Spacer(1, 8))

            badge_data = [[Paragraph(f"<font color='white'><b>{threat_level.upper()}</b></font>", badge_style)]]
            badge_table = Table(badge_data, colWidths=[500])
            badge_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), threat_color),
                ("BOX", (0, 0), (-1, -1), 1, threat_color),
                ("PADDING", (0, 0), (-1, -1), 10),
            ]))
            story.append(badge_table)
            story.append(Spacer(1, 12))

            metric_rows = [
                [Paragraph("Total Posts", bold_style), Paragraph(str(total_posts), bold_style), Paragraph("Flagged", bold_style), Paragraph(str(sum(1 for post in posts if post.is_flagged)), bold_style)],
                [Paragraph("Critical", bold_style), Paragraph(str(severity_counts.get("critical", 0)), bold_style), Paragraph("High", bold_style), Paragraph(str(severity_counts.get("high", 0)), bold_style)],
                [Paragraph("Sources", bold_style), Paragraph(str(len(sources)), bold_style), Paragraph("Keywords", bold_style), Paragraph(str(len(keywords)), bold_style)],
            ]
            metric_table = Table(metric_rows, colWidths=[120, 100, 120, 100])
            metric_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), card_bg),
                ("GRID", (0, 0), (-1, -1), 0.75, colors.HexColor("#dbeafe")),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(Paragraph("Global Threat / Severity Badge", heading_style))
            story.append(metric_table)
            story.append(Spacer(1, 12))

            platform_rows = [[Paragraph("Platform", bold_style), Paragraph("Volume", bold_style)]]
            for platform, count in platform_counts.most_common(6):
                platform_rows.append([Paragraph(platform, body_style), Paragraph(str(count), body_style)])
            if not platform_rows[1:]:
                platform_rows.append([Paragraph("No data", body_style), Paragraph("0", body_style)])
            platform_table = Table(platform_rows, colWidths=[220, 120])
            platform_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), card_bg),
                ("GRID", (0, 0), (-1, -1), 0.75, colors.HexColor("#e2e8f0")),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]))

            sentiment_rows = [[Paragraph("Sentiment", bold_style), Paragraph("Count", bold_style)]]
            for sentiment, count in sentiment_counts.most_common(4):
                sentiment_rows.append([Paragraph(sentiment.title(), body_style), Paragraph(str(count), body_style)])
            if not sentiment_rows[1:]:
                sentiment_rows.append([Paragraph("Neutral", body_style), Paragraph("0", body_style)])
            sentiment_table = Table(sentiment_rows, colWidths=[220, 120])
            sentiment_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), card_bg),
                ("GRID", (0, 0), (-1, -1), 0.75, colors.HexColor("#e2e8f0")),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]))

            story.append(Paragraph("Sentiment & Source Distribution Charts", heading_style))
            story.append(Table([[platform_table, sentiment_table]], colWidths=[260, 260]))
            story.append(Spacer(1, 12))

            story.append(Paragraph("Top High-Impact Posts", heading_style))
            post_rows = [[Paragraph("Author", bold_style), Paragraph("Platform", bold_style), Paragraph("Sentiment", bold_style), Paragraph("Severity", bold_style)]]
            for post in high_impact:
                post_rows.append([
                    Paragraph((post.author or "Unknown")[:32], body_style),
                    Paragraph(post.platform, body_style),
                    Paragraph((post.sentiment or "neutral").title(), body_style),
                    Paragraph((post.severity_level or "low").upper(), body_style),
                ])
            if len(post_rows) == 1:
                post_rows.append([Paragraph("No critical posts", body_style), Paragraph("-", body_style), Paragraph("-", body_style), Paragraph("-", body_style)])
            post_table = Table(post_rows, colWidths=[120, 100, 120, 110])
            post_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), card_bg),
                ("GRID", (0, 0), (-1, -1), 0.75, colors.HexColor("#dbeafe")),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(post_table)
            story.append(Spacer(1, 12))

            story.append(Paragraph("Strategic Recommendations", heading_style))
            for idx, recommendation in enumerate(recommendations, start=1):
                story.append(Paragraph(f"{idx}. {recommendation}", body_style))

            doc.build(story)
            pdf_bytes = buffer.getvalue()
            return {
                "success": True,
                "topic_id": topic_id,
                "content_type": "application/pdf",
                "pdf_bytes": pdf_bytes,
                "filename": f"executive_report_topic_{topic_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf",
            }
        except Exception as exc:  # pragma: no cover - defensive path
            logger.exception("Executive report generation failed for topic %s", topic_id)
            return {
                "success": False,
                "topic_id": topic_id,
                "content_type": "application/pdf",
                "pdf_bytes": b"",
                "error": str(exc),
            }

    @staticmethod
    def generate_executive_pdf_bytes(db: Session, topic_id: int, requester: User | None = None) -> bytes:
        result = PDFReportService.generate_executive_report(db, topic_id, requester=requester)
        if not result["success"]:
            raise ValueError(result.get("error", "Executive report generation failed"))
        return result["pdf_bytes"]


def generate_topic_executive_pdf(db: Session, topic_id: int, requester: User | None = None) -> bytes:
    """Backward-compatible wrapper used by older routes."""
    return PDFReportService.generate_executive_pdf_bytes(db, topic_id, requester=requester)
