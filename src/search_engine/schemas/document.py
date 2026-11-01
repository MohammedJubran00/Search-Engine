"""Public document API schemas that never expose private storage paths."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    """Safe document metadata returned to its authenticated owner."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    original_filename: str
    content_type: str
    file_size: int
    processing_status: str
    indexing_status: str = "not_indexed"
    created_at: datetime
    updated_at: datetime


class IndexingJobResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    document_id: uuid.UUID
    status: str
    stage: str
    attempt_count: int
    completed_chunks: int
    total_chunks: int | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentPage(BaseModel):
    items: list[DocumentResponse]
    total: int
    limit: int
    offset: int
