"""Local-only CLI for a real, quota-consuming Phase 6 RAG smoke test."""

import argparse
import asyncio
import json
import uuid
from dataclasses import asdict

from src.search_engine.core.config import settings
from src.search_engine.database.database import SessionLocal
from src.search_engine.services.rag_answer_service import RagAnswerService


async def _ask(args: argparse.Namespace) -> None:
    async with SessionLocal() as session:
        result = await RagAnswerService(session).answer(
            user_id=args.user_id,
            question=args.question,
            top_k=args.top_k,
            document_ids=args.document_id,
            min_similarity=args.min_similarity,
        )
    payload = asdict(result)
    payload["status"] = result.status.value
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Ask a question over owned indexed documents. This makes real Gemini "
            "embedding, token-counting, and generation requests and may consume quota."
        )
    )
    parser.add_argument("--user-id", required=True, type=uuid.UUID)
    parser.add_argument("--document-id", action="append", type=uuid.UUID)
    parser.add_argument("--question", required=True)
    parser.add_argument("--top-k", type=int, default=settings.rag_retrieval_top_k)
    parser.add_argument("--min-similarity", type=float)
    asyncio.run(_ask(parser.parse_args()))


if __name__ == "__main__":
    main()
