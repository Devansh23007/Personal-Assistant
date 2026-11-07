from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.inboxzero.models import EmailAccount, EmailDraft, EmailMessage
from app.modules.inboxzero.schemas import (
    EmailDraftCreate,
    EmailDraftUpdate,
    EmailMessageUpdate,
    InboxStatsRead,
)


def get_or_create_account(db: Session, user_id: int, email_address: str) -> EmailAccount:
    account = db.scalar(
        select(EmailAccount).where(EmailAccount.user_id == user_id, EmailAccount.email_address == email_address.lower())
    )
    if not account:
        account = EmailAccount(
            user_id=user_id,
            email_address=email_address.lower(),
            provider="gmail",
            is_active=True,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
    return account


def seed_demo_inbox_if_empty(db: Session, user_id: int, account: EmailAccount) -> None:
    count = db.scalar(select(func.count(EmailMessage.id)).where(EmailMessage.user_id == user_id))
    if count and count > 0:
        return

    now = datetime.now(timezone.utc)
    demo_emails = [
        {
            "sender": "sarah.lead@company.internal",
            "sender_name": "Sarah Connor",
            "recipient": account.email_address,
            "subject": "Urgent: Q4 Product Strategy Deck Review",
            "snippet": "Hi team, please review slides 14-20 regarding the roadmap before our 3 PM sync today. Need your sign-off.",
            "body_text": "Hi team,\n\nPlease review slides 14-20 regarding the roadmap before our 3 PM sync today. We need your sign-off on the engineering commitments and milestone dates.\n\nThanks,\nSarah",
            "category": "action_needed",
            "summary": "Urgent review required for Q4 Strategy Deck (slides 14-20) prior to today's 3 PM sync.",
            "is_read": False,
            "received_at": now - timedelta(hours=2),
        },
        {
            "sender": "reservations@skyhighair.com",
            "sender_name": "SkyHigh Airlines",
            "recipient": account.email_address,
            "subject": "Flight Confirmation: San Francisco to New York (Booking #SH-8849)",
            "snippet": "Your booking is confirmed! Flight SH402 departs SFO at 08:30 AM on Friday, Nov 14th.",
            "body_text": "Dear Traveler,\n\nYour flight SH402 from San Francisco (SFO) to New York (JFK) is confirmed for Friday, Nov 14, 2026 at 08:30 AM.\nTerminal 2, Seat 14A.\n\nSafe travels!",
            "category": "receipts",
            "summary": "Flight SH402 confirmed for Nov 14 departing SFO at 8:30 AM to JFK. Seat 14A.",
            "is_read": True,
            "received_at": now - timedelta(hours=8),
        },
        {
            "sender": "alex.dev@partner.org",
            "sender_name": "Alex Mercer",
            "recipient": account.email_address,
            "subject": "API Integration Partnership Proposal",
            "snippet": "Hey, I loved your recent work on modular architecture. Are you available for a quick 15-minute call this week?",
            "body_text": "Hey,\n\nI was reviewing your recent updates on modular AI assistants and think there's a strong opportunity for us to collaborate on automated workflows. Could we schedule a brief 15-minute intro this Thursday or Friday?\n\nBest,\nAlex",
            "category": "primary",
            "summary": "Partnership inquiry proposing a 15-minute collaboration call on Thursday or Friday.",
            "is_read": False,
            "received_at": now - timedelta(days=1),
        },
        {
            "sender": "newsletter@techdigest.io",
            "sender_name": "TechDigest Weekly",
            "recipient": account.email_address,
            "subject": "TechDigest #412: The Rise of Autonomous Personal Agents",
            "snippet": "This week: How AI tools, local LLMs, and modular monoliths are transforming developer productivity...",
            "body_text": "Welcome to TechDigest #412!\n\nToday's highlights:\n- Agentic coding with subagents\n- Managing state and approval gates\n- Python 3.14 features\n\nRead more at techdigest.io",
            "category": "newsletters",
            "summary": "Weekly roundup on autonomous AI personal agents, approval gates, and Python 3.14.",
            "is_read": True,
            "received_at": now - timedelta(days=2),
        },
    ]

    for item in demo_emails:
        msg = EmailMessage(
            user_id=user_id,
            account_id=account.id,
            external_id=f"demo-{abs(hash(item['subject']))}",
            thread_id=f"thread-{abs(hash(item['subject']))}",
            **item,
        )
        db.add(msg)
    db.commit()


def list_messages(
    db: Session,
    user_id: int,
    category: str | None = None,
    is_read: bool | None = None,
    is_archived: bool = False,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[EmailMessage]:
    query = select(EmailMessage).where(EmailMessage.user_id == user_id, EmailMessage.is_archived == is_archived)

    if category and category != "all":
        query = query.where(EmailMessage.category == category)
    if is_read is not None:
        query = query.where(EmailMessage.is_read == is_read)
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                EmailMessage.subject.ilike(term),
                EmailMessage.sender.ilike(term),
                EmailMessage.sender_name.ilike(term),
                EmailMessage.snippet.ilike(term),
            )
        )

    query = query.order_by(EmailMessage.received_at.desc()).offset(offset).limit(limit)
    return list(db.scalars(query).all())


