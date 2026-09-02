from datetime import datetime, timedelta, timezone

from app.models import MonitoredSource, Post, Topic
from app.services.alerts import AlertManager
from app.services import reports as reports_module
from app.services.reports import PDFReportService


def test_pdf_service_generates_report_bytes(db, seeded_db):
    topic = Topic(title="Crisis Topic", description="Executive report test")
    db.add(topic)
    db.flush()
    source = MonitoredSource(platform="rss", name="Report Source", url_or_handle="https://example.com/source")
    db.add(source)
    db.flush()

    db.add(
        Post(
            topic_id=topic.id,
            source_id=source.id,
            external_id="p-1",
            platform="rss",
            author="Test Author",
            content="A coordinated narrative about a violent incident in the city.",
            post_url="https://example.com/post/1",
            published_at=datetime.now(timezone.utc),
            scraped_at=datetime.now(timezone.utc),
            severity_level="critical",
            is_flagged=True,
            is_important=True,
            is_dangerous=True,
            sentiment="negative",
            content_fingerprint="abc123",
            raw_metadata={"source_url": "https://example.com/source"},
        )
    )
    db.commit()

    report = PDFReportService.generate_executive_report(db, topic.id, requester=seeded_db["super_admin"])

    assert report["success"] is True
    assert report["content_type"] == "application/pdf"
    assert len(report["pdf_bytes"]) > 1000


def test_pdf_service_localizes_arabic_report(db, seeded_db, monkeypatch):
    topic = Topic(title="المراقبة العامة", description="اختبار التقرير العربي")
    db.add(topic)
    db.commit()
    shaped_text: list[str] = []
    real_shape_arabic = reports_module.shape_arabic

    def capture_arabic(value: str) -> str:
        shaped_text.append(value)
        return real_shape_arabic(value)

    monkeypatch.setattr(reports_module, "shape_arabic", capture_arabic)

    report = PDFReportService.generate_executive_report(
        db,
        topic.id,
        requester=seeded_db["super_admin"],
        language="ar",
    )

    assert report["success"] is True
    assert report["pdf_bytes"].startswith(b"%PDF-")
    assert "سري // تقرير الاستخبارات التنفيذي" in shaped_text
    assert "التوصيات الاستراتيجية" in shaped_text


def test_alert_manager_detects_volume_and_cib_alerts(db, seeded_db):
    topic = Topic(title="Alert Topic")
    db.add(topic)
    db.flush()
    source_a = MonitoredSource(platform="rss", name="Alert Source A", url_or_handle="https://example.com/alert-a")
    source_b = MonitoredSource(platform="rss", name="Alert Source B", url_or_handle="https://example.com/alert-b")
    source_c = MonitoredSource(platform="rss", name="Alert Source C", url_or_handle="https://example.com/alert-c")
    db.add_all([source_a, source_b, source_c])
    db.flush()

    base = datetime.now(timezone.utc)
    for idx in range(10):
        db.add(
            Post(
                topic_id=topic.id,
                source_id=[source_a.id, source_b.id, source_c.id][idx % 3],
                external_id=f"alert-{idx}",
                platform="rss",
                author=f"author-{idx % 5}",
                content="Identical messaging pattern for detection.",
                post_url=f"https://example.com/{idx}",
                published_at=base + timedelta(minutes=idx * 2),
                scraped_at=base + timedelta(minutes=idx * 2),
                severity_level="high" if idx % 3 == 0 else "low",
                is_flagged=idx % 3 == 0,
                is_important=idx % 2 == 0,
                is_dangerous=idx % 3 == 0,
                sentiment="negative",
                content_fingerprint="samehash",
            )
        )
    db.commit()

    alerts = AlertManager.evaluate_topic_alerts(db, topic.id)

    assert alerts["topic_id"] == topic.id
    assert alerts["summary"]["total_alerts"] >= 1
    assert any(alert["type"] in {"volume_spike", "critical_content", "cib_coordination"} for alert in alerts["alerts"])
