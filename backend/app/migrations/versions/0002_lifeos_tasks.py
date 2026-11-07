"""Create LifeOS tasks and reminders table.

Revision ID: 0002_lifeos_tasks
Revises: 0001_initial_users
Create Date: 2026-11-07
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_lifeos_tasks"
down_revision = "0001_initial_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lifeos_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("tags", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_lifeos_tasks_user_id", "lifeos_tasks", ["user_id"])
    op.create_index("ix_lifeos_tasks_status", "lifeos_tasks", ["status"])
    op.create_index("ix_lifeos_tasks_due_date", "lifeos_tasks", ["due_date"])


def downgrade() -> None:
    op.drop_index("ix_lifeos_tasks_due_date", table_name="lifeos_tasks")
    op.drop_index("ix_lifeos_tasks_status", table_name="lifeos_tasks")
    op.drop_index("ix_lifeos_tasks_user_id", table_name="lifeos_tasks")
    op.drop_table("lifeos_tasks")
