"""Unit and integration tests for the Export Data tab and the print report API.

Covers the export service (filters, column selection, chunked writers, job
registry), the new HTTP surface, and the query-plan guarantee that the export
never degrades into a full table scan of `posts`.
"""

from __future__ import annotations

import ast
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import event, text

from app.api import export as export_api
from app.models import MonitoredSource, Post
from app.services import export_service as es
from app.services.xlsx_writer import MAX_CELL_CHARS, StreamingXlsxWriter

NOW = datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #


def _seed_analysis_posts(db, topic_id: int, source_id: int, count: int = 12) -> None:
    """Posts spread across every ai_status, with Arabic analysis output."""
    statuses = ["pending", "done", "failed", "skipped", "processing"]
    for index in range(count):
        status = statuses[index % len(statuses)]
        db.add(
            Post(
                topic_id=topic_id,
                source_id=source_id,
                external_id=f"analysis-{index}",
                platform="rss",
                author=f"author-{index % 3}",
                content=f"منشور تجريبي رقم {index} about keyword-{index % 4}",
                title=f"عنوان {index}",
                published_at=NOW - timedelta(hours=index),
                scraped_at=NOW,
                ai_status=status,
                ai_summary=f"ملخص الذكاء الاصطناعي {index}" if status == "done" else None,
                ai_analyzed_at=NOW - timedelta(hours=index) if status == "done" else None,
                severity_level=["low", "medium", "high", "critical"][index % 4],
                sentiment=["positive", "negative", "neutral"][index % 3],
                sentiment_score=index % 5,
                violence_category="weapon_related" if index % 2 else None,
                tags=["urgent", f"t{index % 3}"] if index % 2 else [],
                is_flagged=index % 3 == 0,
                is_important=index % 4 == 0,
                is_dangerous=index % 5 == 0,
                media_urls=["/media/a.jpg", "/media/b.mp4"] if index % 2 else [],
                post_url=f"https://example.com/p/{index}",
                content_fingerprint=f"fp{index:032d}"[:32],
            )
        )
    db.flush()


@pytest.fixture()
def populated(db, seeded_db):
    """`seeded_db` plus 12 analysed posts in topic A and 4 in topic B.

    The extra rows exist so the export has every `ai_status`, a mix of
    severities/platforms, and Arabic `ai_summary` text to search against. They
    are re-published on top of the shared fixture rather than replacing it, so
    the per-topic access-control assertions still see the baseline rows.
    """
    source_a = db.query(MonitoredSource).filter(MonitoredSource.name == "A Feed").one()
    source_b = db.query(MonitoredSource).filter(MonitoredSource.name == "B Feed").one()
    _seed_analysis_posts(db, seeded_db["topic_a"].id, source_a.id, count=12)
    _seed_analysis_posts(db, seeded_db["topic_b"].id, source_b.id, count=4)
    # A post older than DEFAULT_RANGE_DAYS so the "unbounded export" guard has
    # something it must actually exclude.
    db.add(
        Post(
            topic_id=seeded_db["topic_a"].id,
            source_id=source_a.id,
            external_id="analysis-ancient",
            platform="rss",
            author="author-old",
            content="منشور قديم جدا ancient-keyword-only",
            published_at=NOW - timedelta(days=es.DEFAULT_RANGE_DAYS + 7),
            scraped_at=NOW,
            ai_status="done",
            ai_summary="ملخص قديم",
        )
    )
    db.commit()
    return {**seeded_db, "db": db, "source_a": source_a, "source_b": source_b}


@pytest.fixture(autouse=True)
def clean_export_jobs():
    """The registry is process-wide, so one test's job would leak into the next."""
    es.export_jobs.clear()
    yield
    es.export_jobs.clear()


@pytest.fixture()
def export_sessions(db, monkeypatch):
    """Make the download endpoint read the fixture's rows, not the real database.

    ``open_export_session()`` deliberately bypasses the request-scoped
    ``get_db`` session (FastAPI tears that down before the body streams). Under
    test the app's ``get_db`` is overridden with a session bound to the
    in-memory connection, so ``SessionLocal`` is repointed at that same
    connection: a second session sees the same uncommitted rows, and closing it
    at the end of the stream is harmless.
    """
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setattr(
        export_api,
        "SessionLocal",
        sessionmaker(bind=db.get_bind(), expire_on_commit=False),
    )


# --------------------------------------------------------------------------- #
# Column catalogue                                                             #
# --------------------------------------------------------------------------- #


def test_resolve_columns_defaults_when_unset():
    resolved = es.resolve_columns(None)
    assert [column.key for column in resolved] == list(es.DEFAULT_COLUMN_KEYS)
    # Defaults must still carry the fields the analyst actually asked for.
    keys = {column.key for column in resolved}
    assert {"id", "content", "ai_summary", "ai_status", "published_at", "post_url", "source_name"} <= keys


def test_resolve_columns_honours_explicit_selection_in_catalogue_order():
    resolved = es.resolve_columns(["ai_summary", "id", "content"])
    # Catalogue order, not request order, so two equivalent requests produce
    # byte-identical column layouts.
    assert [column.key for column in resolved] == ["id", "content", "ai_summary"]


def test_resolve_columns_rejects_unknown_and_forbidden_keys():
    with pytest.raises(es.ExportColumnError):
        es.resolve_columns(["id", "raw_ai_response"])
    with pytest.raises(es.ExportColumnError):
        es.resolve_columns(["id", "drop_table"])
    with pytest.raises(es.ExportColumnError):
        es.resolve_columns(["raw_ai_response"])


