from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.inboxzero.schemas import (
    EmailDraftCreate,
    EmailDraftRead,
    EmailDraftUpdate,
    EmailMessageRead,
    EmailMessageUpdate,
    GenerateDraftRequest,
    InboxStatsRead,
)
from app.modules.inboxzero.service import (
    approve_and_send_draft,
    create_draft,
    delete_draft,
    generate_draft_reply,
    get_draft,
    get_inbox_stats,
    get_message,
    get_or_create_account,
    list_drafts,
    list_messages,
    seed_demo_inbox_if_empty,
    update_draft,
    update_message,
)

router = APIRouter(prefix="/inboxzero", tags=["inboxzero"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/stats", response_model=InboxStatsRead)
def get_stats(current_user: CurrentUser, db: DbSession) -> InboxStatsRead:
    account = get_or_create_account(db, current_user.id, current_user.email)
    seed_demo_inbox_if_empty(db, current_user.id, account)
    return get_inbox_stats(db, current_user.id)


@router.get("/messages", response_model=list[EmailMessageRead])
def get_messages(
    current_user: CurrentUser,
    db: DbSession,
    category: str | None = Query(default=None),
    is_read: bool | None = Query(default=None),
    is_archived: bool = Query(default=False),
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[EmailMessageRead]:
    account = get_or_create_account(db, current_user.id, current_user.email)
    seed_demo_inbox_if_empty(db, current_user.id, account)
    messages = list_messages(
        db,
        current_user.id,
        category=category,
        is_read=is_read,
        is_archived=is_archived,
        search=search,
        limit=limit,
        offset=offset,
    )
    return [EmailMessageRead.model_validate(m) for m in messages]


@router.get("/messages/{message_id}", response_model=EmailMessageRead)
def get_single_message(message_id: int, current_user: CurrentUser, db: DbSession) -> EmailMessageRead:
    msg = get_message(db, current_user.id, message_id)
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found")
    return EmailMessageRead.model_validate(msg)


@router.patch("/messages/{message_id}", response_model=EmailMessageRead)
def update_email_message(
    message_id: int,
    payload: EmailMessageUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> EmailMessageRead:
    msg = update_message(db, current_user.id, message_id, payload)
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found")
    return EmailMessageRead.model_validate(msg)


@router.post("/messages/{message_id}/draft-reply", response_model=EmailDraftRead, status_code=status.HTTP_201_CREATED)
def draft_reply(
    message_id: int,
    payload: GenerateDraftRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> EmailDraftRead:
    try:
        draft = generate_draft_reply(db, current_user.id, message_id, instructions=payload.instructions)
        return EmailDraftRead.model_validate(draft)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err


@router.get("/drafts", response_model=list[EmailDraftRead])
def get_drafts(
    current_user: CurrentUser,
    db: DbSession,
    status: str | None = Query(default=None),
) -> list[EmailDraftRead]:
    drafts = list_drafts(db, current_user.id, status=status)
    return [EmailDraftRead.model_validate(d) for d in drafts]


@router.post("/drafts", response_model=EmailDraftRead, status_code=status.HTTP_201_CREATED)
def create_new_draft(
    payload: EmailDraftCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> EmailDraftRead:
    account = get_or_create_account(db, current_user.id, current_user.email)
    draft = create_draft(db, current_user.id, account.id, payload)
    return EmailDraftRead.model_validate(draft)


@router.patch("/drafts/{draft_id}", response_model=EmailDraftRead)
def update_existing_draft(
    draft_id: int,
    payload: EmailDraftUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> EmailDraftRead:
    draft = update_draft(db, current_user.id, draft_id, payload)
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    return EmailDraftRead.model_validate(draft)


@router.post("/drafts/{draft_id}/send", response_model=EmailDraftRead)
def send_approved_draft(
    draft_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> EmailDraftRead:
    # Explicit human-in-the-loop approval gate
    draft = approve_and_send_draft(db, current_user.id, draft_id)
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    return EmailDraftRead.model_validate(draft)


@router.delete("/drafts/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_draft(
    draft_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    deleted = delete_draft(db, current_user.id, draft_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
