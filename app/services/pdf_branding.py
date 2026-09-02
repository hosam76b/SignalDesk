"""Shared branding helpers for generated PDF reports: app logo footer and Arabic text support."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

_LOGO_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "logo.svg"

_logo_drawing: Drawing | None = None
_logo_load_attempted = False

# (regular font name, bold font name, regular TTF path, bold TTF path)
_ARABIC_FONT_CANDIDATES: list[tuple[str, str, str, str]] = [
    ("ArabicUI", "ArabicUI-Bold", "C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/tahomabd.ttf"),
    ("ArabicUI", "ArabicUI-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("ArabicUI", "ArabicUI-Bold", "/Library/Fonts/Tahoma.ttf", "/Library/Fonts/Tahoma Bold.ttf"),
]
_arabic_font_names = ("Helvetica", "Helvetica-Bold")
_arabic_font_registered = False


def get_logo_drawing() -> Drawing | None:
    """Return a cached ReportLab Drawing for the app logo, or None if it can't be loaded."""
    global _logo_drawing, _logo_load_attempted
    if _logo_load_attempted:
        return _logo_drawing
    _logo_load_attempted = True
    try:
        from svglib.svglib import svg2rlg

        _logo_drawing = svg2rlg(str(_LOGO_PATH))
    except Exception:
        logger.exception("Failed to load application logo for PDF reports")
        _logo_drawing = None
    return _logo_drawing


def ensure_arabic_font() -> tuple[str, str]:
    """Register an Arabic-capable TTF font with ReportLab; returns (regular, bold) font names."""
    global _arabic_font_names, _arabic_font_registered
    if _arabic_font_registered:
        return _arabic_font_names
    _arabic_font_registered = True
    for regular_name, bold_name, regular_path, bold_path in _ARABIC_FONT_CANDIDATES:
        try:
            if not Path(regular_path).exists():
                continue
            pdfmetrics.registerFont(TTFont(regular_name, regular_path))
            if Path(bold_path).exists():
                pdfmetrics.registerFont(TTFont(bold_name, bold_path))
            else:
                bold_name = regular_name
            _arabic_font_names = (regular_name, bold_name)
            return _arabic_font_names
        except Exception:
            logger.warning("Could not register Arabic font from %s", regular_path)
    logger.warning("No Arabic-capable font found on this system; Arabic PDF text may render incorrectly")
    return _arabic_font_names


def shape_arabic(text: str) -> str:
    """Reshape and bidi-reorder Arabic text so it renders correctly (RTL, joined letterforms) in ReportLab."""
    if not text:
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        logger.exception("Failed to reshape Arabic text for PDF rendering")
        return text


def draw_report_footer(canvas: Any, doc: Any, footer_text: str, page_label: str) -> None:
    """Draw the app logo and a page label at the bottom of every page."""
    canvas.saveState()
    page_width = doc.pagesize[0]
    drawing = get_logo_drawing()
    if drawing is not None and drawing.height:
        scale = 14.0 / drawing.height
        canvas.saveState()
        canvas.translate(doc.leftMargin, 16)
        canvas.scale(scale, scale)
        renderPDF.draw(drawing, canvas, 0, 0)
        canvas.restoreState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#94a3b8"))
    canvas.drawRightString(page_width - doc.rightMargin, 22, footer_text)
    canvas.drawRightString(page_width - doc.rightMargin, 12, f"{page_label} {doc.page}")
    canvas.restoreState()