def test_export_columns_are_unique_and_labelled_in_both_languages():
    keys = [column.key for column in es.EXPORT_COLUMNS]
    assert len(keys) == len(set(keys))
    for column in es.EXPORT_COLUMNS:
        assert column.label_ar and column.label_en
        assert column.pdf_header("ar") and column.pdf_header("en")


# --------------------------------------------------------------------------- #
# Date window                                                                  #
# --------------------------------------------------------------------------- #


def test_resolve_date_window_keeps_an_explicit_window():
    start, end, defaulted = es.resolve_date_window(NOW - timedelta(days=7), NOW)
    assert start == NOW - timedelta(days=7)
    assert end == NOW
    assert defaulted is False


def test_resolve_date_window_defaults_when_neither_bound_is_given():
    """The free-text `search` cannot use an index, so an unbounded window is refused."""
    start, end, defaulted = es.resolve_date_window(None, None)
    assert defaulted is True
    assert (end - start) == timedelta(days=es.DEFAULT_RANGE_DAYS)


def test_resolve_date_window_defaults_a_half_open_window():
    start, end, from_open = es.resolve_date_window(None, NOW)
    assert from_open is True
    assert (end - start) == timedelta(days=es.DEFAULT_RANGE_DAYS)

    start, end, to_open = es.resolve_date_window(NOW - timedelta(days=3), None)
    assert to_open is True
    assert start == NOW - timedelta(days=3)
    # The open-ended future is capped at "now", evaluated at call time rather
    # than at import time, so compare against a freshly read clock.
    live_now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert live_now <= end <= live_now + timedelta(seconds=5)


def test_resolve_date_window_normalises_aware_bounds_to_naive_utc():
    """`posts.published_at` is naive; an aware bound must not be compared as local time."""
    aware = datetime(2026, 1, 1, 12, 0, tzinfo=timezone(timedelta(hours=3)))
    start, _end, _defaulted = es.resolve_date_window(aware, None)
    assert start.tzinfo is None
    assert start == datetime(2026, 1, 1, 9, 0)


def test_export_filters_bound_the_window_even_without_explicit_dates():
    filters = es.ExportFilters()
    assert filters.date_to_bound - filters.date_from_bound == timedelta(days=es.DEFAULT_RANGE_DAYS)


# --------------------------------------------------------------------------- #
# Filters                                                                      #
# --------------------------------------------------------------------------- #


def test_apply_post_filters_scopes_to_allowed_topics(populated):
    db = populated["db"]
    filters = es.ExportFilters(
        date_from=NOW - timedelta(days=1),
        date_to=NOW + timedelta(hours=1),
        columns=es.resolve_columns(["id"]),
        allowed_topic_ids=(populated["topic_b"].id,),
    )
    rows = es.build_post_query(db, filters).all()
    assert rows
    assert {row.topic_id for row in rows} == {populated["topic_b"].id}


def test_apply_post_filters_with_empty_scope_matches_nothing(populated):
    """`IN ()` is invalid SQL, so an empty scope must be expressed safely."""
    db = populated["db"]
    filters = es.ExportFilters(
        date_from=NOW - timedelta(days=1),
        date_to=NOW + timedelta(hours=1),
        columns=es.resolve_columns(["id"]),
        allowed_topic_ids=(),
    )
    assert es.count_matching_posts(db, filters) == 0


def test_search_escapes_like_wildcards(populated):
    """A literal `%` in the search box must not turn into a match-everything."""
    db = populated["db"]
    base = dict(
        date_from=NOW - timedelta(days=1),
        date_to=NOW + timedelta(hours=1),
        columns=es.resolve_columns(["id"]),
    )
    literal = es.ExportFilters(search="%", **base)
    assert es.count_matching_posts(db, literal) == 0

    wildcard = es.ExportFilters(search="%25", **base)  # '%25' -> escaped literal '%25'
    assert es.count_matching_posts(db, wildcard) == 0

    real = es.ExportFilters(search="keyword-1", **base)
    assert es.count_matching_posts(db, real) > 0


def test_search_covers_ai_summary_not_just_content(populated):
    db = populated["db"]
    filters = es.ExportFilters(
        search="الذكاء الاصطناعي",
        date_from=NOW - timedelta(days=1),
        date_to=NOW + timedelta(hours=1),
        columns=es.resolve_columns(["id"]),
    )
    rows = es.build_post_query(db, filters).all()
    assert rows
    assert all(row.ai_status == "done" for row in rows)


def test_count_and_summary_describe_the_same_rows(populated):
    """The preview breakdown must not drift from what the file actually contains."""
    db = populated["db"]
    filters = es.ExportFilters(
        ai_status="all",
        date_from=NOW - timedelta(days=1),
        date_to=NOW + timedelta(hours=1),
        columns=es.resolve_columns(None),
    )
    total = es.count_matching_posts(db, filters)
    summary = es.summarize_matching_posts(db, filters)
    assert sum(summary["by_ai_status"].values()) == total
    assert sum(summary["by_severity"].values()) == total
    assert sum(summary["by_platform"].values()) == total


def test_row_limit_caps_streamed_rows_but_not_the_reported_total(populated):
    db = populated["db"]
    filters = es.ExportFilters(
        date_from=NOW - timedelta(days=1),
        date_to=NOW + timedelta(hours=1),
        columns=es.resolve_columns(["id"]),
        limit=3,
    )
    total = es.count_matching_posts(db, filters)
    streamed = sum(len(chunk) for chunk in es.iter_post_chunks(db, filters))
    assert total > 3
    assert streamed == 3
    assert filters.effective_limit == 3


