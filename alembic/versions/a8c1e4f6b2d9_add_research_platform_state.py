"""add persistent conversations, indexing jobs, usage, and preferences

Revision ID: a8c1e4f6b2d9
Revises: f7a9c2d4e6b8
Create Date: 2026-11-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a8c1e4f6b2d9"
down_revision: Union[str, Sequence[str], None] = "f7a9c2d4e6b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_document_index_states_status", "document_index_states", type_="check"
    )
    op.create_check_constraint(
        "ck_document_index_states_status",
        "document_index_states",
        "status IN ('not_indexed', 'queued', 'processing', 'completed', 'failed')",
    )
    op.add_column(
        "conversations",
        sa.Column("mode", sa.String(length=32), server_default="general", nullable=False),
    )
    op.create_check_constraint(
        "ck_conversations_mode",
        "conversations",
        "mode IN ('general', 'documents', 'deep')",
    )
    op.create_index(
        "ix_conversations_user_updated", "conversations", ["user_id", "updated_at"]
    )
    op.create_index("ix_documents_user_created", "documents", ["user_id", "created_at"])

    op.create_table(
        "conversation_documents",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("conversation_id", "document_id"),
    )
    op.create_index(
        "ix_conversation_documents_user",
        "conversation_documents",
        ["user_id", "conversation_id"],
    )

    op.create_table(
        "indexing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(32), server_default="queued", nullable=False),
        sa.Column("stage", sa.String(64), server_default="queued", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_chunks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_chunks", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('queued', 'processing', 'completed', 'failed')", name="ck_indexing_jobs_status"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_indexing_jobs_attempt_nonnegative"),
        sa.CheckConstraint("completed_chunks >= 0 AND (total_chunks IS NULL OR total_chunks >= completed_chunks)", name="ck_indexing_jobs_progress"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_indexing_jobs_document_id", "indexing_jobs", ["document_id"])
    op.create_index("ix_indexing_jobs_claim", "indexing_jobs", ["status", "created_at"])
    op.create_index("ix_indexing_jobs_user_created", "indexing_jobs", ["user_id", "created_at"])
    op.create_index(
        "uq_indexing_jobs_active_document",
        "indexing_jobs",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'processing')"),
    )

    op.create_table(
        "usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("embedding_tokens", sa.Integer(), nullable=True),
        sa.Column("request_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("estimated", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(14, 8), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_events_request_id", "usage_events", ["request_id"])
    op.create_index("ix_usage_events_user_created", "usage_events", ["user_id", "created_at"])
    op.create_index("ix_usage_events_conversation_created", "usage_events", ["conversation_id", "created_at"])

    op.create_table(
        "user_preferences",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("response_language", sa.String(16), server_default="auto", nullable=False),
        sa.Column("response_depth", sa.String(16), server_default="auto", nullable=False),
        sa.Column("default_mode", sa.String(16), server_default="general", nullable=False),
        sa.Column("theme", sa.String(16), server_default="dark", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("response_language IN ('auto', 'en', 'ar')", name="ck_preferences_language"),
        sa.CheckConstraint("response_depth IN ('auto', 'concise', 'balanced', 'detailed')", name="ck_preferences_depth"),
        sa.CheckConstraint("default_mode IN ('general', 'documents', 'deep')", name="ck_preferences_mode"),
        sa.CheckConstraint("theme IN ('dark', 'light', 'system')", name="ck_preferences_theme"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
    op.drop_index("ix_usage_events_conversation_created", table_name="usage_events")
    op.drop_index("ix_usage_events_user_created", table_name="usage_events")
    op.drop_index("ix_usage_events_request_id", table_name="usage_events")
    op.drop_table("usage_events")
    op.drop_index("uq_indexing_jobs_active_document", table_name="indexing_jobs")
    op.drop_index("ix_indexing_jobs_user_created", table_name="indexing_jobs")
    op.drop_index("ix_indexing_jobs_claim", table_name="indexing_jobs")
    op.drop_index("ix_indexing_jobs_document_id", table_name="indexing_jobs")
    op.drop_table("indexing_jobs")
    op.drop_index("ix_conversation_documents_user", table_name="conversation_documents")
    op.drop_table("conversation_documents")
    op.drop_index("ix_conversations_user_updated", table_name="conversations")
    op.drop_index("ix_documents_user_created", table_name="documents")
    op.drop_constraint("ck_conversations_mode", "conversations", type_="check")
    op.drop_column("conversations", "mode")
    op.drop_constraint(
        "ck_document_index_states_status", "document_index_states", type_="check"
    )
    op.execute("UPDATE document_index_states SET status = 'failed' WHERE status = 'queued'")
    op.create_check_constraint(
        "ck_document_index_states_status",
        "document_index_states",
        "status IN ('not_indexed', 'processing', 'completed', 'failed')",
    )
