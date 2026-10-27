"""Small boundary contracts for RAG components that will be implemented later.

The existing application has no reusable document-ingestion or vector-search
abstractions. These protocols define the service/repository boundary without
choosing orchestration logic or coupling the current chat flow to RAG.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    """Identity and ownership metadata for one uploaded document."""

    id: uuid.UUID
    user_id: uuid.UUID
    filename: str
    content_type: str
    storage_path: Path


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Text extracted from a validated upload."""

    text: str
    metadata: Mapping[str, str | int | float | bool] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TextChunk:
    """A stable, ordered piece of an owned document."""

    document_id: uuid.UUID
    user_id: uuid.UUID
    index: int
    text: str
    metadata: Mapping[str, str | int | float | bool] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """A chunk returned by similarity search, with distance/score metadata."""

    chunk: TextChunk
    score: float


class DocumentParser(Protocol):
    """Extract text from a stored, already validated PDF, DOCX, or TXT file."""

    def parse(self, path: Path, content_type: str) -> ParsedDocument: ...


class TextChunker(Protocol):
    """Split parsed text using configured size and overlap values."""

    def split(self, document: DocumentRecord, parsed: ParsedDocument) -> list[TextChunk]: ...


class EmbeddingProvider(Protocol):
    """Generate Gemini embeddings for document chunks and retrieval queries."""

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class VectorStore(Protocol):
    """Persist and retrieve vectors while enforcing user ownership."""

    async def upsert(
        self,
        chunks: Sequence[TextChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> None: ...

    async def search(
        self,
        *,
        user_id: uuid.UUID,
        query_embedding: Sequence[float],
        limit: int,
        document_ids: Sequence[uuid.UUID] | None = None,
    ) -> list[RetrievedChunk]: ...
