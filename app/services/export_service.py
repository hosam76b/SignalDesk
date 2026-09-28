"""Filtered, column-selectable, streaming exports of posts and AI analysis.

Design constraints that shaped this module:

* **No full table scans.** Every predicate the UI can set is on an indexed
  column (``published_at``, ``ai_status``, ``topic_id``, ``source_id``) and the
  two composite indexes added in migration ``0010`` let SQLite satisfy them
  with an index seek. Because a free-text ``search`` term cannot use any index,
  an export with neither a date window nor a status/topic/source filter is
  refused by default: :data:`DEFAULT_RANGE_DAYS` is substituted so the window is
  always bounded. See :func:`resolve_date_window`.
* **Bounded memory.** Nothing accumulates a whole result set. Rows are pulled
  with ``yield_per`` in :data:`EXPORT_CHUNK_ROWS`-sized batches, and every
  writer is a byte-chunk generator. The two formats that cannot be emitted
  incrementally -- XLSX (a ZIP) and PDF (ReportLab wants a seekable file) --
  spill to an on-disk temporary file and are read back in fixed-size blocks, so
  RAM use is one block regardless of export size.
* **Honest failures.** A ``StreamingResponse`` commits its status line and
  headers before the body exists, so an exception raised late in a generator can
  only ever reach the client as a *truncated download*. The formats that need the
  whole document before their first byte (:data:`SPOOLED_FORMATS`) are therefore
  built up front by :func:`build_export_spool`, while the route can still raise a
  real status code. :data:`PDF_CELL_MAX_CHARS` is the other half of the same
  problem: ReportLab aborts a build outright when one cell wraps taller than the
  page frame, which on a live archive means any long post URL.
* **Progress.** Every writer takes an ``on_progress`` callback invoked with the
  running row count, which the export-job registry turns into a percentage for
  the progress bar. Its denominator is the number of rows the *file* will hold,
  not the number the filter matched -- see :func:`export_row_total`.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, BinaryIO, Callable, Iterator, Sequence
from uuid import uuid4
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, or_
from sqlalchemy.orm import Query, Session

from app.models.post import (
    AI_STATUS_DONE,
    AI_STATUS_FAILED,
    AI_STATUS_PENDING,
    AI_STATUS_PROCESSING,
    AI_STATUS_SKIPPED,
    Post,
)
from app.models.source import MonitoredSource
from app.models.topic import UserTopic
from app.services.pdf_branding import draw_report_footer, ensure_arabic_font, shape_arabic
from app.services.xlsx_writer import StreamingXlsxWriter

logger = logging.getLogger(__name__)

EXPORT_FORMATS: tuple[str, ...] = ("csv", "json", "xlsx", "pdf")

#: Media type per format. ``text/csv`` deliberately carries no charset:
#: ``StreamingResponse`` appends ``; charset=utf-8`` to any ``text/*`` type, so
#: spelling it out here would send the header twice.
EXPORT_MEDIA_TYPES: dict[str, str] = {
    "csv": "text/csv",
    "json": "application/json; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}

#: Formats that cannot be produced a byte at a time. XLSX is a ZIP and PDF is
#: laid out in one pass by ReportLab, so both have to exist in full before their
#: first byte can be written. :func:`build_export_spool` builds them up front so
#: a failure is an HTTP error rather than a truncated download.
SPOOLED_FORMATS: frozenset[str] = frozenset({"xlsx", "pdf"})

#: Size of the blocks a spooled document is read back out in. Also the read
#: size used for the PDF temporary file.
EXPORT_BLOCK_BYTES = 64 * 1024

EXPORT_EXTENSIONS: dict[str, str] = {
    "csv": "csv",
    "json": "json",
    "xlsx": "xlsx",
    "pdf": "pdf",
}

#: Every ``ai_status`` the UI may filter on, in the order the dropdown lists
#: them. Kept in step with the constants in :mod:`app.models.post`.
AI_STATUS_OPTIONS: tuple[str, ...] = (
    "all",
    AI_STATUS_DONE,
    AI_STATUS_PENDING,
    AI_STATUS_PROCESSING,
    AI_STATUS_FAILED,
    AI_STATUS_SKIPPED,
)

#: Rows pulled from the database per batch. Large enough to amortise the cursor
#: round-trip, small enough that a wide ``content`` column stays cheap.
EXPORT_CHUNK_ROWS = 500

#: Hard ceiling on a single export. The streaming writers make a large export
#: survivable, but a 50k-row PDF is not a report anyone can read, and the cap
#: bounds the worst-case wall clock for one request.
EXPORT_MAX_ROWS = 50_000

#: A PDF detail table stops here; the statistical summary always covers the
#: full filtered set, and the row count actually printed is stated in the report.
PDF_MAX_DETAIL_ROWS = 500

#: Cell text longer than this is elided in the PDF detail table. ReportLab lays a
#: ``Paragraph`` out inside the frame it is handed and raises ``LayoutError`` if
#: the result is taller than the frame -- which, because the document is written
#: to a temporary file before the first byte is sent, kills the whole download.
#: Post URLs and AI summaries in a live archive routinely exceed this, so the cap
#: is what keeps a real dataset from failing the export outright.
PDF_CELL_MAX_CHARS = 140

#: Detail rows per printed table. One table spanning the whole detail block would
#: be a single several-hundred-row flowable that ReportLab has to measure in one
#: pass; batching keeps each flowable about page-sized and repeats the header.
PDF_DETAIL_ROWS_PER_TABLE = 38

#: Applied when the caller supplies no date window at all. See the module
#: docstring: this is what keeps an unrestricted export off a full table scan.
DEFAULT_RANGE_DAYS = 30

#: Registry bounds. Jobs hold only counters plus the resolved filter set, so a
#: handful of concurrent exports is cheap; the TTL sweep is what stops a user
#: from leaving entries behind by abandoning the progress poll.
JOB_TTL_SECONDS = 3600
MAX_TRACKED_JOBS = 100

#: Column widths for the XLSX sheet, keyed by export column.
_XLSX_COLUMN_WIDTHS: dict[str, int] = {
    "id": 8,
    "topic_id": 10,
    "source_id": 10,
    "source_name": 22,
    "platform": 12,
    "author": 20,
    "title": 32,
    "content": 60,
    "ai_summary": 48,
    "ai_status": 12,
    "ai_analyzed_at": 20,
    "violence_category": 18,
    "severity_level": 14,
    "sentiment": 12,
    "sentiment_score": 14,
    "is_flagged": 10,
    "is_important": 11,
    "is_dangerous": 12,
    "tags": 24,
    "published_at": 20,
    "scraped_at": 20,
    "post_url": 40,
    "media_count": 12,
    "content_fingerprint": 18,
}


@dataclass(frozen=True)
class ExportColumn:
    """One selectable export column."""

    key: str
    label_ar: str
    label_en: str
    group: str
    default: bool
    #: Suffix appended to the label in the PDF detail table header. Kept short
    #: so the table fits A4 portrait.
    pdf_header_ar: str = ""
    pdf_header_en: str = ""

    def label(self, lang: str) -> str:
        return self.label_ar if lang == "ar" else self.label_en

    def pdf_header(self, lang: str) -> str:
        if lang == "ar" and self.pdf_header_ar:
            return self.pdf_header_ar
        if lang != "ar" and self.pdf_header_en:
            return self.pdf_header_en
        return self.label(self.lang_fallback(lang))

    @staticmethod
    def lang_fallback(lang: str) -> str:
        return "ar" if lang == "ar" else "en"


#: The full catalogue offered in the Export tab. ``default=True`` columns are
#: what an export gets when the caller does not choose explicitly.
EXPORT_COLUMNS: tuple[ExportColumn, ...] = (
    ExportColumn("id", "المعرف", "ID", "identity", True, "م", "ID"),
    ExportColumn("topic_id", "رقم الموضوع", "Topic", "identity", False, "موضوع", "Topic"),
    ExportColumn("source_id", "رقم المصدر", "Source ID", "identity", False, "مرقم", "Src ID"),
    ExportColumn("source_name", "اسم المصدر", "Source name", "identity", True, "المصدر", "Source"),
    ExportColumn("platform", "المنصة", "Platform", "identity", True, "المنصة", "Platform"),
    ExportColumn("author", "الكاتب", "Author", "identity", True, "الكاتب", "Author"),
    ExportColumn("title", "العنوان", "Title", "content", False, "العنوان", "Title"),
    ExportColumn("content", "النص الأصلي", "Original text", "content", True, "النص", "Content"),
    ExportColumn("ai_summary", "ملخص الذكاء الاصطناعي", "AI summary", "ai", True, "الملخص", "AI summary"),
    ExportColumn("ai_status", "حالة التحليل", "AI status", "ai", True, "الحالة", "AI status"),
    ExportColumn("ai_analyzed_at", "تاريخ التحليل", "Analysed at", "ai", False, "تاريخ التحليل", "Analysed at"),
    ExportColumn("violence_category", "تصنيف العنف", "Violence category", "ai", False, "التصنيف", "Category"),
    ExportColumn("severity_level", "مستوى الخطورة", "Severity", "ai", True, "الخطورة", "Severity"),
    ExportColumn("sentiment", "المشاعر", "Sentiment", "ai", False, "المشاعر", "Sentiment"),
    ExportColumn("sentiment_score", "درجة المشاعر", "Sentiment score", "ai", False, "الدرجة", "Score"),
    ExportColumn("is_flagged", "مُعلَّم", "Flagged", "flags", False, "مُعلَّم", "Flagged"),
    ExportColumn("is_important", "مهم", "Important", "flags", False, "مهم", "Important"),
    ExportColumn("is_dangerous", "خطير", "Dangerous", "flags", False, "خطير", "Dangerous"),
    ExportColumn("tags", "الوسوم", "Tags", "flags", False, "الوسوم", "Tags"),
    ExportColumn("published_at", "تاريخ النشر", "Published at", "dates", True, "النشر", "Published"),
    ExportColumn("scraped_at", "تاريخ الجمع", "Scraped at", "dates", False, "الجمع", "Scraped"),
    ExportColumn("post_url", "رابط المنشور", "Post URL", "dates", True, "الرابط", "URL"),
    ExportColumn("media_count", "عدد الوسائط", "Media count", "dates", False, "الوسائط", "Media"),
    ExportColumn("content_fingerprint", "بصمة المحتوى", "Fingerprint", "dates", False, "البصمة", "Hash"),
)

COLUMNS_BY_KEY: dict[str, ExportColumn] = {column.key: column for column in EXPORT_COLUMNS}

DEFAULT_COLUMN_KEYS: tuple[str, ...] = tuple(
    column.key for column in EXPORT_COLUMNS if column.default
)

#: Never exported: the raw model response is large, may carry provider-specific
#: fields, and is an internal debugging artefact rather than analysis output.
FORBIDDEN_COLUMNS: frozenset[str] = frozenset({"raw_ai_response"})


class ExportColumnError(ValueError):
    """Raised when the requested column selection is unusable."""


def resolve_columns(keys: Sequence[str] | None) -> tuple[ExportColumn, ...]:
    """Validate a requested column selection and return it in catalogue order.

    Unknown or forbidden keys are rejected rather than silently dropped: an
    export quietly missing a column the analyst ticked is worse than an error.
    """
    if not keys:
        return tuple(column for column in EXPORT_COLUMNS if column.default)
    seen: set[str] = set()
    for key in keys:
        if key in FORBIDDEN_COLUMNS:
            raise ExportColumnError(f"Column '{key}' cannot be exported")
        if key not in COLUMNS_BY_KEY:
            raise ExportColumnError(f"Unknown export column '{key}'")
        seen.add(key)
    return tuple(column for column in EXPORT_COLUMNS if column.key in seen)


def _naive_utc(value: datetime | None) -> datetime | None:
    """Normalise a filter bound to naive UTC.

    ``posts.published_at`` is a naive ``DateTime`` column and the SQLite driver
    renders bind values without an offset. Converting an aware bound to naive
    UTC keeps the comparison on the same scale as the stored values instead of
    comparing UTC text against local time.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class ExportFilters:
    """A resolved export request. `allowed_topic_ids` is the authorisation scope."""

    format: str = "csv"
    lang: str = "ar"
    date_from: datetime | None = None
    date_to: datetime | None = None
    ai_status: str = "all"
    topic_id: int | None = None
    source_id: int | None = None
    search: str = ""
    columns: tuple[ExportColumn, ...] = ()
    limit: int = EXPORT_MAX_ROWS
    allowed_topic_ids: tuple[int, ...] | None = None
    requested_by: str = ""

    @property
    def date_from_bound(self) -> datetime:
        return self.date_from or _now_naive() - timedelta(days=DEFAULT_RANGE_DAYS)

    @property
    def date_to_bound(self) -> datetime:
        return self.date_to or _now_naive()

    @property
    def effective_limit(self) -> int:
        return max(1, min(self.limit, EXPORT_MAX_ROWS))

    def describe(self, lang: str) -> str:
        """Human-readable one-line summary of the applied filters, for the report header."""
        ar = lang == "ar"
        start = self.date_from_bound.strftime("%Y-%m-%d %H:%M")
        end = self.date_to_bound.strftime("%Y-%m-%d %H:%M")
        parts = [
            f"{'الفترة' if ar else 'Window'}: {start} → {end}",
            f"{'الحالة' if ar else 'AI status'}: {self.ai_status}",
        ]
        if self.topic_id is not None:
            parts.append(f"{'الموضوع' if ar else 'Topic'}: {self.topic_id}")
        if self.source_id is not None:
            parts.append(f"{'المصدر' if ar else 'Source'}: {self.source_id}")
        if self.search:
            parts.append(f"{'بحث' if ar else 'Search'}: {self.search}")
        return " | ".join(parts)


