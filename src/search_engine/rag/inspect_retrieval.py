"""Local-only semantic retrieval inspection using real indexed documents."""

import argparse
import asyncio
import uuid

from src.search_engine.core.config import settings
from src.search_engine.database.database import SessionLocal
from src.search_engine.services.retrieval_service import SemanticRetrievalService

_DEFAULT_PREVIEW_CHARACTERS = 180


async def _inspect(args: argparse.Namespace) -> None:
    async with SessionLocal() as session:
        results = await SemanticRetrievalService(session).retrieve(
            user_id=args.user_id,
            query=args.query,
            top_k=args.top_k,
            document_ids=args.document_id,
            min_similarity=args.min_similarity,
        )

    if not results:
        print("No matching indexed chunks were found.")
        return
    for result in results:
        page = result.page_number if result.page_number is not None else "n/a"
        character_range = (
            f"{result.char_start}:{result.char_end}"
            if result.char_start is not None
            else "n/a"
        )
        print(
            f"rank={result.rank} similarity={result.cosine_similarity:.6f} "
            f"distance={result.cosine_distance:.6f} document={result.document_id} "
            f"filename={result.filename!r} page={page} "
            f"chunk={result.chunk_index} range={character_range}"
        )
        if args.show_text:
            print(result.text)
        else:
            preview = " ".join(result.text.split())[: args.preview_characters]
            print(f"  preview={preview!r}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect user-scoped semantic retrieval. This may call Gemini and consume "
            "API quota; it does not generate answers."
        )
    )
    parser.add_argument("--user-id", required=True, type=uuid.UUID)
    parser.add_argument("--document-id", action="append", type=uuid.UUID)
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=settings.rag_retrieval_top_k)
    parser.add_argument("--min-similarity", type=float)
    parser.add_argument(
        "--preview-characters",
        type=int,
        default=_DEFAULT_PREVIEW_CHARACTERS,
    )
    parser.add_argument(
        "--show-text",
        action="store_true",
        help="Print complete retrieved chunks; use only with trusted local content.",
    )
    asyncio.run(_inspect(parser.parse_args()))


if __name__ == "__main__":
    main()
