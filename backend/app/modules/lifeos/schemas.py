from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    priority: str = Field(default="medium", pattern="^(low|medium|high|urgent)$")
    due_date: datetime | None = None
    reminder_at: datetime | None = None
    timezone: str = Field(default="UTC", max_length=64)
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v: object) -> list[str]:
        if isinstance(v, str):
            if not v.strip():
                return []
            return [tag.strip() for tag in v.split(",") if tag.strip()]
        if isinstance(v, list):
            return [str(tag).strip() for tag in v if str(tag).strip()]
        return []


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    status: str | None = Field(default=None, pattern="^(pending|in_progress|completed|cancelled)$")
    priority: str | None = Field(default=None, pattern="^(low|medium|high|urgent)$")
    due_date: datetime | None = None
    reminder_at: datetime | None = None
    timezone: str | None = Field(default=None, max_length=64)
    tags: list[str] | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v: object) -> list[str] | None:
        if v is None:
            return None
        if isinstance(v, str):
            if not v.strip():
                return []
            return [tag.strip() for tag in v.split(",") if tag.strip()]
        if isinstance(v, list):
            return [str(tag).strip() for tag in v if str(tag).strip()]
        return []


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    description: str | None
    status: str
    priority: str
    due_date: datetime | None
    reminder_at: datetime | None
    timezone: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime | None
    completed_at: datetime | None

    @field_validator("tags", mode="before")
    @classmethod
    def format_tags(cls, v: object) -> list[str]:
        if isinstance(v, str):
            if not v.strip():
                return []
            return [tag.strip() for tag in v.split(",") if tag.strip()]
        if isinstance(v, list):
            return [str(tag) for tag in v]
        return []


class TaskSummaryRead(BaseModel):
    total: int
    pending: int
    in_progress: int
    completed: int
    overdue: int
    due_today: int
