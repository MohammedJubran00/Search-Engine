"""Local-only command for explicitly indexing one existing owned document."""

import argparse
import asyncio
import uuid

from src.search_engine.database.database import SessionLocal
from src.search_engine.services.document_indexing_service import DocumentIndexingService


async def _index(
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    supersede_processing: bool,
) -> None:
    async with SessionLocal() as session:
        result = await DocumentIndexingService(session).index(
            document_id=document_id,
            user_id=user_id,
            supersede_processing=supersede_processing,
        )
    print(
        f"Indexed document {result.document_id} generation={result.generation} "
        f"chunks={result.chunk_count}."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Index one existing authorized document using Gemini. This consumes API "
            "quota and requires the Phase 4 migration."
        )
    )
    parser.add_argument("document_id", type=uuid.UUID)
    parser.add_argument("user_id", type=uuid.UUID)
    parser.add_argument(
        "--supersede-processing",
        action="store_true",
        help=(
            "Recover an abandoned processing claim by advancing its generation; "
            "use only after confirming the prior worker is stale."
        ),
    )
    args = parser.parse_args()
    asyncio.run(
        _index(
            args.document_id,
            args.user_id,
            supersede_processing=args.supersede_processing,
        )
    )


if __name__ == "__main__":
    main()
