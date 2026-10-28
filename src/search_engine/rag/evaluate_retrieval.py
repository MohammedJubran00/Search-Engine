"""Local-only golden-dataset evaluation across retrieval configurations."""

import argparse
import asyncio
import uuid
from pathlib import Path

from src.search_engine.core.config import settings
from src.search_engine.database.database import SessionLocal
from src.search_engine.rag.evaluation import (
    aggregate_metrics,
    evaluate_ranked_results,
    load_golden_dataset,
)
from src.search_engine.services.retrieval_service import (
    RetrievalError,
    SemanticRetrievalService,
)


async def _evaluate(args: argparse.Namespace) -> None:
    cases = load_golden_dataset(args.dataset)
    thresholds = args.min_similarity or [None]
    async with SessionLocal() as session:
        service = SemanticRetrievalService(session)
        for top_k in args.top_k:
            for threshold in thresholds:
                evaluated = []
                failures = 0
                for case in cases:
                    try:
                        results = await service.retrieve(
                            user_id=args.user_id,
                            query=case.question,
                            top_k=top_k,
                            min_similarity=threshold,
                        )
                    except RetrievalError as exc:
                        failures += 1
                        print(
                            f"case={case.case_id} retrieval_failure={type(exc).__name__}"
                        )
                        continue
                    metric = evaluate_ranked_results(case, results, k=top_k)
                    evaluated.append(metric)
                    print(
                        f"case={case.case_id} hit={metric.hit_at_k} "
                        f"recall={metric.recall_at_k} precision={metric.precision_at_k:.4f} "
                        f"rr={metric.reciprocal_rank} "
                        f"false_positives={metric.false_positive_count}"
                    )
                label = threshold if threshold is not None else "none"
                if evaluated:
                    summary = aggregate_metrics(evaluated)
                    print(
                        f"configuration top_k={top_k} min_similarity={label} "
                        f"hit={summary.hit_at_k} recall={summary.recall_at_k} "
                        f"precision={summary.precision_at_k:.4f} mrr={summary.mrr} "
                        f"false_positives={summary.false_positive_count} "
                        f"retrieval_failures={failures}"
                    )
                else:
                    print(
                        f"configuration top_k={top_k} min_similarity={label} "
                        f"retrieval_failures={failures} no_evaluable_results=true"
                    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate retrieval against human labels. This makes real Gemini query "
            "embedding calls and may consume API quota."
        )
    )
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--user-id", required=True, type=uuid.UUID)
    parser.add_argument("--top-k", action="append", type=int, default=[])
    parser.add_argument("--min-similarity", action="append", type=float)
    args = parser.parse_args()
    if not args.top_k:
        args.top_k = [settings.rag_retrieval_top_k]
    asyncio.run(_evaluate(args))


if __name__ == "__main__":
    main()
