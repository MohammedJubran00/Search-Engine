"""Ground-truth retrieval metrics for fixed, human-labeled golden datasets."""

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean

from src.search_engine.rag.contracts import RetrievedChunk


class GoldenDatasetError(ValueError):
    """Raised when evaluation labels are missing or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class GoldenQuery:
    """One human-labeled retrieval question and its source evidence."""

    case_id: str
    question: str
    expected_document_ids: tuple[uuid.UUID, ...]
    relevant_chunk_ids: tuple[uuid.UUID, ...]
    relevant_pages: tuple[tuple[uuid.UUID, int], ...]
    expected_evidence: tuple[str, ...]
    answerable: bool


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    """Metrics for one query at K; similarity alone is not a relevance label."""

    case_id: str
    k: int
    hit_at_k: float | None
    recall_at_k: float | None
    precision_at_k: float
    reciprocal_rank: float | None
    false_positive_count: int
    retrieved_count: int


@dataclass(frozen=True, slots=True)
class AggregateRetrievalMetrics:
    """Macro averages plus explicit unanswerable-query false positives."""

    case_count: int
    answerable_case_count: int
    hit_at_k: float | None
    recall_at_k: float | None
    precision_at_k: float
    mrr: float | None
    false_positive_count: int


def load_golden_dataset(path: Path) -> list[GoldenQuery]:
    """Load JSON Lines labels without inferring or fabricating relevance."""
    cases: list[GoldenQuery] = []
    seen_ids: set[str] = set()
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                case = _parse_case(payload)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise GoldenDatasetError(
                    f"Invalid golden dataset entry on line {line_number}."
                ) from exc
            if case.case_id in seen_ids:
                raise GoldenDatasetError(f"Duplicate case id: {case.case_id}")
            seen_ids.add(case.case_id)
            cases.append(case)
    if not cases:
        raise GoldenDatasetError("Golden dataset must contain at least one case.")
    return cases


def evaluate_ranked_results(
    case: GoldenQuery,
    results: list[RetrievedChunk],
    *,
    k: int,
) -> RetrievalMetrics:
    """Evaluate already-ranked results using only explicit golden labels."""
    if k <= 0:
        raise GoldenDatasetError("Evaluation K must be positive.")
    ranked = results[:k]
    relevant_keys = _relevant_keys(case)
    matched: set[tuple[str, object]] = set()
    first_relevant_rank: int | None = None
    relevant_result_count = 0
    for rank, result in enumerate(ranked, start=1):
        key = _result_relevance_key(case, result)
        if key is not None:
            matched.add(key)
            relevant_result_count += 1
            if first_relevant_rank is None:
                first_relevant_rank = rank

    if case.answerable:
        hit = 1.0 if matched else 0.0
        recall = len(matched) / len(relevant_keys)
        reciprocal_rank = 0.0 if first_relevant_rank is None else 1.0 / first_relevant_rank
        false_positives = 0
    else:
        hit = None
        recall = None
        reciprocal_rank = None
        false_positives = len(ranked)

    precision = (
        relevant_result_count / len(ranked)
        if ranked
        else (0.0 if case.answerable else 1.0)
    )
    return RetrievalMetrics(
        case_id=case.case_id,
        k=k,
        hit_at_k=hit,
        recall_at_k=recall,
        precision_at_k=precision,
        reciprocal_rank=reciprocal_rank,
        false_positive_count=false_positives,
        retrieved_count=len(ranked),
    )


def aggregate_metrics(metrics: list[RetrievalMetrics]) -> AggregateRetrievalMetrics:
    if not metrics:
        raise GoldenDatasetError("At least one evaluated case is required.")
    answerable = [metric for metric in metrics if metric.hit_at_k is not None]
    return AggregateRetrievalMetrics(
        case_count=len(metrics),
        answerable_case_count=len(answerable),
        hit_at_k=_optional_mean([metric.hit_at_k for metric in answerable]),
        recall_at_k=_optional_mean([metric.recall_at_k for metric in answerable]),
        precision_at_k=fmean(metric.precision_at_k for metric in metrics),
        mrr=_optional_mean([metric.reciprocal_rank for metric in answerable]),
        false_positive_count=sum(metric.false_positive_count for metric in metrics),
    )


def _parse_case(payload: object) -> GoldenQuery:
    if not isinstance(payload, dict):
        raise GoldenDatasetError("Golden entry must be an object.")
    case_id = str(payload["id"]).strip()
    question = str(payload["question"]).strip()
    answerable = payload["answerable"]
    if not case_id or not question or not isinstance(answerable, bool):
        raise GoldenDatasetError("Golden id, question, and answerable are required.")
    document_ids = tuple(uuid.UUID(value) for value in payload["expected_document_ids"])
    chunk_ids = tuple(uuid.UUID(value) for value in payload.get("relevant_chunk_ids", []))
    pages = tuple(
        (uuid.UUID(item["document_id"]), int(item["page_number"]))
        for item in payload.get("relevant_pages", [])
    )
    evidence = tuple(str(value) for value in payload.get("expected_evidence", []))
    if any(page < 1 for _, page in pages):
        raise GoldenDatasetError("Relevant page numbers must be positive.")
    if answerable and not (chunk_ids or pages or document_ids):
        raise GoldenDatasetError("Answerable cases require explicit relevance labels.")
    if answerable and not evidence:
        raise GoldenDatasetError("Answerable cases require expected evidence.")
    if not answerable and (chunk_ids or pages):
        raise GoldenDatasetError("Unanswerable cases cannot label chunks or pages.")
    return GoldenQuery(
        case_id=case_id,
        question=question,
        expected_document_ids=document_ids,
        relevant_chunk_ids=chunk_ids,
        relevant_pages=pages,
        expected_evidence=evidence,
        answerable=answerable,
    )


def _relevant_keys(case: GoldenQuery) -> set[tuple[str, object]]:
    if case.relevant_chunk_ids:
        return {("chunk", value) for value in case.relevant_chunk_ids}
    if case.relevant_pages:
        return {("page", value) for value in case.relevant_pages}
    if case.answerable:
        return {("document", value) for value in case.expected_document_ids}
    return set()


def _result_relevance_key(
    case: GoldenQuery,
    result: RetrievedChunk,
) -> tuple[str, object] | None:
    relevant = _relevant_keys(case)
    candidates = (
        ("chunk", result.chunk_id),
        ("page", (result.document_id, result.page_number)),
        ("document", result.document_id),
    )
    return next((candidate for candidate in candidates if candidate in relevant), None)


def _optional_mean(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return fmean(present) if present else None