def resolve_date_window(
    date_from: datetime | None,
    date_to: datetime | None,
) -> tuple[datetime, datetime, bool]:
    """Return ``(from, to, defaulted)`` for the export window.

    A caller that supplies neither bound gets the last
    :data:`DEFAULT_RANGE_DAYS` days rather than the entire table: a free-text
    ``search`` cannot be served by an index, so an unbounded window is the one
    shape of this query that degrades into a scan of the whole archive.
    """
    start = _naive_utc(date_from)
    end = _naive_utc(date_to)
    if start is not None and end is not None:
        return start, end, False
    if start is None and end is None:
        now = _now_naive()
        return now - timedelta(days=DEFAULT_RANGE_DAYS), now, True
    if start is None:
        # An open-ended past plus a future bound would still scan everything;
        # anchor it the same number of days before the bound the UI defaults to.
        return end - timedelta(days=DEFAULT_RANGE_DAYS), end, True
    # Open-ended future: cap at "now" so a stray client date does not export
    # every row that happens to match the other filters.
    return start, min(end or _now_naive(), _now_naive()), True


def _escape_like(term: str) -> str:
    """Escape LIKE metacharacters so a search box searches for literal text."""
    for char in ("\\", "%", "_"):
        term = term.replace(char, "\\" + char)
    return term


