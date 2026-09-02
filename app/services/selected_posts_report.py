"""Export a user-selected set of posts (e.g. from the intelligence feed) as PDF/CSV/JSON/XLSX."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from xml.sax.saxutils import escape
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.post import Post
from app.services.pdf_branding import draw_report_footer, ensure_arabic_font, shape_arabic
from app.services.xlsx_writer import build_minimal_xlsx

LABELS = {
    "ar": {
        "title": "تقرير الأخبار المحددة",
        "generated": "تاريخ الإنشاء",
        "analyst": "المحلل",
        "count": "عدد الأخبار المحددة",
        "headers": ["#", "المنصة", "الكاتب", "الخطورة", "التاريخ", "المحتوى"],
        "no_content": "لا يوجد محتوى",
        "footer": "SignalDesk — منصة المراقبة والاستخبارات الرقمية",
        "unanalyzed": "غير محلل",
        "page": "صفحة",
    },
    "en": {
        "title": "Selected News Report",
        "generated": "Generated",
        "analyst": "Analyst",
        "count": "Selected items",
        "headers": ["#", "Platform", "Author", "Severity", "Date", "Content"],
        "no_content": "No content",
        "footer": "SignalDesk \u2014 Threat Intelligence & Media Monitoring Platform",
        "unanalyzed": "Unanalyzed",
        "page": "Page",
    },
}

_PDF_COL_WIDTHS = [22, 55, 80, 55, 75, 235]


def generate_selected_posts_pdf(posts: list[Post], lang: str, requester_name: str) -> bytes:
    """Build a bilingual PDF report for exactly the given posts, with the app logo in the footer."""
    lang = lang if lang in LABELS else "en"
    labels = LABELS[lang]
    is_ar = lang == "ar"
    font_regular, font_bold = ensure_arabic_font() if is_ar else ("Helvetica", "Helvetica-Bold")

    def t(text: str) -> str:
        return shape_arabic(text) if is_ar else text

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=48,
    )
    styles = getSampleStyleSheet()
    primary = colors.HexColor("#0f172a")
    muted = colors.HexColor("#64748b")
    card_bg = colors.HexColor("#f8fafc")
    align = 2 if is_ar else 0  # ReportLab alignment: 0=left, 2=right

    title_style = ParagraphStyle("SelTitle", parent=styles["Heading1"], fontName=font_bold, fontSize=18, leading=22, textColor=primary, alignment=align)
    subtitle_style = ParagraphStyle("SelSub", parent=styles["Normal"], fontName=font_regular, fontSize=9, leading=12, textColor=muted, alignment=align)
    body_style = ParagraphStyle("SelBody", parent=styles["Normal"], fontName=font_regular, fontSize=8.5, leading=11, textColor=colors.HexColor("#334155"), alignment=align)
    bold_style = ParagraphStyle("SelBold", parent=body_style, fontName=font_bold)

    story: list[Any] = []
    story.append(Paragraph(t(labels["title"]), title_style))
    gen_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    story.append(Paragraph(t(f"{labels['generated']}: {gen_time} | {labels['analyst']}: {requester_name}"), subtitle_style))
    story.append(Paragraph(t(f"{labels['count']}: {len(posts)}"), subtitle_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceBefore=2, spaceAfter=10))

    rows: list[list[Any]] = [[Paragraph(f"<b>{t(header)}</b>", bold_style) for header in labels["headers"]]]
    for index, post in enumerate(posts, start=1):
        content = post.content or post.ai_summary or labels["no_content"]
        date_str = post.published_at.strftime("%Y-%m-%d %H:%M") if post.published_at else "-"
        severity = post.severity_level or labels["unanalyzed"]
        rows.append([
            Paragraph(str(index), body_style),
            Paragraph(t(post.platform or "-"), body_style),
            Paragraph(t(post.author or "-"), body_style),
            Paragraph(t(severity), body_style),
            Paragraph(date_str, body_style),
            Paragraph(t(escape(content)), body_style),
        ])

    table = Table(rows, colWidths=_PDF_COL_WIDTHS, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), card_bg),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("PADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(table)

    def footer(canvas: Any, pdf_doc: Any) -> None:
        draw_report_footer(canvas, pdf_doc, labels["footer"], labels["page"])

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def _post_rows(posts: list[Post]) -> list[dict[str, Any]]:
    return [
        {
            "id": post.id,
            "topic_id": post.topic_id,
            "platform": post.platform,
            "author": post.author,
            "title": post.title or "",
            "content": post.content,
            "severity_level": post.severity_level or "",
            "sentiment": post.sentiment or "",
            "published_at": post.published_at.isoformat() if post.published_at else "",
            "scraped_at": post.scraped_at.isoformat() if post.scraped_at else "",
            "post_url": post.post_url or "",
            "ai_summary": post.ai_summary or "",
        }
        for post in posts
    ]


def generate_selected_posts_csv(posts: list[Post]) -> bytes:
    fieldnames = ["id", "topic_id", "platform", "author", "title", "content", "severity_level", "sentiment", "published_at", "scraped_at", "post_url", "ai_summary"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in _post_rows(posts):
        writer.writerow(row)
    # UTF-8 BOM so Excel displays Arabic content correctly when opening the CSV directly.
    return output.getvalue().encode("utf-8-sig")


def generate_selected_posts_json(posts: list[Post]) -> bytes:
    return json.dumps(_post_rows(posts), ensure_ascii=False, indent=2).encode("utf-8")


def generate_selected_posts_xlsx(posts: list[Post]) -> bytes:
    header = ["id", "topic_id", "platform", "author", "title", "content", "severity_level", "sentiment", "published_at", "scraped_at", "post_url", "ai_summary"]
    rows = [header] + [[row.get(key, "") for key in header] for row in _post_rows(posts)]
    return build_minimal_xlsx(rows, sheet_name="Selected Posts")
