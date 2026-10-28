"""Validated Gemini embeddings with bounded batching, concurrency, and retry.

No document text, credentials, or vectors are logged here. The provider uses
the existing async LangChain Gemini client but keeps task types operation-
specific so document and future query embeddings cannot be confused.
"""

import asyncio
import math
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol, TypeVar

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from src.search_engine.core.config import settings

GEMINI_MAX_BATCH_SIZE = 100
_UNIT_NORM_TOLERANCE = 1e-6
_EmbeddingResult = TypeVar("_EmbeddingResult")


class EmbeddingProviderError(RuntimeError):
    """Base error for safe embedding-provider failures."""


class EmbeddingRateLimitError(EmbeddingProviderError):
    """Raised when transient API exhaustion remains after bounded retries."""


class InvalidEmbeddingError(EmbeddingProviderError, ValueError):
    """Raised when Gemini returns unusable embedding data."""


class EmbeddingClient(Protocol):
    """Async subset of the LangChain Gemini embedding client used here."""

    async def aembed_documents(
        self,
        texts: list[str],
        *,
        batch_size: int,
        task_type: str,
        output_dimensionality: int,
    ) -> list[list[float]]: ...

    async def aembed_query(
        self,
        text: str,
        *,
        task_type: str,
        output_dimensionality: int,
    ) -> list[float]: ...


