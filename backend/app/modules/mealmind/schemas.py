import datetime as dt
import json

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IngredientItem(BaseModel):
    name: str = Field(min_length=1)
    quantity: str = Field(default="1")
    category: str = Field(default="produce")  # produce, dairy, meat, pantry, bakery, other


class RecipeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    prep_time_minutes: int = Field(default=20, ge=1, le=480)
    ingredients: list[IngredientItem] = Field(default_factory=list)
    instructions: str = Field(min_length=1)
    dietary_tags: list[str] = Field(default_factory=list)

    @field_validator("dietary_tags", mode="before")
    @classmethod
    def parse_tags(cls, v: object) -> list[str]:
        if isinstance(v, str):
            if not v.strip():
                return []
            return [t.strip() for t in v.split(",") if t.strip()]
        if isinstance(v, list):
            return [str(t).strip() for t in v if str(t).strip()]
        return []


class RecipeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    description: str | None
    prep_time_minutes: int
    ingredients: list[IngredientItem] = Field(default_factory=list)
    instructions: str
    dietary_tags: list[str] = Field(default_factory=list)
    created_at: dt.datetime

    @classmethod
    def from_orm_model(cls, r: object) -> "RecipeRead":
        raw_ingredients = getattr(r, "ingredients_json", "[]")
        try:
            parsed_ing = json.loads(raw_ingredients) if isinstance(raw_ingredients, str) else []
            ingredients = [IngredientItem(**item) if isinstance(item, dict) else IngredientItem(name=str(item)) for item in parsed_ing]
        except Exception:
            ingredients = []

        raw_tags = getattr(r, "dietary_tags", "")
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()] if isinstance(raw_tags, str) else []

        return cls(
            id=getattr(r, "id"),
            user_id=getattr(r, "user_id"),
            title=getattr(r, "title"),
            description=getattr(r, "description"),
            prep_time_minutes=getattr(r, "prep_time_minutes"),
            ingredients=ingredients,
            instructions=getattr(r, "instructions"),
            dietary_tags=tags,
            created_at=getattr(r, "created_at"),
        )


class MealPlanCreate(BaseModel):
    plan_date: dt.date = Field(alias="date")
    meal_type: str = Field(pattern="^(breakfast|lunch|dinner|snack)$")
    recipe_id: int | None = None
    custom_meal_name: str | None = None
    notes: str | None = None


class MealPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    user_id: int
    plan_date: dt.date = Field(alias="date")
    meal_type: str
    recipe_id: int | None
    custom_meal_name: str | None
    recipe_title: str | None = None
    notes: str | None
    created_at: dt.datetime


class GroceryItemCreate(BaseModel):
    item_name: str = Field(min_length=1, max_length=255)
    quantity: str = Field(default="1", max_length=100)
    category: str = Field(default="produce", max_length=64)
    estimated_cost: float = Field(default=0.0, ge=0)
    source_meal_plan_id: int | None = None


class GroceryItemUpdate(BaseModel):
    item_name: str | None = None
    quantity: str | None = None
    category: str | None = None
    is_purchased: bool | None = None
    estimated_cost: float | None = None


class GroceryItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    item_name: str
    quantity: str
    category: str
    is_purchased: bool
    estimated_cost: float
    source_meal_plan_id: int | None
    created_at: dt.datetime


class GroceryListSummary(BaseModel):
    total_items: int
    purchased_items: int
    pending_items: int
    estimated_total_cost: float
    items_by_category: dict[str, list[GroceryItemRead]]
