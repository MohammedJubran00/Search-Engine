"""Phase 4 Gemini embedding validation, batching, and retry tests."""

import asyncio
import math
from collections.abc import Sequence

import pytest

from src.search_engine.rag.embeddings import (
    EmbeddingProviderError,
    EmbeddingRateLimitError,
    GeminiEmbeddingProvider,
    InvalidEmbeddingError,
)

DIMENSIONS = 1_536


class FakeEmbeddingClient:
    def __init__(
        self,
        vector: Sequence[float] | None = None,
        *,
        failures: list[Exception] | None = None,
    ) -> None:
        self.vector = list(
            vector if vector is not None else ([3.0, 4.0] + [0.0] * (DIMENSIONS - 2))
        )
        self.failures = list(failures or [])
        self.document_calls: list[dict[str, object]] = []
        self.query_calls: list[dict[str, object]] = []
        self.active = 0
        self.max_active = 0

    async def aembed_documents(
        self,
        texts: list[str],
        *,
        batch_size: int,
        task_type: str,
        output_dimensionality: int,
    ) -> list[list[float]]:
        self.document_calls.append(
            {
                "texts": list(texts),
                "batch_size": batch_size,
                "task_type": task_type,
                "output_dimensionality": output_dimensionality,
            }
        )
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0)
        self.active -= 1
        if self.failures:
            raise self.failures.pop(0)
        return [list(self.vector) for _ in texts]

    async def aembed_query(
        self,
        text: str,
        *,
        task_type: str,
        output_dimensionality: int,
    ) -> list[float]:
        self.query_calls.append(
            {
                "text": text,
                "task_type": task_type,
                "output_dimensionality": output_dimensionality,
            }
        )
        if self.failures:
            raise self.failures.pop(0)
        return list(self.vector)


class ShortResponseClient(FakeEmbeddingClient):
    async def aembed_documents(
        self,
        texts: list[str],
        *,
        batch_size: int,
        task_type: str,
        output_dimensionality: int,
    ) -> list[list[float]]:
        await super().aembed_documents(
            texts,
            batch_size=batch_size,
            task_type=task_type,
            output_dimensionality=output_dimensionality,
        )
        return []


async def _no_sleep(_: float) -> None:
    return None


def _provider(client: FakeEmbeddingClient, **overrides: object) -> GeminiEmbeddingProvider:
    options = {
        "client": client,
        "dimensions": DIMENSIONS,
        "batch_size": 2,
        "max_concurrency": 2,
        "max_retries": 2,
        "retry_base_seconds": 0,
        "sleep": _no_sleep,
    }
    options.update(overrides)
    return GeminiEmbeddingProvider(**options)  # type: ignore[arg-type]


def test_document_embeddings_use_exact_dimension_task_type_and_l2_norm() -> None:
    client = FakeEmbeddingClient()
    vectors = asyncio.run(_provider(client).embed_documents(["alpha", "beta"]))

    assert len(vectors) == 2
    assert all(len(vector) == DIMENSIONS for vector in vectors)
    assert all(math.isclose(math.hypot(*vector), 1.0) for vector in vectors)
    assert vectors[0][:2] == pytest.approx([0.6, 0.8])
    assert client.document_calls[0]["task_type"] == "RETRIEVAL_DOCUMENT"
    assert client.document_calls[0]["output_dimensionality"] == DIMENSIONS


def test_query_embedding_uses_retrieval_query_task_type() -> None:
    client = FakeEmbeddingClient()
    vector = asyncio.run(_provider(client).embed_query("future question"))

    assert len(vector) == DIMENSIONS
    assert math.isclose(math.hypot(*vector), 1.0)
    assert client.query_calls == [
        {
            "text": "future question",
            "task_type": "RETRIEVAL_QUERY",
            "output_dimensionality": DIMENSIONS,
        }
    ]


def test_batches_are_bounded_ordered_and_duplicate_text_is_embedded_once() -> None:
    client = FakeEmbeddingClient()
    texts = ["alpha", "beta", "alpha", "gamma", "delta"]

    vectors = asyncio.run(_provider(client).embed_documents(texts))

    requested = [
        text
        for call in client.document_calls
        for text in call["texts"]  # type: ignore[union-attr]
    ]
    assert requested == ["alpha", "beta", "gamma", "delta"]
    assert all(len(call["texts"]) <= 2 for call in client.document_calls)  # type: ignore[arg-type]
    assert client.max_active <= 2
    assert vectors[0] == vectors[2]
    assert len(vectors) == len(texts)


@pytest.mark.parametrize(
    "vector",
    [
        [],
        [1.0] * (DIMENSIONS - 1),
        [0.0] * DIMENSIONS,
        [math.nan] + [0.0] * (DIMENSIONS - 1),
        [math.inf] + [0.0] * (DIMENSIONS - 1),
    ],
    ids=["empty", "wrong-size", "zero", "nan", "infinity"],
)
def test_invalid_vectors_are_rejected(vector: list[float]) -> None:
    with pytest.raises(InvalidEmbeddingError):
        asyncio.run(_provider(FakeEmbeddingClient(vector)).embed_documents(["text"]))


def test_rate_limit_is_retried_with_bounded_attempts() -> None:
    client = FakeEmbeddingClient(
        failures=[EmbeddingRateLimitError("429"), EmbeddingRateLimitError("429")]
    )

    vectors = asyncio.run(_provider(client).embed_documents(["text"]))

    assert len(vectors) == 1
    assert len(client.document_calls) == 3


def test_exhausted_rate_limit_and_permanent_api_failure_are_safe() -> None:
    limited = FakeEmbeddingClient(
        failures=[EmbeddingRateLimitError("429")] * 3,
    )
    with pytest.raises(EmbeddingRateLimitError):
        asyncio.run(_provider(limited).embed_documents(["text"]))

    permanent = FakeEmbeddingClient(failures=[RuntimeError("secret upstream detail")])
    with pytest.raises(EmbeddingProviderError, match="request failed"):
        asyncio.run(_provider(permanent).embed_query("text"))


def test_empty_input_avoids_api_calls_and_blank_text_is_rejected() -> None:
    client = FakeEmbeddingClient()
    provider = _provider(client)

    assert asyncio.run(provider.embed_documents([])) == []
    assert client.document_calls == []
    with pytest.raises(EmbeddingProviderError, match="must not be empty"):
        asyncio.run(provider.embed_documents(["  "]))


def test_batch_response_count_mismatch_is_rejected() -> None:
    with pytest.raises(InvalidEmbeddingError, match="response count"):
        asyncio.run(_provider(ShortResponseClient()).embed_documents(["text"]))


@pytest.mark.parametrize("batch_size", [0, 101])
def test_invalid_batch_configuration_is_rejected(batch_size: int) -> None:
    with pytest.raises(ValueError, match="batch size"):
        _provider(FakeEmbeddingClient(), batch_size=batch_size)
