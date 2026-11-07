from datetime import datetime, timedelta, timezone
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.docuvault.models import Document
from app.modules.learnloop.models import Flashcard, StudyDeck
from app.modules.learnloop.schemas import (
    DeckCreate,
    DeckRead,
    FlashcardCreate,
    FlashcardRead,
)


def seed_demo_deck_if_empty(db: Session, user_id: int) -> None:
    count = db.scalar(select(func.count(StudyDeck.id)).where(StudyDeck.user_id == user_id))
    if count and count > 0:
        return

    now = datetime.now(timezone.utc)
    deck = StudyDeck(
        user_id=user_id,
        title="Modern Software Architecture & Async Flashcards",
        description="Key architectural principles and asynchronous programming patterns.",
    )
    db.add(deck)
    db.commit()
    db.refresh(deck)

    cards = [
        {
            "front": "What is a Modular Monolith in backend design?",
            "back": "A single deployable system structured into isolated domain packages with strict boundary APIs and explicit dependencies.",
            "status": "new",
        },
        {
            "front": "Why is pool_pre_ping important in SQLAlchemy?",
            "back": "It tests connections for liveness before checkout to prevent OperationalError on stale or disconnected sockets.",
            "status": "review",
            "last_reviewed_at": now - timedelta(days=1),
            "next_review_at": now + timedelta(days=2),
            "review_count": 1,
        },
        {
            "front": "What is an Approval Gate in an AI agent architecture?",
            "back": "A safety checkpoint where irreversible or external actions (e.g., sending emails or financial transactions) require human confirmation before execution.",
            "status": "mastered",
            "last_reviewed_at": now - timedelta(days=3),
            "next_review_at": now + timedelta(days=7),
            "review_count": 3,
        },
    ]

    for c in cards:
        db.add(Flashcard(deck_id=deck.id, **c))
    db.commit()


def create_deck(db: Session, user_id: int, payload: DeckCreate) -> StudyDeck:
    deck = StudyDeck(
        user_id=user_id,
        title=payload.title,
        description=payload.description,
        document_id=payload.document_id,
    )
    db.add(deck)
    db.commit()
    db.refresh(deck)

    for c in payload.initial_cards:
        db.add(Flashcard(deck_id=deck.id, front=c.front, back=c.back))
    db.commit()
    return deck


def _is_card_due(card: Flashcard, now: datetime) -> bool:
    if card.status == "new":
        return True
    if not card.next_review_at:
        return True
    review_at = card.next_review_at
    if review_at.tzinfo is None:
        review_at = review_at.replace(tzinfo=timezone.utc)
    return review_at <= now


def list_decks_with_stats(db: Session, user_id: int) -> list[DeckRead]:
    decks = list(db.scalars(select(StudyDeck).where(StudyDeck.user_id == user_id)).all())
    now = datetime.now(timezone.utc)

    result: list[DeckRead] = []
    for d in decks:
        cards = list(db.scalars(select(Flashcard).where(Flashcard.deck_id == d.id)).all())
        card_count = len(cards)
        mastered_count = sum(1 for c in cards if c.status == "mastered")
        due_count = sum(1 for c in cards if _is_card_due(c, now))

        result.append(
            DeckRead(
                id=d.id,
                user_id=d.user_id,
                document_id=d.document_id,
                title=d.title,
                description=d.description,
                card_count=card_count,
                mastered_count=mastered_count,
                due_count=due_count,
                created_at=d.created_at,
            )
        )
    return result


def get_deck(db: Session, user_id: int, deck_id: int) -> StudyDeck | None:
    return db.scalar(select(StudyDeck).where(StudyDeck.user_id == user_id, StudyDeck.id == deck_id))


def delete_deck(db: Session, user_id: int, deck_id: int) -> bool:
    deck = get_deck(db, user_id, deck_id)
    if not deck:
        return False
    db.delete(deck)
    db.commit()
    return True


def add_card_to_deck(
    db: Session,
    user_id: int,
    deck_id: int,
    payload: FlashcardCreate,
) -> Flashcard | None:
    deck = get_deck(db, user_id, deck_id)
    if not deck:
        return None
    card = Flashcard(deck_id=deck.id, front=payload.front, back=payload.back, status="new")
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


def list_cards_for_deck(
    db: Session,
    user_id: int,
    deck_id: int,
    due_only: bool = False,
) -> list[Flashcard]:
    deck = get_deck(db, user_id, deck_id)
    if not deck:
        return []

    query = select(Flashcard).where(Flashcard.deck_id == deck.id)
    if due_only:
        now = datetime.now(timezone.utc)
        query = query.where(
            (Flashcard.status == "new") | (Flashcard.next_review_at <= now) | (Flashcard.next_review_at.is_(None))
        )
    return list(db.scalars(query).all())


def review_card(
    db: Session,
    user_id: int,
    card_id: int,
    rating: str,
) -> Flashcard | None:
    # Join with deck to ensure user owns card
    card = db.scalar(
        select(Flashcard)
        .join(StudyDeck, StudyDeck.id == Flashcard.deck_id)
        .where(StudyDeck.user_id == user_id, Flashcard.id == card_id)
    )
    if not card:
        return None

    now = datetime.now(timezone.utc)
    card.last_reviewed_at = now
    card.review_count += 1

    if rating == "easy":
        card.status = "mastered"
        card.next_review_at = now + timedelta(days=7)
    elif rating == "good":
        card.status = "review"
        card.next_review_at = now + timedelta(days=3)
    else:  # hard
        card.status = "review"
        card.next_review_at = now + timedelta(days=1)

    db.commit()
    db.refresh(card)
    return card


def generate_deck_from_document(
    db: Session,
    user_id: int,
    doc_id: int,
    num_cards: int = 4,
) -> StudyDeck | None:
    doc = db.scalar(select(Document).where(Document.user_id == user_id, Document.id == doc_id))
    if not doc:
        return None

    deck = StudyDeck(
        user_id=user_id,
        document_id=doc.id,
        title=f"Study Deck: {doc.title}",
        description=f"Auto-generated revision deck from '{doc.filename}' in DocuVault.",
    )
    db.add(deck)
    db.commit()
    db.refresh(deck)

    # Extract sentences/paragraphs to create flashcards
    import re

    raw_chunks = [ln.strip() for ln in doc.content_text.splitlines() if ln.strip() and not ln.startswith("#")]
    sentences: list[str] = []
    for chunk in raw_chunks:
        sub_sentences = re.split(r"(?<=[.!?])\s+", chunk)
        for s in sub_sentences:
            s_clean = s.strip()
            if s_clean:
                sentences.append(s_clean)

    created_count = 0
    for item in sentences:
        if created_count >= num_cards:
            break
        if ":" in item:
            parts = item.split(":", 1)
            prompt = parts[0].lstrip("-*1234567890. ").strip()
            answer = parts[1].strip()
            if prompt and answer:
                db.add(Flashcard(deck_id=deck.id, front=f"Explain or define: {prompt}", back=answer))
                created_count += 1
        elif len(item) > 20:
            db.add(
                Flashcard(
                    deck_id=deck.id,
                    front=f"Key concept from {doc.title}:",
                    back=item,
                )
            )
            created_count += 1

    if created_count == 0:
        db.add(
            Flashcard(
                deck_id=deck.id,
                front=f"Summary of {doc.title}",
                back=doc.summary or doc.content_text[:200],
            )
        )

    db.commit()
    return deck