def test_accessible_topic_ids_respects_assignments(populated):
    db = populated["db"]
    assert es.accessible_topic_ids(db, populated["super_admin"]) is None
    assert es.accessible_topic_ids(db, populated["monitor_a"]) == (populated["topic_a"].id,)
    assert es.accessible_topic_ids(db, populated["unassigned"]) == ()


# --------------------------------------------------------------------------- #
# Writers                                                                      #
# --------------------------------------------------------------------------- #


def _filters(**overrides):
    base = dict(
        format="csv",
        lang="ar",
        date_from=NOW - timedelta(days=1),
        date_to=NOW + timedelta(hours=1),
        columns=es.resolve_columns(None),
        requested_by="analyst@example.com",
    )
    base.update(overrides)
    return es.ExportFilters(**base)


def test_iter_csv_chunks_starts_with_a_utf8_bom(populated):
    """Excel only reads Arabic correctly from a CSV that opens with a BOM."""
    db = populated["db"]
    payload = b"".join(es.iter_csv_chunks(db, _filters()))
    assert payload.startswith(b"\xef\xbb\xbf")


def test_iter_csv_chunks_header_and_row_count_match_the_filter(populated):
    db = populated["db"]
    filters = _filters(ai_status="done")
    payload = b"".join(es.iter_csv_chunks(db, filters)).decode("utf-8-sig")
    lines = [line for line in payload.splitlines() if line]
    assert lines[0].split(",") == [column.key for column in filters.columns]
    assert len(lines) - 1 == es.count_matching_posts(db, filters)


def test_iter_csv_chunks_is_chunked_not_one_blob(populated):
    """A large export must reach the client incrementally."""
    db = populated["db"]
    filters = _filters()
    chunks = list(es.iter_csv_chunks(db, filters))
    # One BOM/header chunk plus at least one chunk per batch of rows.
    assert len(chunks) > 2
    assert b"".join(chunks).startswith(b"\xef\xbb\xbf")


def test_writers_report_monotonic_progress(populated):
    db = populated["db"]
    for fmt in es.EXPORT_FORMATS:
        seen: list[int] = []
        payload = b"".join(
            es.iter_export_chunks(db, _filters(format=fmt), {"total_rows": 0}, seen.append)
        )
        assert payload, f"{fmt} produced no bytes"
        assert seen == sorted(seen), f"{fmt} progress went backwards"
        assert seen and seen[-1] == es.count_matching_posts(db, _filters(format=fmt))


def test_iter_json_chunks_emits_a_valid_envelope_with_every_row(populated):
    db = populated["db"]
    filters = _filters(format="json", ai_status="failed")
    document = json.loads(b"".join(es.iter_json_chunks(db, filters)).decode("utf-8"))
    assert set(document) == {"meta", "rows"}
    assert len(document["rows"]) == es.count_matching_posts(db, filters)
    assert document["meta"]["columns"] == [column.key for column in filters.columns]
    assert document["meta"]["filters"]["ai_status"] == "failed"
    assert document["meta"]["requested_by"] == "analyst@example.com"
    assert "generated_at" in document["meta"]
    # Native types survive, so integrators get numbers rather than strings.
    assert all(isinstance(row["id"], int) for row in document["rows"])


def test_json_row_keys_track_the_selected_columns(populated):
    db = populated["db"]
    filters = _filters(format="json", columns=es.resolve_columns(["id", "ai_summary", "is_flagged"]))
    document = json.loads(b"".join(es.iter_json_chunks(db, filters)).decode("utf-8"))
    assert set(document["rows"][0]) == {"id", "ai_summary", "is_flagged"}
    assert isinstance(document["rows"][0]["is_flagged"], bool)


def test_iter_xlsx_chunks_produces_a_valid_filterable_workbook(populated):
    db = populated["db"]
    filters = _filters(format="xlsx", columns=es.resolve_columns(None))
    archive_bytes = b"".join(es.iter_xlsx_chunks(db, filters))
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        assert archive.testzip() is None
        sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
    expected = es.count_matching_posts(db, filters)
    # Header row plus one row per record.
    assert sheet.count("<row ") == expected + 1
    assert "autoFilter" in sheet, "the header row must carry an auto-filter"
    assert "state=\"frozen\"" in sheet
    assert 's="1"' in sheet, "the header row must be styled, not plain"
    assert "<cols>" in sheet


def test_xlsx_workbook_is_arabic_readable(populated):
    db = populated["db"]
    filters = _filters(format="xlsx", columns=es.resolve_columns(["id", "ai_summary"]))
    archive_bytes = b"".join(es.iter_xlsx_chunks(db, filters))
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "ملخص الذكاء الاصطناعي" in sheet


def test_iter_pdf_chunks_produces_a_pdf_with_summary_and_branding(populated):
    db = populated["db"]
    filters = _filters(format="pdf")
    summary = {"total_rows": es.count_matching_posts(db, filters), **es.summarize_matching_posts(db, filters)}
    payload = b"".join(es.iter_pdf_chunks(db, filters, summary))
    assert payload.startswith(b"%PDF-")
    assert len(payload) > 1000


def test_pdf_detail_table_is_capped_below_the_row_count(populated, monkeypatch):
    """A 50k-row PDF is unreadable; the cap must hold and be stated in the report."""
    db = populated["db"]
    monkeypatch.setattr(es, "PDF_MAX_DETAIL_ROWS", 3)
    filters = _filters(format="pdf")
    seen: list[int] = []
    total = es.count_matching_posts(db, filters)
    assert total > 3
    b"".join(es.iter_pdf_chunks(db, filters, {"total_rows": total}, seen.append))
    assert max(seen) <= 3


