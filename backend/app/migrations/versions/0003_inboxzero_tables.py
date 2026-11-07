"""Create InboxZero email accounts, messages, and drafts tables.

Revision ID: 0003_inboxzero_tables
Revises: 0002_lifeos_tasks
Create Date: 2026-11-07
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_inboxzero_tables"
down_revision = "0002_lifeos_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Email Accounts
    op.create_table(
        "email_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email_address", sa.String(length=320), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="gmail"),
        sa.Column("access_token", sa.String(length=2000), nullable=True),
        sa.Column("refresh_token", sa.String(length=2000), nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_email_accounts_user_id", "email_accounts", ["user_id"])
    op.create_index("ix_email_accounts_email_address", "email_accounts", ["email_address"])

    # 2. Email Messages
    op.create_table(
        "email_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("email_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("thread_id", sa.String(length=128), nullable=True),
        sa.Column("sender", sa.String(length=320), nullable=False),
        sa.Column("sender_name", sa.String(length=128), nullable=True),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("snippet", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="primary"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_email_messages_user_id", "email_messages", ["user_id"])
    op.create_index("ix_email_messages_account_id", "email_messages", ["account_id"])
    op.create_index("ix_email_messages_category", "email_messages", ["category"])
    op.create_index("ix_email_messages_is_read", "email_messages", ["is_read"])

    # 3. Email Drafts
    op.create_table(
        "email_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("email_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reply_to_message_id", sa.Integer(), sa.ForeignKey("email_messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_email_drafts_user_id", "email_drafts", ["user_id"])
    op.create_index("ix_email_drafts_status", "email_drafts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_email_drafts_status", table_name="email_drafts")
    op.drop_index("ix_email_drafts_user_id", table_name="email_drafts")
    op.drop_table("email_drafts")

    op.drop_index("ix_email_messages_is_read", table_name="email_messages")
    op.drop_index("ix_email_messages_category", table_name="email_messages")
    op.drop_index("ix_email_messages_account_id", table_name="email_messages")
    op.drop_index("ix_email_messages_user_id", table_name="email_messages")
    op.drop_table("email_messages")

    op.drop_index("ix_email_accounts_email_address", table_name="email_accounts")
    op.drop_index("ix_email_accounts_user_id", table_name="email_accounts")
    op.drop_table("email_accounts")