class GeminiEmbeddingProvider:
    """Generate normalized Gemini vectors without retrieval or persistence."""

    def __init__(
        self,
        *,
        client: EmbeddingClient | None = None,
        model: str = settings.rag_embedding_model,
        dimensions: int = settings.rag_embedding_dimensions,
        document_task_type: str = settings.rag_embedding_document_task_type,
        query_task_type: str = settings.rag_embedding_query_task_type,
        normalize: bool = settings.rag_embedding_normalize,
        batch_size: int = settings.rag_embedding_batch_size,
        max_concurrency: int = settings.rag_embedding_max_concurrency,
        max_retries: int = settings.rag_embedding_max_retries,
        retry_base_seconds: float = settings.rag_embedding_retry_base_seconds,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        _validate_provider_configuration(
            dimensions=dimensions,
            batch_size=batch_size,
            max_concurrency=max_concurrency,
            max_retries=max_retries,
            retry_base_seconds=retry_base_seconds,
        )
        self._client = (
            client
            if client is not None
            else GoogleGenerativeAIEmbeddings(
                model=model,
                api_key=settings.gemini_api_key,
                output_dimensionality=dimensions,
            )
        )
        self.dimensions = dimensions
        self.document_task_type = document_task_type
        self.query_task_type = query_task_type
        self.normalize = normalize
        self.batch_size = batch_size
        self.max_concurrency = max_concurrency
        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds
        self._sleep = sleep

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed unique nonblank texts in bounded batches and restore order."""
        if not texts:
            return []
        unique_texts: list[str] = []
        unique_positions: dict[str, int] = {}
        positions: list[int] = []
        for text in texts:
            _validate_embedding_text(text)
            position = unique_positions.get(text)
            if position is None:
                position = len(unique_texts)
                unique_positions[text] = position
                unique_texts.append(text)
            positions.append(position)

        batches = [
            unique_texts[index : index + self.batch_size]
            for index in range(0, len(unique_texts), self.batch_size)
        ]
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def embed_batch(batch: list[str]) -> list[list[float]]:
            async with semaphore:
                raw = await self._with_retry(
                    lambda: self._client.aembed_documents(
                        batch,
                        batch_size=len(batch),
                        task_type=self.document_task_type,
                        output_dimensionality=self.dimensions,
                    )
                )
            if len(raw) != len(batch):
                raise InvalidEmbeddingError(
                    "Embedding response count does not match the request."
                )
            return [self._prepare_vector(vector) for vector in raw]

        grouped = await asyncio.gather(*(embed_batch(batch) for batch in batches))
        unique_vectors = [vector for group in grouped for vector in group]
        return [unique_vectors[position] for position in positions]

    async def embed_query(self, text: str) -> list[float]:
        """Embed one future retrieval query with its distinct task type."""
        _validate_embedding_text(text)
        raw = await self._with_retry(
            lambda: self._client.aembed_query(
                text,
                task_type=self.query_task_type,
                output_dimensionality=self.dimensions,
            )
        )
        return self._prepare_vector(raw)

    def _prepare_vector(self, vector: Sequence[float]) -> list[float]:
        if self.normalize:
            return normalize_embedding(vector, dimensions=self.dimensions)
        validated = validate_embedding(
            vector,
            dimensions=self.dimensions,
            require_unit_norm=False,
        )
        return list(validated)

    async def _with_retry(
        self,
        operation: Callable[[], Awaitable[_EmbeddingResult]],
    ) -> _EmbeddingResult:
        for attempt in range(self.max_retries + 1):
            try:
                return await operation()
            except Exception as exc:
                retryable = _is_retryable(exc)
                if not retryable or attempt == self.max_retries:
                    if isinstance(exc, EmbeddingProviderError):
                        raise
                    if retryable:
                        raise EmbeddingRateLimitError(
                            "Gemini embedding capacity remained unavailable after retries."
                        ) from exc
                    raise EmbeddingProviderError(
                        "Gemini embedding request failed."
                    ) from exc
                await self._sleep(self.retry_base_seconds * (2**attempt))
        raise AssertionError("Unreachable embedding retry state.")


def normalize_embedding(
    vector: Sequence[float],
    *,
    dimensions: int,
) -> list[float]:
    """Validate and L2-normalize one vector using overflow-safe math."""
    values = validate_embedding(
        vector,
        dimensions=dimensions,
        require_unit_norm=False,
    )
    norm = math.hypot(*values)
    if norm == 0.0:
        raise InvalidEmbeddingError("Embedding vector has zero norm.")
    normalized = [value / norm for value in values]
    validate_embedding(
        normalized,
        dimensions=dimensions,
        require_unit_norm=True,
    )
    return normalized


def validate_embedding(
    vector: Sequence[float],
    *,
    dimensions: int,
    require_unit_norm: bool,
) -> tuple[float, ...]:
    """Return finite floats after dimension and optional unit-norm checks."""
    if len(vector) != dimensions:
        raise InvalidEmbeddingError(
            f"Embedding must contain exactly {dimensions} dimensions."
        )
    try:
        values = tuple(float(value) for value in vector)
    except (TypeError, ValueError) as exc:
        raise InvalidEmbeddingError("Embedding contains a non-numeric value.") from exc
    if not values or not all(math.isfinite(value) for value in values):
        raise InvalidEmbeddingError("Embedding contains a non-finite value.")
    norm = math.hypot(*values)
    if norm == 0.0:
        raise InvalidEmbeddingError("Embedding vector has zero norm.")
    if require_unit_norm and not math.isclose(
        norm,
        1.0,
        rel_tol=_UNIT_NORM_TOLERANCE,
        abs_tol=_UNIT_NORM_TOLERANCE,
    ):
        raise InvalidEmbeddingError("Embedding vector is not L2-normalized.")
    return values


def _validate_embedding_text(text: str) -> None:
    if not isinstance(text, str) or not text.strip():
        raise EmbeddingProviderError("Embedding input text must not be empty.")


def _validate_provider_configuration(
    *,
    dimensions: int,
    batch_size: int,
    max_concurrency: int,
    max_retries: int,
    retry_base_seconds: float,
) -> None:
    if dimensions <= 0:
        raise ValueError("Embedding dimensions must be positive.")
    if not 1 <= batch_size <= GEMINI_MAX_BATCH_SIZE:
        raise ValueError(
            f"Embedding batch size must be between 1 and {GEMINI_MAX_BATCH_SIZE}."
        )
    if max_concurrency <= 0:
        raise ValueError("Embedding concurrency must be positive.")
    if max_retries < 0:
        raise ValueError("Embedding retry count cannot be negative.")
    if retry_base_seconds < 0:
        raise ValueError("Embedding retry delay cannot be negative.")


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, EmbeddingRateLimitError):
        return True
    current: BaseException | None = exc
    while current is not None:
        status = getattr(current, "status", None) or getattr(
            current, "status_code", None
        )
        if status in (429, 500, 502, 503, 504):
            return True
        message = str(current).lower()
        if any(
            marker in message
            for marker in (
                "429",
                "rate limit",
                "resource exhausted",
                "temporarily unavailable",
                "service unavailable",
            )
        ):
            return True
        current = current.__cause__ or current.__context__
    return False
