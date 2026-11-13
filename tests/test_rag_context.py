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
    document_id = uuid.uuid4()
    chunks = [_chunk(1, "Useful evidence.", document_id=document_id),
              _chunk(2, "  useful   EVIDENCE. ", document_id=document_id)]
    result = asyncio.run(
        RagContextBuilder().build(chunks, token_counter=_count, available_tokens=50)
    )
    assert [source.label for source in result.sources] == ["S1"]
    assert result.duplicate_chunks_skipped == 1


def test_context_keeps_identical_text_from_different_documents() -> None:
    result = asyncio.run(RagContextBuilder().build(
        [_chunk(1, "Same topic."), _chunk(2, "Same topic.")],
        token_counter=_count, available_tokens=50,
    ))
    assert [source.label for source in result.sources] == ["S1", "S2"]


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


def test_complete_context_retains_all_text_with_one_exact_count():
    calls = []
    async def count(text):
        calls.append(text)
        return len(text.split())
    chunks = [_chunk(1, 'Meaningful short source.'), _chunk(2, 'Another complete source with a date: 2026-11-02.')]
    result = asyncio.run(RagContextBuilder().build(chunks, token_counter=count, available_tokens=1000))
    assert len(calls) == 1
    assert all(chunk.text in result.text for chunk in chunks)
    assert result.truncated_source_count == 0
    assert result.token_count == len(result.text.split())


def test_context_identifies_source_filename_and_escapes_unsafe_characters() -> None:
    chunk = _chunk(1, 'Chapter seven content.')
    from dataclasses import replace
    chunk = replace(chunk, filename='7-Arch & "Design".pdf')
    result = asyncio.run(RagContextBuilder().build(
        [chunk], token_counter=_count, available_tokens=100,
    ))
    assert 'filename="7-Arch &amp; &quot;Design&quot;.pdf"' in result.text
    assert result.sources[0].filename == '7-Arch & "Design".pdf'


def test_nonadditive_token_counts_trim_context_instead_of_failing() -> None:
    async def count_with_separator_cost(text: str) -> int:
        return len(text.split()) + 5 * text.count('\n\n')

    result = asyncio.run(RagContextBuilder().build(
        [_chunk(1, 'First source details.'), _chunk(2, 'Second source details.')],
        token_counter=count_with_separator_cost,
        available_tokens=14,
    ))
    assert result.sources
    assert result.token_count <= 14
    assert len(result.sources) == 1
