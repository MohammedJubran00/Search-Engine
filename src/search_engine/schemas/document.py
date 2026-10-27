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
    created_at: datetime
    updated_at: datetime
