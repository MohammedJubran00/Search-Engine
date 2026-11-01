"""Durable PostgreSQL-backed document indexing work item."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.search_engine.database.database import Base


class IndexingJob(Base):
    __tablename__ = "indexing_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed')",
            name="ck_indexing_jobs_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_indexing_jobs_attempt_nonnegative"),
        CheckConstraint(
            "completed_chunks >= 0 AND (total_chunks IS NULL OR total_chunks >= completed_chunks)",
            name="ck_indexing_jobs_progress",
        ),
        Index("ix_indexing_jobs_claim", "status", "created_at"),
        Index("ix_indexing_jobs_user_created", "user_id", "created_at"),
        Index(
            "uq_indexing_jobs_active_document",
            "document_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'processing')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", server_default="queued")
    stage: Mapped[str] = mapped_column(String(64), nullable=False, default="queued", server_default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    completed_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total_chunks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
