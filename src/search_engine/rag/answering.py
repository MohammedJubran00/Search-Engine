"""Structured contracts shared by RAG context and answer generation."""

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AnswerStatus(StrEnum):
    """Whether the available document evidence supports an answer."""

    ANSWERED = "answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True, slots=True)
class SourceReference:
    """Authenticated retrieval evidence exposed with a stable source label."""

    label: str
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    filename: str
    page_number: int | None
    rank: int
    cosine_similarity: float
    evidence_excerpt: str


@dataclass(frozen=True, slots=True)
class BuiltContext:
    """Bounded prompt context and the exact sources it contains."""

    text: str
    sources: tuple[SourceReference, ...]
    token_count: int
    available_tokens: int
    duplicate_chunks_skipped: int = 0
    truncated_source_count: int = 0


@dataclass(frozen=True, slots=True)
class GenerationDraft:
    """Validated shape returned by a generation provider before source mapping."""

    status: AnswerStatus
    answer: str
    citation_labels: tuple[str, ...] = ()
    usage: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RagAnswerResult:
    """Final answer with citations mapped only to authenticated retrieval rows."""

    status: AnswerStatus
    answer: str
    citations: tuple[SourceReference, ...]
    sources: tuple[SourceReference, ...]
    retrieved_chunk_count: int
    context_token_count: int
    generation_seconds: float | None = None
    usage: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
