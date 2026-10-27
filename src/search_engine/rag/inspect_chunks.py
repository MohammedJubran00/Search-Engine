"""Local CLI for inspecting parser and chunker output without persistence."""

import argparse
import uuid
from pathlib import Path

from src.search_engine.core.config import settings
from src.search_engine.rag.chunking import RagTextChunker
from src.search_engine.rag.contracts import DocumentRecord
from src.search_engine.rag.parsers import (
    DOCX_CONTENT_TYPE,
    PDF_CONTENT_TYPE,
    TXT_CONTENT_TYPE,
    RagDocumentParser,
)

_CONTENT_TYPES = {
    ".pdf": PDF_CONTENT_TYPE,
    ".docx": DOCX_CONTENT_TYPE,
    ".txt": TXT_CONTENT_TYPE,
}
_DEFAULT_PREVIEW_CHARACTERS = 120
_DEFAULT_SHORT_CHUNK_CHARACTERS = 50


def main() -> None:
    args = _arguments()
    path = args.path.resolve()
    content_type = _CONTENT_TYPES.get(path.suffix.lower())
    if content_type is None:
        raise SystemExit("Only local PDF, DOCX, and TXT files are supported.")
    if not path.is_file():
        raise SystemExit(f"File does not exist: {path}")

    parser = RagDocumentParser(
        max_docx_uncompressed_bytes=settings.rag_max_docx_uncompressed_bytes
    )
    parsed = parser.parse(path, content_type)
    document = DocumentRecord(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename=path.name,
        content_type=content_type,
        storage_path=path,
    )
    chunker = RagTextChunker(
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    chunks = chunker.split(document, parsed)

    print(
        f"Parsed {len(parsed.text)} characters across {len(parsed.pages)} source page(s); "
        f"generated {len(chunks)} chunk(s)."
    )
    for chunk in chunks:
        page = chunk.metadata.get("page_number", "n/a")
        flags = _quality_flags(
            len(chunk.text),
            short_threshold=args.short_threshold,
            chunk_size=args.chunk_size,
        )
        flag_text = f" [{', '.join(flags)}]" if flags else ""
        print(
            f"chunk={chunk.index} length={len(chunk.text)} page={page} "
            f"range={chunk.metadata['char_start']}:{chunk.metadata['char_end']}"
            f"{flag_text}"
        )
        if args.show_text:
            print(chunk.text)
        else:
            preview = " ".join(chunk.text.split())[: args.preview_characters]
            print(f"  preview={preview!r}")

    if not chunks:
        print("WARNING: no non-whitespace chunks were generated.")
    if args.show_text:
        print("\n--- Extracted text ---")
        print(parsed.text)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect local RAG parsing and chunking without API calls or storage.",
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--chunk-size", type=int, default=settings.rag_chunk_size)
    parser.add_argument("--chunk-overlap", type=int, default=settings.rag_chunk_overlap)
    parser.add_argument(
        "--preview-characters",
        type=int,
        default=_DEFAULT_PREVIEW_CHARACTERS,
    )
    parser.add_argument(
        "--short-threshold",
        type=int,
        default=_DEFAULT_SHORT_CHUNK_CHARACTERS,
    )
    parser.add_argument(
        "--show-text",
        action="store_true",
        help="Print full chunks and extracted text; use only for trusted local documents.",
    )
    return parser.parse_args()


def _quality_flags(
    length: int,
    *,
    short_threshold: int,
    chunk_size: int,
) -> list[str]:
    flags: list[str] = []
    if length == 0:
        flags.append("EMPTY")
    elif length < short_threshold:
        flags.append("SHORT")
    if length > chunk_size:
        flags.append("OVER_LIMIT")
    return flags


if __name__ == "__main__":
    main()
