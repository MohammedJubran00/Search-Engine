"""Durable, concurrency-safe indexing job queue."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.models.document import Document
from src.search_engine.models.document_index_state import DocumentIndexState
from src.search_engine.models.indexing_job import IndexingJob


class IndexingJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, *, document_id: uuid.UUID, user_id: uuid.UUID) -> IndexingJob | None:
        document = await self._session.scalar(
            select(Document).where(Document.id == document_id, Document.user_id == user_id)
        )
        if document is None:
            return None
        active = await self._session.scalar(
            select(IndexingJob).where(
                IndexingJob.document_id == document_id,
                IndexingJob.status.in_(("queued", "processing")),
            )
        )
        if active is not None:
            return active
        state = await self._session.get(DocumentIndexState, document_id)
        if state is None:
            state = DocumentIndexState(document_id=document_id, status="queued")
            self._session.add(state)
        else:
            state.status = "queued"
            state.error_message = None
        job = IndexingJob(document_id=document_id, user_id=user_id)
        self._session.add(job)
        await self._session.flush()
        return job

    async def latest_for_document(
        self, *, document_id: uuid.UUID, user_id: uuid.UUID
    ) -> IndexingJob | None:
        return await self._session.scalar(
            select(IndexingJob)
            .where(IndexingJob.document_id == document_id, IndexingJob.user_id == user_id)
            .order_by(IndexingJob.created_at.desc())
            .limit(1)
        )

    async def claim_next(self) -> IndexingJob | None:
        job = await self._session.scalar(
            select(IndexingJob)
            .where(IndexingJob.status == "queued")
            .order_by(IndexingJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        job.status = "processing"
        job.stage = "claiming"
        job.attempt_count += 1
        job.started_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return job

    async def progress(
        self, job_id: uuid.UUID, *, stage: str,
        completed_chunks: int = 0, total_chunks: int | None = None,
    ) -> None:
        job = await self._session.get(IndexingJob, job_id)
        if job is None:
            return
        job.stage = stage
        job.completed_chunks = completed_chunks
        job.total_chunks = total_chunks
        job.updated_at = datetime.now(timezone.utc)
        await self._session.flush()

    async def finish(self, job_id: uuid.UUID, *, error: str | None = None) -> None:
        job = await self._session.get(IndexingJob, job_id)
        if job is None:
            return
        job.status = "failed" if error else "completed"
        job.stage = "failed" if error else "completed"
        job.error_message = error
        if not error and job.total_chunks is not None:
            job.completed_chunks = job.total_chunks
        job.finished_at = datetime.now(timezone.utc)
        job.updated_at = job.finished_at
        await self._session.flush()
