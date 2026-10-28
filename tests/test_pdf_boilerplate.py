"""Conservative repeated PDF header/footer removal regression tests."""

import uuid
from pathlib import Path

import pymupdf

from src.search_engine.rag.chunking import RagTextChunker
from src.search_engine.rag.contracts import DocumentRecord, RetrievedChunk
from src.search_engine.rag.evaluation import GoldenQuery, evaluate_ranked_results
from src.search_engine.rag.parsers import PDF_CONTENT_TYPE, RagDocumentParser


def _boilerplate_pdf(page_count: int, *, unique_first_header: bool = True) -> bytes:
    document = pymupdf.open()
    for page_number in range(1, page_count + 1):
        page = document.new_page()
        header = (
            "2026 Goals"
            if unique_first_header and page_number == 1
            else "BETHLEHEM UNIVERSITY | SOFTWARE ENGINEERING"
        )
        page.insert_text((36, 30), header)
        page.insert_text((36, 62), f"Section {page_number}")
        page.insert_text((72, 130), "Scope")
        page.insert_text(
            (72, 160),
            f"Milestone {page_number}: preserve 2026-10-{20 + page_number} and value {page_number * 25}%.",
        )
        page.insert_text((72, 815), f"AI Restaurant Operations System • {page_number}")
    data = document.tobytes()
    document.close()
    return data


def _parser() -> RagDocumentParser:
    return RagDocumentParser(max_docx_uncompressed_bytes=1024 * 1024)


def test_repeated_page_edge_boilerplate_is_removed_without_global_length_filter(
    tmp_path: Path,
) -> None:
    path = tmp_path / "proposal.pdf"
    path.write_bytes(_boilerplate_pdf(4))

    parsed = _parser().parse(path, PDF_CONTENT_TYPE)

    assert [page.page_number for page in parsed.pages] == [1, 2, 3, 4]
    assert parsed.metadata["removed_boilerplate_patterns"] == 2
    assert parsed.metadata["removed_boilerplate_lines"] == 7
    assert "BETHLEHEM UNIVERSITY" not in parsed.text
    assert "AI Restaurant Operations System" not in parsed.text
    assert "2026 Goals" in parsed.pages[0].text
    for page_number, page in enumerate(parsed.pages, start=1):
        assert f"Section {page_number}" in page.text
        assert "Scope" in page.text
        assert f"2026-10-{20 + page_number}" in page.text
        assert f"value {page_number * 25}%" in page.text

    record = DocumentRecord(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="proposal.pdf",
        content_type=PDF_CONTENT_TYPE,
        storage_path=path,
    )
    chunks = RagTextChunker(chunk_size=90, chunk_overlap=15).split(record, parsed)
    combined = "\n".join(chunk.text for chunk in chunks)
    assert "Scope" in combined
    assert "2026 Goals" in combined
    assert "AI Restaurant Operations System" not in combined
    assert {chunk.metadata["page_number"] for chunk in chunks} == {1, 2, 3, 4}


def test_two_page_repetition_is_not_enough_to_remove_content(tmp_path: Path) -> None:
    path = tmp_path / "short.pdf"
    path.write_bytes(_boilerplate_pdf(2, unique_first_header=False))

    parsed = _parser().parse(path, PDF_CONTENT_TYPE)

    assert parsed.metadata["removed_boilerplate_patterns"] == 0
    assert parsed.metadata["removed_boilerplate_lines"] == 0
    assert parsed.text.count("BETHLEHEM UNIVERSITY") == 2
    assert parsed.text.count("AI Restaurant Operations System") == 2


def test_reported_query_labels_improve_when_verified_footer_chunks_are_excluded() -> None:
    document_id = uuid.uuid4()
    relevant_ids = (uuid.uuid4(), uuid.uuid4())
    case = GoldenQuery(
        case_id="restaurant-goals",
        question="What are the main goals of the restaurant AI project?",
        expected_document_ids=(document_id,),
        relevant_chunk_ids=relevant_ids,
        relevant_pages=(),
        expected_evidence=(
            "Proposed Application / Service / Solution",
            "Expected value and boundaries",
        ),
        answerable=True,
    )
    texts = (
        "Proposed Application / Service / Solution",
        "Expected value and boundaries",
        "AI Restaurant Operations System • 2",
        "AI Restaurant Operations System • 8",
        "AI Restaurant Operations System • 3",
    )
    similarities = (0.737768, 0.731102, 0.719660, 0.712557, 0.706473)
    before = [
        RetrievedChunk(
            chunk_id=(relevant_ids[index] if index < 2 else uuid.uuid4()),
            document_id=document_id,
            filename="proposal.pdf",
            chunk_index=index,
            text=text,
            page_number=index + 2,
            char_start=0,
            char_end=len(text),
            cosine_distance=1.0 - similarities[index],
            cosine_similarity=similarities[index],
            rank=index + 1,
        )
        for index, text in enumerate(texts)
    ]
    after = [
        result
        for result in before
        if not result.text.startswith("AI Restaurant Operations System")
    ]

    before_metrics = evaluate_ranked_results(case, before, k=5)
    after_metrics = evaluate_ranked_results(case, after, k=5)
    assert before_metrics.hit_at_k == after_metrics.hit_at_k == 1.0
    assert before_metrics.recall_at_k == after_metrics.recall_at_k == 1.0
    assert before_metrics.precision_at_k == 0.4
    assert after_metrics.precision_at_k == 1.0
