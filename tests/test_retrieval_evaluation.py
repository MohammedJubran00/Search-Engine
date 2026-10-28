"""Golden-dataset validation and retrieval metric tests."""

import uuid
from pathlib import Path

import pytest

from src.search_engine.rag.contracts import RetrievedChunk
from src.search_engine.rag.evaluation import (
    GoldenDatasetError,
    aggregate_metrics,
    evaluate_ranked_results,
    load_golden_dataset,
)

FIXTURE = Path(__file__).parent / "fixtures" / "retrieval_golden.jsonl"


def _result(
    *,
    chunk_id: str,
    document_id: str,
    rank: int,
    page_number: int | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.UUID(chunk_id),
        document_id=uuid.UUID(document_id),
        filename="fixture.txt",
        chunk_index=rank - 1,
        text="labeled evidence",
        page_number=page_number,
        char_start=0,
        char_end=16,
        cosine_distance=0.1 * rank,
        cosine_similarity=1.0 - 0.1 * rank,
        rank=rank,
    )


def test_fixed_golden_dataset_covers_required_quality_scenarios() -> None:
    cases = load_golden_dataset(FIXTURE)

    assert len(cases) == 10
    assert {case.case_id for case in cases} >= {
        "exact-terminology",
        "paraphrased-goal",
        "arabic-query-english-source",
        "english-query-arabic-source",
        "multi-chunk-evidence",
        "absent-answer",
        "date-and-number",
        "similar-documents",
        "incomplete-indexing",
    }
    assert any(not case.answerable for case in cases)
    assert all(case.expected_evidence for case in cases if case.answerable)


def test_hit_recall_precision_and_reciprocal_rank_use_explicit_chunk_labels() -> None:
    case = next(
        item for item in load_golden_dataset(FIXTURE) if item.case_id == "multi-chunk-evidence"
    )
    results = [
        _result(
            chunk_id="dddddddd-dddd-dddd-dddd-ddddddddddd1",
            document_id="22222222-2222-2222-2222-222222222222",
            rank=1,
        ),
        _result(
            chunk_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2",
            document_id="11111111-1111-1111-1111-111111111111",
            rank=2,
        ),
        _result(
            chunk_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
            document_id="11111111-1111-1111-1111-111111111111",
            rank=3,
        ),
    ]

    at_two = evaluate_ranked_results(case, results, k=2)
    assert at_two.hit_at_k == 1.0
    assert at_two.recall_at_k == 0.5
    assert at_two.precision_at_k == 0.5
    assert at_two.reciprocal_rank == 0.5

    at_three = evaluate_ranked_results(case, results, k=3)
    assert at_three.recall_at_k == 1.0
    assert at_three.precision_at_k == pytest.approx(2 / 3)


def test_page_labels_and_unanswerable_false_positives_are_explicit() -> None:
    cases = load_golden_dataset(FIXTURE)
    page_case = next(item for item in cases if item.case_id == "page-label")
    page_result = _result(
        chunk_id="eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee1",
        document_id="11111111-1111-1111-1111-111111111111",
        rank=1,
        page_number=3,
    )
    assert evaluate_ranked_results(page_case, [page_result], k=1).recall_at_k == 1.0

    absent = next(item for item in cases if item.case_id == "absent-answer")
    false_positive = evaluate_ranked_results(absent, [page_result], k=1)
    clean_empty = evaluate_ranked_results(absent, [], k=1)
    assert false_positive.hit_at_k is None
    assert false_positive.false_positive_count == 1
    assert false_positive.precision_at_k == 0.0
    assert clean_empty.false_positive_count == 0
    assert clean_empty.precision_at_k == 1.0

    summary = aggregate_metrics([false_positive, clean_empty])
    assert summary.answerable_case_count == 0
    assert summary.false_positive_count == 1
    assert summary.precision_at_k == 0.5


def test_invalid_or_unlabeled_golden_data_is_rejected(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text(
        '{"id":"missing-labels","question":"Q?","expected_document_ids":[],"answerable":true}\n',
        encoding="utf-8",
    )

    with pytest.raises(GoldenDatasetError):
        load_golden_dataset(invalid)
