"""SQLAlchemy ORM models.

Import model modules so `Base.metadata` includes every table for Alembic.
"""

from src.search_engine.models.conversation import Conversation
from src.search_engine.models.conversation_document import ConversationDocument
from src.search_engine.models.document import DOCUMENT_PROCESSING_STATUSES, Document
from src.search_engine.models.document_chunk import DocumentChunk
from src.search_engine.models.document_index_state import DocumentIndexState
from src.search_engine.models.message import Message, MESSAGE_ROLES
from src.search_engine.models.indexing_job import IndexingJob
from src.search_engine.models.usage_event import UsageEvent
from src.search_engine.models.user_preference import UserPreference
from src.search_engine.models.user import User

__all__ = [
    "Conversation",
    "ConversationDocument",
    "DOCUMENT_PROCESSING_STATUSES",
    "Document",
    "DocumentChunk",
    "DocumentIndexState",
    "MESSAGE_ROLES",
    "Message",
    "IndexingJob",
    "UsageEvent",
    "UserPreference",
    "User",
]
