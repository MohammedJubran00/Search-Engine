"""Application boundary for durable automatic document indexing."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.models.indexing_job import IndexingJob
from src.search_engine.repositories.indexing_job_repository import IndexingJobRepository


class IndexingQueueService:
    def __init__(self, session: AsyncSession) -> None:
        self._jobs = IndexingJobRepository(session)

    async def enqueue(self, *, document_id: uuid.UUID, user_id: uuid.UUID) -> IndexingJob:
        job = await self._jobs.enqueue(document_id=document_id, user_id=user_id)
        if job is None:
            raise LookupError("Document not found.")
        return job

    async def latest(self, *, document_id: uuid.UUID, user_id: uuid.UUID) -> IndexingJob | None:
        return await self._jobs.latest_for_document(document_id=document_id, user_id=user_id)
