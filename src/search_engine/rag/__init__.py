"""Contracts for the future document-retrieval pipeline.

This package is intentionally not wired into the HTTP or chat layers yet.
"""

from src.search_engine.rag.contracts import (
    DocumentParser,
    DocumentRecord,
    EmbeddingProvider,
    ParsedDocument,
    RetrievedChunk,
    TextChunk,
    TextChunker,
    VectorStore,
)

__all__ = [
    "DocumentParser",
    "DocumentRecord",
    "EmbeddingProvider",
    "ParsedDocument",
    "RetrievedChunk",
    "TextChunk",
    "TextChunker",
    "VectorStore",
]
