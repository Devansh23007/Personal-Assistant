from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.learnloop.schemas import (
    DeckCreate,
    DeckRead,
    FlashcardCreate,
    FlashcardRead,
    FlashcardReviewRequest,
    GenerateDeckFromDocRequest,
)
from app.modules.learnloop.service import (
    add_card_to_deck,
    create_deck,
    delete_deck,
    generate_deck_from_document,
    get_deck,
    list_cards_for_deck,
    list_decks_with_stats,
    review_card,
    seed_demo_deck_if_empty,
)

router = APIRouter(prefix="/learnloop", tags=["learnloop"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/decks", response_model=list[DeckRead])
def get_decks(current_user: CurrentUser, db: DbSession) -> list[DeckRead]:
    seed_demo_deck_if_empty(db, current_user.id)
    return list_decks_with_stats(db, current_user.id)


@router.post("/decks", response_model=DeckRead, status_code=status.HTTP_201_CREATED)
def create_new_deck(payload: DeckCreate, current_user: CurrentUser, db: DbSession) -> DeckRead:
    deck = create_deck(db, current_user.id, payload)
    decks = list_decks_with_stats(db, current_user.id)
    matching = next((d for d in decks if d.id == deck.id), None)
    if not matching:
        return DeckRead(
            id=deck.id,
            user_id=deck.user_id,
            document_id=deck.document_id,
            title=deck.title,
            description=deck.description,
            card_count=len(payload.initial_cards),
            mastered_count=0,
            due_count=len(payload.initial_cards),
            created_at=deck.created_at,
        )
    return matching


@router.get("/decks/{deck_id}", response_model=DeckRead)
def get_single_deck(deck_id: int, current_user: CurrentUser, db: DbSession) -> DeckRead:
    decks = list_decks_with_stats(db, current_user.id)
    deck = next((d for d in decks if d.id == deck_id), None)
    if not deck:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")
    return deck


@router.delete("/decks/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_deck(deck_id: int, current_user: CurrentUser, db: DbSession) -> None:
    deleted = delete_deck(db, current_user.id, deck_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")


@router.post("/decks/generate-from-doc/{doc_id}", response_model=DeckRead, status_code=status.HTTP_201_CREATED)
def generate_deck(
    doc_id: int,
    current_user: CurrentUser,
    db: DbSession,
    payload: GenerateDeckFromDocRequest | None = None,
) -> DeckRead:
    req = payload or GenerateDeckFromDocRequest()
    deck = generate_deck_from_document(db, current_user.id, doc_id, num_cards=req.num_cards)
    if not deck:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    decks = list_decks_with_stats(db, current_user.id)
    return next(d for d in decks if d.id == deck.id)


@router.get("/decks/{deck_id}/cards", response_model=list[FlashcardRead])
def get_deck_cards(
    deck_id: int,
    current_user: CurrentUser,
    db: DbSession,
    due_only: bool = Query(default=False),
) -> list[FlashcardRead]:
    cards = list_cards_for_deck(db, current_user.id, deck_id, due_only=due_only)
    return [FlashcardRead.model_validate(c) for c in cards]


@router.post("/decks/{deck_id}/cards", response_model=FlashcardRead, status_code=status.HTTP_201_CREATED)
def add_card(
    deck_id: int,
    payload: FlashcardCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> FlashcardRead:
    card = add_card_to_deck(db, current_user.id, deck_id, payload)
    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")
    return FlashcardRead.model_validate(card)


@router.post("/cards/{card_id}/review", response_model=FlashcardRead)
def submit_card_review(
    card_id: int,
    payload: FlashcardReviewRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> FlashcardRead:
    card = review_card(db, current_user.id, card_id, rating=payload.rating)
    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    return FlashcardRead.model_validate(card)
