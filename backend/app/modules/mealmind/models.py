import datetime as dt

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Recipe(Base):
    __tablename__ = "mealmind_recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    prep_time_minutes: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    ingredients_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    dietary_tags: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    meal_plans: Mapped[list["MealPlan"]] = relationship("MealPlan", back_populates="recipe", cascade="all, delete-orphan")


class MealPlan(Base):
    __tablename__ = "mealmind_meal_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    meal_type: Mapped[str] = mapped_column(String(32), nullable=False)  # breakfast, lunch, dinner, snack
    recipe_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("mealmind_recipes.id", ondelete="SET NULL"), nullable=True)
    custom_meal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    recipe: Mapped[Recipe | None] = relationship("Recipe", back_populates="meal_plans")


class GroceryItem(Base):
    __tablename__ = "mealmind_grocery_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[str] = mapped_column(String(100), default="1", nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="produce", nullable=False)  # produce, dairy, meat, pantry, bakery, other
    is_purchased: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    source_meal_plan_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mealmind_meal_plans.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
