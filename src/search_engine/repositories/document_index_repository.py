"""Atomic ownership-scoped persistence for document chunks and index state."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.core.config import settings
from src.search_engine.models.document import Document
from src.search_engine.models.document_chunk import DocumentChunk
from src.search_engine.models.document_index_state import DocumentIndexState
from src.search_engine.rag.contracts import TextChunk
from src.search_engine.rag.embeddings import validate_embedding


class ConcurrentDocumentIndexingError(RuntimeError):
    """Raised when the document already has an active indexing generation."""


class IndexingClaimLostError(RuntimeError):
    """Raised when a stale worker attempts to finalize another generation."""


class InvalidIndexPayloadError(ValueError):
    """Raised before database mutation when chunks and vectors are inconsistent."""


@dataclass(frozen=True, slots=True)
class IndexingClaim:
    """Authorized document plus the generation owned by one indexing run."""

    document: Document
    generation: int


class DocumentIndexRepository:
    """Claim and atomically replace one authorized document's vector index."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(
        self,
        *,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        supersede_processing: bool = False,
    ) -> IndexingClaim | None:
        document = await self._lock_document(document_id, user_id)
        if document is None:
            return None
        state = await self._lock_state(document_id)
        if state is None:
            state = DocumentIndexState(
                document_id=document_id,
                status="processing",
                generation=1,
                error_message=None,
                updated_at=datetime.now(timezone.utc),
            )
            self._session.add(state)
        else:
            if state.status == "processing" and not supersede_processing:
                raise ConcurrentDocumentIndexingError(
                    "Document indexing is already in progress."
                )
            state.status = "processing"
            state.generation += 1
            state.error_message = None
            state.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return IndexingClaim(document=document, generation=state.generation)

    async def replace(
        self,
        *,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        generation: int,
        chunks: Sequence[TextChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> int:
        rows = prepare_document_chunks(
            document_id=document_id,
            user_id=user_id,
            chunks=chunks,
            embeddings=embeddings,
        )
        document = await self._lock_document(document_id, user_id)
        if document is None:
            raise IndexingClaimLostError("Document indexing claim is no longer valid.")
        state = await self._lock_state(document_id)
        _require_generation(state, generation)

        await self._session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        self._session.add_all(rows)
        state.status = "completed"
        state.error_message = None
        state.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return len(rows)

    async def mark_failed(
        self,
        *,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        generation: int,
        error_message: str,
    ) -> bool:
        document = await self._lock_document(document_id, user_id)
        if document is None:
            return False
        state = await self._lock_state(document_id)
        if (
            state is None
            or state.generation != generation
            or state.status != "processing"
        ):
            return False
        state.status = "failed"
        state.error_message = error_message
        state.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return True

    async def _lock_document(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Document | None:
        result = await self._session.execute(
            select(Document)
            .where(Document.id == document_id, Document.user_id == user_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def _lock_state(
        self,
        document_id: uuid.UUID,
    ) -> DocumentIndexState | None:
        result = await self._session.execute(
            select(DocumentIndexState)
            .where(DocumentIndexState.document_id == document_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()


def prepare_document_chunks(
    *,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    chunks: Sequence[TextChunk],
    embeddings: Sequence[Sequence[float]],
) -> list[DocumentChunk]:
    """Validate the complete replacement payload before any SQL mutation."""
    if not chunks:
        raise InvalidIndexPayloadError("At least one chunk is required.")
    if len(chunks) != len(embeddings):
        raise InvalidIndexPayloadError("Every chunk must have exactly one embedding.")

    rows: list[DocumentChunk] = []
    for expected_index, (chunk, embedding) in enumerate(
        zip(chunks, embeddings, strict=True)
    ):
        if chunk.document_id != document_id or chunk.user_id != user_id:
            raise InvalidIndexPayloadError("Chunk ownership does not match the document.")
        if chunk.index != expected_index:
            raise InvalidIndexPayloadError(
                "Chunk indexes must be unique, contiguous, and zero-based."
            )
        if not chunk.text.strip():
            raise InvalidIndexPayloadError("Chunk content must not be empty.")
        page_number = _optional_metadata_integer(chunk, "page_number")
        char_start = _optional_metadata_integer(chunk, "char_start")
        char_end = _optional_metadata_integer(chunk, "char_end")
        if page_number is not None and page_number < 1:
            raise InvalidIndexPayloadError("PDF page numbers must be positive.")
        if (char_start is None) != (char_end is None):
            raise InvalidIndexPayloadError("Chunk character ranges must be complete.")
        if char_start is not None and (char_start < 0 or char_end < char_start):
            raise InvalidIndexPayloadError("Chunk character range is invalid.")
        vector = validate_embedding(
            embedding,
            dimensions=settings.rag_embedding_dimensions,
            require_unit_norm=settings.rag_embedding_normalize,
        )
        rows.append(
            DocumentChunk(
                document_id=document_id,
                chunk_index=chunk.index,
                content=chunk.text,
                page_number=page_number,
                char_start=char_start,
                char_end=char_end,
                embedding=list(vector),
            )
        )
    return rows


def _optional_metadata_integer(chunk: TextChunk, key: str) -> int | None:
    value = chunk.metadata.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidIndexPayloadError(f"Chunk {key} must be an integer.")
    return value


def _require_generation(
    state: DocumentIndexState | None,
    generation: int,
) -> None:
    if (
        state is None
        or state.status != "processing"
        or state.generation != generation
    ):
        raise IndexingClaimLostError("Document indexing generation is no longer active.")
