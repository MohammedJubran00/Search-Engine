"""Persistent indexing lifecycle for one uploaded RAG document.

Upload parsing and vector indexing are separate operations. This one-to-one
state keeps their lifecycle semantics independent and supplies a generation
token for safe retries and concurrent-worker exclusion.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.search_engine.database.database import Base

DOCUMENT_INDEXING_STATUSES = ("not_indexed", "processing", "completed", "failed")


class DocumentIndexState(Base):
    """Indexing status and generation for exactly one document."""

    __tablename__ = "document_index_states"
    __table_args__ = (
        CheckConstraint(
            "status IN ('not_indexed', 'processing', 'completed', 'failed')",
            name="ck_document_index_states_status",
        ),
        CheckConstraint(
            "generation >= 0",
            name="ck_document_index_states_generation_nonnegative",
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="not_indexed",
        server_default="not_indexed",
    )
    generation: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
