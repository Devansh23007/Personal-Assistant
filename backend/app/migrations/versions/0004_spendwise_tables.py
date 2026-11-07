"""Create SpendWise transactions and budgets tables.

Revision ID: 0004_spendwise_tables
Revises: 0003_inboxzero_tables
Create Date: 2026-11-07
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_spendwise_tables"
down_revision = "0003_inboxzero_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Transactions
    op.create_table(
        "spendwise_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False, server_default="expense"),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="Other"),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("payment_method", sa.String(length=64), nullable=False, server_default="Credit Card"),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tags", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_spendwise_transactions_user_id", "spendwise_transactions", ["user_id"])
    op.create_index("ix_spendwise_transactions_type", "spendwise_transactions", ["type"])
    op.create_index("ix_spendwise_transactions_category", "spendwise_transactions", ["category"])
    op.create_index("ix_spendwise_transactions_date", "spendwise_transactions", ["date"])

    # 2. Budgets
    op.create_table(
        "spendwise_budgets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("monthly_limit", sa.Float(), nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_spendwise_budgets_user_id", "spendwise_budgets", ["user_id"])
    op.create_index("ix_spendwise_budgets_month", "spendwise_budgets", ["month"])


def downgrade() -> None:
    op.drop_index("ix_spendwise_budgets_month", table_name="spendwise_budgets")
    op.drop_index("ix_spendwise_budgets_user_id", table_name="spendwise_budgets")
    op.drop_table("spendwise_budgets")

    op.drop_index("ix_spendwise_transactions_date", table_name="spendwise_transactions")
    op.drop_index("ix_spendwise_transactions_category", table_name="spendwise_transactions")
    op.drop_index("ix_spendwise_transactions_type", table_name="spendwise_transactions")
    op.drop_index("ix_spendwise_transactions_user_id", table_name="spendwise_transactions")
    op.drop_table("spendwise_transactions")
