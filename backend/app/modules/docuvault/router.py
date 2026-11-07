from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.docuvault.schemas import (
    DocumentCreate,
    DocumentRead,
    DocumentSearchResult,
    DocumentUpdate,
)
from app.modules.docuvault.service import (
    create_document,
    delete_document,
    get_document,
    list_documents,
    search_documents_rag,
    seed_demo_documents_if_empty,
    update_document,
)

router = APIRouter(prefix="/docuvault", tags=["docuvault"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/documents", response_model=list[DocumentRead])
def get_documents(
    current_user: CurrentUser,
    db: DbSession,
    tag: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[DocumentRead]:
    seed_demo_documents_if_empty(db, current_user.id)
    docs = list_documents(db, current_user.id, tag=tag, search=search, limit=limit, offset=offset)
    return [DocumentRead.model_validate(d) for d in docs]


@router.post("/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload_document(
    payload: DocumentCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> DocumentRead:
    doc = create_document(db, current_user.id, payload)
    return DocumentRead.model_validate(doc)


@router.get("/documents/search", response_model=DocumentSearchResult)
def search_documents(
    current_user: CurrentUser,
    db: DbSession,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=5, ge=1, le=20),
) -> DocumentSearchResult:
    seed_demo_documents_if_empty(db, current_user.id)
    return search_documents_rag(db, current_user.id, query=q, limit=limit)


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_single_document(document_id: int, current_user: CurrentUser, db: DbSession) -> DocumentRead:
    doc = get_document(db, current_user.id, document_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentRead.model_validate(doc)


@router.patch("/documents/{document_id}", response_model=DocumentRead)
def update_existing_document(
    document_id: int,
    payload: DocumentUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> DocumentRead:
    doc = update_document(db, current_user.id, document_id, payload)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentRead.model_validate(doc)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_document(document_id: int, current_user: CurrentUser, db: DbSession) -> None:
    deleted = delete_document(db, current_user.id, document_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
