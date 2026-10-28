"""PostgreSQL-backed exact pgvector ranking and ownership tests."""

import asyncio
import uuid

import pytest

from src.search_engine.database.database import SessionLocal, engine
from src.search_engine.models import Document, DocumentChunk, DocumentIndexState, User
from src.search_engine.repositories.document_retrieval_repository import (
    DocumentRetrievalRepository,
)

DIMENSIONS = 1_536


def _unit_vector(first: float, second: float = 0.0) -> list[float]:
    return [first, second] + [0.0] * (DIMENSIONS - 2)


def test_exact_cosine_search_filters_ownership_status_nulls_and_thresholds() -> None:
    async def scenario() -> None:
        async with SessionLocal() as session:
            transaction = await session.begin()
            try:
                owner = User(
                    full_name="Retrieval Owner",
                    email=f"retrieval-owner-{uuid.uuid4()}@example.com",
                    password_hash="not-used",
                )
                other = User(
                    full_name="Other Owner",
                    email=f"retrieval-other-{uuid.uuid4()}@example.com",
                    password_hash="not-used",
                )
                session.add_all([owner, other])
                await session.flush()

                primary = Document(
                    user_id=owner.id,
                    original_filename="primary.txt",
                    storage_path=f"{uuid.uuid4()}.txt",
                    content_type="text/plain",
                    file_size=10,
                    processing_status="completed",
                )
                secondary = Document(
                    user_id=owner.id,
                    original_filename="secondary.txt",
                    storage_path=f"{uuid.uuid4()}.txt",
                    content_type="text/plain",
                    file_size=10,
                    processing_status="completed",
                )
                failed = Document(
                    user_id=owner.id,
                    original_filename="failed.txt",
                    storage_path=f"{uuid.uuid4()}.txt",
                    content_type="text/plain",
                    file_size=10,
                    processing_status="completed",
                )
                foreign = Document(
                    user_id=other.id,
                    original_filename="foreign.txt",
                    storage_path=f"{uuid.uuid4()}.txt",
                    content_type="text/plain",
                    file_size=10,
                    processing_status="completed",
                )
                session.add_all([primary, secondary, failed, foreign])
                await session.flush()
                session.add_all(
                    [
                        DocumentIndexState(
                            document_id=primary.id,
                            status="completed",
                            generation=1,
                        ),
                        DocumentIndexState(
                            document_id=secondary.id,
                            status="completed",
                            generation=1,
                        ),
                        DocumentIndexState(
                            document_id=failed.id,
                            status="failed",
                            generation=1,
                        ),
                        DocumentIndexState(
                            document_id=foreign.id,
                            status="completed",
                            generation=1,
                        ),
                    ]
                )
                await session.flush()

                perfect_a = DocumentChunk(
                    document_id=primary.id,
                    chunk_index=0,
                    content="perfect zero",
                    page_number=1,
                    char_start=0,
                    char_end=12,
                    embedding=_unit_vector(1.0),
                )
                perfect_b = DocumentChunk(
                    document_id=primary.id,
                    chunk_index=1,
                    content="perfect one",
                    page_number=2,
                    char_start=13,
                    char_end=24,
                    embedding=_unit_vector(1.0),
                )
                weaker = DocumentChunk(
                    document_id=secondary.id,
                    chunk_index=0,
                    content="weaker",
                    embedding=_unit_vector(0.8, 0.6),
                )
                null_vector = DocumentChunk(
                    document_id=secondary.id,
                    chunk_index=1,
                    content="not embedded",
                    embedding=None,
                )
                failed_chunk = DocumentChunk(
                    document_id=failed.id,
                    chunk_index=0,
                    content="failed index",
                    embedding=_unit_vector(1.0),
                )
                foreign_chunk = DocumentChunk(
                    document_id=foreign.id,
                    chunk_index=0,
                    content="foreign secret",
                    embedding=_unit_vector(1.0),
                )
                session.add_all(
                    [
                        perfect_a,
                        perfect_b,
                        weaker,
                        null_vector,
                        failed_chunk,
                        foreign_chunk,
                    ]
                )
                await session.flush()

                repository = DocumentRetrievalRepository(session)
                query = _unit_vector(1.0)
                results = await repository.search(
                    user_id=owner.id,
                    query_embedding=query,
                    limit=10,
                )

                assert [result.text for result in results] == [
                    "perfect zero",
                    "perfect one",
                    "weaker",
                ]
                assert [result.rank for result in results] == [1, 2, 3]
                assert results[0].cosine_distance == pytest.approx(0.0)
                assert results[0].cosine_similarity == pytest.approx(1.0)
                assert results[2].cosine_distance == pytest.approx(0.2)
                assert results[2].cosine_similarity == pytest.approx(0.8)
                assert results[0].filename == "primary.txt"
                assert results[0].page_number == 1
                assert results[0].char_start == 0
                assert results[0].char_end == 12

                thresholded = await repository.search(
                    user_id=owner.id,
                    query_embedding=query,
                    limit=10,
                    min_similarity=0.9,
                )
                assert [result.text for result in thresholded] == [
                    "perfect zero",
                    "perfect one",
                ]

                filtered = await repository.search(
                    user_id=owner.id,
                    query_embedding=query,
                    limit=10,
                    document_ids=[secondary.id],
                )
                assert [result.text for result in filtered] == ["weaker"]

                foreign_results = await repository.search(
                    user_id=owner.id,
                    query_embedding=query,
                    limit=10,
                    document_ids=[foreign.id],
                )
                assert foreign_results == []
                assert await repository.resolve_owned_document_ids(
                    user_id=owner.id,
                    document_ids=[primary.id, foreign.id],
                ) == {primary.id}
                assert await repository.has_searchable_chunks(user_id=owner.id)
            finally:
                await transaction.rollback()
        await engine.dispose()

    asyncio.run(scenario())