def apply_post_filters(query: Query, filters: ExportFilters) -> Query:
    """Apply every export predicate to `query`.

    Shared by the count, the breakdowns and the row streaming so the three can
    never disagree about which rows an export covers.
    """
    if filters.allowed_topic_ids is not None:
        # `IN ()` is invalid SQL, so an empty scope is expressed as a
        # match-nothing id rather than being special-cased at every call site.
        scope = filters.allowed_topic_ids or (-1,)
        query = query.filter(Post.topic_id.in_(scope))
    if filters.topic_id is not None:
        query = query.filter(Post.topic_id == filters.topic_id)
    if filters.source_id is not None:
        query = query.filter(Post.source_id == filters.source_id)
    if filters.ai_status != "all":
        query = query.filter(Post.ai_status == filters.ai_status)
    query = query.filter(Post.published_at >= filters.date_from_bound)
    query = query.filter(Post.published_at <= filters.date_to_bound)
    search = filters.search.strip()
    if search:
        pattern = f"%{_escape_like(search)}%"
        query = query.filter(
            or_(
                Post.content.ilike(pattern, escape="\\"),
                Post.ai_summary.ilike(pattern, escape="\\"),
                Post.title.ilike(pattern, escape="\\"),
                Post.author.ilike(pattern, escape="\\"),
            )
        )
    return query


