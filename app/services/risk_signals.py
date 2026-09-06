"""Deterministic risk screening used as a safety net around the AI analysis.

The LLM providers can be unavailable, rate limited or simply under-rate an
explicit threat. This module applies rule-based Arabic/English detection so that
self-harm, violence and weapon content is always surfaced, and it never lowers a
severity the model already assigned.
"""

from __future__ import annotations

import html
import re
import unicodedata

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

_TAG_PATTERN = re.compile(r"<[^>]+>")
_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u0652\u0640]")

# (compiled pattern, violence_category, severity)
_RISK_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(
            r"انتحار|انتحر|هنتحر|سانتحر|ساانتحر|هموت|بموت|عايز اموت|عاوز اموت|اريد الموت|"
            r"انهي حياتي|انهاء حياتي|اقتل نفسي|هقتل نفسي|اذي نفسي|ايذاء النفس|اقطع نفسي|"
            r"\bsuicide\b|\bsuicidal\b|kill myself|end my life|killing myself|"
            r"self[ -]?harm|hurt myself|cut myself|want to die|wanna die",
            re.IGNORECASE,
        ),
        "self_harm",
        "critical",
    ),
    (
        re.compile(
            r"هقتلك|ساقتلك|سنقتل|هنقتلكم|اقتلوا|سنذبح|نذبح|هنفجر|سنفجر|تفجير|عملية انتحارية|"
            r"\bi will kill you\b|\bkill (?:him|her|them|you)\b|\bmassacre\b|\bbomb(?:ing)?\b|"
            r"\bshoot (?:him|her|them|you)\b|death threat",
            re.IGNORECASE,
        ),
        "physical_violence",
        "critical",
    ),
    (
        re.compile(
            r"سلاح|اسلحه|أسلحة|مسدس|بندقيه|بندقية|رصاص|قنبله|قنبلة|متفجرات|ذخيره|ذخيرة|"
            r"\bfirearm\b|\bhandgun\b|\brifle\b|\bammunition\b|\bexplosive",
            re.IGNORECASE,
        ),
        "weapon_related",
        "high",
    ),
    (
        re.compile(
            r"تحريض|حرضوا|انتفضوا واقتلوا|اقتلوهم|احرقوا|هاجموا|خربوا|"
            r"\bincite\b|\bincitement\b|burn (?:it|them) down|attack them",
            re.IGNORECASE,
        ),
        "incitement",
        "high",
    ),
    (
        re.compile(
            r"داعش|القاعده|القاعدة|تنظيم ارهابي|جهاد مسلح|خلافه اسلاميه|"
            r"\bisis\b|\bal[- ]?qaeda\b|\bterror(?:ist|ism)\b|violent jihad",
            re.IGNORECASE,
        ),
        "extremism",
        "high",
    ),
    (
        re.compile(
            r"اغتصاب|تحرش جنسي|استغلال جنسي|"
            r"\brape\b|sexual assault|sexual abuse",
            re.IGNORECASE,
        ),
        "sexual_violence",
        "critical",
    ),
]


def clean_text(raw: str | None) -> str:
    """Strip HTML markup/entities that scrapers store verbatim (Reddit RSS, feeds)."""
    if not raw:
        return ""
    text = _COMMENT_PATTERN.sub(" ", raw)
    text = _TAG_PATTERN.sub(" ", text)
    text = html.unescape(text)
    return " ".join(text.split())


def _normalize(text: str) -> str:
    """Fold Arabic orthographic variants so keyword rules match real-world spelling."""
    normalized = unicodedata.normalize("NFKC", text).lower()
    normalized = _ARABIC_DIACRITICS.sub("", normalized)
    return normalized.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"}))


def screen_text(text: str) -> dict[str, str | list[str]] | None:
    """Return the highest-severity rule match for ``text``, or None when clean."""
    normalized = _normalize(clean_text(text))
    if not normalized:
        return None

    best: tuple[int, str, str] | None = None
    matches: list[str] = []
    for pattern, category, severity in _RISK_RULES:
        found = pattern.search(normalized)
        if not found:
            continue
        matches.append(found.group(0))
        rank = SEVERITY_ORDER[severity]
        if best is None or rank > best[0]:
            best = (rank, category, severity)

    if best is None:
        return None
    return {"violence_category": best[1], "severity_level": best[2], "matched": matches}


def apply_risk_signals(analysis: dict, text: str) -> dict:
    """Escalate an analysis result with rule-based findings; never downgrades it."""
    signal = screen_text(text)
    if signal is None:
        return analysis

    current = SEVERITY_ORDER.get(str(analysis.get("severity_level") or "low"), 0)
    detected = SEVERITY_ORDER[str(signal["severity_level"])]
    if detected > current:
        analysis["severity_level"] = signal["severity_level"]
        analysis["violence_category"] = signal["violence_category"]
    elif not analysis.get("violence_category"):
        analysis["violence_category"] = signal["violence_category"]

    analysis["is_flagged"] = True
    analysis["risk_signals"] = signal["matched"]
    if not analysis.get("success") and analysis.get("ai_summary") in (None, "", "تعذر تحليل المحتوى حالياً"):
        analysis["ai_summary"] = f"رصد آلي لمؤشرات خطورة ({signal['violence_category']}) بانتظار التحليل الكامل"
    return analysis
