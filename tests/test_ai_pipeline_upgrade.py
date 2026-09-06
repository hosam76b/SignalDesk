"""Regression tests for the upgraded multi-provider, concurrent AI pipeline."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.knowledge import KnowledgeDocument
from app.models.keyword import Keyword
from app.models.post import Post
from app.models.source import MonitoredSource
from app.models.topic import PromptTemplate, Topic
from app.models.user import User
from app.services import ai_orchestrator as orchestrator_module
from app.services.ai_service import (
    AIAnalysisOutput,
    AIAnalysisService,
    _coerce_payload,
    _extract_json_object,
    run_sync,
)
from app.services.knowledge_context import (
    chunk_text,
    cosine_similarity,
    embed_text,
    get_topic_knowledge_context,
)


VALID_PAYLOAD = {
    "violence_category": "incitement",
    "severity_level": "high",
    "ai_summary": "المنشور يتضمن تحريضاً واضحاً على العنف ضد مجموعة محددة.",
    "is_flagged": True,
    "detected_entities": ["مجموعة أ", "مدينة ب"],
    "sentiment_score": -70,
}


def _service(provider: str, *, api_key: str = "test-key") -> AIAnalysisService:
    service = AIAnalysisService()
    service.client = None
    service.runtime_config.update({
        "provider": provider,
        "model": "gemini-2.0-flash" if provider == "google_ai_studio" else "openai/gpt-4o-mini",
        "base_url": "https://example.invalid/v1",
        "api_key": api_key,
    })
    return service


# --------------------------------------------------------------------------
# Schema compliance
# --------------------------------------------------------------------------

def test_schema_rejects_out_of_range_sentiment():
    with pytest.raises(Exception):
        AIAnalysisOutput(severity_level="low", ai_summary="x", is_flagged=False, sentiment_score=500)


def test_coerce_payload_maps_unknown_category_and_string_numbers():
    coerced = _coerce_payload({
        "violence_category": "Unknown Category",
        "severity_level": "SEVERE",
        "ai_summary": "ملخص",
        "is_flagged": "yes",
        "detected_entities": ["أحمد", "", "  "],
        "sentiment_score": "-45.6",
    })
    assert coerced["violence_category"] == "other"
    assert coerced["severity_level"] == "low"
    assert coerced["sentiment_score"] == -45
    assert coerced["detected_entities"] == ["أحمد"]
    assert AIAnalysisOutput.model_validate(coerced).is_flagged is True


def test_extract_json_object_tolerates_markdown_fences():
    parsed = _extract_json_object('```json\n{"severity_level": "low"}\n```')
    assert parsed == {"severity_level": "low"}


# --------------------------------------------------------------------------
# Provider calls and fallback chain
# --------------------------------------------------------------------------

def test_google_provider_returns_normalized_arabic_result(monkeypatch):
    service = _service("google_ai_studio")
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": '{"violence_category": "incitement",'
                                                                   ' "severity_level": "high",'
                                                                   ' "ai_summary": "تحريض على العنف",'
                                                                   ' "is_flagged": true,'
                                                                   ' "detected_entities": ["جهة"],'
                                                                   ' "sentiment_score": -80}'}]}}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["body"] = kwargs.get("json")
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", lambda **_kwargs: FakeClient())
    result = run_sync(service.analyze_post_content_async("منشور يحرض على العنف"))

    assert result["success"] is True
    assert result["provider"] == "google_ai_studio"
    assert result["severity_level"] == "high"
    assert result["violence_category"] == "incitement"
    assert result["is_flagged"] is True
    assert result["sentiment_score"] == -80
    assert result["detected_entities"] == ["جهة"]
    # Native structured output must be requested, not free-form text.
    assert captured["body"]["generationConfig"]["response_mime_type"] == "application/json"
    assert "response_schema" in captured["body"]["generationConfig"]
    assert str(captured["url"]).endswith(":generateContent")


def test_openrouter_provider_uses_json_response_format(monkeypatch):
    service = _service("openrouter")
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"severity_level": "medium",'
                                                        ' "ai_summary": "ملخص تحليلي",'
                                                        ' "is_flagged": false}'}}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, **kwargs):
            captured["headers"] = kwargs.get("headers")
            captured["body"] = kwargs.get("json")
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", lambda **_kwargs: FakeClient())
    result = run_sync(service.analyze_post_content_async("محتوى عادي"))

    assert result["success"] is True
    assert result["provider"] == "openrouter"
    assert result["severity_level"] == "medium"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["headers"]["Authorization"] == "Bearer test-key"


def test_custom_openai_provider_uses_openai_compatible_chat_completion(monkeypatch):
    service = _service("custom_openai", api_key="")
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"severity_level": "low",'
                                                        ' "ai_summary": "تحليل من مزود مخصص",'
                                                        ' "is_flagged": false}'}}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs.get("headers")
            captured["body"] = kwargs.get("json")
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", lambda **_kwargs: FakeClient())
    result = run_sync(service.analyze_post_content_async("محتوى عادي"))

    assert result["success"] is True
    assert result["provider"] == "custom_openai"
    assert str(captured["url"]).endswith("/chat/completions")
    assert "Authorization" not in captured["headers"]
    assert captured["body"]["response_format"] == {"type": "json_object"}


def test_openai_compatible_provider_fetches_models(monkeypatch):
    service = _service("custom_openai", api_key="custom-key")
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"data": [{"id": "gpt-oss:20b"}, {"id": "qwen3:32b"}]}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        return FakeResponse()

    monkeypatch.setattr("httpx.get", fake_get)

    assert service.fetch_models() == ["gpt-oss:20b", "qwen3:32b"]
    assert str(captured["url"]).endswith("/models")
    assert captured["headers"]["Authorization"] == "Bearer custom-key"


def test_cloud_failure_falls_back_to_local_ollama(monkeypatch):
    service = _service("google_ai_studio")

    class FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            raise TimeoutError("gateway timeout")

    class FakeOllamaClient:
        def chat(self, **_kwargs):
            return {"message": {"content": '{"severity_level": "critical", "ai_summary": "تهديد مباشر",'
                                           ' "is_flagged": true, "violence_category": "physical_violence"}'}}

    monkeypatch.setattr("httpx.AsyncClient", lambda **_kwargs: FailingClient())
    monkeypatch.setattr(service, "_ollama_client", lambda: FakeOllamaClient())
    monkeypatch.setattr(service, "_provider_model", lambda provider: "qwen2.5:7b")

    result = run_sync(service.analyze_post_content_async("تهديد صريح"))

    assert result["success"] is True
    assert result["provider"] == "ollama"
    assert result["severity_level"] == "critical"
    assert result["is_flagged"] is True


def test_all_providers_failing_returns_safe_structure(monkeypatch):
    service = _service("openrouter")

    class FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            raise ConnectionError("unreachable")

    monkeypatch.setattr("httpx.AsyncClient", lambda **_kwargs: FailingClient())
    monkeypatch.setattr(service, "_ollama_client", lambda: None)

    result = service.analyze_post_content("نص للتحليل")

    assert result["success"] is False
    assert result["is_flagged"] is False
    assert result["severity_level"] == "low"
    assert result["detected_entities"] == []
    assert result["sentiment_score"] == 0
    assert result["error"]


def test_unconfigured_engine_never_raises(monkeypatch):
    monkeypatch.setattr("app.services.ai_service.settings.ai_fallback_enabled", False, raising=False)
    service = AIAnalysisService()
    service.client = None
    service.runtime_config.update({"provider": "openrouter", "api_key": "", "base_url": ""})

    result = service.analyze_post_content("محتوى بدون مزود مهيأ")

    assert result["success"] is False
    assert result["severity_level"] == "low"


def test_vision_support_depends_on_model_name():
    service = _service("google_ai_studio")
    assert service.supports_vision is True
    service.runtime_config["model"] = "mistral:7b"
    assert service.supports_vision is False


def test_images_are_attached_for_vision_models(monkeypatch):
    service = _service("google_ai_studio")
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": '{"severity_level": "low",'
                                                                   ' "ai_summary": "لا يوجد تهديد",'
                                                                   ' "is_flagged": false}'}]}}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, **kwargs):
            captured["body"] = kwargs.get("json")
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", lambda **_kwargs: FakeClient())
    result = run_sync(service.analyze_post_content_async(
        "صورة منشور", [{"mime_type": "image/jpeg", "data": "AAAA"}]
    ))

    parts = captured["body"]["contents"][0]["parts"]
    assert result["success"] is True
    assert any("inline_data" in part for part in parts)


# --------------------------------------------------------------------------
# Semantic RAG retrieval
# --------------------------------------------------------------------------

def test_embeddings_are_normalized_and_similarity_is_semantic():
    vector = embed_text("هجوم مسلح على مبنى حكومي")
    assert pytest.approx(cosine_similarity(vector, vector), abs=1e-6) == 1.0
    related = embed_text("هجوم مسلح على مبنى")
    unrelated = embed_text("مباراة كرة قدم ودية")
    assert cosine_similarity(vector, related) > cosine_similarity(vector, unrelated)


def test_chunk_text_respects_size_limit():
    chunks = chunk_text(" ".join(f"جملة رقم {index}." for index in range(200)), chunk_chars=120)
    assert len(chunks) > 1
    assert all(len(chunk) <= 130 for chunk in chunks)


def _seed_topic(db: Session) -> Topic:
    user = User(email=f"rag-{time.time_ns()}@example.com", hashed_password=hash_password("pw"),
                full_name="RAG User", role="super_admin")
    db.add(user)
    db.flush()
    topic = Topic(title=f"Topic {time.time_ns()}", created_by=user)
    db.add(topic)
    db.flush()
    return topic


def test_rag_retrieves_the_relevant_document_not_the_newest(db: Session):
    topic = _seed_topic(db)
    db.add_all([
        KnowledgeDocument(
            topic_id=topic.id, title="تهريب السلاح", filename="a.txt", file_type="text/plain",
            file_path="/tmp/a.txt",
            extracted_text="تقرير عن تهريب السلاح والأسلحة النارية عبر الحدود الشمالية للبلاد.",
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ),
        KnowledgeDocument(
            topic_id=topic.id, title="الزراعة", filename="b.txt", file_type="text/plain",
            file_path="/tmp/b.txt",
            extracted_text="دليل زراعة القمح والشعير وطرق الري الحديثة في المناطق الجافة.",
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
    ])
    db.flush()

    context = get_topic_knowledge_context(db, topic.id, query="تهريب الأسلحة النارية عبر الحدود", top_k=1)

    assert "تهريب السلاح" in context
    assert "الزراعة" not in context


def test_knowledge_context_without_query_keeps_legacy_behaviour(db: Session):
    topic = _seed_topic(db)
    db.add(KnowledgeDocument(
        topic_id=topic.id, title="مرجع", filename="c.txt", file_type="text/plain",
        file_path="/tmp/c.txt", extracted_text="نص مرجعي للاختبار",
    ))
    db.flush()

    assert "مرجع" in get_topic_knowledge_context(db, topic.id)


def test_knowledge_context_is_empty_without_documents(db: Session):
    topic = _seed_topic(db)
    assert get_topic_knowledge_context(db, topic.id, query="أي شيء") == ""


# --------------------------------------------------------------------------
# Concurrent batch processing
# --------------------------------------------------------------------------

def _seed_posts(db: Session, count: int) -> Topic:
    topic = _seed_topic(db)
    source = MonitoredSource(platform="facebook", name="Source", url_or_handle="https://example.com/page")
    db.add(source)
    db.flush()
    now = datetime.now(timezone.utc)
    db.add_all([
        Post(topic_id=topic.id, source_id=source.id, external_id=f"ext-{index}-{time.time_ns()}",
             platform="facebook", author="Author", content=f"منشور اختباري رقم {index}",
             published_at=now, scraped_at=now)
        for index in range(count)
    ])
    db.flush()
    return topic


def test_batch_runs_concurrently_and_persists_results(db: Session, monkeypatch):
    _seed_posts(db, 50)
    call_delay = 0.2

    async def fake_analyze(_text: str, _images=None):
        await asyncio.sleep(call_delay)
        return {
            "success": True,
            "provider": "google_ai_studio",
            "violence_category": None,
            "severity_level": "low",
            "ai_summary": "ملخص تحليلي باللغة العربية",
            "is_flagged": False,
            "detected_entities": ["كيان"],
            "sentiment_score": 10,
            "raw_response": dict(VALID_PAYLOAD),
            "error": None,
        }

    monkeypatch.setattr(orchestrator_module.ai_service, "analyze_post_content_async", fake_analyze)
    monkeypatch.setattr(orchestrator_module, "dispatch_event_blocking", lambda *_a, **_k: None)
    monkeypatch.setattr(orchestrator_module.settings, "ai_max_concurrency", 5)

    started = time.perf_counter()
    result = orchestrator_module.process_unanalyzed_posts(db, batch_size=50)
    elapsed = time.perf_counter() - started

    assert result["success"] is True
    assert result["processed"] == 50
    assert result["analyzed"] == 50
    assert result["updated"] == 50
    assert result["failed"] == 0
    # Sequential execution would need 50 * 0.2s = 10s; bounded concurrency must be far faster.
    assert elapsed < 5.0

    analyzed = db.query(Post).filter(Post.ai_summary.isnot(None)).all()
    assert len(analyzed) == 50
    assert all(post.severity_level == "low" for post in analyzed)
    assert all(post.entities == ["كيان"] for post in analyzed)
    assert all(post.sentiment in {"positive", "negative", "neutral"} for post in analyzed)


def test_batch_records_failures_without_aborting(db: Session, monkeypatch):
    _seed_posts(db, 4)
    calls = {"count": 0}

    async def flaky_analyze(_text: str, _images=None):
        calls["count"] += 1
        if calls["count"] % 2 == 0:
            return orchestrator_module.fallback_result("provider unavailable")
        return {
            "success": True,
            "provider": "ollama",
            "violence_category": None,
            "severity_level": "medium",
            "ai_summary": "ملخص",
            "is_flagged": False,
            "detected_entities": [],
            "sentiment_score": 0,
            "raw_response": {},
            "error": None,
        }

    monkeypatch.setattr(orchestrator_module.ai_service, "analyze_post_content_async", flaky_analyze)
    monkeypatch.setattr(orchestrator_module, "dispatch_event_blocking", lambda *_a, **_k: None)

    result = orchestrator_module.process_unanalyzed_posts(db, batch_size=10)

    assert result["processed"] == 4
    assert result["analyzed"] + result["failed"] == 4
    assert result["failed"] >= 1
    assert result["errors"]


def test_batch_uses_active_topic_prompt_and_injects_post_content(db: Session, monkeypatch):
    topic = _seed_posts(db, 1)
    post = db.query(Post).filter(Post.topic_id == topic.id).first()
    post.content = "خبر عن محاولة تهريب أسلحة عبر الحدود"
    db.add(Keyword(topic_id=topic.id, word_or_phrase="تهريب", category="risk", is_active=True))
    db.add(PromptTemplate(
        topic_id=topic.id,
        name="تحليل مخصص",
        template="حلل أخبار {topic_name} وفق الكلمات: {keywords}",
        provider="openrouter",
        model_name="deepseek/deepseek-v4-flash-0731",
        is_active=1,
    ))
    db.commit()
    captured: dict[str, str] = {}

    async def fake_analyze(text: str, _images=None):
        captured["text"] = text
        return {
            "success": True,
            "provider": "openrouter",
            "violence_category": "weapon_related",
            "severity_level": "high",
            "ai_summary": "رصد محاولة تهريب أسلحة مرتبطة بالموضوع.",
            "is_flagged": True,
            "detected_entities": [],
            "sentiment_score": -50,
            "raw_response": {},
            "error": None,
        }

    monkeypatch.setattr(orchestrator_module.ai_service, "analyze_post_content_async", fake_analyze)
    monkeypatch.setattr(orchestrator_module, "dispatch_event_blocking", lambda *_a, **_k: None)

    result = orchestrator_module.process_unanalyzed_posts(db, batch_size=1)

    assert result["analyzed"] == 1
    assert "حلل أخبار" in captured["text"]
    assert "وزارة الداخلية" in captured["text"] or topic.title in captured["text"]
    assert "تهريب" in captured["text"]
    assert "خبر عن محاولة تهريب أسلحة عبر الحدود" in captured["text"]


def test_empty_batch_is_a_no_op(db: Session):
    result = orchestrator_module.process_unanalyzed_posts(db, batch_size=10)
    assert result["processed"] == 0
    assert result["analyzed"] == 0
    assert result["success"] is True


def test_invalid_batch_size_is_rejected(db: Session):
    with pytest.raises(ValueError):
        orchestrator_module.process_unanalyzed_posts(db, batch_size=0)
