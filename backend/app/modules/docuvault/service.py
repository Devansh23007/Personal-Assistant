from datetime import datetime, timezone
import os
from pathlib import Path
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.docuvault.models import Document
from app.modules.docuvault.schemas import (
    DocumentCreate,
    DocumentRead,
    DocumentSearchResult,
    DocumentUpdate,
    SearchCitation,
)

STORAGE_ROOT = Path("storage/documents")


def _generate_doc_summary(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return "Empty document."
    first_few = " ".join(lines[:3])
    if len(first_few) > 280:
        return first_few[:277] + "…"
    return first_few


def seed_demo_documents_if_empty(db: Session, user_id: int) -> None:
    count = db.scalar(select(func.count(Document.id)).where(Document.user_id == user_id))
    if count and count > 0:
        return

    sample_docs = [
        {
            "title": "Agentic Coding System Architecture",
            "filename": "agentic_architecture.md",
            "content_type": "text/markdown",
            "tags": "architecture,ai,agents",
            "content_text": (
                "# Agentic Coding System Architecture\n\n"
                "## Core Design Principles\n"
                "1. Modular Monolith: Every feature lives in its own module with dedicated models, schemas, and endpoints.\n"
                "2. Explicit Human-in-the-Loop: Critical actions like sending emails or irreversible financial operations require user approval.\n"
                "3. Source-Linked Retrieval: Document search must cite specific document IDs and excerpts for transparency.\n"
                "4. Spaced Repetition: Revision loops improve memory retention using active recall intervals."
            ),
        },
        {
            "title": "Python 3.14 Concurrency & Async Guide",
            "filename": "python_async_guide.txt",
            "content_type": "text/plain",
            "tags": "python,async,programming",
            "content_text": (
                "Python Asynchronous Programming Best Practices:\n\n"
                "- Use asyncio for I/O bound tasks such as HTTP requests and database sessions.\n"
                "- Avoid running CPU-heavy computations inside event loop threads; offload to ThreadPoolExecutor via to_thread.\n"
                "- Always use proper connection pooling with pool_pre_ping enabled to prevent stale socket errors.\n"
                "- Keep FastAPI dependency injections cleanly scoped per request."
            ),
        },
    ]

    for item in sample_docs:
        summary = _generate_doc_summary(item["content_text"])
        doc = Document(
            user_id=user_id,
            title=item["title"],
            filename=item["filename"],
            file_path=f"storage/documents/{user_id}/{item['filename']}",
            file_size=len(item["content_text"].encode("utf-8")),
            content_type=item["content_type"],
            content_text=item["content_text"],
            summary=summary,
            tags=item["tags"],
        )
        db.add(doc)
    db.commit()


def create_document(db: Session, user_id: int, payload: DocumentCreate) -> Document:
    user_dir = STORAGE_ROOT / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    file_path = user_dir / payload.filename

    # Save to disk safely
    try:
        file_path.write_text(payload.content_text, encoding="utf-8")
    except Exception:
        pass

    summary = _generate_doc_summary(payload.content_text)
    tags_str = ",".join(payload.tags) if payload.tags else None

    doc = Document(
        user_id=user_id,
        title=payload.title,
        filename=payload.filename,
        file_path=str(file_path).replace("\\", "/"),
        file_size=len(payload.content_text.encode("utf-8")),
        content_type=payload.content_type,
        content_text=payload.content_text,
        summary=summary,
        tags=tags_str,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def list_documents(
    db: Session,
    user_id: int,
    tag: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Document]:
    query = select(Document).where(Document.user_id == user_id)
    if tag:
        query = query.where(Document.tags.ilike(f"%{tag}%"))
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                Document.title.ilike(term),
                Document.filename.ilike(term),
                Document.content_text.ilike(term),
            )
        )
    query = query.order_by(Document.created_at.desc()).offset(offset).limit(limit)
    return list(db.scalars(query).all())


def get_document(db: Session, user_id: int, doc_id: int) -> Document | None:
    return db.scalar(select(Document).where(Document.user_id == user_id, Document.id == doc_id))


def update_document(
    db: Session,
    user_id: int,
    doc_id: int,
    payload: DocumentUpdate,
) -> Document | None:
    doc = get_document(db, user_id, doc_id)
    if not doc:
        return None

    if payload.title is not None:
        doc.title = payload.title
    if payload.tags is not None:
        doc.tags = ",".join(payload.tags) if payload.tags else None
    if payload.summary is not None:
        doc.summary = payload.summary

    db.commit()
    db.refresh(doc)
    return doc


def delete_document(db: Session, user_id: int, doc_id: int) -> bool:
    doc = get_document(db, user_id, doc_id)
    if not doc:
        return False
    # Remove file from disk if exists
    try:
        if os.path.exists(doc.file_path):
            os.remove(doc.file_path)
    except Exception:
        pass

    db.delete(doc)
    db.commit()
    return True


def search_documents_rag(
    db: Session,
    user_id: int,
    query: str,
    limit: int = 5,
) -> DocumentSearchResult:
    terms = [re.escape(t.lower()) for t in query.strip().split() if len(t) > 2]
    all_docs = list(db.scalars(select(Document).where(Document.user_id == user_id)).all())

    citations: list[SearchCitation] = []
    for doc in all_docs:
        text_lower = doc.content_text.lower()
        title_lower = doc.title.lower()

        # Score based on keyword matches
        matches = sum(1 for term in terms if term in text_lower or term in title_lower)
        if matches > 0 or not terms:
            # Extract excerpt
            snippet = ""
            for term in terms:
                pos = text_lower.find(term)
                if pos != -1:
                    start = max(0, pos - 60)
                    end = min(len(doc.content_text), pos + 120)
                    snippet = f"…{doc.content_text[start:end].strip()}…"
                    break
            if not snippet:
                snippet = doc.content_text[:160] + "…"

            citations.append(
                SearchCitation(
                    document_id=doc.id,
                    title=doc.title,
                    snippet=snippet,
                    match_score=float(matches),
                )
            )

    citations.sort(key=lambda x: x.match_score, reverse=True)
    return DocumentSearchResult(
        query=query,
        total_matches=len(citations),
        citations=citations[:limit],
    )
