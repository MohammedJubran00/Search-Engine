"""Pydantic schemas for authenticated chat persistence.

Why it exists: `/chat` must not take `user_id` or treat `session_id` as
identity. The body is only the question and an optional conversation id.

Responsibility: request/response shapes. No SQL, no JWT, no LangGraph.
"""

import uuid
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

from src.search_engine.core.config import settings
from src.search_engine.research.presentation import AnswerPresentation

ChatMode = Literal["general", "documents"]
ResearchMode = Literal["standard", "deep"]
AnswerStatusValue = Literal["answered", "insufficient_evidence"]


def _require_http_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Web citation URL must use HTTP or HTTPS.")
    return value


class ChatCitation(BaseModel):
    """Validated source attribution safe to return to the authenticated user."""

    label: str
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    filename: str
    page_number: int | None = None
    evidence_excerpt: str
    origin: Literal["document"] = "document"


class WebCitation(BaseModel):
    """Validated provenance returned by the web-search tool."""

    origin: Literal["web"] = "web"
    title: str
    url: str
    evidence_excerpt: str = ""
    published_date: str | None = None
    retrieved_at: str | None = None
    publisher: str | None = None
    author: str | None = None
    source_type: str = "unspecified"
    quality_notes: list[str] = Field(default_factory=list)

    @field_validator("url")
    @classmethod
    def validate_public_url(cls, value: str) -> str:
        return _require_http_url(value)


class ResearchSummary(BaseModel):
    search_count: int = Field(ge=0)
    search_failures: int = Field(ge=0)
    termination_reason: str
    tavily_seconds: float = Field(default=0.0, ge=0)


class EvidenceClaim(BaseModel):
    value: str
    currency: str | None = None
    unit: str | None = None
    years: list[str] = Field(default_factory=list)
    source_title: str | None = None
    source_url: str
    evidence_excerpt: str

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        return _require_http_url(value)


class EvidenceRelationship(BaseModel):
    status: Literal[
        "confirmed_agreement",
        "potential_conflict",
        "different_time_periods",
        "insufficient_context",
    ]
    reason: str
    shared_context_terms: list[str] = Field(default_factory=list)
    claims: list[EvidenceClaim] = Field(min_length=2, max_length=2)


class ChatAttachment(BaseModel):
    """Safe document metadata attached to a persisted user turn."""

    document_id: uuid.UUID
    filename: str
    content_type: str
    file_size: int
    processing_status: str
    indexing_status: str


class ChatRequest(BaseModel):
    """Body for `POST /chat` and `POST /chat/stream`."""

    query: str = Field(max_length=settings.rag_retrieval_max_query_characters)
    conversation_id: uuid.UUID | None = None
    mode: ChatMode = "general"
    research_mode: ResearchMode = "standard"
    document_ids: list[uuid.UUID] = Field(
        default_factory=list,
        max_length=settings.rag_chat_max_document_selection,
    )

    @model_validator(mode="after")
    def validate_document_scope(self) -> "ChatRequest":
        self.document_ids = list(dict.fromkeys(self.document_ids))
        if self.mode == "general" and self.document_ids:
            raise ValueError("document_ids may only be used in documents mode")
        if self.mode == "documents" and self.research_mode != "standard":
            raise ValueError("deep research is available only in general mode")
        return self


class ChatResponse(BaseModel):
    """JSON body for a completed non-streaming chat turn."""

    answer: str
    conversation_id: uuid.UUID
    mode: ChatMode = "general"
    status: AnswerStatusValue | None = None
    citations: list[ChatCitation] = Field(default_factory=list)
    web_citations: list[WebCitation] = Field(default_factory=list)
    research_plan: list[str] = Field(default_factory=list)
    research_summary: ResearchSummary | None = None
    evidence_conflicts: list[EvidenceRelationship] = Field(default_factory=list)
    presentation: AnswerPresentation = Field(
        default_factory=lambda: AnswerPresentation(type="standard")
    )


class ConversationMessageOut(BaseModel):
    """One persisted turn returned to the Chat UI."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    role: str
    content: str
    mode: ChatMode = "general"
    status: AnswerStatusValue | None = None
    citations: list[ChatCitation] = Field(default_factory=list)
    web_citations: list[WebCitation] = Field(default_factory=list)
    research_plan: list[str] = Field(default_factory=list)
    research_summary: ResearchSummary | None = None
    evidence_conflicts: list[EvidenceRelationship] = Field(default_factory=list)
    presentation: AnswerPresentation = Field(
        default_factory=lambda: AnswerPresentation(type="standard")
    )
    document_ids: list[uuid.UUID] = Field(default_factory=list)
    attachments: list[ChatAttachment] = Field(default_factory=list)


class LatestConversationResponse(BaseModel):
    """The current user's most recently updated thread, or an empty chat."""

    conversation_id: uuid.UUID | None = None
    messages: list[ConversationMessageOut] = Field(default_factory=list)