def test_pdf_survives_a_cell_longer_than_a_page(populated):
    """The real archive broke this.

    A post URL or AI summary long enough to wrap into a paragraph taller than
    the text frame made ReportLab raise `LayoutError` *inside* `doc.build()`,
    which -- because the document is written to a temporary file before the
    first byte is sent -- surfaced as a truncated download rather than an error.
    """
    db = populated["db"]
    monster = "https://example.invalid/" + ("very-long-path-segment/" * 400) + "?q=" + ("x" * 5000)
    post = db.query(Post).filter(Post.ai_status == es.AI_STATUS_DONE).first()
    assert post is not None
    post.post_url = monster
    post.ai_summary = monster
    db.commit()

    filters = _filters(format="pdf", columns=es.resolve_columns(["id", "post_url", "ai_summary"]))
    payload = b"".join(es.iter_pdf_chunks(db, filters, {"total_rows": 1}))
    assert payload.startswith(b"%PDF-")
    assert payload.rstrip().endswith(b"%%EOF")


def test_pdf_escapes_xml_unsafe_cell_text(populated):
    """`Paragraph` is parsed as mini-XML: a bare `&` in a scraped post is fatal."""
    db = populated["db"]
    post = db.query(Post).filter(Post.ai_status == es.AI_STATUS_DONE).first()
    assert post is not None
    post.title = "a & b < c > d"
    db.commit()

    filters = _filters(format="pdf", columns=es.resolve_columns(["id", "title"]))
    payload = b"".join(es.iter_pdf_chunks(db, filters, {"total_rows": 1}))
    assert payload.startswith(b"%PDF-")


def test_pdf_detail_table_widths_fit_the_page_frame():
    """The old 500pt budget overran A4's 523pt frame, which is unprintable."""
    from reportlab.lib.pagesizes import A4

    frame_width = A4[0] - 72
    detail_columns = [column for column in es.EXPORT_COLUMNS if column.key in {
        "id", "source_name", "platform", "author", "ai_status", "severity_level", "published_at", "post_url",
    }]
    widths = [40] + [int((frame_width - 40) / max(1, len(detail_columns) - 1))] * (len(detail_columns) - 1)
    assert sum(widths) <= frame_width
    assert 40 in widths


def test_pdf_detail_rows_are_batched_into_page_sized_tables():
    """One multi-hundred-row flowable is a single ReportLab measurement pass."""
    assert 10 <= es.PDF_DETAIL_ROWS_PER_TABLE <= 60
    assert es.PDF_DETAIL_ROWS_PER_TABLE < es.PDF_MAX_DETAIL_ROWS


def test_spooled_formats_are_built_before_the_response_starts(populated):
    """A late body exception can only ever look like a truncated download."""
    assert es.SPOOLED_FORMATS == frozenset({"xlsx", "pdf"})
    assert es.SPOOLED_FORMATS.isdisjoint({"csv", "json"})


@pytest.mark.parametrize("fmt", sorted(es.SPOOLED_FORMATS))
def test_build_export_spool_produces_the_whole_document(populated, fmt):
    """Spooling must not truncate, reorder or re-encode anything.

    Byte equality against a *second* build is not the assertion: ReportLab
    stamps a creation time and a document id into every PDF, so two runs of the
    same document differ. The invariant is that the reader hands back exactly
    the bytes the builder wrote.
    """
    db = populated["db"]
    filters = _filters(format=fmt, columns=es.resolve_columns(["id", "ai_summary"]))
    meta = {"total_rows": es.count_matching_posts(db, filters)}
    handle = es.build_export_spool(db, filters, meta)
    try:
        assert handle is not None
        assert handle.readable()
        written = handle.read()
        replayed = b"".join(es.iter_spooled_chunks(handle))
    finally:
        handle.close()
    assert written
    assert replayed == written
    assert written.startswith(b"%PDF-" if fmt == "pdf" else b"PK\x03\x04")


def test_build_export_spool_returns_none_for_a_streaming_format(populated):
    db = populated["db"]
    assert es.build_export_spool(db, _filters(format="csv")) is None
    assert es.build_export_spool(db, _filters(format="json")) is None


def test_csv_media_type_lets_starlette_add_the_charset():
    """Starlette appends `; charset=utf-8` to any `text/*` type, unconditionally."""
    from starlette.responses import StreamingResponse

    response = StreamingResponse(iter([b"a"]), media_type=es.EXPORT_MEDIA_TYPES["csv"])
    assert response.headers["content-type"] == "text/csv; charset=utf-8"


def test_iter_export_chunks_rejects_an_unknown_format(populated):
    db = populated["db"]
    with pytest.raises(es.ExportColumnError):
        b"".join(es.iter_export_chunks(db, _filters(format="parquet")))


# --------------------------------------------------------------------------- #
# StreamingXlsxWriter                                                          #
# --------------------------------------------------------------------------- #


def test_streaming_xlsx_writer_omits_null_cells_but_keeps_addressing():
    writer = StreamingXlsxWriter("S", header=["a", "b", "c"])
    try:
        writer.add_row([1, None, "x"])
        payload = b"".join(writer.iter_bytes())
    finally:
        writer.close()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
    # B2 is absent but C2 still points at column C.
    assert "<c r=\"A2\"" in sheet
    assert "<c r=\"B2\"" not in sheet
    assert "<c r=\"C2\"" in sheet


