"""Create AutoFlow workflows and run execution history tables.

Revision ID: 0007_autoflow_tables
Revises: 0006_mealmind_and_pricepilot
Create Date: 2026-11-07
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_autoflow_tables"
down_revision = "0006_mealmind_and_pricepilot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Workflows
    op.create_table(
        "autoflow_workflows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("trigger_type", sa.String(length=64), nullable=False, server_default="manual"),
        sa.Column("schedule_cron", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_autoflow_workflows_user_id", "autoflow_workflows", ["user_id"])

    # 2. Workflow Runs
    op.create_table(
        "autoflow_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workflow_id", sa.Integer(), sa.ForeignKey("autoflow_workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("triggered_by", sa.String(length=64), nullable=False, server_default="manual"),
        sa.Column("results_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_autoflow_runs_user_workflow", "autoflow_runs", ["user_id", "workflow_id"])


def downgrade() -> None:
    op.drop_table("autoflow_runs")
    op.drop_table("autoflow_workflows")
