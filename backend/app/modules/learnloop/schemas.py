import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class FlashcardCreate(BaseModel):
    front: str = Field(min_length=1, description="Question or concept")
    back: str = Field(min_length=1, description="Answer or explanation")


class FlashcardReviewRequest(BaseModel):
    rating: str = Field(pattern="^(easy|good|hard)$")


class FlashcardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deck_id: int
    front: str
    back: str
    status: str
    review_count: int
    last_reviewed_at: dt.datetime | None
    next_review_at: dt.datetime | None
    created_at: dt.datetime


class DeckCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    document_id: int | None = None
    initial_cards: list[FlashcardCreate] = Field(default_factory=list)


class DeckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    document_id: int | None
    title: str
    description: str | None
    card_count: int = 0
    mastered_count: int = 0
    due_count: int = 0
    created_at: dt.datetime


class GenerateDeckFromDocRequest(BaseModel):
    title: str | None = None
    num_cards: int = Field(default=4, ge=2, le=10)