def test_streaming_xlsx_writer_truncates_over_long_cells():
    """Excel refuses to open a cell past 32767 characters, so it is cut on the way in."""
    writer = StreamingXlsxWriter("S", header=["body"])
    try:
        writer.add_row(["x" * (MAX_CELL_CHARS + 500)])
        payload = b"".join(writer.iter_bytes())
    finally:
        writer.close()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "x" * (MAX_CELL_CHARS + 10) not in sheet
    assert "x" * 1000 in sheet


def test_streaming_xlsx_writer_strips_control_characters():
    writer = StreamingXlsxWriter("S", header=["body"])
    try:
        writer.add_row(["bad\x00\x08byte"])
        payload = b"".join(writer.iter_bytes())
    finally:
        writer.close()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "\x00" not in sheet
    assert "badbyte" in sheet


def test_streaming_xlsx_writer_refuses_rows_after_finalize():
    writer = StreamingXlsxWriter("S", header=["a"])
    try:
        writer.finalize()
        with pytest.raises(RuntimeError):
            writer.add_row([1])
    finally:
        writer.close()


def test_build_minimal_xlsx_still_works_after_the_refactor():
    """The pre-existing buffer-everything writer must keep its original contract."""
    from app.services.xlsx_writer import build_minimal_xlsx

    payload = build_minimal_xlsx([["id", "name"], [1, "منشور"]], sheet_name="Posts")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert archive.testzip() is None
        sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        workbook = archive.read("xl/workbook.xml").decode("utf-8")
    assert "منشور" in sheet
    assert "Posts" in workbook


# --------------------------------------------------------------------------- #
# Job registry                                                                 #
# --------------------------------------------------------------------------- #


def test_job_registry_reports_progress_and_completes():
    registry = es.ExportJobRegistry()
    job = registry.create(_filters(), total_rows=100, stamp="20260101_000000")
    assert job.status == "ready"
    assert job.percent == 0
    assert job.filename.endswith(".csv")

    claimed = registry.claim(job.job_id)
    assert claimed is not None
    assert job.status == "streaming"

    registry.progress(job, 50)
    assert job.percent == 50
    registry.progress(job, 100)
    assert job.percent == 99, "a streaming job must not read as finished early"
    registry.complete(job)
    assert job.percent == 100
    assert job.status == "completed"
    assert job.as_dict()["rows_written"] == 100


def test_job_registry_claim_is_single_use():
    registry = es.ExportJobRegistry()
    job = registry.create(_filters(), total_rows=1, stamp="s")
    assert registry.claim(job.job_id) is not None
    assert registry.claim(job.job_id) is None, "a second download must be refused"


def test_job_registry_expires_jobs_by_ttl():
    registry = es.ExportJobRegistry(ttl_seconds=-1)
    job = registry.create(_filters(), total_rows=1, stamp="s")
    # The TTL sweep runs on every read, so a negative TTL expires immediately.
    assert registry.get(job.job_id) is None


def test_job_registry_is_bounded():
    registry = es.ExportJobRegistry(max_jobs=3)
    created = [registry.create(_filters(), total_rows=1, stamp=str(i)) for i in range(5)]
    assert len(created) == 5
    assert registry.get(created[0].job_id) is None
    assert registry.get(created[-1].job_id) is not None


def test_job_percent_handles_an_empty_result_set():
    registry = es.ExportJobRegistry()
    job = registry.create(_filters(), total_rows=0, stamp="s")
    assert job.percent == 0
    registry.claim(job.job_id)
    registry.complete(job)
    assert job.percent == 100


def test_job_filename_encodes_the_filter():
    filters = _filters(format="xlsx", ai_status="done", topic_id=7)
    registry = es.ExportJobRegistry()
    job = registry.create(filters, total_rows=1, stamp="20260101_010203")
    assert job.filename == "signaldesk_export_done_topic7_20260101_010203.xlsx"
    assert job.media_type.startswith("application/vnd.openxmlformats")


# --------------------------------------------------------------------------- #
# HTTP surface                                                                 #
# --------------------------------------------------------------------------- #


def test_options_requires_authentication(client):
    # `HTTPBearer` answers a missing header with 403, `OAuth2PasswordBearer`
    # with 401; the app uses the former, so accept either.
    assert client.get("/api/v1/export/options").status_code in (401, 403)


def test_options_catalogue_drives_the_ui(client, populated, topic_a_admin_client):
    response = topic_a_admin_client.get("/api/v1/export/options")
    assert response.status_code == 200
    body = response.json()
    assert body["default_columns"]
    assert set(body["ai_statuses"]) == {"all", "done", "pending", "processing", "failed", "skipped"}
    assert {item["value"] for item in body["formats"]} == {"csv", "json", "xlsx", "pdf"}
    assert body["limits"]["max_rows"] == es.EXPORT_MAX_ROWS
    # A topic admin only sees the topics they are assigned to.
    assert [topic["id"] for topic in body["topics"]] == [populated["topic_a"].id]
    assert {source["id"] for source in body["sources"]} == {populated["source_a"].id, populated["source_b"].id}


def test_super_admin_sees_every_topic_in_options(client, super_admin_client, populated):
    body = super_admin_client.get("/api/v1/export/options").json()
    assert {topic["id"] for topic in body["topics"]} == {populated["topic_a"].id, populated["topic_b"].id}


