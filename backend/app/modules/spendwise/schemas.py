import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TransactionBase(BaseModel):
    amount: float = Field(gt=0, description="Transaction amount")
    type: str = Field(default="expense", pattern="^(expense|income)$")
    category: str = Field(default="Other", min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)
    date: dt.date = Field(default_factory=dt.date.today)
    payment_method: str = Field(default="Credit Card", max_length=64)
    is_recurring: bool = False
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


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(BaseModel):
    amount: float | None = Field(default=None, gt=0)
    type: str | None = Field(default=None, pattern="^(expense|income)$")
    category: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, min_length=1, max_length=255)
    date: dt.date | None = None
    payment_method: str | None = Field(default=None, max_length=64)
    is_recurring: bool | None = None
    tags: list[str] | None = None

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


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    amount: float
    type: str
    category: str
    description: str
    date: dt.date
    payment_method: str
    is_recurring: bool
    tags: list[str]
    created_at: dt.datetime

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


class BudgetBase(BaseModel):
    category: str = Field(min_length=1, max_length=64)
    monthly_limit: float = Field(gt=0)
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")  # YYYY-MM


class BudgetCreate(BudgetBase):
    pass


class BudgetUpdate(BaseModel):
    monthly_limit: float = Field(gt=0)


class BudgetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    category: str
    monthly_limit: float
    month: str
    spent: float = 0.0
    remaining: float = 0.0
    percentage_used: float = 0.0
    created_at: dt.datetime
    updated_at: dt.datetime | None


class SpendSummaryRead(BaseModel):
    month: str
    total_income: float
    total_expenses: float
    net_savings: float
    savings_rate: float
    category_breakdown: dict[str, float]
    top_categories: list[dict[str, object]]
    over_budget_count: int


class CSVImportResult(BaseModel):
    imported_count: int
    error_count: int
    messages: list[str] = Field(default_factory=list)
