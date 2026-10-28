"""Reusable semantic retrieval orchestration without answer generation."""

import math
import uuid
from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.core.config import settings
from src.search_engine.rag.contracts import EmbeddingProvider, RetrievedChunk
from src.search_engine.rag.embeddings import (
    EmbeddingProviderError,
    GeminiEmbeddingProvider,
)
from src.search_engine.repositories.document_retrieval_repository import (
    DocumentRetrievalRepository,
)


class RetrievalRepository(Protocol):
    async def resolve_owned_document_ids(
        self,
        *,
        user_id: uuid.UUID,
        document_ids: Sequence[uuid.UUID],
    ) -> set[uuid.UUID]: ...

    async def has_searchable_chunks(
        self,
        *,
        user_id: uuid.UUID,
        document_ids: Sequence[uuid.UUID] | None = None,
    ) -> bool: ...

    async def search(
        self,
        *,
        user_id: uuid.UUID,
        query_embedding: Sequence[float],
        limit: int,
        document_ids: Sequence[uuid.UUID] | None = None,
        min_similarity: float | None = None,
    ) -> list[RetrievedChunk]: ...


class RetrievalError(RuntimeError):
    """Base class for semantic retrieval failures."""


class InvalidRetrievalQueryError(RetrievalError, ValueError):
    """Raised when query text or retrieval controls are invalid."""


class RetrievalDocumentAccessError(RetrievalError, LookupError):
    """Raised when any requested document is missing or foreign."""


class QueryEmbeddingError(RetrievalError):
    """Raised when the query cannot be embedded safely."""


class RetrievalExecutionError(RetrievalError):
    """Raised when PostgreSQL cannot complete semantic retrieval."""


class SemanticRetrievalService:
    """Validate, authorize, embed, and retrieve ranked source chunks."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        repository: RetrievalRepository | None = None,
        embeddings: EmbeddingProvider | None = None,
    ) -> None:
        self._repository = repository or DocumentRetrievalRepository(session)
        self._embeddings = embeddings or GeminiEmbeddingProvider()

    async def retrieve(
        self,
        *,
        user_id: uuid.UUID,
        query: str,
        top_k: int = settings.rag_retrieval_top_k,
        document_ids: Sequence[uuid.UUID] | None = None,
        min_similarity: float | None = settings.rag_retrieval_default_min_similarity,
    ) -> list[RetrievedChunk]:
        clean_query = _validate_query(query)
        _validate_top_k(top_k)
        _validate_min_similarity(min_similarity)
        filters = _validate_document_filters(document_ids)

        try:
            if filters is not None:
                owned = await self._repository.resolve_owned_document_ids(
                    user_id=user_id,
                    document_ids=filters,
                )
                if owned != set(filters):
                    raise RetrievalDocumentAccessError(
                        "One or more requested documents are unavailable."
                    )

            if not await self._repository.has_searchable_chunks(
                user_id=user_id,
                document_ids=filters,
            ):
                return []
        except SQLAlchemyError as exc:
            raise RetrievalExecutionError("Unable to inspect indexed documents.") from exc

        try:
            query_embedding = await self._embeddings.embed_query(clean_query)
        except EmbeddingProviderError as exc:
            raise QueryEmbeddingError("Unable to embed the retrieval query.") from exc

        try:
            return await self._repository.search(
                user_id=user_id,
                query_embedding=query_embedding,
                limit=top_k,
                document_ids=filters,
                min_similarity=min_similarity,
            )
        except SQLAlchemyError as exc:
            raise RetrievalExecutionError("Semantic retrieval failed.") from exc


def _validate_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        raise InvalidRetrievalQueryError("Retrieval query must not be empty.")
    clean_query = query.strip()
    if len(clean_query) > settings.rag_retrieval_max_query_characters:
        raise InvalidRetrievalQueryError("Retrieval query is too long.")
    return clean_query


def _validate_top_k(top_k: int) -> None:
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise InvalidRetrievalQueryError("Top-K must be an integer.")
    if not 1 <= top_k <= settings.rag_retrieval_max_top_k:
        raise InvalidRetrievalQueryError(
            f"Top-K must be between 1 and {settings.rag_retrieval_max_top_k}."
        )


def _validate_min_similarity(min_similarity: float | None) -> None:
    if min_similarity is None:
        return
    if isinstance(min_similarity, bool) or not isinstance(
        min_similarity,
        (int, float),
    ):
        raise InvalidRetrievalQueryError("Minimum similarity must be numeric.")
    if not math.isfinite(float(min_similarity)) or not -1.0 <= min_similarity <= 1.0:
        raise InvalidRetrievalQueryError(
            "Minimum similarity must be finite and between -1 and 1."
        )


def _validate_document_filters(
    document_ids: Sequence[uuid.UUID] | None,
) -> tuple[uuid.UUID, ...] | None:
    if document_ids is None:
        return None
    if len(document_ids) == 0:
        raise InvalidRetrievalQueryError("Document filter must not be empty.")
    if len(document_ids) > settings.rag_retrieval_max_document_filters:
        raise InvalidRetrievalQueryError("Too many document filters were provided.")
    unique: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for document_id in document_ids:
        if not isinstance(document_id, uuid.UUID):
            raise InvalidRetrievalQueryError("Document filters must be UUID values.")
        if document_id not in seen:
            unique.append(document_id)
            seen.add(document_id)
    return tuple(unique)