def test_preview_counts_and_breaks_down(client, topic_a_admin_client, populated):
    response = topic_a_admin_client.post("/api/v1/export/preview", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["total_rows"] > 0
    assert body["truncated"] is False
    assert sum(body["by_ai_status"].values()) == body["total_rows"]
    assert body["effective"]["ai_status"] == "all"
    assert "columns" in body["effective"]


def test_preview_honours_the_ai_status_filter(client, topic_a_admin_client, populated):
    body = topic_a_admin_client.post("/api/v1/export/preview", json={"ai_status": "done"}).json()
    assert list(body["by_ai_status"]) == ["done"]
    assert body["total_rows"] == body["by_ai_status"]["done"]


def test_preview_rejects_an_unknown_ai_status(client, topic_a_admin_client):
    response = topic_a_admin_client.post("/api/v1/export/preview", json={"ai_status": "exploded"})
    assert response.status_code == 422


def test_preview_rejects_an_unknown_format(client, topic_a_admin_client):
    response = topic_a_admin_client.post("/api/v1/export/preview", json={"format": "parquet"})
    assert response.status_code == 422


def test_preview_rejects_an_unknown_column(client, topic_a_admin_client):
    response = topic_a_admin_client.post("/api/v1/export/preview", json={"columns": ["id", "raw_ai_response"]})
    assert response.status_code == 422
    assert "raw_ai_response" in response.json()["detail"]


def test_preview_is_scoped_to_the_callers_topics(
    client, topic_a_admin_client, topic_b_admin_client, populated
):
    mine = topic_a_admin_client.post("/api/v1/export/preview", json={}).json()["total_rows"]
    theirs = topic_b_admin_client.post("/api/v1/export/preview", json={}).json()["total_rows"]
    assert mine > 0 and theirs > 0
    # Each admin only ever sees their own topic's rows.
    assert mine != theirs


def test_cannot_preview_a_topic_you_are_not_assigned_to(client, topic_a_admin_client):
    response = topic_a_admin_client.post("/api/v1/export/preview", json={"topic_id": 999})
    assert response.status_code == 403


def test_export_job_creation_and_streamed_download(client, topic_a_admin_client, populated, export_sessions):
    created = topic_a_admin_client.post(
        "/api/v1/export/jobs",
        json={"format": "csv", "ai_status": "done", "columns": ["id", "ai_summary"]},
    )
    assert created.status_code == 201, created.text
    job = created.json()
    assert job["total_rows"] > 0
    assert job["filename"].endswith(".csv")
    assert job["download_url"].endswith("/download")

    progress = topic_a_admin_client.get(job["poll_url"]).json()
    assert progress["status"] == "ready"
    assert progress["total_rows"] == job["total_rows"]

    download = topic_a_admin_client.get(job["download_url"])
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/csv")
    assert 'filename="' in download.headers["content-disposition"]
    body = download.content.decode("utf-8-sig")
    header = body.splitlines()[0]
    assert header == "id,ai_summary"
    assert len([line for line in body.splitlines() if line]) - 1 == job["total_rows"]

    final = topic_a_admin_client.get(job["poll_url"]).json()
    assert final["status"] == "completed"
    assert final["percent"] == 100


def test_a_job_cannot_be_downloaded_twice(client, topic_a_admin_client, populated, export_sessions):
    job = topic_a_admin_client.post("/api/v1/export/jobs", json={"format": "csv"}).json()
    assert topic_a_admin_client.get(job["download_url"]).status_code == 200
    assert topic_a_admin_client.get(job["download_url"]).status_code == 404


def test_downloading_an_unknown_job_is_404(client, topic_a_admin_client):
    assert topic_a_admin_client.get("/api/v1/export/jobs/deadbeef/download").status_code == 404
    assert topic_a_admin_client.get("/api/v1/export/jobs/deadbeef").status_code == 404


def test_export_download_requires_authentication(client, populated):
    """The progress poll is as sensitive as the download itself."""
    for method, path in (
        ("get", "/api/v1/export/jobs/x/download"),
        ("get", "/api/v1/export/jobs/x"),
    ):
        response = getattr(client, method)(path)
        assert response.status_code in (401, 403), path
    for path in ("/api/v1/export/jobs", "/api/v1/export/preview"):
        assert client.post(path, json={}).status_code in (401, 403), path


@pytest.mark.parametrize("fmt", ["csv", "json", "xlsx", "pdf"])
def test_every_format_streams_a_download(client, topic_a_admin_client, populated, export_sessions, fmt):
    job = topic_a_admin_client.post(
        "/api/v1/export/jobs", json={"format": fmt, "columns": ["id", "ai_summary"]}
    ).json()
    response = topic_a_admin_client.get(job["download_url"])
    assert response.status_code == 200, response.text
    assert response.content
    if fmt == "csv":
        assert response.content.startswith(b"\xef\xbb\xbf")
    if fmt == "json":
        assert json.loads(response.content.decode("utf-8"))["rows"]
    if fmt == "xlsx":
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert archive.testzip() is None
    if fmt == "pdf":
        assert response.content.startswith(b"%PDF-")


def test_download_carries_the_total_row_header_for_the_progress_bar(
    client, topic_a_admin_client, populated, export_sessions
):
    job = topic_a_admin_client.post("/api/v1/export/jobs", json={"format": "csv"}).json()
    response = topic_a_admin_client.get(job["download_url"])
    assert response.headers["X-Export-Total-Rows"] == str(job["total_rows"])
    assert response.headers["X-Export-Job-Id"] == job["job_id"]


def test_row_limit_is_honoured_end_to_end(client, topic_a_admin_client, populated, export_sessions):
    job = topic_a_admin_client.post("/api/v1/export/jobs", json={"format": "csv", "limit": 2}).json()
    body = topic_a_admin_client.get(job["download_url"]).content.decode("utf-8-sig")
    assert job["truncated"] is True
    assert len([line for line in body.splitlines() if line]) - 1 == 2


def test_job_total_rows_is_what_the_file_holds_not_what_matched(client, topic_a_admin_client, populated, export_sessions):
    """The percentage denominator has to be the row count that is actually written.

    Reporting the uncapped match count made a 10-row export out of 4,002
    candidates sit at 0% for the whole download and then jump to 100%.
    """
    job = topic_a_admin_client.post("/api/v1/export/jobs", json={"format": "csv", "limit": 4}).json()
    assert job["total_rows"] == 4
    assert job["matched_rows"] > 4
    assert job["truncated"] is True
    body = topic_a_admin_client.get(job["download_url"]).content.decode("utf-8-sig")
    assert len([line for line in body.splitlines() if line]) - 1 == job["total_rows"]
    final = topic_a_admin_client.get(job["poll_url"]).json()
    assert final["rows_written"] == final["total_rows"] == 4
    assert final["percent"] == 100


def test_pdf_job_total_rows_accounts_for_the_detail_cap(client, topic_a_admin_client, populated, export_sessions, monkeypatch):
    """A PDF cannot print more detail rows than the cap, so it is not the total."""
    monkeypatch.setattr(es, "PDF_MAX_DETAIL_ROWS", 2)
    job = topic_a_admin_client.post("/api/v1/export/jobs", json={"format": "pdf"}).json()
    assert job["total_rows"] == 2
    assert job["matched_rows"] > 2
    response = topic_a_admin_client.get(job["download_url"])
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"%PDF-")


