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
from app.services.pdf_branding import ensure_arabic_font, shape_arabic

logger = logging.getLogger(__name__)


class PDFReportService:
    """Build a topic-scoped executive report in PDF format with local fallback support."""

    @staticmethod
    def generate_executive_report(
        db: Session,
        topic_id: int,
        requester: User | None = None,
        language: str = "en",
    ) -> dict[str, Any]:
        try:
            is_arabic = language.lower() == "ar"

            def text(english: str, arabic: str) -> str:
                return shape_arabic(arabic) if is_arabic else english

            def value(raw_value: Any) -> str:
                rendered = str(raw_value)
                return shape_arabic(rendered) if is_arabic else rendered

            topic = db.query(Topic).filter(Topic.id == topic_id).first()
            if topic is None:
                raise ValueError(f"Topic {topic_id} not found")

            posts = db.query(Post).filter(Post.topic_id == topic_id).order_by(Post.published_at.desc()).all()
            sources = db.query(MonitoredSource).join(Post).filter(Post.topic_id == topic_id).distinct().all()
            keywords = db.query(Keyword).filter(Keyword.topic_id == topic_id).all()

            ai_status = get_ai_status()
            if ai_status.get("enabled"):
                ai_summary = text(
                    "AI executive summary active: narrative synthesis and anomaly scoring were generated using the configured intelligence model.",
                    "ملخص الذكاء الاصطناعي مفعّل: تم إنشاء التحليل السردي وتقييم الحالات الشاذة باستخدام نموذج الاستخبارات المهيأ.",
                )
            else:
                ai_summary = text(
                    "AI is disabled or unavailable. Executive summary is generated from local analytics, severity distribution, post velocity, and raw topic logs to preserve continuity without interruption.",
                    "الذكاء الاصطناعي معطل أو غير متاح. تم إنشاء الملخص التنفيذي من التحليلات المحلية وتوزيع الشدة وسرعة المنشورات وسجلات الموضوع الخام لضمان استمرارية العمل.",
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
                text("Escalate any high or critical posts with coordinated narratives to the analyst queue.", "قم بتصعيد أي منشورات عالية أو حرجة ذات سرديات منسقة إلى قائمة انتظار المحلل."),
                text("Review source velocity and amplification nodes to identify early seed accounts before spread intensifies.", "راجع سرعة المصادر وعقد التضخيم لتحديد الحسابات البادئة مبكرًا قبل تصاعد الانتشار."),
                text("Validate whether repeated content clusters match known disinformation or coordinated influence patterns.", "تحقق مما إذا كانت مجموعات المحتوى المتكرر تتطابق مع أنماط التضليل المعروفة أو التأثير المنسق."),
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
            regular_font, bold_font = ensure_arabic_font() if is_arabic else ("Helvetica", "Helvetica-Bold")
            alignment = 2 if is_arabic else 0

            title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontName=bold_font, fontSize=20, leading=24, textColor=primary, alignment=alignment)
            subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontName=regular_font, fontSize=9, leading=11, textColor=muted, alignment=alignment)
            heading_style = ParagraphStyle("Heading", parent=styles["Heading2"], fontName=bold_font, fontSize=13, leading=15, textColor=primary, spaceBefore=12, spaceAfter=6, alignment=alignment)
            body_style = ParagraphStyle("Body", parent=styles["Normal"], fontName=regular_font, fontSize=9, leading=12, textColor=colors.HexColor("#334155"), alignment=alignment)
            bold_style = ParagraphStyle("BoldBody", parent=body_style, fontName=bold_font)
            badge_style = ParagraphStyle("Badge", parent=styles["Normal"], fontName=bold_font, fontSize=10, leading=12, textColor=colors.white, alignment=1)

            story: list[Any] = []
            story.append(Paragraph(text("CONFIDENTIAL // EXECUTIVE INTELLIGENCE REPORT", "سري // تقرير الاستخبارات التنفيذي"), title_style))
            story.append(Spacer(1, 6))
            story.append(Paragraph(text(f"Topic: {topic.title}", f"الموضوع: {topic.title}"), bold_style))
            generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            analyst = requester.full_name if requester else ("النظام" if is_arabic else "System")
            story.append(Paragraph(text(f"Generated: {generated_at} | Analyst: {analyst}", f"تاريخ الإنشاء: {generated_at} | المحلل: {analyst}"), subtitle_style))
            story.append(Spacer(1, 12))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#dbeafe"), spaceBefore=4, spaceAfter=8))

            threat_color = danger if threat_level in {"Critical", "High"} else warn if threat_level == "Medium" else success
            story.append(Paragraph(text("AI Executive Summary", "الملخص التنفيذي بالذكاء الاصطناعي"), heading_style))
            story.append(Paragraph(ai_summary, body_style))
            story.append(Spacer(1, 8))

            threat_label = {
                "Critical": text("CRITICAL", "حرج"),
                "High": text("HIGH", "عالٍ"),
                "Medium": text("MEDIUM", "متوسط"),
                "Low": text("LOW", "منخفض"),
            }[threat_level]
            badge_data = [[Paragraph(threat_label, badge_style)]]
            badge_table = Table(badge_data, colWidths=[500])
            badge_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), threat_color),
                ("BOX", (0, 0), (-1, -1), 1, threat_color),
                ("PADDING", (0, 0), (-1, -1), 10),
            ]))
            story.append(badge_table)
            story.append(Spacer(1, 12))

            metric_rows = [
                [Paragraph(text("Total Posts", "إجمالي المنشورات"), bold_style), Paragraph(str(total_posts), bold_style), Paragraph(text("Flagged", "المعلّمة"), bold_style), Paragraph(str(sum(1 for post in posts if post.is_flagged)), bold_style)],
                [Paragraph(text("Critical", "حرجة"), bold_style), Paragraph(str(severity_counts.get("critical", 0)), bold_style), Paragraph(text("High", "عالية"), bold_style), Paragraph(str(severity_counts.get("high", 0)), bold_style)],
                [Paragraph(text("Sources", "المصادر"), bold_style), Paragraph(str(len(sources)), bold_style), Paragraph(text("Keywords", "الكلمات المفتاحية"), bold_style), Paragraph(str(len(keywords)), bold_style)],
            ]
            metric_table = Table(metric_rows, colWidths=[120, 100, 120, 100])
            metric_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), card_bg),
                ("GRID", (0, 0), (-1, -1), 0.75, colors.HexColor("#dbeafe")),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(Paragraph(text("Global Threat / Severity Badge", "مؤشر التهديد العام ومستوى الخطورة"), heading_style))
            story.append(metric_table)
            story.append(Spacer(1, 12))

            platform_rows = [[Paragraph(text("Platform", "المنصة"), bold_style), Paragraph(text("Volume", "الحجم"), bold_style)]]
            for platform, count in platform_counts.most_common(6):
                platform_rows.append([Paragraph(value(platform), body_style), Paragraph(str(count), body_style)])
            if not platform_rows[1:]:
                platform_rows.append([Paragraph(text("No data", "لا توجد بيانات"), body_style), Paragraph("0", body_style)])
            platform_table = Table(platform_rows, colWidths=[220, 120])
            platform_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), card_bg),
                ("GRID", (0, 0), (-1, -1), 0.75, colors.HexColor("#e2e8f0")),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]))

            sentiment_rows = [[Paragraph(text("Sentiment", "المشاعر"), bold_style), Paragraph(text("Count", "العدد"), bold_style)]]
            sentiment_labels = {
                "positive": text("Positive", "إيجابي"),
                "negative": text("Negative", "سلبي"),
                "neutral": text("Neutral", "محايد"),
            }
            for sentiment, count in sentiment_counts.most_common(4):
                sentiment_rows.append([Paragraph(sentiment_labels.get(sentiment, value(sentiment.title())), body_style), Paragraph(str(count), body_style)])
            if not sentiment_rows[1:]:
                sentiment_rows.append([Paragraph(text("Neutral", "محايد"), body_style), Paragraph("0", body_style)])
            sentiment_table = Table(sentiment_rows, colWidths=[220, 120])
            sentiment_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), card_bg),
                ("GRID", (0, 0), (-1, -1), 0.75, colors.HexColor("#e2e8f0")),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]))

            story.append(Paragraph(text("Sentiment & Source Distribution Charts", "توزيع المشاعر والمصادر"), heading_style))
            story.append(Table([[platform_table, sentiment_table]], colWidths=[260, 260]))
            story.append(Spacer(1, 12))

            story.append(Paragraph(text("Top High-Impact Posts", "أبرز المنشورات عالية التأثير"), heading_style))
            post_rows = [[Paragraph(text("Author", "الكاتب"), bold_style), Paragraph(text("Platform", "المنصة"), bold_style), Paragraph(text("Sentiment", "المشاعر"), bold_style), Paragraph(text("Severity", "الخطورة"), bold_style)]]
            for post in high_impact:
                post_sentiment = (post.sentiment or "neutral").lower()
                post_severity = (post.severity_level or "low").lower()
                severity_label = {
                    "critical": text("CRITICAL", "حرج"),
                    "high": text("HIGH", "عالٍ"),
                    "medium": text("MEDIUM", "متوسط"),
                    "low": text("LOW", "منخفض"),
                }.get(post_severity, value(post_severity.upper()))
                post_rows.append([
                    Paragraph(value((post.author or ("غير معروف" if is_arabic else "Unknown"))[:32]), body_style),
                    Paragraph(value(post.platform), body_style),
                    Paragraph(sentiment_labels.get(post_sentiment, value(post_sentiment.title())), body_style),
                    Paragraph(severity_label, body_style),
                ])
            if len(post_rows) == 1:
                post_rows.append([Paragraph(text("No critical posts", "لا توجد منشورات حرجة"), body_style), Paragraph("-", body_style), Paragraph("-", body_style), Paragraph("-", body_style)])
            post_table = Table(post_rows, colWidths=[120, 100, 120, 110])
            post_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), card_bg),
                ("GRID", (0, 0), (-1, -1), 0.75, colors.HexColor("#dbeafe")),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(post_table)
            story.append(Spacer(1, 12))

            story.append(Paragraph(text("Strategic Recommendations", "التوصيات الاستراتيجية"), heading_style))
            for idx, recommendation in enumerate(recommendations, start=1):
                story.append(Paragraph(f"{recommendation} .{idx}" if is_arabic else f"{idx}. {recommendation}", body_style))

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
    def generate_executive_pdf_bytes(
        db: Session,
        topic_id: int,
        requester: User | None = None,
        language: str = "en",
    ) -> bytes:
        result = PDFReportService.generate_executive_report(db, topic_id, requester=requester, language=language)
        if not result["success"]:
            raise ValueError(result.get("error", "Executive report generation failed"))
        return result["pdf_bytes"]


def generate_topic_executive_pdf(
    db: Session,
    topic_id: int,
    requester: User | None = None,
    language: str = "en",
) -> bytes:
    """Backward-compatible wrapper used by older routes."""
    return PDFReportService.generate_executive_pdf_bytes(db, topic_id, requester=requester, language=language)
