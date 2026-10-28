"""Contracts for the future document-retrieval pipeline.

This package is intentionally not wired into the HTTP or chat layers yet.
"""

from src.search_engine.rag.chunking import (
    InvalidChunkConfigurationError,
    RagTextChunker,
)
from src.search_engine.rag.contracts import (
    DocumentParser,
    DocumentRecord,
    EmbeddingProvider,
    ParsedDocument,
    ParsedPage,
    RetrievedChunk,
    TextChunk,
    TextChunker,
    VectorStore,
)
from src.search_engine.rag.embeddings import (
    EmbeddingProviderError,
    EmbeddingRateLimitError,
    GeminiEmbeddingProvider,
    InvalidEmbeddingError,
)
from src.search_engine.rag.answering import (
    AnswerStatus,
    RagAnswerResult,
    SourceReference,
)

__all__ = [
    "DocumentParser",
    "DocumentRecord",
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingRateLimitError",
    "GeminiEmbeddingProvider",
    "InvalidChunkConfigurationError",
    "InvalidEmbeddingError",
    "ParsedDocument",
    "ParsedPage",
    "RagTextChunker",
    "RetrievedChunk",
    "TextChunk",
    "TextChunker",
    "VectorStore",
    "AnswerStatus",
    "RagAnswerResult",
    "SourceReference",
]
