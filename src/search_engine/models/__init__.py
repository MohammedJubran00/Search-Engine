"""SQLAlchemy ORM models.

Import model modules so `Base.metadata` includes every table for Alembic.
"""

from src.search_engine.models.conversation import Conversation
from src.search_engine.models.document import DOCUMENT_PROCESSING_STATUSES, Document
from src.search_engine.models.document_chunk import DocumentChunk
from src.search_engine.models.message import Message, MESSAGE_ROLES
from src.search_engine.models.user import User

__all__ = [
    "Conversation",
    "DOCUMENT_PROCESSING_STATUSES",
    "Document",
    "DocumentChunk",
    "MESSAGE_ROLES",
    "Message",
    "User",
]
