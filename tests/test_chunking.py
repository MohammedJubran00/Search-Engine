"""Phase 3 structure-aware chunking and provenance tests."""

import uuid
from pathlib import Path

import pytest

from src.search_engine.rag.chunking import (
    InvalidChunkConfigurationError,
    RagTextChunker,
)
from src.search_engine.rag.contracts import (
    DocumentRecord,
    ParsedDocument,
    ParsedPage,
)
from src.search_engine.rag.parsers import PDF_CONTENT_TYPE, TXT_CONTENT_TYPE


def _record(content_type: str = TXT_CONTENT_TYPE) -> DocumentRecord:
    return DocumentRecord(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="source.txt" if content_type == TXT_CONTENT_TYPE else "source.pdf",
        content_type=content_type,
        storage_path=Path("opaque-source"),
    )


def test_short_document_produces_one_citation_ready_chunk() -> None:
    record = _record()
    parsed = ParsedDocument(text="Heading\n\nA short paragraph dated 2026-10-27.")

    chunks = RagTextChunker(chunk_size=100, chunk_overlap=20).split(record, parsed)

    assert [chunk.index for chunk in chunks] == [0]
    assert chunks[0].text == parsed.text
    assert chunks[0].document_id == record.id
    assert chunks[0].user_id == record.user_id
    assert chunks[0].metadata == {
        "source_filename": "source.txt",
        "content_type": TXT_CONTENT_TYPE,
        "char_start": 0,
        "char_end": len(parsed.text),
    }


def test_pdf_pages_remain_ordered_and_never_mix_page_attribution() -> None:
    record = _record(PDF_CONTENT_TYPE)
    parsed = ParsedDocument(
        text="First page text.\n\n\n\nThird page text.",
        pages=(
            ParsedPage("First page text. " * 8, page_number=1),
            ParsedPage("   ", page_number=2),
            ParsedPage("Third page text. " * 8, page_number=3),
        ),
    )

    chunks = RagTextChunker(chunk_size=55, chunk_overlap=12).split(record, parsed)

    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert {chunk.metadata["page_number"] for chunk in chunks} == {1, 3}
    assert all(
        ("First" in chunk.text) == (chunk.metadata["page_number"] == 1)
        for chunk in chunks
    )
    assert all(
        ("Third" in chunk.text) == (chunk.metadata["page_number"] == 3)
        for chunk in chunks
    )


def test_multilingual_structure_numbers_and_dates_are_preserved() -> None:
    text = (
        "Section 1\n\nRevenue was 1,234.50 USD on 2026-10-27.\n\n"
        "القسم الثاني\n\nبلغت النسبة ٧٥٪ في ٢٠٢٦/١٠/٢٧؟ نعم، بالتأكيد.\n\n"
        "API v2.1 uses UTF-8 and نموذج-ABC-42."
    )
    chunks = RagTextChunker(chunk_size=72, chunk_overlap=16).split(
        _record(),
        ParsedDocument(text=text, pages=(ParsedPage(text=text),)),
    )
    combined = " ".join(chunk.text for chunk in chunks)

    for important in (
        "Section 1",
        "1,234.50 USD",
        "2026-10-27",
        "القسم الثاني",
        "٧٥٪",
        "٢٠٢٦/١٠/٢٧",
        "UTF-8",
        "نموذج-ABC-42",
    ):
        assert important in combined
    for chunk in chunks:
        start = int(chunk.metadata["char_start"])
        end = int(chunk.metadata["char_end"])
        assert text[start:end] == chunk.text
    assert all(len(chunk.text) <= 72 for chunk in chunks)
    assert all("page_number" not in chunk.metadata for chunk in chunks)


def test_overlap_covers_boundaries_without_exceeding_configuration() -> None:
    text = "one two three four five six seven eight nine ten eleven twelve"
    chunks = RagTextChunker(chunk_size=30, chunk_overlap=8).split(
        _record(),
        ParsedDocument(text=text),
    )

    assert len(chunks) > 1
    for previous, current in zip(chunks, chunks[1:], strict=False):
        previous_end = int(previous.metadata["char_end"])
        current_start = int(current.metadata["char_start"])
        overlap = previous_end - current_start
        assert 0 < overlap <= 8
        assert current_start <= previous_end
    assert set(text.split()) <= set(" ".join(chunk.text for chunk in chunks).split())


def test_long_paragraph_is_bounded_and_deterministic() -> None:
    text = " ".join(f"مصطلح{i}-technical" for i in range(80))
    chunker = RagTextChunker(chunk_size=90, chunk_overlap=15)
    parsed = ParsedDocument(text=text)
    record = _record()

    first = chunker.split(record, parsed)
    second = chunker.split(record, parsed)

    assert first == second
    assert len(first) > 1
    assert all(0 < len(chunk.text) <= 90 for chunk in first)
    assert set(text.split()) <= set(" ".join(chunk.text for chunk in first).split())


def test_empty_pages_and_documents_produce_no_chunks() -> None:
    chunker = RagTextChunker(chunk_size=100, chunk_overlap=10)

    assert chunker.split(_record(), ParsedDocument(text="")) == []
    assert chunker.split(
        _record(PDF_CONTENT_TYPE),
        ParsedDocument(
            text=" \n ",
            pages=(ParsedPage("", 1), ParsedPage(" \n", 2)),
        ),
    ) == []


@pytest.mark.parametrize(
    ("chunk_size", "chunk_overlap", "message"),
    [
        (0, 0, "greater than zero"),
        (100, -1, "cannot be negative"),
        (100, 100, "smaller than chunk size"),
        (100, 101, "smaller than chunk size"),
        (True, 0, "must be an integer"),
    ],
)
def test_invalid_chunk_configuration_is_rejected(
    chunk_size: int,
    chunk_overlap: int,
    message: str,
) -> None:
    with pytest.raises(InvalidChunkConfigurationError, match=message):
        RagTextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
