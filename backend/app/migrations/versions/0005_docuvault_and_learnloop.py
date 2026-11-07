"""Create DocuVault documents and LearnLoop decks and flashcards tables.

Revision ID: 0005_docuvault_and_learnloop
Revises: 0004_spendwise_tables
Create Date: 2026-11-07
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_docuvault_and_learnloop"
down_revision = "0004_spendwise_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. DocuVault Documents
    op.create_table(
        "docuvault_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_type", sa.String(length=64), nullable=False, server_default="text/plain"),
        sa.Column("content_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("tags", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_docuvault_documents_user_id", "docuvault_documents", ["user_id"])
    op.create_index("ix_docuvault_documents_title", "docuvault_documents", ["title"])

    # 2. LearnLoop Study Decks
    op.create_table(
        "learnloop_decks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("docuvault_documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_learnloop_decks_user_id", "learnloop_decks", ["user_id"])
    op.create_index("ix_learnloop_decks_document_id", "learnloop_decks", ["document_id"])

    # 3. LearnLoop Flashcards
    op.create_table(
        "learnloop_flashcards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deck_id", sa.Integer(), sa.ForeignKey("learnloop_decks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("front", sa.Text(), nullable=False),
        sa.Column("back", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="new"),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_learnloop_flashcards_deck_id", "learnloop_flashcards", ["deck_id"])
    op.create_index("ix_learnloop_flashcards_status", "learnloop_flashcards", ["status"])


def downgrade() -> None:
    op.drop_index("ix_learnloop_flashcards_status", table_name="learnloop_flashcards")
    op.drop_index("ix_learnloop_flashcards_deck_id", table_name="learnloop_flashcards")
    op.drop_table("learnloop_flashcards")

    op.drop_index("ix_learnloop_decks_document_id", table_name="learnloop_decks")
    op.drop_index("ix_learnloop_decks_user_id", table_name="learnloop_decks")
    op.drop_table("learnloop_decks")

    op.drop_index("ix_docuvault_documents_title", table_name="docuvault_documents")
    op.drop_index("ix_docuvault_documents_user_id", table_name="docuvault_documents")
    op.drop_table("docuvault_documents")
