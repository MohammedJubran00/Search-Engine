"""Run a durable PostgreSQL indexing worker: python -m src.search_engine.indexing_worker."""

import asyncio
import logging

from src.search_engine.core.config import settings
from src.search_engine.database.database import SessionLocal
from src.search_engine.repositories.indexing_job_repository import IndexingJobRepository
from src.search_engine.services.document_indexing_service import DocumentIndexingService
from src.search_engine.repositories.usage_repository import UsageRepository
from src.search_engine.rag.embeddings import GeminiEmbeddingProvider

logger = logging.getLogger(__name__)


async def process_one() -> bool:
    async with SessionLocal() as session:
        jobs = IndexingJobRepository(session)
        job = await jobs.claim_next()
        if job is None:
            await session.rollback()
            return False
        job_id, document_id, user_id = job.id, job.document_id, job.user_id
        await session.commit()

    async with SessionLocal() as session:
        jobs = IndexingJobRepository(session)

        async def progress(stage: str, completed: int, total: int | None) -> None:
            await jobs.progress(
                job_id, stage=stage, completed_chunks=completed, total_chunks=total
            )
            await session.commit()

        try:
            provider_requests = 0

            def count_provider_request() -> None:
                nonlocal provider_requests
                provider_requests += 1

            indexer = DocumentIndexingService(
                session, embeddings=GeminiEmbeddingProvider(on_request=count_provider_request)
            )
            await indexer.index(
                document_id=document_id, user_id=user_id, progress=progress
            )
            await UsageRepository(session).add(
                request_id=job_id, user_id=user_id, conversation_id=None,
                provider="gemini", operation="embedding", status="success",
                model="models/gemini-embedding-001", request_count=provider_requests,
            )
            await jobs.finish(job_id)
            await session.commit()
        except Exception as exc:
            logger.exception("Indexing job failed job_id=%s", job_id)
            await session.rollback()
            await UsageRepository(session).add(
                request_id=job_id, user_id=user_id, conversation_id=None,
                provider="gemini", operation="embedding", status="error",
                model="models/gemini-embedding-001", request_count=provider_requests,
            )
            await jobs.finish(job_id, error="Document indexing failed.")
            await session.commit()
        return True


async def run() -> None:
    while True:
        try:
            worked = await process_one()
            if not worked:
                await asyncio.sleep(settings.indexing_worker_poll_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            # The PostgreSQL queue is durable. A transient database failure must
            # not permanently kill the consumer and strand future uploads.
            logger.exception("Indexing worker loop failed; retrying")
            await asyncio.sleep(settings.indexing_worker_poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