def get_message(db: Session, user_id: int, message_id: int) -> EmailMessage | None:
    return db.scalar(select(EmailMessage).where(EmailMessage.user_id == user_id, EmailMessage.id == message_id))


def update_message(db: Session, user_id: int, message_id: int, payload: EmailMessageUpdate) -> EmailMessage | None:
    msg = get_message(db, user_id, message_id)
    if not msg:
        return None

    if payload.is_read is not None:
        msg.is_read = payload.is_read
    if payload.is_archived is not None:
        msg.is_archived = payload.is_archived
    if payload.category is not None:
        msg.category = payload.category

    db.commit()
    db.refresh(msg)
    return msg


def create_draft(db: Session, user_id: int, account_id: int, payload: EmailDraftCreate) -> EmailDraft:
    draft = EmailDraft(
        user_id=user_id,
        account_id=account_id,
        recipient=str(payload.recipient),
        subject=payload.subject,
        body=payload.body,
        reply_to_message_id=payload.reply_to_message_id,
        status="draft",
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def generate_draft_reply(
    db: Session,
    user_id: int,
    message_id: int,
    instructions: str = "Draft a polite and concise response.",
) -> EmailDraft:
    msg = get_message(db, user_id, message_id)
    if not msg:
        raise ValueError("Referenced email message not found.")

    subject = f"Re: {msg.subject}" if not msg.subject.lower().startswith("re:") else msg.subject
    recipient = msg.sender
    salutation = f"Hi {msg.sender_name.split()[0]}," if msg.sender_name else "Hello,"

    # Contextual draft synthesis based on category
    if msg.category == "action_needed":
        body_content = (
            f"{salutation}\n\n"
            f"Thank you for the update. I have reviewed the requested items and have noted the priority. "
            f"Everything looks aligned from my end for our upcoming sync.\n\n"
            f"Best regards,\nPersonal Assistant"
        )
    else:
        body_content = (
            f"{salutation}\n\n"
            f"Thank you for reaching out regarding '{msg.subject}'. "
            f"I have received your note and will follow up with further details shortly.\n\n"
            f"Best regards,\nPersonal Assistant"
        )

    draft = EmailDraft(
        user_id=user_id,
        account_id=msg.account_id,
        recipient=recipient,
        subject=subject,
        body=body_content,
        reply_to_message_id=msg.id,
        status="awaiting_approval",
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def list_drafts(db: Session, user_id: int, status: str | None = None) -> list[EmailDraft]:
    query = select(EmailDraft).where(EmailDraft.user_id == user_id)
    if status and status != "all":
        query = query.where(EmailDraft.status == status)
    query = query.order_by(EmailDraft.created_at.desc())
    return list(db.scalars(query).all())


def get_draft(db: Session, user_id: int, draft_id: int) -> EmailDraft | None:
    return db.scalar(select(EmailDraft).where(EmailDraft.user_id == user_id, EmailDraft.id == draft_id))


def update_draft(db: Session, user_id: int, draft_id: int, payload: EmailDraftUpdate) -> EmailDraft | None:
    draft = get_draft(db, user_id, draft_id)
    if not draft:
        return None

    if payload.recipient is not None:
        draft.recipient = str(payload.recipient)
    if payload.subject is not None:
        draft.subject = payload.subject
    if payload.body is not None:
        draft.body = payload.body
    if payload.status is not None:
        draft.status = payload.status

    db.commit()
    db.refresh(draft)
    return draft


def approve_and_send_draft(db: Session, user_id: int, draft_id: int) -> EmailDraft | None:
    draft = get_draft(db, user_id, draft_id)
    if not draft:
        return None

    # Approval gate: user explicitly commits the send action
    draft.status = "sent"
    draft.sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(draft)
    return draft


def delete_draft(db: Session, user_id: int, draft_id: int) -> bool:
    draft = get_draft(db, user_id, draft_id)
    if not draft:
        return False
    db.delete(draft)
    db.commit()
    return True


def get_inbox_stats(db: Session, user_id: int) -> InboxStatsRead:
    all_msgs = list(
        db.scalars(select(EmailMessage).where(EmailMessage.user_id == user_id, EmailMessage.is_archived == False)).all()
    )
    unread = sum(1 for m in all_msgs if not m.is_read)
    action_needed = sum(1 for m in all_msgs if m.category == "action_needed" and not m.is_read)

    pending_drafts = db.scalar(
        select(func.count(EmailDraft.id)).where(
            EmailDraft.user_id == user_id,
            EmailDraft.status.in_(["draft", "awaiting_approval"]),
        )
    ) or 0

    return InboxStatsRead(
        total=len(all_msgs),
        unread=unread,
        action_needed=action_needed,
        drafts_pending=pending_drafts,
    )
