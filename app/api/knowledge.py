"""Knowledge base document management endpoints."""

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin_user, get_current_user
from app.db.session import get_db
from app.models.knowledge import KnowledgeDocument
from app.models.topic import Topic
from app.models.user import User

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge Base"])
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "storage" / "knowledge"
ALLOWED_TYPES = {".txt", ".md", ".csv", ".json", ".pdf"}


class KnowledgeDocumentRead(BaseModel):
    id: int
    topic_id: int
    title: str
    filename: str
    file_type: str
    tags: str | None
    extracted_text: str | None
    created_at: str


def serialize(document: KnowledgeDocument) -> dict:
    return {
        "id": document.id, "topic_id": document.topic_id, "title": document.title,
        "filename": document.filename, "file_type": document.file_type,
        "tags": document.tags, "extracted_text": document.extracted_text,
        "created_at": document.created_at.isoformat(),
    }


@router.get("/topics/{topic_id}/documents", response_model=list[KnowledgeDocumentRead])
def list_documents(topic_id: int, search: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    query = db.query(KnowledgeDocument).filter(KnowledgeDocument.topic_id == topic_id)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter((KnowledgeDocument.title.ilike(term)) | (KnowledgeDocument.extracted_text.ilike(term)) | (KnowledgeDocument.tags.ilike(term)))
    return [serialize(item) for item in query.order_by(KnowledgeDocument.created_at.desc()).all()]


@router.post("/topics/{topic_id}/documents", response_model=KnowledgeDocumentRead)
async def upload_document(topic_id: int, title: str = Form(...), tags: str | None = Form(None), file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    if db.query(Topic).filter(Topic.id == topic_id).first() is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Supported files: TXT, Markdown, CSV, JSON, PDF")
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File is too large; maximum size is 20 MB")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_path = UPLOAD_DIR / f"{uuid4().hex}{suffix}"
    stored_path.write_bytes(content)
    extracted_text = None
    if suffix != ".pdf":
        extracted_text = content.decode("utf-8", errors="replace")[:500_000]
    document = KnowledgeDocument(topic_id=topic_id, created_by_id=current_user.id, title=title.strip(), filename=file.filename or stored_path.name, file_type=file.content_type or suffix, file_path=str(stored_path), extracted_text=extracted_text, tags=tags)
    db.add(document)
    db.commit()
    db.refresh(document)
    return serialize(document)


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_admin_user)):
    document = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    Path(document.file_path).unlink(missing_ok=True)
    db.delete(document)
    db.commit()