@pytest.mark.parametrize("fmt", ["csv", "json", "xlsx", "pdf"])
def test_export_row_total_applies_every_cap(fmt):
    filters = es.ExportFilters(format=fmt, limit=10)
    assert es.export_row_total(100, filters) == 10, "the row limit is always the first cap"
    assert es.export_row_total(5, filters) == 5
    assert es.export_row_total(0, filters) == 0
    if fmt == "pdf":
        roomy = es.ExportFilters(format=fmt, limit=5_000)
        assert es.export_row_total(5_000, roomy) == es.PDF_MAX_DETAIL_ROWS
        assert es.export_row_total(10, roomy) == 10, "the cap never invents rows"


def test_search_filter_reaches_the_downloaded_file(client, topic_a_admin_client, populated, export_sessions):
    job = topic_a_admin_client.post(
        "/api/v1/export/jobs",
        json={"format": "json", "search": "keyword-1", "columns": ["id", "content"]},
    ).json()
    document = json.loads(topic_a_admin_client.get(job["download_url"]).content.decode("utf-8"))
    assert document["rows"]
    assert all("keyword-1" in row["content"] for row in document["rows"])
    assert len(document["rows"]) == job["total_rows"]


# --------------------------------------------------------------------------- #
# Print report inputs (PostDetailOutput)                                       #
# --------------------------------------------------------------------------- #


def test_post_detail_response_carries_the_ai_analysis(client, topic_a_admin_client, populated):
    """`response_model=PostDetailOutput` silently strips undeclared columns.

    The print report has nothing to render without these, which is why the
    assertion is on the wire format rather than on the ORM object.
    """
    db = populated["db"]
    post = (
        db.query(Post)
        .filter(Post.topic_id == populated["topic_a"].id, Post.ai_summary.isnot(None))
        .first()
    )
    assert post is not None
    body = topic_a_admin_client.get(f"/api/v1/posts/{post.id}").json()
    assert body["ai_summary"] == post.ai_summary
    assert body["ai_status"] == post.ai_status
    assert body["ai_analyzed_at"] == post.ai_analyzed_at.isoformat()
    assert "violence_category" in body
    assert "tags" in body
    assert "raw_ai_response" in body


def test_post_detail_reports_a_pending_post_without_a_summary(client, topic_a_admin_client, populated):
    db = populated["db"]
    post = (
        db.query(Post)
        .filter(Post.topic_id == populated["topic_a"].id, Post.ai_status == "pending")
        .first()
    )
    assert post is not None
    body = topic_a_admin_client.get(f"/api/v1/posts/{post.id}").json()
    assert body["ai_summary"] is None
    assert body["ai_status"] == "pending"


def test_single_post_pdf_export_still_works(client, topic_a_admin_client, populated):
    """The print dialog's "download PDF" reuses this endpoint; do not regress it."""
    db = populated["db"]
    post = db.query(Post).filter(Post.topic_id == populated["topic_a"].id).first()
    response = topic_a_admin_client.post(
        "/api/v1/posts/export/pdf", json={"post_ids": [post.id], "lang": "ar"}
    )
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-")


# --------------------------------------------------------------------------- #
# Query plan: no full table scan                                               #
# --------------------------------------------------------------------------- #


def _query_plan(db, filters) -> str:
    statement = es.build_post_query(db, filters).statement
    compiled = str(statement.compile(db.bind, compile_kwargs={"literal_binds": True}))
    rows = db.execute(text("EXPLAIN QUERY PLAN " + compiled)).all()
    return " | ".join(str(row[-1]) for row in rows)


def _assert_no_full_scan(plan: str) -> None:
    # `SEARCH posts USING INDEX ...` is fine; a bare `SCAN posts` is not.
    assert "SCAN posts" not in plan, f"export query degraded to a table scan: {plan}"
    assert "posts USING INDEX" in plan, f"export query is not using an index: {plan}"


def test_export_indexes_exist(db):
    names = {
        row[0]
        for row in db.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='posts'")
        ).all()
    }
    assert "ix_posts_export_date" in names
    assert "ix_posts_export_ai_date" in names


