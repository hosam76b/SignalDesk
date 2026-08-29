"""Builds topic-scoped reference context from the Knowledge Base for AI analysis."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgeDocument

MAX_DOCUMENTS = 3
MAX_CHARS_PER_DOCUMENT = 800


def get_topic_knowledge_context(db: Session, topic_id: int) -> str:
    """Return a short reference block from the topic's Knowledge Base documents, or "" if none."""
    documents = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.topic_id == topic_id, KnowledgeDocument.extracted_text.isnot(None))
        .order_by(KnowledgeDocument.created_at.desc())
        .limit(MAX_DOCUMENTS)
        .all()
    )
    if not documents:
        return ""

    blocks = []
    for document in documents:
        excerpt = (document.extracted_text or "").strip()[:MAX_CHARS_PER_DOCUMENT]
        if excerpt:
            blocks.append(f"[{document.title}]: {excerpt}")
    return "\n".join(blocks)
