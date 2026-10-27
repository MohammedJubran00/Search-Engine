"""Structure-aware, deterministic text chunking for parsed RAG documents.

Why it exists: the RAG contracts define a chunking boundary, but parsing is
the last implemented production step. This module stays inside the RAG layer
and converts parser output into citation-ready chunks without persistence,
embedding calls, or chat integration.
"""

from collections.abc import Iterable

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.search_engine.rag.contracts import (
    DocumentRecord,
    ParsedDocument,
    ParsedPage,
    TextChunk,
)

# Ordered from strongest structural boundary to the character fallback.
# Punctuation includes common English and Arabic sentence separators.
STRUCTURE_SEPARATORS = (
    "\n\n",
    "\n",
    ". ",
    "؟ ",
    "! ",
    "? ",
    "؛ ",
    "، ",
    " ",
    "",
)


class InvalidChunkConfigurationError(ValueError):
    """Raised when character chunk size and overlap cannot be applied safely."""


class RagTextChunker:
    """Split parsed pages into ordered, character-bounded citation chunks.

    ``chunk_size`` and ``chunk_overlap`` are measured in Python characters
    (Unicode code points), not tokens or UTF-8 bytes.
    """

    def __init__(self, *, chunk_size: int, chunk_overlap: int) -> None:
        _validate_configuration(chunk_size, chunk_overlap)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=list(STRUCTURE_SEPARATORS),
            keep_separator="end",
            add_start_index=True,
            strip_whitespace=True,
            length_function=len,
        )

    def split(
        self,
        document: DocumentRecord,
        parsed: ParsedDocument,
    ) -> list[TextChunk]:
        """Return zero-based chunks in source order without crossing pages."""
        chunks: list[TextChunk] = []
        for page in _source_pages(parsed):
            if not page.text.strip():
                continue
            for split_document in self._splitter.create_documents([page.text]):
                text = split_document.page_content
                if not text:
                    continue
                start = int(split_document.metadata.get("start_index", 0))
                metadata: dict[str, str | int | float | bool] = {
                    "source_filename": document.filename,
                    "content_type": document.content_type,
                    "char_start": start,
                    "char_end": start + len(text),
                }
                if page.page_number is not None:
                    metadata["page_number"] = page.page_number
                chunks.append(
                    TextChunk(
                        document_id=document.id,
                        user_id=document.user_id,
                        index=len(chunks),
                        text=text,
                        metadata=metadata,
                    )
                )
        return chunks


def _source_pages(parsed: ParsedDocument) -> Iterable[ParsedPage]:
    if parsed.pages:
        return parsed.pages
    if parsed.text:
        return (ParsedPage(text=parsed.text),)
    return ()


def _validate_configuration(chunk_size: int, chunk_overlap: int) -> None:
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int):
        raise InvalidChunkConfigurationError("Chunk size must be an integer.")
    if isinstance(chunk_overlap, bool) or not isinstance(chunk_overlap, int):
        raise InvalidChunkConfigurationError("Chunk overlap must be an integer.")
    if chunk_size <= 0:
        raise InvalidChunkConfigurationError("Chunk size must be greater than zero.")
    if chunk_overlap < 0:
        raise InvalidChunkConfigurationError("Chunk overlap cannot be negative.")
    if chunk_overlap >= chunk_size:
        raise InvalidChunkConfigurationError(
            "Chunk overlap must be smaller than chunk size."
        )
