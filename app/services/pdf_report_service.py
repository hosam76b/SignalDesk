"""Automated Executive Intelligence PDF Report Generator using ReportLab."""

from __future__ import annotations

import io
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session

from app.models.keyword import Keyword
from app.models.post import Post
from app.models.source import MonitoredSource
from app.models.topic import Topic
from app.models.user import User
from app.models.knowledge import KnowledgeDocument

logger = logging.getLogger(__name__)


class NumberedCanvas(colors.Color):
    """Canvas helper for running header and page numbering."""


def sanitize_text(text: Any) -> str:
    """Ensure text is safe for ReportLab Paragraphs and XML rendering."""
    if text is None:
        return ""
    val = str(text)
    val = val.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return val.strip()


def generate_topic_executive_pdf(
    db: Session,
    topic_id: int,
    requester: User | None = None,
) -> bytes:
    """Generate an Executive Intelligence PDF Report for a given topic."""
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if topic is None:
        raise ValueError(f"Topic {topic_id} not found")

    # Gather data
    posts = db.query(Post).filter(Post.topic_id == topic_id).all()
    sources = db.query(MonitoredSource).join(Post).filter(Post.topic_id == topic_id).distinct().all()
    keywords = db.query(Keyword).filter(Keyword.topic_id == topic_id).all()

    total_posts = len(posts)
    flagged_posts = sum(1 for p in posts if p.is_flagged)
    dangerous_posts = sum(1 for p in posts if p.is_dangerous or p.severity_level == "critical")
    important_posts = sum(1 for p in posts if p.is_important or p.severity_level == "high")

    # Platform counts
    platform_counter = Counter(p.platform for p in posts)
    severity_counter = Counter(p.severity_level or "unclassified" for p in posts)
    sentiment_counter = Counter(p.sentiment or "neutral" for p in posts)

    # Categories
    category_counter = Counter(p.violence_category for p in posts if p.violence_category)

    # High severity posts
    critical_posts = [
        p for p in posts if p.severity_level in ("critical", "high") or p.is_dangerous or p.is_flagged
    ][:8]

    # PDF Document setup
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

    # Custom styles
    primary_color = colors.HexColor("#0f172a")  # Slate 900
    accent_color = colors.HexColor("#3b82f6")   # Blue 500
    danger_color = colors.HexColor("#ef4444")   # Red 500
    muted_color = colors.HexColor("#64748b")    # Slate 500
    card_bg = colors.HexColor("#f8fafc")        # Slate 50

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        textColor=primary_color,
        fontName="Helvetica-Bold",
    )
    subtitle_style = ParagraphStyle(
        "DocSubTitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=muted_color,
        fontName="Helvetica",
    )
    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        textColor=primary_color,
        fontName="Helvetica-Bold",
        spaceBefore=12,
        spaceAfter=6,
    )
    normal_style = ParagraphStyle(
        "StandardText",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
        fontName="Helvetica",
    )
    bold_style = ParagraphStyle(
        "BoldText",
        parent=normal_style,
        fontName="Helvetica-Bold",
    )
    banner_style = ParagraphStyle(
        "BannerText",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.white,
        fontName="Helvetica-Bold",
        alignment=1,  # Center
    )

    story = []

    # 1. Header Banner
    banner_table = Table(
        [[Paragraph("CONFIDENTIAL // DIGITAL MEDIA INTELLIGENCE REPORT", banner_style)]],
        colWidths=[522],
    )
    banner_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), primary_color),
        ("PADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 12))

    # 2. Topic Title & Metadata
    gen_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    author_name = requester.full_name if requester else "System Automation"

    header_data = [
        [
            Paragraph(f"Topic: {sanitize_text(topic.title)}", title_style),
            Paragraph(f"<b>Generated:</b> {gen_time}<br/><b>Auditor:</b> {sanitize_text(author_name)}", subtitle_style),
        ]
    ]
    header_table = Table(header_data, colWidths=[340, 182])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(header_table)

    if topic.description:
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<i>Scope: {sanitize_text(topic.description)}</i>", subtitle_style))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceBefore=2, spaceAfter=8))

    # 3. Key Metrics Table (KPI Grid)
    story.append(Paragraph("1. EXECUTIVE METRICS &amp; RISK PROFILE", heading_style))

    kpi_data = [
        [
            Paragraph("<b>Total Posts</b>", normal_style),
            Paragraph("<b>Flagged Threats</b>", normal_style),
            Paragraph("<b>Critical Signals</b>", normal_style),
            Paragraph("<b>Active Sources</b>", normal_style),
            Paragraph("<b>Keywords</b>", normal_style),
        ],
        [
            Paragraph(f"<font size=14 color='#0f172a'><b>{total_posts}</b></font>", bold_style),
            Paragraph(f"<font size=14 color='#f59e0b'><b>{flagged_posts}</b></font>", bold_style),
            Paragraph(f"<font size=14 color='#ef4444'><b>{dangerous_posts}</b></font>", bold_style),
            Paragraph(f"<font size=14 color='#3b82f6'><b>{len(sources)}</b></font>", bold_style),
            Paragraph(f"<font size=14 color='#64748b'><b>{len(keywords)}</b></font>", bold_style),
        ],
    ]
    kpi_table = Table(kpi_data, colWidths=[104, 104, 104, 104, 106])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), card_bg),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 12))

    # 4. Threat & Severity Breakdown + Platform Volume (Two Column Tables)
    story.append(Paragraph("2. PLATFORM VOLUME &amp; SEVERITY DISTRIBUTION", heading_style))

    platform_rows = [
        [Paragraph("<b>Platform</b>", bold_style), Paragraph("<b>Posts</b>", bold_style), Paragraph("<b>Share</b>", bold_style)]
    ]
    for plat, count in platform_counter.most_common(6):
        pct = f"{(count / total_posts * 100):.1f}%" if total_posts else "0%"
        platform_rows.append([Paragraph(plat.capitalize(), normal_style), Paragraph(str(count), normal_style), Paragraph(pct, normal_style)])
    if len(platform_rows) == 1:
        platform_rows.append([Paragraph("No posts", normal_style), Paragraph("0", normal_style), Paragraph("0%", normal_style)])

    plat_table = Table(platform_rows, colWidths=[100, 80, 70])
    plat_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("PADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    severity_rows = [
        [Paragraph("<b>Severity</b>", bold_style), Paragraph("<b>Count</b>", bold_style), Paragraph("<b>Sentiment</b>", bold_style)]
    ]
    for sev in ("critical", "high", "medium", "low"):
        cnt = severity_counter.get(sev, 0)
        col = "#ef4444" if sev == "critical" else "#f97316" if sev == "high" else "#eab308" if sev == "medium" else "#22c55e"
        severity_rows.append([
            Paragraph(f"<font color='{col}'><b>{sev.upper()}</b></font>", normal_style),
            Paragraph(str(cnt), normal_style),
            Paragraph(f"{sentiment_counter.get(sev, '-')}", normal_style),
        ])

    sev_table = Table(severity_rows, colWidths=[90, 80, 82])
    sev_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("PADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    two_col = Table([[plat_table, sev_table]], colWidths=[260, 262])
    two_col.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(two_col)
    story.append(Spacer(1, 12))

    # 5. Top Threat Categories & Active Monitored Sources
    if category_counter:
        story.append(Paragraph("3. DETECTED THREAT CATEGORIES", heading_style))
        cat_data = [[Paragraph("<b>Category</b>", bold_style), Paragraph("<b>Occurrences</b>", bold_style)]]
        for cat, cnt in category_counter.most_common(5):
            cat_data.append([Paragraph(cat.replace("_", " ").title(), normal_style), Paragraph(str(cnt), normal_style)])
        cat_table = Table(cat_data, colWidths=[350, 172])
        cat_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(cat_table)
        story.append(Spacer(1, 10))

    # 6. Critical & High Priority Alerts Listing
    story.append(Paragraph("4. CRITICAL &amp; HIGH-SEVERITY ALERTS", heading_style))
    if critical_posts:
        alert_rows = [
            [
                Paragraph("<b>ID</b>", bold_style),
                Paragraph("<b>Platform &amp; Author</b>", bold_style),
                Paragraph("<b>Severity</b>", bold_style),
                Paragraph("<b>AI Summary / Content</b>", bold_style),
                Paragraph("<b>Date</b>", bold_style),
            ]
        ]
        for post in critical_posts:
            summary = post.ai_summary or (post.content[:150] + "...")
            col = "#ef4444" if post.severity_level == "critical" or post.is_dangerous else "#f97316"
            date_str = post.published_at.strftime("%m-%d %H:%M") if post.published_at else "-"
            alert_rows.append([
                Paragraph(f"#{post.id}", normal_style),
                Paragraph(f"{post.platform.capitalize()}<br/>@{sanitize_text(post.author[:20])}", normal_style),
                Paragraph(f"<font color='{col}'><b>{(post.severity_level or 'alert').upper()}</b></font>", normal_style),
                Paragraph(sanitize_text(summary[:200]), normal_style),
                Paragraph(date_str, normal_style),
            ])

        alert_table = Table(alert_rows, colWidths=[36, 110, 66, 230, 80])
        alert_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(KeepTogether(alert_table))
    else:
        story.append(Paragraph("<i>No critical or high-severity threat posts detected in this topic.</i>", normal_style))

    knowledge_docs = db.query(KnowledgeDocument).filter(KnowledgeDocument.topic_id == topic_id).order_by(KnowledgeDocument.created_at.desc()).limit(10).all()
    if knowledge_docs:
        story.append(Spacer(1, 14))
        story.append(Paragraph("5. KNOWLEDGE BASE REFERENCES USED IN ANALYSIS", heading_style))
        for doc in knowledge_docs:
            story.append(Paragraph(f"&bull; {sanitize_text(doc.title)} ({sanitize_text(doc.file_type)})", normal_style))

    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceBefore=4, spaceAfter=8))
    story.append(Paragraph(
        "Confidential document generated by Media Monitoring &amp; Intelligence Platform. All rights reserved.",
        subtitle_style,
    ))

    # Build PDF
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

