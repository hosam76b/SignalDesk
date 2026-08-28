"""Local Ollama service for evaluating monitored post content."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from dotenv import set_key

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
}
PROVIDERS = {"ollama", "openrouter", "google_ai_studio"}

VALID_SEVERITIES = {"low", "medium", "high", "critical"}
VALID_CATEGORIES = {
    "hate_speech", "incitement", "physical_violence", "sexual_violence",
    "psychological_violence", "weapon_related", "gang_related", "extremism",
    "self_harm", "other",
}

SYSTEM_PROMPT = """Analyze the input news/post for security and threat monitoring.
Return valid JSON ONLY with exactly these keys:
{
  "violence_category": "string or null",
  "severity_level": "low, medium, high, or critical",
  "ai_summary": "concise summary in clear Arabic language",
  "is_flagged": true or false
}
Set is_flagged to true when severity is high or critical, or when violence or a threat is detected.
Set violence_category to null when the content is clean.
Do not include markdown, explanations, or any keys besides the four requested keys."""


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
        else:
            base_url = settings.ollama_base_url
            model = settings.ai_model or settings.ollama_model
            api_key = ""
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
            self.client = ollama.Client(host=settings.ollama_base_url)
            logger.info("Ollama client initialized: host=%s model=%s", settings.ollama_base_url, settings.ollama_model)
        except Exception:
            logger.exception("Failed to initialize Ollama client")
            self.enabled = False
            self.client = None

    @property
    def status(self) -> dict[str, Any]:
        provider = str(self.runtime_config.get("provider") or "ollama").strip().lower()
        if provider not in {"ollama", "openrouter", "google_ai_studio"}:
            provider = "ollama"

        if provider == "ollama":
            enabled = bool(getattr(settings, "ollama_enabled", True)) and bool(self.runtime_config.get("base_url")) and self.client is not None
            model = self.runtime_config.get("model") or settings.ollama_model
        elif provider == "openrouter":
            enabled = bool(self.runtime_config.get("api_key")) and bool(self.runtime_config.get("base_url"))
            model = self.runtime_config.get("model") or settings.openrouter_model
        else:
            enabled = bool(self.runtime_config.get("api_key")) and bool(self.runtime_config.get("base_url"))
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
            "configured": bool(self.runtime_config["base_url"]) and (provider == "ollama" or bool(self.runtime_config["api_key"])),
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
                self.client = ollama.Client(host=normalized_url)
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
        elif provider == "openrouter":
            env_names["OPENROUTER_BASE_URL"] = normalized_url
            env_names["OPENROUTER_MODEL"] = model.strip()
            if api_key is not None and api_key.strip():
                env_names["OPENROUTER_API_KEY"] = api_key.strip()
        else:
            env_names["GOOGLE_AI_STUDIO_BASE_URL"] = normalized_url
            env_names["GOOGLE_AI_STUDIO_MODEL"] = model.strip()
            if api_key is not None and api_key.strip():
                env_names["GOOGLE_AI_STUDIO_API_KEY"] = api_key.strip()
        for key, value in env_names.items():
            set_key(env_path, key, value)
        return self.get_config()

    def fetch_models(self) -> list[str]:
        provider = self.runtime_config["provider"]
        base_url = self.runtime_config["base_url"]
        headers = {"Authorization": f"Bearer {self.runtime_config['api_key']}"} if self.runtime_config["api_key"] else {}
        if provider == "ollama":
            response = httpx.get(f"{base_url}/api/tags", timeout=15, trust_env=False)
            response.raise_for_status()
            return [item["name"] for item in response.json().get("models", []) if item.get("name")]
        if provider == "openrouter":
            response = httpx.get(f"{base_url}/models", headers=headers, timeout=15, trust_env=False)
            response.raise_for_status()
            return [item["id"] for item in response.json().get("data", []) if item.get("id")]
        response = httpx.get(f"{base_url}", params={"key": self.runtime_config["api_key"]}, timeout=15, trust_env=False)
        response.raise_for_status()
        return [item["name"].removeprefix("models/") for item in response.json().get("models", []) if item.get("name")]

    def test_connection(self) -> dict[str, Any]:
        models = self.fetch_models()
        return {"success": True, "provider": self.runtime_config["provider"], "model": self.runtime_config["model"], "models": models}

    def analyze_post_content(self, text: str) -> dict[str, Any]:
        """Analyze post text and return a normalized JSON-compatible result."""
        content = (text or "").strip()
        if not content:
            return self._fallback("Post content is empty")
        if self.runtime_config.get("provider") != "ollama" or self.client is None or not self.status["enabled"]:
            return self._fallback("AI engine is disabled or unavailable")

        try:
            response = self.client.chat(
                model=self.runtime_config["model"],
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": content[:10000]},
                ],
                format="json",
            )
            response_content = response["message"]["content"]
            parsed_response = json.loads(response_content)
            if not isinstance(parsed_response, dict):
                raise ValueError("Ollama response must be a JSON object")

            result = self._normalize_result(parsed_response)
            result.update({
                "success": True,
                "raw_response": parsed_response,
                "error": None,
            })
            return result
        except (KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
            logger.exception("Invalid JSON response from Ollama: %s", exc)
            return self._fallback(str(exc))
        except (ConnectionError, TimeoutError) as exc:
            logger.exception("Ollama connection error while analyzing content: %s", exc)
            return self._fallback(str(exc))
        except Exception as exc:
            if ollama is not None and isinstance(exc, ollama.ResponseError):
                logger.exception("Ollama request failed: %s", exc)
            else:
                logger.exception("Unexpected Ollama analysis failure: %s", exc)
            return self._fallback(str(exc))

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

        return {
            "violence_category": category,
            "severity_level": severity,
            "ai_summary": str(data.get("ai_summary", "تم تحليل المحتوى"))[:1000],
            "is_flagged": severity in {"high", "critical"} or category is not None,
        }

    @staticmethod
    def _fallback(error: str) -> dict[str, Any]:
        """Return a non-flagging result when AI cannot provide analysis."""
        return {
            "success": False,
            "violence_category": None,
            "severity_level": "low",
            "ai_summary": "تعذر تحليل المحتوى حالياً",
            "is_flagged": False,
            "raw_response": {"error": error},
            "error": error,
        }


ai_service = AIAnalysisService()


def analyze_post_content(text: str) -> dict[str, Any]:
    """Analyze content using the shared Ollama service instance."""
    return ai_service.analyze_post_content(text)


def get_ai_status() -> dict[str, Any]:
    """Return the current optional AI engine status."""
    return ai_service.status
