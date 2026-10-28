"""Exact pgvector cosine search with mandatory document ownership filtering."""

import uuid
from collections.abc import Sequence

from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.core.config import settings
from src.search_engine.models.document import Document
from src.search_engine.models.document_chunk import DocumentChunk
from src.search_engine.models.document_index_state import DocumentIndexState
from src.search_engine.rag.contracts import RetrievedChunk
from src.search_engine.rag.embeddings import validate_embedding


class DocumentRetrievalRepository:
    """Run parameterized exact vector queries without loading vectors into Python."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_owned_document_ids(
        self,
        *,
        user_id: uuid.UUID,
        document_ids: Sequence[uuid.UUID],
    ) -> set[uuid.UUID]:
        if not document_ids:
            return set()
        result = await self._session.execute(
            select(Document.id).where(
                Document.user_id == user_id,
                Document.id.in_(document_ids),
            )
        )
        return set(result.scalars().all())

    async def has_searchable_chunks(
        self,
        *,
        user_id: uuid.UUID,
        document_ids: Sequence[uuid.UUID] | None = None,
    ) -> bool:
        statement = (
            select(literal(1))
            .select_from(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(
                DocumentIndexState,
                DocumentIndexState.document_id == Document.id,
            )
            .where(
                Document.user_id == user_id,
                DocumentIndexState.status == "completed",
                DocumentChunk.embedding.is_not(None),
            )
            .limit(1)
        )
        if document_ids is not None:
            statement = statement.where(Document.id.in_(document_ids))
        result = await self._session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def search(
        self,
        *,
        user_id: uuid.UUID,
        query_embedding: Sequence[float],
        limit: int,
        document_ids: Sequence[uuid.UUID] | None = None,
        min_similarity: float | None = None,
    ) -> list[RetrievedChunk]:
        vector = validate_embedding(
            query_embedding,
            dimensions=settings.rag_embedding_dimensions,
            require_unit_norm=settings.rag_embedding_normalize,
        )
        distance = DocumentChunk.embedding.cosine_distance(list(vector)).label(
            "cosine_distance"
        )
        statement = (
            select(
                DocumentChunk.id.label("chunk_id"),
                DocumentChunk.document_id,
                Document.original_filename.label("filename"),
                DocumentChunk.chunk_index,
                DocumentChunk.content,
                DocumentChunk.page_number,
                DocumentChunk.char_start,
                DocumentChunk.char_end,
                distance,
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(
                DocumentIndexState,
                DocumentIndexState.document_id == Document.id,
            )
            .where(
                Document.user_id == user_id,
                DocumentIndexState.status == "completed",
                DocumentChunk.embedding.is_not(None),
            )
        )
        if document_ids is not None:
            statement = statement.where(Document.id.in_(document_ids))
        if min_similarity is not None:
            statement = statement.where(distance <= 1.0 - min_similarity)
        statement = statement.order_by(
            distance.asc(),
            DocumentChunk.document_id.asc(),
            DocumentChunk.chunk_index.asc(),
            DocumentChunk.id.asc(),
        ).limit(limit)

        rows = (await self._session.execute(statement)).all()
        return [
            RetrievedChunk(
                chunk_id=row.chunk_id,
                document_id=row.document_id,
                filename=row.filename,
                chunk_index=row.chunk_index,
                text=row.content,
                page_number=row.page_number,
                char_start=row.char_start,
                char_end=row.char_end,
                cosine_distance=float(row.cosine_distance),
                cosine_similarity=1.0 - float(row.cosine_distance),
                rank=rank,
            )
            for rank, row in enumerate(rows, start=1)
        ]
