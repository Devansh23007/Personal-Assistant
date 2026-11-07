"""Create MealMind meal planning, recipes, grocery list, and PricePilot comparison tables.

Revision ID: 0006_mealmind_and_pricepilot
Revises: 0005_docuvault_and_learnloop
Create Date: 2026-11-07
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_mealmind_and_pricepilot"
down_revision = "0005_docuvault_and_learnloop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. MealMind Recipes
    op.create_table(
        "mealmind_recipes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prep_time_minutes", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("ingredients_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("dietary_tags", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_mealmind_recipes_user_id", "mealmind_recipes", ["user_id"])

    # 2. MealMind Meal Plans
    op.create_table(
        "mealmind_meal_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("meal_type", sa.String(length=32), nullable=False),
        sa.Column("recipe_id", sa.Integer(), sa.ForeignKey("mealmind_recipes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("custom_meal_name", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_mealmind_meal_plans_user_date", "mealmind_meal_plans", ["user_id", "date"])

    # 3. MealMind Grocery Items
    op.create_table(
        "mealmind_grocery_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_name", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.String(length=100), nullable=False, server_default="1"),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="produce"),
        sa.Column("is_purchased", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("estimated_cost", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("source_meal_plan_id", sa.Integer(), sa.ForeignKey("mealmind_meal_plans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_mealmind_grocery_items_user_id", "mealmind_grocery_items", ["user_id"])

    # 4. PricePilot Products
    op.create_table(
        "pricepilot_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("item_name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("store_name", sa.String(length=100), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False, server_default="each"),
        sa.Column("in_stock", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("deal_description", sa.String(length=255), nullable=True),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_pricepilot_products_item_store", "pricepilot_products", ["item_name", "store_name"])


def downgrade() -> None:
    op.drop_table("pricepilot_products")
    op.drop_table("mealmind_grocery_items")
    op.drop_table("mealmind_meal_plans")
    op.drop_table("mealmind_recipes")
