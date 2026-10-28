"""Token-bounded, source-aware RAG context tests."""

import asyncio
import uuid

from src.search_engine.rag.context import RagContextBuilder
from src.search_engine.rag.contracts import RetrievedChunk


async def _count(text: str) -> int:
    return len(text.split())


def _chunk(rank: int, text: str, *, document_id: uuid.UUID | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=document_id or uuid.uuid4(),
        filename=f"document-{rank}.pdf",
        chunk_index=rank - 1,
        text=text,
        page_number=rank,
        char_start=0,
        char_end=len(text),
        cosine_distance=0.1,
        cosine_similarity=0.9,
        rank=rank,
    )


def test_context_deduplicates_identical_content_and_keeps_stable_labels() -> None:
    chunks = [_chunk(1, "Useful evidence."), _chunk(2, "  useful   EVIDENCE. ")]
    result = asyncio.run(
        RagContextBuilder().build(chunks, token_counter=_count, available_tokens=50)
    )
    assert [source.label for source in result.sources] == ["S1"]
    assert result.duplicate_chunks_skipped == 1


def test_context_preserves_multiple_sources_within_budget() -> None:
    chunks = [
        _chunk(1, " ".join(f"alpha{i}" for i in range(30))),
        _chunk(2, " ".join(f"beta{i}" for i in range(30))),
    ]
    result = asyncio.run(
        RagContextBuilder().build(chunks, token_counter=_count, available_tokens=30)
    )
    assert len(result.sources) == 2
    assert result.token_count <= 30
    assert result.truncated_source_count == 2


def test_oversized_source_is_cut_at_word_boundary() -> None:
    result = asyncio.run(
        RagContextBuilder().build(
            [_chunk(1, "one two three four five six seven eight nine ten")],
            token_counter=_count,
            available_tokens=7,
        )
    )
    assert result.token_count <= 7
    assert result.sources
    assert not result.sources[0].evidence_excerpt.endswith(" thre")


def test_empty_retrieved_text_is_not_exposed_as_a_source() -> None:
    result = asyncio.run(
        RagContextBuilder().build(
            [_chunk(1, "   ")], token_counter=_count, available_tokens=20
        )
    )
    assert result.text == ""
    assert result.sources == ()
