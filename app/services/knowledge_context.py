"""Semantic (vector) retrieval of topic-scoped Knowledge Base context for AI analysis.

Documents are chunked and embedded with a deterministic, dependency-free hashing
embedder, so retrieval works fully offline and needs no schema change. Embeddings
are cached in-process per document revision and rebuilt when a document changes.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import unicodedata
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgeDocument
from config import settings

logger = logging.getLogger(__name__)

MAX_DOCUMENTS = 3
MAX_CHARS_PER_DOCUMENT = 800
MAX_INDEXED_DOCUMENTS = 50
EMBEDDING_DIM = 384
MIN_RELEVANCE = 0.05

_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u0652\u0640]")
_TOKEN_PATTERN = re.compile(r"[\w\u0600-\u06ff]+", re.UNICODE)

# document_id -> (revision_key, [(chunk_text, embedding)])
_CHUNK_CACHE: dict[int, tuple[tuple[object, ...], list[tuple[str, list[float]]]]] = {}


def _normalize(text: str) -> str:
    """Lowercase and strip Arabic diacritics/orthographic variants for stable tokens."""
    normalized = unicodedata.normalize("NFKC", text).lower()
    normalized = _ARABIC_DIACRITICS.sub("", normalized)
    return normalized.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"}))


def _features(text: str) -> Iterable[str]:
    """Yield word unigrams, word bigrams and character trigrams."""
    tokens = _TOKEN_PATTERN.findall(_normalize(text))
    yield from tokens
    for first, second in zip(tokens, tokens[1:]):
        yield f"{first}_{second}"
    joined = " ".join(tokens)
    for index in range(len(joined) - 2):
        yield joined[index : index + 3]


def embed_text(text: str) -> list[float]:
    """Return an L2-normalized hashed bag-of-features embedding."""
    vector = [0.0] * EMBEDDING_DIM
    for feature in _features(text or ""):
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
        vector[index] += 1.0 if digest[4] & 1 else -1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Cosine similarity for already normalized vectors, clamped to [-1, 1]."""
    score = sum(a * b for a, b in zip(left, right))
    return max(-1.0, min(1.0, score))


def chunk_text(text: str, chunk_chars: int | None = None) -> list[str]:
    """Split text into sentence-aligned chunks small enough to embed meaningfully."""
    size = int(chunk_chars or getattr(settings, "knowledge_chunk_chars", 700) or 700)
    sentences = re.split(r"(?<=[.!?؟\n])\s+", (text or "").strip())
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 > size and current:
            chunks.append(current)
            current = sentence[:size]
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def index_document(document: KnowledgeDocument) -> list[tuple[str, list[float]]]:
    """Return (and cache) the embedded chunks for one knowledge document."""
    text = document.extracted_text or ""
    revision = (document.updated_at, len(text))
    cached = _CHUNK_CACHE.get(document.id)
    if cached is not None and cached[0] == revision:
        return cached[1]
    embedded = [(chunk, embed_text(chunk)) for chunk in chunk_text(text)]
    _CHUNK_CACHE[document.id] = (revision, embedded)
    return embedded


def invalidate_document(document_id: int) -> None:
    """Drop cached embeddings after a document is updated or deleted."""
    _CHUNK_CACHE.pop(document_id, None)


def _legacy_context(documents: list[KnowledgeDocument]) -> str:
    """Chronological excerpts, used when RAG is disabled or no query is supplied."""
    blocks = []
    for document in documents[:MAX_DOCUMENTS]:
        excerpt = (document.extracted_text or "").strip()[:MAX_CHARS_PER_DOCUMENT]
        if excerpt:
            blocks.append(f"[{document.title}]: {excerpt}")
    return "\n".join(blocks)


def get_topic_knowledge_context(db: Session, topic_id: int, query: str = "", top_k: int | None = None) -> str:
    """Return the Knowledge Base chunks most relevant to ``query``, or "" if none.

    Without a query (or with RAG disabled) it falls back to the most recent excerpts.
    """
    documents = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.topic_id == topic_id, KnowledgeDocument.extracted_text.isnot(None))
        .order_by(KnowledgeDocument.created_at.desc())
        .limit(MAX_INDEXED_DOCUMENTS)
        .all()
    )
    if not documents:
        return ""

    if not bool(getattr(settings, "knowledge_rag_enabled", True)) or not (query or "").strip():
        return _legacy_context(documents)

    limit = int(top_k or getattr(settings, "knowledge_rag_top_k", 3) or 3)
    query_vector = embed_text(query)
    scored: list[tuple[float, str, str]] = []
    for document in documents:
        try:
            for chunk, vector in index_document(document):
                scored.append((cosine_similarity(query_vector, vector), document.title, chunk))
        except Exception:
            logger.exception("Failed to embed knowledge document %s", document.id)

    scored.sort(key=lambda item: item[0], reverse=True)
    blocks = [
        f"[{title}]: {chunk[:MAX_CHARS_PER_DOCUMENT]}"
        for score, title, chunk in scored[:limit]
        if score >= MIN_RELEVANCE
    ]
    return "\n".join(blocks) if blocks else _legacy_context(documents)
