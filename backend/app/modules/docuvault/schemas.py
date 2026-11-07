import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    filename: str = Field(min_length=1, max_length=255)
    content_text: str = Field(min_length=1)
    content_type: str = Field(default="text/plain", max_length=64)
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v: object) -> list[str]:
        if isinstance(v, str):
            if not v.strip():
                return []
            return [t.strip() for t in v.split(",") if t.strip()]
        if isinstance(v, list):
            return [str(t).strip() for t in v if str(t).strip()]
        return []


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    tags: list[str] | None = None
    summary: str | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v: object) -> list[str] | None:
        if v is None:
            return None
        if isinstance(v, str):
            if not v.strip():
                return []
            return [t.strip() for t in v.split(",") if t.strip()]
        if isinstance(v, list):
            return [str(t).strip() for t in v if str(t).strip()]
        return []


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    filename: str
    file_size: int
    content_type: str
    content_text: str
    summary: str | None
    tags: list[str]
    created_at: dt.datetime
    updated_at: dt.datetime | None

    @field_validator("tags", mode="before")
    @classmethod
    def format_tags(cls, v: object) -> list[str]:
        if isinstance(v, str):
            if not v.strip():
                return []
            return [t.strip() for t in v.split(",") if t.strip()]
        if isinstance(v, list):
            return [str(t) for t in v]
        return []


class SearchCitation(BaseModel):
    document_id: int
    title: str
    snippet: str
    match_score: float = 1.0


class DocumentSearchResult(BaseModel):
    query: str
    total_matches: int
    citations: list[SearchCitation]
