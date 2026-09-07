"""Multi-provider AI service for evaluating monitored post content.

Supports Google AI Studio (Gemini), OpenRouter and a local Ollama server with an
automatic fallback chain: the configured cloud provider is tried first and the
local Ollama instance is used when it fails, times out or is unreachable. Every
entry point returns a normalized dict and never raises, so batch processing keeps
running when no provider is configured at all.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Coroutine, Literal, TypeVar

import httpx
from dotenv import set_key
from pydantic import BaseModel, Field, ValidationError

try:
    import ollama
except ImportError:  # pragma: no cover - depends on deployment extras
    ollama = None  # type: ignore[assignment]

from config import settings

logger = logging.getLogger(__name__)

MODEL_OPTIONS = {
    "ollama": ["qwen2.5:7b", "llama3.1:8b", "mistral:7b", "deepseek-r1:7b"],
    "openrouter": ["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet", "google/gemini-2.0-flash-001", "meta-llama/llama-3.1-8b-instruct"],
    "google_ai_studio": ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
    "custom_openai": ["gpt-4o-mini", "gpt-4.1-mini", "local-model"],
}
PROVIDERS = {"ollama", "openrouter", "google_ai_studio", "custom_openai"}
OPENAI_COMPATIBLE_PROVIDERS = {"openrouter", "custom_openai"}
API_KEY_OPTIONAL_PROVIDERS = {"ollama", "custom_openai"}

VALID_SEVERITIES = {"low", "medium", "high", "critical"}
VIOLENCE_CATEGORIES = (
    "hate_speech", "incitement", "physical_violence", "sexual_violence",
    "psychological_violence", "weapon_related", "gang_related", "extremism",
    "self_harm", "other",
)
VALID_CATEGORIES = set(VIOLENCE_CATEGORIES)

# Substrings identifying models able to accept inline image parts.
VISION_MODEL_HINTS = ("gemini", "gpt-4o", "claude-3", "llava", "vl", "vision", "pixtral")

SYSTEM_PROMPT = """Analyze the input news/post for security and threat monitoring.
Return valid JSON ONLY with exactly these keys:
{
  "violence_category": "one of hate_speech, incitement, physical_violence, sexual_violence, psychological_violence, weapon_related, gang_related, extremism, self_harm, other - or null",
  "severity_level": "low, medium, high, or critical",
  "ai_summary": "concise analytical summary in clear Arabic language",
  "is_flagged": true or false,
  "detected_entities": ["names of people, groups, organizations or places mentioned"],
  "sentiment_score": "integer from -100 (very negative) to 100 (very positive)"
}
When an image is attached, also read any visible text, symbols, logos and flags in it.
Set is_flagged to true when severity is high or critical, or when violence or a threat is detected.
Set violence_category to null when the content is clean.
Do not include markdown, explanations, or any keys besides the six requested keys."""

_T = TypeVar("_T")


class AIAnalysisOutput(BaseModel):
    """Strict schema every provider response is validated against."""

    violence_category: Literal[VIOLENCE_CATEGORIES] | None = None  # type: ignore[valid-type]
    severity_level: Literal["low", "medium", "high", "critical"] = "low"
    ai_summary: str = Field(default="تم تحليل المحتوى", description="Concise analytical summary in clear Arabic")
    is_flagged: bool = False
    detected_entities: list[str] = Field(default_factory=list)
    sentiment_score: int = Field(default=0, ge=-100, le=100, description="Sentiment from -100 to 100")


# Provider-native JSON schema (Gemini `responseSchema` / OpenAPI subset).
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "violence_category": {"type": "string", "nullable": True, "enum": list(VIOLENCE_CATEGORIES)},
        "severity_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "ai_summary": {"type": "string"},
        "is_flagged": {"type": "boolean"},
        "detected_entities": {"type": "array", "items": {"type": "string"}},
        "sentiment_score": {"type": "integer"},
    },
    "required": ["severity_level", "ai_summary", "is_flagged"],
}


def run_sync(coro: Coroutine[Any, Any, _T]) -> _T:
    """Execute a coroutine from sync code, even when an event loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _extract_json_object(raw: str) -> dict[str, Any]:
    """Parse a JSON object from a model response, tolerating markdown fences."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start : end + 1]
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Provider response must be a JSON object")
    return parsed


def _redact_secret(text: str) -> str:
    """Remove API keys from provider error messages before logging or returning them."""
    return re.sub(r"([?&]key=)[^&\s]+", r"\1<redacted>", text)


def _coerce_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Map provider quirks (unknown labels, string numbers) onto the strict schema."""
    data = dict(payload)

    category = data.get("violence_category")
    if category in ("", "none", "null", "None"):
        category = None
    if category is not None:
        normalized = str(category).strip().lower().replace(" ", "_").replace("-", "_")
        data["violence_category"] = normalized if normalized in VALID_CATEGORIES else "other"
    else:
        data["violence_category"] = None

    severity = str(data.get("severity_level", "low")).strip().lower()
    data["severity_level"] = severity if severity in VALID_SEVERITIES else "low"

    entities = data.get("detected_entities")
    data["detected_entities"] = [str(item) for item in entities if str(item).strip()] if isinstance(entities, list) else []

    try:
        data["sentiment_score"] = max(-100, min(100, int(float(data.get("sentiment_score") or 0))))
    except (TypeError, ValueError):
        data["sentiment_score"] = 0

    data["is_flagged"] = bool(data.get("is_flagged"))
    data["ai_summary"] = str(data.get("ai_summary") or "تم تحليل المحتوى")
    return data


