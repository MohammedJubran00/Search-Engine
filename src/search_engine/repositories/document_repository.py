"""Ownership-scoped database access for RAG documents.

Why it exists: document SQL and user isolation must not live in HTTP routes or
filesystem services. Every id lookup includes the authenticated ``user_id``.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.models.document import (
    DOCUMENT_PROCESSING_STATUSES,
    Document,
)


class DocumentRepository:
    """Read and write documents through one SQLAlchemy session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        original_filename: str,
        storage_path: str,
        content_type: str,
        file_size: int,
    ) -> Document:
        document = Document(
            user_id=user_id,
            original_filename=original_filename,
            storage_path=storage_path,
            content_type=content_type,
            file_size=file_size,
            processing_status="pending",
        )
        self._session.add(document)
        await self._session.flush()
        await self._session.refresh(document)
        return document

    async def list_for_user(self, user_id: uuid.UUID) -> list[Document]:
        result = await self._session.execute(
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id_for_user(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Document | None:
        result = await self._session.execute(
            select(Document).where(
                Document.id == document_id,
                Document.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def set_status(
        self,
        document: Document,
        status: str,
        *,
        error_message: str | None = None,
    ) -> None:
        if status not in DOCUMENT_PROCESSING_STATUSES:
            raise ValueError("Invalid document processing status.")
        document.processing_status = status
        document.error_message = error_message
        document.updated_at = datetime.now(timezone.utc)
        await self._session.flush()

    async def delete(self, document: Document) -> None:
        await self._session.delete(document)
        await self._session.flush()
