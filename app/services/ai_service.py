"""Local Ollama service for evaluating monitored post content."""

from __future__ import annotations

import json
import logging
from typing import Any

try:
    import ollama
except ImportError:  # pragma: no cover - depends on deployment extras
    ollama = None  # type: ignore[assignment]

from config import settings

logger = logging.getLogger(__name__)

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
    """Evaluate post content through the local Ollama server."""

    def __init__(self) -> None:
        self.client: Any = None
        if ollama is None:
            logger.warning("Ollama is not installed; external AI workflows remain available")
            return
        try:
            self.client = ollama.Client(
                host=settings.ollama_base_url,
            )
            logger.info(
                "Ollama client initialized: host=%s model=%s",
                settings.ollama_base_url,
                settings.ollama_model,
            )
        except Exception:
            logger.exception("Failed to initialize Ollama client")

    def analyze_post_content(self, text: str) -> dict[str, Any]:
        """Analyze post text and return a normalized JSON-compatible result."""
        content = (text or "").strip()
        if not content:
            return self._fallback("Post content is empty")
        if self.client is None:
            return self._fallback("Ollama client is unavailable")

        try:
            response = self.client.chat(
                model=settings.ollama_model,
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
        """Return a non-flagging result when Ollama cannot provide analysis."""
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
