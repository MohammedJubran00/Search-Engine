"""Explicit, retry-safe document chunking and vector indexing workflow.

This service is invoked only by an explicit authenticated indexing action, never
by upload. It commits a short generation claim before parser/Gemini work, then
atomically swaps chunks and marks that generation complete.
"""

import asyncio
import uuid
from dataclasses import dataclass
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.core.config import settings
from src.search_engine.rag.chunking import RagTextChunker
from src.search_engine.rag.contracts import (
    DocumentRecord,
    EmbeddingProvider,
    TextChunk,
)
from src.search_engine.rag.embeddings import (
    EmbeddingRateLimitError,
    GeminiEmbeddingProvider,
)
from src.search_engine.rag.parsers import DocumentParseError, RagDocumentParser
from src.search_engine.rag.storage import DocumentStorage, StorageOperationError
from src.search_engine.repositories.document_index_repository import (
    ConcurrentDocumentIndexingError,
    DocumentIndexRepository,
    IndexingClaim,
)


class DocumentIndexingError(RuntimeError):
    """Base error for indexing failures safe to expose to internal callers."""


class DocumentIndexingNotFoundError(DocumentIndexingError, LookupError):
    """Raised for missing and foreign documents without leaking ownership."""


class EmptyDocumentIndexError(DocumentIndexingError, ValueError):
    """Raised when parsing produces no non-whitespace chunks."""


class DocumentChunkLimitError(DocumentIndexingError, ValueError):
    """Raised before embeddings when a document exceeds the local cost bound."""


class DocumentIndexingQuotaError(DocumentIndexingError):
    """Raised when provider capacity remains unavailable after safe retries."""


@dataclass(frozen=True, slots=True)
class DocumentIndexingResult:
    """Summary of one successfully persisted indexing generation."""

    document_id: uuid.UUID
    generation: int
    chunk_count: int


class DocumentIndexingService:
    """Index an existing authorized document without changing upload behavior."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        repository: DocumentIndexRepository | None = None,
        storage: DocumentStorage | None = None,
        parser: RagDocumentParser | None = None,
        chunker: RagTextChunker | None = None,
        embeddings: EmbeddingProvider | None = None,
        max_chunks: int | None = None,
    ) -> None:
        self._session = session
        self._index = repository or DocumentIndexRepository(session)
        self._storage = storage or DocumentStorage(settings.rag_storage_dir)
        self._parser = parser or RagDocumentParser(
            max_docx_uncompressed_bytes=settings.rag_max_docx_uncompressed_bytes,
            pdf_boilerplate_min_pages=settings.rag_pdf_boilerplate_min_pages,
            pdf_boilerplate_page_ratio=settings.rag_pdf_boilerplate_page_ratio,
            pdf_boilerplate_margin_ratio=settings.rag_pdf_boilerplate_margin_ratio,
            pdf_boilerplate_max_line_characters=(
                settings.rag_pdf_boilerplate_max_line_characters
            ),
        )
        self._chunker = chunker or RagTextChunker(
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
        )
        self._embeddings = embeddings or GeminiEmbeddingProvider()
        self._max_chunks = max_chunks or settings.rag_indexing_max_chunks
        if self._max_chunks < 1:
            raise ValueError("Indexing maximum chunks must be positive.")

    async def index(
        self,
        *,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        supersede_processing: bool = False,
        progress: Callable[[str, int, int | None], Awaitable[None]] | None = None,
    ) -> DocumentIndexingResult:
        try:
            claim = await self._index.claim(
                document_id=document_id,
                user_id=user_id,
                supersede_processing=supersede_processing,
            )
            if claim is None:
                raise DocumentIndexingNotFoundError
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        try:
            chunks = await self._prepare_chunks(claim)
            if progress:
                await progress("chunked", 0, len(chunks))
            vectors = await self._embeddings.embed_documents(
                [chunk.text for chunk in chunks]
            )
            if progress:
                await progress("embedded", len(vectors), len(chunks))
            chunk_count = await self._index.replace(
                document_id=document_id,
                user_id=user_id,
                generation=claim.generation,
                chunks=chunks,
                embeddings=vectors,
            )
            await self._session.commit()
            if progress:
                await progress("stored", chunk_count, chunk_count)
            return DocumentIndexingResult(
                document_id=document_id,
                generation=claim.generation,
                chunk_count=chunk_count,
            )
        except asyncio.CancelledError:
            await self._session.rollback()
            await self._record_failure(claim, "Document indexing was cancelled.")
            raise
        except Exception as exc:
            await self._session.rollback()
            await self._record_failure(claim, _safe_failure_message(exc))
            if isinstance(exc, DocumentIndexingError):
                raise
            if isinstance(exc, EmbeddingRateLimitError):
                raise DocumentIndexingQuotaError(
                    "Embedding quota or provider capacity is currently unavailable."
                ) from exc
            if isinstance(exc, (DocumentParseError, StorageOperationError)):
                raise DocumentIndexingError(str(exc)) from exc
            raise DocumentIndexingError("Unable to index the document.") from exc

    async def _prepare_chunks(self, claim: IndexingClaim) -> list[TextChunk]:
        document = claim.document
        path = self._storage.path_for(document.storage_path)
        parsed = await asyncio.to_thread(
            self._parser.parse,
            path,
            document.content_type,
        )
        record = DocumentRecord(
            id=document.id,
            user_id=document.user_id,
            filename=document.original_filename,
            content_type=document.content_type,
            storage_path=path,
        )
        chunks = self._chunker.split(record, parsed)
        if not chunks:
            raise EmptyDocumentIndexError("Document contains no indexable text.")
        if len(chunks) > self._max_chunks:
            raise DocumentChunkLimitError(
                f"Document exceeds the {self._max_chunks}-chunk indexing limit."
            )
        return chunks

    async def _record_failure(
        self,
        claim: IndexingClaim,
        message: str,
    ) -> None:
        try:
            await self._index.mark_failed(
                document_id=claim.document.id,
                user_id=claim.document.user_id,
                generation=claim.generation,
                error_message=message,
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()


def _safe_failure_message(exc: Exception) -> str:
    if isinstance(exc, EmptyDocumentIndexError):
        return "Document contains no indexable text."
    if isinstance(exc, DocumentChunkLimitError):
        return str(exc)
    if isinstance(exc, DocumentParseError):
        return str(exc)
    if isinstance(exc, ConcurrentDocumentIndexingError):
        return "Document indexing is already in progress."
    return "Document indexing failed."