def build_post_query(db: Session, filters: ExportFilters) -> Query:
    """Filtered posts, newest first.

    The ordering matches the leading columns of ``ix_posts_export_date`` so
    SQLite walks the index in order instead of sorting the result set.
    """
    query = apply_post_filters(db.query(Post), filters)
    return query.order_by(Post.published_at.desc(), Post.id.desc())


def count_matching_posts(db: Session, filters: ExportFilters) -> int:
    """Number of rows the export will contain, ignoring the row cap."""
    query = apply_post_filters(db.query(Post.id), filters)
    return int(query.with_entities(func.count()).scalar() or 0)


def summarize_matching_posts(db: Session, filters: ExportFilters) -> dict[str, dict[str, int]]:
    """Break the filtered set down by AI status, severity and platform.

    Reuses :func:`apply_post_filters`, so these figures always describe the
    same rows the file will contain.
    """
    base = apply_post_filters(db.query(Post), filters)

    def grouped(column: Any) -> dict[str, int]:
        rows = base.with_entities(column, func.count()).group_by(column).all()
        return {str(key if key is not None else "unknown"): int(count) for key, count in rows}

    return {
        "by_ai_status": grouped(Post.ai_status),
        "by_severity": grouped(Post.severity_level),
        "by_platform": grouped(Post.platform),
    }


def accessible_topic_ids(db: Session, user: Any) -> tuple[int, ...] | None:
    """Topic ids `user` may export, or ``None`` for an unrestricted export.

    A super admin sees every topic. Everyone else is limited to their
    ``user_topics`` assignments, which is what stops a bulk export from
    bypassing the per-topic checks the read endpoints apply.
    """
    from app.core.deps import normalize_role

    if normalize_role(getattr(user, "role", None)) == "super_admin":
        return None
    rows = db.query(UserTopic.topic_id).filter(UserTopic.user_id == user.id).all()
    return tuple(sorted({int(topic_id) for (topic_id,) in rows}))


def _source_names(db: Session) -> dict[int, str]:
    """Map source id -> display name.

    Loaded as a standalone small-table read rather than a join on the posts
    query: joining would let the planner fold an unindexed predicate into the
    posts scan, and this table only ever holds one row per monitored source.
    """
    rows = db.query(MonitoredSource.id, MonitoredSource.name).all()
    return {int(source_id): name for source_id, name in rows}


def _iso(value: datetime | None) -> str:
    return value.isoformat(sep=" ") if value else ""


def _list_text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(entry) for entry in value)
    if value in (None, ""):
        return ""
    return str(value)


def row_values(post: Post, source_names: dict[int, str], columns: Sequence[ExportColumn]) -> list[Any]:
    """Project one post onto the selected columns, in selection order.

    Values stay native (int/bool/str) so JSON keeps its types and XLSX can
    store real numbers; the text formats stringify at the edge.
    """
    values: list[Any] = []
    for column in columns:
        key = column.key
        if key == "id":
            values.append(post.id)
        elif key == "topic_id":
            values.append(post.topic_id)
        elif key == "source_id":
            values.append(post.source_id)
        elif key == "source_name":
            values.append(source_names.get(post.source_id, ""))
        elif key == "platform":
            values.append(post.platform or "")
        elif key == "author":
            values.append(post.author or "")
        elif key == "title":
            values.append(post.title or "")
        elif key == "content":
            values.append(post.content or "")
        elif key == "ai_summary":
            values.append(post.ai_summary or "")
        elif key == "ai_status":
            values.append(post.ai_status or "")
        elif key == "ai_analyzed_at":
            values.append(_iso(post.ai_analyzed_at))
        elif key == "violence_category":
            values.append(post.violence_category or "")
        elif key == "severity_level":
            values.append(post.severity_level or "")
        elif key == "sentiment":
            values.append(post.sentiment or "")
        elif key == "sentiment_score":
            values.append(post.sentiment_score)
        elif key == "is_flagged":
            values.append(bool(post.is_flagged))
        elif key == "is_important":
            values.append(bool(post.is_important))
        elif key == "is_dangerous":
            values.append(bool(post.is_dangerous))
        elif key == "tags":
            values.append(_list_text(post.tags))
        elif key == "published_at":
            values.append(_iso(post.published_at))
        elif key == "scraped_at":
            values.append(_iso(post.scraped_at))
        elif key == "post_url":
            values.append(post.post_url or post.source_url or "")
        elif key == "media_count":
            values.append(len(post.media_urls) if isinstance(post.media_urls, list) else 0)
        elif key == "content_fingerprint":
            values.append(post.content_fingerprint or "")
        else:  # pragma: no cover - resolve_columns() rejects unknown keys
            values.append("")
    return values