def test_date_window_export_uses_the_export_index(populated):
    db = populated["db"]
    plan = _query_plan(db, _filters())
    _assert_no_full_scan(plan)
    assert "ix_posts_export_date" in plan


@pytest.mark.parametrize("status", ["done", "pending", "processing", "failed", "skipped"])
def test_status_filtered_export_uses_the_status_index(populated, status):
    """`ix_posts_ai_queue` is partial to pending/failed, so `done` and `skipped`
    would have no usable index at all without `ix_posts_export_ai_date`."""
    db = populated["db"]
    plan = _query_plan(db, _filters(ai_status=status))
    _assert_no_full_scan(plan)
    assert "ix_posts_export_ai_date" in plan


def test_topic_and_source_filtered_export_does_not_scan(populated):
    db = populated["db"]
    filters = _filters(topic_id=populated["topic_a"].id, source_id=populated["source_a"].id)
    _assert_no_full_scan(_query_plan(db, filters))


def test_free_text_search_over_a_bounded_window_does_not_scan(populated):
    """LIKE cannot use an index, but the bounded window keeps it a range scan."""
    db = populated["db"]
    _assert_no_full_scan(_query_plan(db, _filters(search="keyword-1")))


def test_unbounded_export_is_refused_by_the_date_window_default(populated):
    """A free-text search with no window would scan everything, so one is imposed."""
    db = populated["db"]
    old_post = (
        db.query(Post)
        .filter(Post.published_at < NOW - timedelta(days=es.DEFAULT_RANGE_DAYS + 5))
        .first()
    )
    assert old_post is not None, "fixture must include a post older than the default window"
    # A token that appears only on the aged post, so "no match" can only be
    # explained by the date window and not by a term nobody wrote.
    token = old_post.content.split()[-1]
    narrowed = es.ExportFilters(search=token, columns=es.resolve_columns(["id"]))
    assert es.count_matching_posts(db, narrowed) == 0

    # Widening the window brings the row back, proving the search term does
    # match and that the default window is what excluded it.
    widened = es.ExportFilters(
        search=token,
        date_from=NOW - timedelta(days=es.DEFAULT_RANGE_DAYS + 30),
        columns=es.resolve_columns(["id"]),
    )
    assert es.count_matching_posts(db, widened) == 1


def test_export_query_never_touches_the_partial_ai_queue_index(populated):
    """Using the worker's partial index here would be wrong: it cannot satisfy
    the `published_at` window or the non-pending statuses."""
    db = populated["db"]
    for status in ("all", "done", "skipped", "processing"):
        assert "ix_posts_ai_queue" not in _query_plan(db, _filters(ai_status=status))


def test_migration_and_selfheal_declare_the_same_export_indexes():
    """Alembic and the startup self-heal must not drift from the ORM."""
    orm_indexes = {
        index.name: tuple(column.name for column in index.columns)
        for index in Post.__table__.indexes
    }
    assert orm_indexes["ix_posts_export_date"] == ("published_at", "id")
    assert orm_indexes["ix_posts_export_ai_date"] == ("ai_status", "published_at", "id")

    migration = (
        Path(__file__).resolve().parent.parent / "migrations" / "versions" / "0010_export_indexes.py"
    ).read_text(encoding="utf-8")
    assert "ix_posts_export_date" in migration
    assert "ix_posts_export_ai_date" in migration

    init_db = (
        Path(__file__).resolve().parent.parent / "app" / "db" / "init_db.py"
    ).read_text(encoding="utf-8")
    assert "ix_posts_export_date" in init_db
    assert "ix_posts_export_ai_date" in init_db


def test_existing_partial_ai_queue_index_is_untouched():
    """The export work must not have disturbed the queue claim's index."""
    queue = next(index for index in Post.__table__.indexes if index.name == "ix_posts_ai_queue")
    where = str(queue.dialect_options["sqlite"]["where"])
    assert "ai_status" in where and "pending" in where and "failed" in where
    assert [column.name for column in queue.columns] == ["id"]


# --------------------------------------------------------------------------- #
# Source-level guarantees                                                       #
# --------------------------------------------------------------------------- #


def test_streaming_download_does_not_use_the_request_scoped_session():
    """FastAPI 0.104 tears down `yield` dependencies before the body streams.

    Closing `get_db` early would hand the generator a closed session, so the
    streaming path must open its own.
    """
    source = (Path(__file__).resolve().parent.parent / "app" / "api" / "export.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    download = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "download_export_job"
    )
    parameters = {argument.arg for argument in download.args.args}
    assert "db" not in parameters, "the download endpoint must not take the request-scoped session"
    body = ast.unparse(download)
    assert "open_export_session()" in body
    assert "session.close()" in body, "the streaming session must be closed when the body ends"


def test_export_never_filters_on_ai_summary():
    """`ai_status` is the indexed lifecycle column; `ai_summary` is not, and the
    empty-string sentinel was removed precisely so it could not be filtered on."""
    source = (
        Path(__file__).resolve().parent.parent / "app" / "services" / "export_service.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    apply_filters = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "apply_post_filters"
    )
    predicates = [ast.unparse(statement) for statement in apply_filters.body if isinstance(statement, ast.Assign)]
    compared = [text for text in predicates if ".ai_summary" in text or ".ai_summary ==" in text]
    for text in compared:
        # A LIKE over ai_summary is a legitimate keyword search; a bare
        # `ai_summary IS NULL` / `== ''` comparison is not.
        assert "ilike" in text, f"ai_summary must only be searched, never equality-filtered: {text}"
