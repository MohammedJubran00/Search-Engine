"""Phase 5 retrieval service validation and authorization tests."""

import asyncio
import math
import uuid

import pytest

from src.search_engine.rag.contracts import RetrievedChunk
from src.search_engine.rag.embeddings import EmbeddingProviderError
from src.search_engine.services.retrieval_service import (
    InvalidRetrievalQueryError,
    QueryEmbeddingError,
    RetrievalDocumentAccessError,
    SemanticRetrievalService,
)

DIMENSIONS = 1_536


class FakeQueryEmbeddings:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.queries: list[str] = []

    async def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        if self.error:
            raise self.error
        return [1.0] + [0.0] * (DIMENSIONS - 1)

    async def embed_documents(self, texts):
        raise AssertionError("Retrieval must not embed documents.")


class FakeRetrievalRepository:
    def __init__(self) -> None:
        self.owned: set[uuid.UUID] = set()
        self.searchable = True
        self.results: list[RetrievedChunk] = []
        self.search_calls: list[dict[str, object]] = []
        self.has_calls: list[dict[str, object]] = []

    async def resolve_owned_document_ids(self, *, user_id, document_ids):
        return set(document_ids) & self.owned

    async def has_searchable_chunks(self, *, user_id, document_ids=None):
        self.has_calls.append({"user_id": user_id, "document_ids": document_ids})
        return self.searchable

    async def search(
        self,
        *,
        user_id,
        query_embedding,
        limit,
        document_ids=None,
        min_similarity=None,
    ):
        self.search_calls.append(
            {
                "user_id": user_id,
                "query_embedding": query_embedding,
                "limit": limit,
                "document_ids": document_ids,
                "min_similarity": min_similarity,
            }
        )
        return self.results


def _result(rank: int = 1) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        filename="source.pdf",
        chunk_index=rank - 1,
        text="retrieved evidence",
        page_number=2,
        char_start=10,
        char_end=28,
        cosine_distance=0.2,
        cosine_similarity=0.8,
        rank=rank,
    )


def _service(repository, embeddings) -> SemanticRetrievalService:
    return SemanticRetrievalService(
        None,
        repository=repository,
        embeddings=embeddings,
    )


def test_retrieval_embeds_trimmed_query_and_passes_validated_controls() -> None:
    user_id = uuid.uuid4()
    document_id = uuid.uuid4()
    repository = FakeRetrievalRepository()
    repository.owned = {document_id}
    repository.results = [_result()]
    embeddings = FakeQueryEmbeddings()

    results = asyncio.run(
        _service(repository, embeddings).retrieve(
            user_id=user_id,
            query="  What is the goal?  ",
            top_k=7,
            document_ids=[document_id, document_id],
            min_similarity=0.35,
        )
    )

    assert results == repository.results
    assert embeddings.queries == ["What is the goal?"]
    assert repository.search_calls[0]["limit"] == 7
    assert repository.search_calls[0]["document_ids"] == (document_id,)
    assert repository.search_calls[0]["min_similarity"] == 0.35
    vector = repository.search_calls[0]["query_embedding"]
    assert len(vector) == DIMENSIONS  # type: ignore[arg-type]
    assert math.isclose(math.hypot(*vector), 1.0)  # type: ignore[arg-type]


@pytest.mark.parametrize("query", ["", "   ", None])
def test_invalid_queries_are_rejected_before_embedding(query: object) -> None:
    embeddings = FakeQueryEmbeddings()
    with pytest.raises(InvalidRetrievalQueryError):
        asyncio.run(
            _service(FakeRetrievalRepository(), embeddings).retrieve(
                user_id=uuid.uuid4(),
                query=query,  # type: ignore[arg-type]
            )
        )
    assert embeddings.queries == []


@pytest.mark.parametrize("top_k", [0, -1, 51, True, 1.5])
def test_invalid_top_k_is_rejected(top_k: object) -> None:
    with pytest.raises(InvalidRetrievalQueryError, match="Top-K"):
        asyncio.run(
            _service(FakeRetrievalRepository(), FakeQueryEmbeddings()).retrieve(
                user_id=uuid.uuid4(),
                query="question",
                top_k=top_k,  # type: ignore[arg-type]
            )
        )


@pytest.mark.parametrize("threshold", [-1.1, 1.1, math.nan, math.inf, True])
def test_invalid_similarity_threshold_is_rejected(threshold: object) -> None:
    with pytest.raises(InvalidRetrievalQueryError, match="similarity"):
        asyncio.run(
            _service(FakeRetrievalRepository(), FakeQueryEmbeddings()).retrieve(
                user_id=uuid.uuid4(),
                query="question",
                min_similarity=threshold,  # type: ignore[arg-type]
            )
        )


def test_foreign_document_filter_is_rejected_without_embedding() -> None:
    repository = FakeRetrievalRepository()
    embeddings = FakeQueryEmbeddings()
    with pytest.raises(RetrievalDocumentAccessError):
        asyncio.run(
            _service(repository, embeddings).retrieve(
                user_id=uuid.uuid4(),
                query="question",
                document_ids=[uuid.uuid4()],
            )
        )
    assert embeddings.queries == []
    assert repository.search_calls == []


def test_no_indexed_chunks_returns_empty_without_api_cost() -> None:
    repository = FakeRetrievalRepository()
    repository.searchable = False
    embeddings = FakeQueryEmbeddings()

    results = asyncio.run(
        _service(repository, embeddings).retrieve(
            user_id=uuid.uuid4(),
            query="question",
        )
    )

    assert results == []
    assert embeddings.queries == []
    assert repository.search_calls == []


def test_embedding_failure_is_distinct_from_empty_results() -> None:
    embeddings = FakeQueryEmbeddings(EmbeddingProviderError("upstream"))
    with pytest.raises(QueryEmbeddingError, match="Unable to embed"):
        asyncio.run(
            _service(FakeRetrievalRepository(), embeddings).retrieve(
                user_id=uuid.uuid4(),
                query="question",
            )
        )
