from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class EmailAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email_address: str
    provider: str
    is_active: bool
    created_at: datetime


class EmailMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    external_id: str | None
    sender: str
    sender_name: str | None
    recipient: str
    subject: str
    snippet: str
    body_text: str | None
    category: str
    summary: str | None
    is_read: bool
    is_archived: bool
    received_at: datetime
    created_at: datetime


class EmailMessageUpdate(BaseModel):
    is_read: bool | None = None
    is_archived: bool | None = None
    category: str | None = Field(default=None, pattern="^(primary|action_needed|updates|receipts|newsletters)$")


class EmailDraftCreate(BaseModel):
    recipient: EmailStr
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1)
    reply_to_message_id: int | None = None


class EmailDraftUpdate(BaseModel):
    recipient: EmailStr | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = None
    status: str | None = Field(default=None, pattern="^(draft|awaiting_approval|sent|discarded)$")


class EmailDraftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    account_id: int
    reply_to_message_id: int | None
    recipient: str
    subject: str
    body: str
    status: str
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


class InboxStatsRead(BaseModel):
    total: int
    unread: int
    action_needed: int
    drafts_pending: int


class GenerateDraftRequest(BaseModel):
    instructions: str = Field(default="Draft a professional, concise, and helpful reply.")