def cell_text(value: Any) -> str:
    """Flatten a native value for the text formats (CSV, XLSX, PDF)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def iter_post_chunks(
    db: Session,
    filters: ExportFilters,
    chunk_size: int = EXPORT_CHUNK_ROWS,
) -> Iterator[list[Post]]:
    """Yield filtered posts in batches, capped at the export row limit.

    ``yield_per`` keeps SQLAlchemy streaming from the DBAPI cursor instead of
    buffering the whole result in the identity map, which is what stops a
    50k-row export from becoming 50k live ORM objects.
    """
    query = build_post_query(db, filters).limit(filters.effective_limit)
    if chunk_size < 1:
        chunk_size = 1
    for batch in query.yield_per(chunk_size):
        # SQLAlchemy yields bare entities for a single-entity query and row
        # tuples otherwise; normalise to a list of posts either way.
        if isinstance(batch, Post):
            yield [batch]
        else:
            yield list(batch)


def build_export_filename(filters: ExportFilters, stamp: str) -> str:
    """``signaldesk_export_<scope>_<format>_<stamp>.<ext>``."""
    parts = ["signaldesk_export"]
    if filters.ai_status != "all":
        parts.append(filters.ai_status)
    if filters.topic_id is not None:
        parts.append(f"topic{filters.topic_id}")
    if filters.source_id is not None:
        parts.append(f"source{filters.source_id}")
    parts.append(stamp)
    return "_".join(parts) + "." + EXPORT_EXTENSIONS[filters.format]


# --------------------------------------------------------------------------- #
# Writers. Each is a byte-chunk generator that reports progress via callback.  #
# --------------------------------------------------------------------------- #


def iter_csv_chunks(
    db: Session,
    filters: ExportFilters,
    on_progress: Callable[[int], None] | None = None,
) -> Iterator[bytes]:
    """CSV chunks encoded as UTF-8 with a BOM.

    The BOM is what makes Excel read Arabic columns correctly when the file is
    opened by double-click; without it the same content renders as mojibake.
    """
    columns = filters.columns
    source_names = _source_names(db)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([column.key for column in columns])
    yield buffer.getvalue().encode("utf-8-sig")
    buffer.seek(0)
    buffer.truncate(0)

    written = 0
    for chunk in iter_post_chunks(db, filters):
        for post in chunk:
            writer.writerow([cell_text(value) for value in row_values(post, source_names, columns)])
        written += len(chunk)
        payload = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        yield payload.encode("utf-8")
        if on_progress is not None:
            on_progress(written)


def iter_json_chunks(
    db: Session,
    filters: ExportFilters,
    meta: dict[str, Any] | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> Iterator[bytes]:
    """JSON chunks: an envelope with the applied filters, then one object per row.

    Rows are emitted individually rather than as one dumped array so a large
    export never has to exist as a single Python object graph.
    """
    columns = filters.columns
    source_names = _source_names(db)
    envelope = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requested_by": filters.requested_by,
        "format": filters.format,
        "columns": [column.key for column in columns],
        "filters": {
            "date_from": filters.date_from_bound.isoformat(),
            "date_to": filters.date_to_bound.isoformat(),
            "ai_status": filters.ai_status,
            "topic_id": filters.topic_id,
            "source_id": filters.source_id,
            "search": filters.search or None,
            "row_limit": filters.effective_limit,
        },
    }
    if meta:
        envelope.update(meta)
    yield ('{\n  "meta": ' + json.dumps(envelope, ensure_ascii=False, indent=2) + ',\n  "rows": [').encode("utf-8")

    written = 0
    first = True
    for chunk in iter_post_chunks(db, filters):
        for post in chunk:
            record = dict(zip((column.key for column in columns), row_values(post, source_names, columns)))
            separator = "" if first else ","
            first = False
            yield (separator + "\n    " + json.dumps(record, ensure_ascii=False)).encode("utf-8")
        written += len(chunk)
        if on_progress is not None:
            on_progress(written)
    yield b"\n  ]\n}\n"


def iter_xlsx_chunks(
    db: Session,
    filters: ExportFilters,
    on_progress: Callable[[int], None] | None = None,
) -> Iterator[bytes]:
    """XLSX chunks: a styled, auto-filtered workbook assembled into memory once.

    The workbook is fully materialised in a :class:`StreamingXlsxWriter` (the
    *rows* stream, so no ORM/row buffer is retained) and then handed back in
    256 KiB blocks. ReportLab and ``zipfile`` both need random access to their
    output, so the compressed archive is the one thing that has to be complete
    before the first byte goes out.
    """
    columns = filters.columns
    source_names = _source_names(db)
    header = [column.label(filters.lang) for column in columns]
    widths = [_XLSX_COLUMN_WIDTHS.get(column.key, 18) for column in columns]
    writer = StreamingXlsxWriter("Posts", header=header, column_widths=widths)
    try:
        written = 0
        for chunk in iter_post_chunks(db, filters):
            for post in chunk:
                writer.add_row(row_values(post, source_names, columns))
            written += len(chunk)
            if on_progress is not None:
                on_progress(written)
        for block in writer.iter_bytes():
            yield block
    finally:
        writer.close()


_PDF_LABELS = {
    "ar": {
        "title": "تقرير تصدير البيانات",
        "generated": "تاريخ الإنشاء",
        "requested_by": "بواسطة",
        "summary": "الملخص الإحصائي",
        "detail": "تفاصيل البيانات",
        "total": "إجمالي السجلات",
        "shown": "الصفوف المطبوعة",
        "note": "الصفوف المعروضة محدودة بحد أقصى لضمان قابلية القراءة؛ راجع ملخص الإحصائي-analysis للأرقام الكاملة.",
        "by_ai_status": "حسب حالة تحليل الذكاء الاصطناعي",
        "by_severity": "حسب مستوى الخطورة",
        "by_platform": "حسب المنصة",
        "footer": "SignalDesk — منصة المراقبة والاستخبارات الرقمية",
        "page": "صفحة",
        "truncated": "تنبيه: تم قصّ النتيجة عند الحد الأقصى للصفوف المصدَّرة.",
        "none": "لا توجد بيانات",
    },
    "en": {
        "title": "Data Export Report",
        "generated": "Generated",
        "requested_by": "Requested by",
        "summary": "Statistical summary",
        "detail": "Record detail",
        "total": "Total records",
        "shown": "Rows printed",
        "note": "Printed rows are capped for readability; the statistical summary always covers the full filtered set.",
        "by_ai_status": "By AI analysis status",
        "by_severity": "By severity",
        "by_platform": "By platform",
        "footer": "SignalDesk — Threat Intelligence & Media Monitoring Platform",
        "page": "Page",
        "truncated": "Notice: the result was capped at the maximum export row limit.",
        "none": "No data",
    },
}


def _pdf_label(lang: str, key: str) -> str:
    return _PDF_LABELS[lang if lang in _PDF_LABELS else "en"][key]


def _pdf_counts_table(
    title: str,
    counts: dict[str, int],
    labels: dict[str, str],
    is_ar: bool,
    body_style: ParagraphStyle,
    align: int,
) -> Table | None:
    if not counts:
        return None
    key_label = labels["by_ai_status"] if title == labels["by_ai_status"] else title
    rows: list[list[Any]] = [
        [Paragraph(f"<b>{xml_escape(shape_arabic(key_label) if is_ar else key_label)}</b>", body_style)],
        [Paragraph(f"<b>{xml_escape(shape_arabic(labels['total']) if is_ar else labels['total'])}</b>", body_style)],
    ]
    for key, count in sorted(counts.items(), key=lambda item: (-item[1], str(item[0]))):
        label = str(key) if key != "unknown" else labels["none"]
        rows.append([
            Paragraph(xml_escape(shape_arabic(label) if is_ar else label), body_style),
            Paragraph(str(count), body_style),
        ])
    table = Table(rows, colWidths=[300, 110], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("PADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def iter_pdf_chunks(
    db: Session,
    filters: ExportFilters,
    summary: dict[str, Any] | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> Iterator[bytes]:
    """PDF report chunks: statistical summary plus a bounded detail table.

    ReportLab writes to a seekable file object, so the document is built in an
    on-disk temporary file and read back in 64 KiB blocks -- the request never
    holds the whole PDF in memory.
    """
    lang = filters.lang if filters.lang in ("ar", "en") else "en"
    is_ar = lang == "ar"
    labels = _PDF_LABELS[lang]
    font_regular, font_bold = ensure_arabic_font() if is_ar else ("Helvetica", "Helvetica-Bold")
    align = 2 if is_ar else 0

    def t(text: str) -> str:
        return shape_arabic(text) if is_ar else text

    summary = summary or {}
    columns = filters.columns
    # The detail table only prints the columns that fit a page legibly; the
    # full selection is still honoured by the data formats.
    detail_columns = [column for column in columns if column.key in {
        "id", "source_name", "platform", "author", "ai_status", "severity_level", "published_at", "post_url",
    }] or columns[:3]
    source_names = _source_names(db)

    styles = getSampleStyleSheet()
    primary = colors.HexColor("#0f172a")
    muted = colors.HexColor("#64748b")
    title_style = ParagraphStyle(
        "ExportTitle", parent=styles["Heading1"], fontName=font_bold, fontSize=17, leading=21,
        textColor=primary, alignment=align,
    )
    subtitle_style = ParagraphStyle(
        "ExportSubtitle", parent=styles["Normal"], fontName=font_regular, fontSize=8.5, leading=12,
        textColor=muted, alignment=align,
    )
    body_style = ParagraphStyle(
        "ExportBody", parent=styles["Normal"], fontName=font_regular, fontSize=8, leading=10.5,
        textColor=colors.HexColor("#334155"), alignment=align,
    )
    bold_style = ParagraphStyle("ExportBold", parent=body_style, fontName=font_bold)

    with tempfile.TemporaryFile() as handle:
        doc = SimpleDocTemplate(
            handle, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=48,
        )
        story: list[Any] = []
        story.append(Paragraph(t(labels["title"]), title_style))
        generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        story.append(Paragraph(t(f"{labels['generated']}: {generated}"), subtitle_style))
        if filters.requested_by:
            story.append(Paragraph(t(f"{labels['requested_by']}: {filters.requested_by}"), subtitle_style))
        story.append(Paragraph(t(filters.describe(lang)), subtitle_style))
        story.append(Spacer(1, 8))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=10))

        story.append(Paragraph(t(labels["summary"]), bold_style))
        # `or 0` rather than a dict default: a caller that passes the key with a
        # null value is normal, and int(None) would abort the whole document.
        total = int(summary.get("total_rows") or 0)
        story.append(Paragraph(
            t(f"{labels['total']}: {min(total, filters.effective_limit)}"),
            body_style,
        ))
        if total > filters.effective_limit:
            story.append(Paragraph(t(labels["truncated"]), body_style))
        for key in ("by_ai_status", "by_severity", "by_platform"):
            table = _pdf_counts_table(labels[key], dict(summary.get(key) or {}), labels, is_ar, body_style, align)
            if table is not None:
                story.append(Spacer(1, 4))
                story.append(table)
        story.append(Spacer(1, 12))

        story.append(Paragraph(t(labels["detail"]), bold_style))
        printed_rows = min(total, filters.effective_limit, PDF_MAX_DETAIL_ROWS)
        story.append(Paragraph(t(f"{labels['shown']}: {printed_rows}"), body_style))
        if total:
            # Stated before the table rather than after it, so it reads as a
            # caption instead of an interruption between two printed pages.
            story.append(Paragraph(t(labels["note"]), subtitle_style))
        story.append(Spacer(1, 4))

        header_cells = [Paragraph(f"<b>{t(column.pdf_header(lang))}</b>", bold_style) for column in detail_columns]
        # A4 less the margins SimpleDocTemplate was built with. The old hardcoded
        # 500pt budget overran the 523pt frame, which is one of the two ways this
        # table used to become unprintable.
        frame_width = A4[0] - 72
        widths = [40] + [int((frame_width - 40) / max(1, len(detail_columns) - 1))] * (len(detail_columns) - 1)
        detail_style = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("PADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])

        def cell(value: Any) -> Paragraph:
            """One detail cell: escaped, elided, and shaped if the report is Arabic."""
            text = cell_text(value)
            if len(text) > PDF_CELL_MAX_CHARS:
                text = text[: PDF_CELL_MAX_CHARS - 1].rstrip() + "…"
            # A Paragraph is parsed as mini-XML, so an ampersand or a stray
            # angle bracket in a scraped post is a hard failure, not mojibake.
            return Paragraph(xml_escape(t(text)), body_style)

        page_rows: list[list[Any]] = []
        printed = 0
        for chunk in iter_post_chunks(db, filters):
            for post in chunk:
                if printed >= PDF_MAX_DETAIL_ROWS:
                    break
                cells: list[Any] = [cell(post.id)]
                for column, value in zip(detail_columns, row_values(post, source_names, detail_columns)):
                    if column.key == "id":
                        continue
                    cells.append(cell(value))
                page_rows.append(cells)
                printed += 1
                if len(page_rows) >= PDF_DETAIL_ROWS_PER_TABLE:
                    story.append(Table(
                        [header_cells, *page_rows], colWidths=widths, repeatRows=1, style=detail_style,
                    ))
                    page_rows = []
            if on_progress is not None:
                on_progress(printed)
            if printed >= PDF_MAX_DETAIL_ROWS:
                break
        if page_rows:
            story.append(Table(
                [header_cells, *page_rows], colWidths=widths, repeatRows=1, style=detail_style,
            ))
        elif not printed:
            story.append(Paragraph(t(labels["none"]), body_style))

        def footer(canvas: Any, pdf_doc: Any) -> None:
            draw_report_footer(canvas, pdf_doc, labels["footer"], labels["page"])

        doc.build(story, onFirstPage=footer, onLaterPages=footer)
        handle.seek(0)
        while True:
            block = handle.read(EXPORT_BLOCK_BYTES)
            if not block:
                break
            yield block


def iter_export_chunks(
    db: Session,
    filters: ExportFilters,
    meta: dict[str, Any] | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> Iterator[bytes]:
    """Dispatch to the writer for ``filters.format``."""
    if filters.format == "csv":
        return iter_csv_chunks(db, filters, on_progress)
    if filters.format == "json":
        return iter_json_chunks(db, filters, meta, on_progress)
    if filters.format == "xlsx":
        return iter_xlsx_chunks(db, filters, on_progress)
    if filters.format == "pdf":
        return iter_pdf_chunks(db, filters, meta, on_progress)
    raise ExportColumnError(f"Unsupported export format '{filters.format}'")


def build_export_spool(
    db: Session,
    filters: ExportFilters,
    meta: dict[str, Any] | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> BinaryIO | None:
    """Build the export up front, returning a seekable file, or ``None``.

    Only the formats in :data:`SPOOLED_FORMATS` need this. A ``StreamingResponse``
    sends its status line and ``Content-Disposition`` before the body is
    produced, so an exception raised while generating a late chunk can only ever
    reach the client as a *truncated download* -- a file that opens, is the right
    size in the header, and is silently incomplete. Doing the whole build here,
    while the route can still raise, turns that into an honest HTTP 500.

    The completed document lands in an on-disk temporary file, so the peak
    memory cost is one :data:`EXPORT_BLOCK_BYTES` block rather than the export.
    The caller owns the returned handle and must close it.
    """
    if filters.format not in SPOOLED_FORMATS:
        return None
    handle = tempfile.TemporaryFile()
    try:
        for block in iter_export_chunks(db, filters, meta, on_progress):
            handle.write(block)
    except BaseException:
        handle.close()
        raise
    handle.seek(0)
    return handle


def iter_spooled_chunks(handle: BinaryIO, block_size: int = EXPORT_BLOCK_BYTES) -> Iterator[bytes]:
    """Read a built export back out in fixed-size blocks."""
    handle.seek(0)
    while True:
        block = handle.read(block_size)
        if not block:
            return
        yield block


def export_row_total(matched_rows: int, filters: ExportFilters) -> int:
    """How many rows the *file* will contain, which is what progress measures.

    Two separate caps apply and they are not the same number: the row limit is
    the analyst's own bound, and a PDF additionally cannot print more than
    :data:`PDF_MAX_DETAIL_ROWS` detail rows. The uncapped count is reported
    separately as ``matched_rows`` so the UI can say the result was truncated.
    """
    total = max(0, min(matched_rows, filters.effective_limit))
    if filters.format == "pdf":
        total = min(total, PDF_MAX_DETAIL_ROWS)
    return total


# --------------------------------------------------------------------------- #
# Export jobs: progress tracking for the StreamingResponse download.          #
# --------------------------------------------------------------------------- #


@dataclass
class ExportJob:
    """Progress record for one in-flight export.

    Only counters and the resolved filter set live here, so tracking an export
    costs nothing even for the largest allowed request.
    """

    job_id: str
    filename: str
    media_type: str
    total_rows: int
    filters: ExportFilters
    status: str = "ready"  # ready | streaming | completed | failed | aborted
    rows_written: int = 0
    error: str | None = None
    started_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)
    downloaded: bool = False

    @property
    def percent(self) -> int:
        if self.status in ("completed", "failed", "aborted"):
            return 100 if self.status == "completed" else self.percent_at_end
        if self.total_rows <= 0:
            return 100 if self.status == "streaming" else 0
        return min(99, int(self.rows_written * 100 / self.total_rows))

    @property
    def percent_at_end(self) -> int:
        if self.total_rows <= 0:
            return 0
        return min(100, int(self.rows_written * 100 / self.total_rows))

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "filename": self.filename,
            "media_type": self.media_type,
            "total_rows": self.total_rows,
            "rows_written": self.rows_written,
            "percent": self.percent,
            "error": self.error,
            "downloaded": self.downloaded,
        }


class ExportJobRegistry:
    """In-memory, TTL-bounded registry of export jobs.

    The progress bar polls this while the ``StreamingResponse`` body is being
    generated, so the two must share process state; a persistent store would be
    the right answer for a multi-worker deployment, and the seam is this class.
    """

    def __init__(self, ttl_seconds: float = JOB_TTL_SECONDS, max_jobs: int = MAX_TRACKED_JOBS) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_jobs = max_jobs
        self._jobs: dict[str, ExportJob] = {}

    def _sweep(self) -> None:
        now = time.monotonic()
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if now - job.updated_at > self._ttl_seconds
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)
        # Bounded by insertion order; the oldest (least recently created) goes
        # first once the cap is reached.
        while len(self._jobs) > self._max_jobs:
            oldest = min(self._jobs.values(), key=lambda job: job.started_at)
            self._jobs.pop(oldest.job_id, None)

    def create(self, filters: ExportFilters, total_rows: int, stamp: str) -> ExportJob:
        self._sweep()
        job = ExportJob(
            job_id=uuid4().hex,
            filename=build_export_filename(filters, stamp),
            media_type=EXPORT_MEDIA_TYPES[filters.format],
            total_rows=max(0, int(total_rows)),
            filters=filters,
        )
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> ExportJob | None:
        self._sweep()
        return self._jobs.get(job_id)

    def claim(self, job_id: str) -> ExportJob | None:
        """Return the job for streaming, refusing a second concurrent download."""
        job = self.get(job_id)
        if job is None or job.downloaded or job.status == "streaming":
            return None
        job.downloaded = True
        job.status = "streaming"
        job.updated_at = time.monotonic()
        return job

    def progress(self, job: ExportJob, rows_written: int) -> None:
        job.rows_written = rows_written
        job.updated_at = time.monotonic()

    def complete(self, job: ExportJob) -> None:
        job.status = "completed"
        job.rows_written = max(job.rows_written, job.total_rows)
        job.updated_at = time.monotonic()

    def fail(self, job: ExportJob, error: str) -> None:
        job.status = "failed"
        job.error = error[:500]
        job.updated_at = time.monotonic()
        logger.exception("Export job %s failed", job.job_id)

    def abandon(self, job: ExportJob) -> None:
        job.status = "aborted"
        job.updated_at = time.monotonic()

    def clear(self) -> None:
        self._jobs.clear()


#: Process-wide registry used by the router.
export_jobs = ExportJobRegistry()
