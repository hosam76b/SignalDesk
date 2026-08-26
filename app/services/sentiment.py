"""Small dependency-free sentiment classifier used before optional AI analysis."""

POSITIVE = {"good", "great", "safe", "success", "نجاح", "جيد", "آمن"}
NEGATIVE = {"bad", "danger", "violence", "threat", "سيئ", "خطر", "عنف", "تهديد"}


def analyze_sentiment(text: str) -> dict[str, float | str]:
    words = set((text or "").lower().split())
    positive = len(words & POSITIVE)
    negative = len(words & NEGATIVE)
    score = (positive - negative) / max(positive + negative, 1)
    label = "positive" if score > 0 else "negative" if score < 0 else "neutral"
    return {"label": label, "score": round(score, 3)}