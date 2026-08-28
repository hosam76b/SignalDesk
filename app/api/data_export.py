"""Read and write APIs for external automation integrations."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_topic_user, get_current_user
from app.db.session import get_db
from app.models.post import Post
from app.models.user import User

router = APIRouter(prefix="/api", tags=["Data Integration"])


class PostExport(BaseModel):
    """Stable post contract for n8n, Hermes, and custom consumers."""

    id: int
    topic_id: int
    external_id: str
    platform: str
    source_id: int
    source_url: str | None
    title: str | None
    content: str
    author: str
    published_at: datetime
    scraped_at: datetime
    post_url: str | None
    media_urls: list[Any] = Field(default_factory=list)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    violence_category: str | None
    severity_level: str | None
    ai_summary: str | None
    tags: list[str] = Field(default_factory=list)
    is_flagged: bool
    is_important: bool
    is_dangerous: bool

    @classmethod
    def from_post(cls, post: Post) -> "PostExport":
        metadata = post.raw_metadata if isinstance(post.raw_metadata, dict) else {}
        return cls(
            id=post.id,
            topic_id=post.topic_id,
            external_id=post.external_id,
            platform=post.platform,
            source_id=post.source_id,
            source_url=post.source_url or metadata.get("source_url") or post.post_url,
            title=post.title,
            content=post.content,
            author=post.author,
            published_at=post.published_at,
            scraped_at=post.scraped_at,
            post_url=post.post_url,
            media_urls=post.media_urls if isinstance(post.media_urls, list) else [],
            raw_metadata=metadata,
            violence_category=post.violence_category,
            severity_level=post.severity_level,
            ai_summary=post.ai_summary,
            tags=post.tags if isinstance(post.tags, list) else [],
            is_flagged=post.is_flagged,
            is_important=post.is_important,
            is_dangerous=post.is_dangerous,
        )


class PostAnalysisUpdate(BaseModel):
    """Analysis result submitted by an external automation workflow."""

    severity_level: Literal["low", "medium", "high", "critical"]
    ai_summary: str = Field(min_length=1, max_length=10000)
    tags: list[str] = Field(default_factory=list, max_length=100)
    is_flagged: bool


@router.get("/data/posts/latest", response_model=list[PostExport])
def latest_posts(
    since: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[PostExport]:
    """Return recently scraped posts for polling consumers."""
    query = db.query(Post)
    if since is not None:
        query = query.filter(Post.scraped_at > since)
    posts = query.order_by(Post.scraped_at.desc(), Post.id.desc()).limit(limit).all()
    return [PostExport.from_post(post) for post in posts]


@router.get("/data/posts/stream", response_model=list[PostExport], include_in_schema=False)
def stream_posts(
    since: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[PostExport]:
    """Compatibility alias for consumers using the stream route."""
    return latest_posts(since=since, limit=limit, db=db, _=_) 


@router.patch("/posts/{post_id}/analysis", response_model=PostExport)
def update_post_analysis(
    post_id: int,
    update: PostAnalysisUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PostExport:
    """Persist externally generated analysis for one ingested post."""
    post = db.query(Post).filter(Post.id == post_id).first()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    post.severity_level = update.severity_level
    post.ai_summary = update.ai_summary
    post.tags = sorted(set(tag.strip() for tag in update.tags if tag.strip()))
    post.is_flagged = update.is_flagged or update.severity_level in {"high", "critical"}
    db.commit()
    db.refresh(post)
    return PostExport.from_post(post)


def _topic_post_rows(db: Session, topic_id: int) -> list[dict[str, Any]]:
    rows = db.query(Post).filter(Post.topic_id == topic_id).order_by(Post.published_at.desc()).all()
    return [{
        "published_at": (post.published_at.isoformat() if post.published_at else ""),
        "author": post.author,
        "platform": post.platform,
        "url": post.post_url or post.source_url or "",
        "content": post.content,
        "sentiment": post.sentiment or "unknown",
        "severity_score": post.sentiment_score if post.sentiment_score is not None else 0,
        "content_hash": post.content_fingerprint or "",
        "topic_id": post.topic_id,
    } for post in rows]


@router.get("/topics/{topic_id}/export/csv")
def export_topic_csv(
    topic_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_topic_user),
) -> Response:
    """Download a filtered topic dataset as CSV."""
    fieldnames = ["published_at", "author", "platform", "url", "content", "sentiment", "severity_score", "content_hash", "topic_id"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in _topic_post_rows(db, topic_id):
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    payload = output.getvalue().encode("utf-8")
    return Response(
        content=payload,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="topic_{topic_id}_export.csv"'},
    )


@router.get("/topics/{topic_id}/export/json")
def export_topic_json(
    topic_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_topic_user),
) -> Response:
    """Download a filtered topic dataset as JSON."""
    payload = json.dumps(_topic_post_rows(db, topic_id), ensure_ascii=False, indent=2).encode("utf-8")
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="topic_{topic_id}_export.json"'},
    )


@router.get("/topics/{topic_id}/export/xlsx")
def export_topic_xlsx(
    topic_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_topic_user),
) -> Response:
    """Download a filtered topic dataset as a minimal .xlsx workbook."""
    rows = _topic_post_rows(db, topic_id)
    header = ["published_at", "author", "platform", "url", "content", "sentiment", "severity_score", "content_hash", "topic_id"]
    all_rows = [header]
    for row in rows:
        all_rows.append([row.get(key, "") for key in header])

    def excel_col(index: int) -> str:
        result = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            result = chr(65 + remainder) + result
        return result

    sheet_rows = []
    for row_idx, row in enumerate(all_rows, start=1):
        cell_xml = []
        for col_idx, value in enumerate(row, start=1):
            ref = f"{excel_col(col_idx)}{row_idx}"
            if isinstance(value, (int, float)):
                cell_xml.append(f'<c r="{ref}" t="n"><v>{value}</v></c>')
            else:
                text = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                cell_xml.append(f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        sheet_rows.append(f"<row r=\"{row_idx}\">{''.join(cell_xml)}</row>")

    sheet_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{''.join(sheet_rows)}</sheetData></worksheet>'''
    workbook_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Posts" sheetId="1" r:id="rId1"/></sheets></workbook>'''
    rels_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'''
    app_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Microsoft Excel</Application></Properties>'''
    core_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:creator>SignalDesk</dc:creator><cp:lastModifiedBy>SignalDesk</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">2025-01-01T00:00:00Z</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">2025-01-01T00:00:00Z</dcterms:modified></cp:coreProperties>'''
    styles_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts><fills count="1"><fill><patternFill patternType="none"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''
    xlsx_buffer = io.BytesIO()
    with zipfile.ZipFile(xlsx_buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', content_types)
        archive.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>')
        archive.writestr('docProps/core.xml', core_xml)
        archive.writestr('docProps/app.xml', app_xml)
        archive.writestr('xl/workbook.xml', workbook_xml)
        archive.writestr('xl/_rels/workbook.xml.rels', rels_xml)
        archive.writestr('xl/worksheets/sheet1.xml', sheet_xml)
        archive.writestr('xl/styles.xml', styles_xml)
    return Response(
        content=xlsx_buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="topic_{topic_id}_export.xlsx"'},
    )