class AIAnalysisService:
    """Evaluate post content through the local Ollama server when enabled."""

    def __init__(self) -> None:
        self.client: Any = None
        provider = str(getattr(settings, "ai_provider", "ollama") or "ollama").strip().lower()
        if provider == "openrouter":
            base_url = settings.openrouter_base_url
            model = settings.ai_model or settings.openrouter_model
            api_key = settings.openrouter_api_key
        elif provider == "google_ai_studio":
            base_url = settings.google_ai_studio_base_url
            model = settings.ai_model or settings.google_ai_studio_model
            api_key = settings.google_ai_studio_api_key or settings.gemini_api_key
        elif provider == "custom_openai":
            base_url = settings.custom_openai_base_url
            model = settings.ai_model or settings.custom_openai_model
            api_key = settings.custom_openai_api_key
        else:
            base_url = settings.ollama_base_url
            model = settings.ai_model or settings.ollama_model
            api_key = settings.ollama_api_key
            provider = "ollama"
        self.enabled = bool(getattr(settings, "ollama_enabled", True)) and bool(base_url)
        self.runtime_config = {
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "api_key": api_key,
        }
        if ollama is None:
            logger.warning("Ollama is not installed; external AI workflows remain available")
            self.enabled = False
            return
        try:
            self.client = self._make_ollama_client(settings.ollama_base_url, settings.ollama_api_key)
            logger.info("Ollama client initialized: host=%s model=%s", settings.ollama_base_url, settings.ollama_model)
        except Exception:
            logger.exception("Failed to initialize Ollama client")
            self.enabled = False
            self.client = None

    @property
    def status(self) -> dict[str, Any]:
        provider = str(self.runtime_config.get("provider") or "ollama").strip().lower()
        if provider not in PROVIDERS:
            provider = "ollama"

        if provider == "ollama":
            enabled = bool(getattr(settings, "ollama_enabled", True)) and bool(self.runtime_config.get("base_url")) and self.client is not None
            model = self.runtime_config.get("model") or settings.ollama_model
        elif provider == "openrouter":
            enabled = self._provider_ready(provider)
            model = self.runtime_config.get("model") or settings.openrouter_model
        elif provider == "custom_openai":
            enabled = self._provider_ready(provider)
            model = self.runtime_config.get("model") or settings.custom_openai_model
        else:
            enabled = self._provider_ready(provider)
            model = self.runtime_config.get("model") or settings.google_ai_studio_model

        return {
            "enabled": enabled,
            "mode": provider if enabled else "disabled",
            "provider": provider if enabled else "disabled",
            "model": model if enabled else None,
            "available_models": MODEL_OPTIONS.get(provider, []),
        }

    def get_config(self) -> dict[str, Any]:
        """Return editable connection fields without exposing the stored secret."""
        provider = self.runtime_config["provider"]
        return {
            "provider": provider,
            "model": self.runtime_config["model"],
            "base_url": self.runtime_config["base_url"],
            "has_api_key": bool(self.runtime_config["api_key"]),
            "configured": bool(self.runtime_config["base_url"]) and (provider in API_KEY_OPTIONAL_PROVIDERS or bool(self.runtime_config["api_key"])),
        }

    def configure(self, provider: str, model: str, base_url: str, api_key: str | None) -> dict[str, Any]:
        provider = provider.strip().lower()
        if provider not in PROVIDERS:
            raise ValueError("Unsupported AI provider")
        if not model.strip() or not base_url.strip():
            raise ValueError("Model and base URL are required")
        normalized_url = base_url.strip().rstrip("/")
        if provider == "ollama" and normalized_url.endswith("/api"):
            normalized_url = normalized_url[:-4]
        self.runtime_config.update({"provider": provider, "model": model.strip(), "base_url": normalized_url})
        if api_key is not None:
            self.runtime_config["api_key"] = api_key.strip()
        if provider == "ollama" and ollama is not None:
            try:
                self.client = self._make_ollama_client(normalized_url, self.runtime_config["api_key"])
                self.enabled = bool(getattr(settings, "ollama_enabled", True))
            except Exception:
                logger.exception("Failed to configure Ollama client")
                self.client = None
                self.enabled = False
        env_path = str(settings.model_config.get("env_file"))
        env_names = {"AI_PROVIDER": provider, "AI_MODEL": model.strip()}
        if provider == "ollama":
            env_names["OLLAMA_BASE_URL"] = normalized_url
            env_names["OLLAMA_MODEL"] = model.strip()
            if api_key is not None and api_key.strip():
                env_names["OLLAMA_API_KEY"] = api_key.strip()
        elif provider == "openrouter":
            env_names["OPENROUTER_BASE_URL"] = normalized_url
            env_names["OPENROUTER_MODEL"] = model.strip()
            if api_key is not None and api_key.strip():
                env_names["OPENROUTER_API_KEY"] = api_key.strip()
        elif provider == "google_ai_studio":
            env_names["GOOGLE_AI_STUDIO_BASE_URL"] = normalized_url
            env_names["GOOGLE_AI_STUDIO_MODEL"] = model.strip()
            if api_key is not None and api_key.strip():
                env_names["GOOGLE_AI_STUDIO_API_KEY"] = api_key.strip()
        else:
            env_names["CUSTOM_OPENAI_BASE_URL"] = normalized_url
            env_names["CUSTOM_OPENAI_MODEL"] = model.strip()
            if api_key is not None and api_key.strip():
                env_names["CUSTOM_OPENAI_API_KEY"] = api_key.strip()
        for key, value in env_names.items():
            set_key(env_path, key, value)
        return self.get_config()

    def fetch_models(self) -> list[str]:
        provider = self.runtime_config["provider"]
        base_url = self.runtime_config["base_url"]
        headers = {"Authorization": f"Bearer {self.runtime_config['api_key']}"} if self.runtime_config["api_key"] else {}
        if provider == "ollama":
            response = httpx.get(f"{base_url}/api/tags", headers=headers, timeout=15, trust_env=False)
            response.raise_for_status()
            return [item["name"] for item in response.json().get("models", []) if item.get("name")]
        if provider in OPENAI_COMPATIBLE_PROVIDERS:
            response = httpx.get(f"{base_url}/models", headers=headers, timeout=15, trust_env=False)
            response.raise_for_status()
            return [item["id"] for item in response.json().get("data", []) if item.get("id")]
        response = httpx.get(f"{base_url}", params={"key": self.runtime_config["api_key"]}, timeout=15, trust_env=False)
        response.raise_for_status()
        return [item["name"].removeprefix("models/") for item in response.json().get("models", []) if item.get("name")]

    def test_connection(self) -> dict[str, Any]:
        models = self.fetch_models()
        return {"success": True, "provider": self.runtime_config["provider"], "model": self.runtime_config["model"], "models": models}

    # ------------------------------------------------------------------
    # Provider chain
    # ------------------------------------------------------------------
    @property
    def supports_vision(self) -> bool:
        """True when the active model can accept inline images."""
        if not bool(getattr(settings, "ai_vision_enabled", True)):
            return False
        model = str(self.runtime_config.get("model") or "").lower()
        return any(hint in model for hint in VISION_MODEL_HINTS)

    def _provider_chain(self) -> list[str]:
        """Ordered providers to attempt: primary first, then the offline fallback."""
        chain: list[str] = []
        primary = str(self.runtime_config.get("provider") or "ollama").strip().lower()
        if self._provider_ready(primary):
            chain.append(primary)
        if bool(getattr(settings, "ai_fallback_enabled", True)):
            fallback = str(getattr(settings, "ai_fallback_provider", "ollama") or "ollama").strip().lower()
            if fallback not in chain and self._provider_ready(fallback):
                chain.append(fallback)
        return chain

    def _provider_ready(self, provider: str) -> bool:
        """Check that the given provider has the credentials/endpoint it needs."""
        if provider == "ollama":
            return bool(getattr(settings, "ollama_enabled", True)) and bool(self._ollama_client()) and bool(self._provider_model("ollama"))
        if provider in OPENAI_COMPATIBLE_PROVIDERS:
            has_key = provider in API_KEY_OPTIONAL_PROVIDERS or bool(self._provider_api_key(provider))
            return has_key and bool(self._provider_base_url(provider)) and bool(self._provider_model(provider))
        if provider == "google_ai_studio":
            return bool(self._provider_api_key("google_ai_studio")) and bool(self._provider_base_url("google_ai_studio")) and bool(self._provider_model(provider))
        return False

    def _is_active(self, provider: str) -> bool:
        return str(self.runtime_config.get("provider") or "").strip().lower() == provider

    def _provider_model(self, provider: str) -> str:
        if self._is_active(provider):
            return str(self.runtime_config.get("model") or "")
        defaults = {
            "ollama": settings.ollama_model,
            "openrouter": settings.openrouter_model,
            "google_ai_studio": settings.google_ai_studio_model,
            "custom_openai": settings.custom_openai_model,
        }
        return str(defaults.get(provider) or "")

    def _provider_base_url(self, provider: str) -> str:
        if self._is_active(provider):
            return str(self.runtime_config.get("base_url") or "")
        defaults = {
            "ollama": settings.ollama_base_url,
            "openrouter": settings.openrouter_base_url,
            "google_ai_studio": settings.google_ai_studio_base_url,
            "custom_openai": settings.custom_openai_base_url,
        }
        return str(defaults.get(provider) or "")

    def _provider_api_key(self, provider: str) -> str:
        if self._is_active(provider):
            return str(self.runtime_config.get("api_key") or "")
        if provider == "openrouter":
            return str(settings.openrouter_api_key or "")
        if provider == "google_ai_studio":
            return str(settings.google_ai_studio_api_key or settings.gemini_api_key or "")
        if provider == "custom_openai":
            return str(settings.custom_openai_api_key or "")
        return ""

    def _ollama_client(self) -> Any:
        """Return the shared Ollama client, creating one lazily for fallback use."""
        if self.client is not None or ollama is None:
            return self.client
        host = self._provider_base_url("ollama")
        if not host:
            return None
        try:
            self.client = self._make_ollama_client(host, self._provider_api_key("ollama"))
        except Exception:
            logger.exception("Failed to initialize the fallback Ollama client")
            self.client = None
        return self.client

    @staticmethod
    def _make_ollama_client(host: str, api_key: str | None = None) -> Any:
        headers = {"Authorization": f"Bearer {api_key.strip()}"} if api_key and api_key.strip() else None
        return ollama.Client(host=host, headers=headers) if headers else ollama.Client(host=host)

    async def analyze_post_content_async(
        self,
        text: str,
        images: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Analyze post text (optionally with inline images) through the provider chain."""
        content = (text or "").strip()
        if not content:
            return self._fallback("Post content is empty")

        chain = self._provider_chain()
        if not chain:
            return self._fallback("AI engine is disabled or unavailable")

        inline_images = images if (images and self.supports_vision) else []
        callers = {
            "ollama": self._call_ollama,
            "openrouter": self._call_openai_compatible,
            "google_ai_studio": self._call_google,
            "custom_openai": self._call_openai_compatible,
        }
        last_error = "AI engine is disabled or unavailable"
        for provider in chain:
            try:
                payload = await callers[provider](provider, content[:10000], inline_images)
                validated = AIAnalysisOutput.model_validate(_coerce_payload(payload))
                result = self._normalize_result(validated.model_dump())
                result.update({
                    "success": True,
                    "provider": provider,
                    "raw_response": payload,
                    "error": None,
                })
                return result
            except (ValidationError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
                detail = _redact_secret(str(exc))
                last_error = f"{provider}: invalid response ({detail})"
                logger.warning("Invalid AI response from %s: %s", provider, detail)
            except (httpx.HTTPError, ConnectionError, TimeoutError, asyncio.TimeoutError) as exc:
                detail = _redact_secret(str(exc)) or type(exc).__name__
                last_error = f"{provider}: connection failed ({detail})"
                logger.warning("AI provider %s unreachable: %s", provider, detail)
            except Exception as exc:  # provider SDK errors (e.g. ollama.ResponseError)
                detail = _redact_secret(str(exc))
                last_error = f"{provider}: {detail}"
                logger.warning("AI provider %s failed: %s", provider, detail)

        return self._fallback(last_error)

    async def _call_google(self, provider: str, content: str, images: list[dict[str, str]]) -> dict[str, Any]:
        """Call Google AI Studio generateContent with a native structured output schema."""
        base_url = self._provider_base_url(provider).rstrip("/")
        model = self._provider_model(provider)
        parts: list[dict[str, Any]] = [{"text": content}]
        for image in images:
            parts.append({"inline_data": {"mime_type": image["mime_type"], "data": image["data"]}})
        body = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0.2,
                "response_mime_type": "application/json",
                "response_schema": RESPONSE_SCHEMA,
            },
        }
        async with httpx.AsyncClient(timeout=self._timeout, trust_env=False) as client:
            response = await client.post(
                f"{base_url}/{model}:generateContent",
                params={"key": self._provider_api_key(provider)},
                json=body,
            )
            response.raise_for_status()
            data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise ValueError("Google AI Studio returned no candidates")
        text_parts = candidates[0].get("content", {}).get("parts") or []
        raw = "".join(str(part.get("text", "")) for part in text_parts)
        return _extract_json_object(raw)

    async def _call_openai_compatible(self, provider: str, content: str, images: list[dict[str, str]]) -> dict[str, Any]:
        """Call an OpenAI-compatible chat completion with JSON-object response formatting."""
        base_url = self._provider_base_url(provider).rstrip("/")
        user_content: Any = content
        if images:
            user_content = [{"type": "text", "text": content}] + [
                {"type": "image_url", "image_url": {"url": f"data:{image['mime_type']};base64,{image['data']}"}}
                for image in images
            ]
        body = {
            "model": self._provider_model(provider),
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        }
        headers = {"X-Title": "SignalDesk"}
        api_key = self._provider_api_key(provider)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        async with httpx.AsyncClient(timeout=self._timeout, trust_env=False) as client:
            response = await client.post(f"{base_url}/chat/completions", headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError(f"{provider} returned no choices")
        return _extract_json_object(choices[0].get("message", {}).get("content", ""))

    async def _call_ollama(self, provider: str, content: str, images: list[dict[str, str]]) -> dict[str, Any]:
        """Call an Ollama-compatible /api/chat endpoint with optional cloud auth."""
        base_url = self._provider_base_url(provider).rstrip("/")
        if not base_url:
            raise ValueError("Ollama base URL is unavailable")

        message: dict[str, Any] = {"role": "user", "content": content}
        if images:
            message["images"] = [image["data"] for image in images]
        headers = {"Authorization": f"Bearer {self._provider_api_key(provider)}"} if self._provider_api_key(provider) else {}
        body = {
            "model": self._provider_model(provider),
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, message],
            "format": "json",
            "stream": False,
        }
        client = self._ollama_client()
        if client is not None and hasattr(client, "chat"):
            data = await asyncio.to_thread(client.chat, **body)
            return _extract_json_object(data.get("message", {}).get("content", ""))

        async with httpx.AsyncClient(timeout=self._timeout, trust_env=False) as client:
            response = await client.post(f"{base_url}/api/chat", headers=headers, json=body)
            if response.status_code == 401:
                detail = response.text.strip()[:240] or response.reason_phrase
                raise PermissionError(f"Ollama authentication failed: {detail}")
            response.raise_for_status()
            data = response.json()
        return _extract_json_object(data.get("message", {}).get("content", ""))

    @property
    def _timeout(self) -> float:
        return float(getattr(settings, "ai_request_timeout", 45.0) or 45.0)

    def analyze_post_content(self, text: str, images: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """Synchronous wrapper kept for existing callers and background workers."""
        return run_sync(self.analyze_post_content_async(text, images))

    @staticmethod
    def _normalize_result(data: dict[str, Any]) -> dict[str, Any]:
        category = data.get("violence_category")
        if category is not None:
            category = str(category).strip().lower()
            if category not in VALID_CATEGORIES:
                category = "other"

        severity = str(data.get("severity_level", "low")).strip().lower()
        if severity not in VALID_SEVERITIES:
            severity = "low"

        raw_entities = data.get("detected_entities") or []
        entities = [str(item).strip()[:120] for item in raw_entities if str(item).strip()][:20] if isinstance(raw_entities, list) else []

        try:
            sentiment_score = max(-100, min(100, int(data.get("sentiment_score") or 0)))
        except (TypeError, ValueError):
            sentiment_score = 0

        return {
            "violence_category": category,
            "severity_level": severity,
            "ai_summary": str(data.get("ai_summary", "تم تحليل المحتوى"))[:1000],
            "is_flagged": bool(data.get("is_flagged")) or severity in {"high", "critical"} or category is not None,
            "detected_entities": entities,
            "sentiment_score": sentiment_score,
        }

    @staticmethod
    def _fallback(error: str) -> dict[str, Any]:
        """Return a non-flagging result when AI cannot provide analysis."""
        return {
            "success": False,
            "provider": None,
            "violence_category": None,
            "severity_level": "low",
            "ai_summary": "تعذر تحليل المحتوى حالياً",
            "is_flagged": False,
            "detected_entities": [],
            "sentiment_score": 0,
            "raw_response": {"error": error},
            "error": error,
        }


ai_service = AIAnalysisService()


def analyze_post_content(text: str, images: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Analyze content using the shared multi-provider service instance."""
    return ai_service.analyze_post_content(text, images)


async def analyze_post_content_async(text: str, images: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Async variant used by the concurrent batch orchestrator."""
    return await ai_service.analyze_post_content_async(text, images)


def fallback_result(error: str) -> dict[str, Any]:
    """Safe, non-flagging analysis payload used when no provider can answer."""
    return AIAnalysisService._fallback(error)


def get_ai_status() -> dict[str, Any]:
    """Return the current optional AI engine status."""
    return ai_service.status
