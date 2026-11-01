"""Owner-scoped persistence for conversation document associations."""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.models.conversation_document import ConversationDocument
from src.search_engine.models.document import Document


class ConversationDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_ids(self, conversation_id: uuid.UUID, user_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self._session.execute(
            select(ConversationDocument.document_id)
            .where(
                ConversationDocument.conversation_id == conversation_id,
                ConversationDocument.user_id == user_id,
            )
            .order_by(ConversationDocument.created_at, ConversationDocument.document_id)
        )
        return list(result.scalars().all())

    async def replace(
        self,
        *,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        document_ids: Sequence[uuid.UUID],
        verify_ownership: bool = True,
    ) -> None:
        unique_ids = list(dict.fromkeys(document_ids))
        if unique_ids and verify_ownership:
            owned = await self._session.execute(
                select(Document.id).where(Document.user_id == user_id, Document.id.in_(unique_ids))
            )
            if set(owned.scalars().all()) != set(unique_ids):
                raise LookupError("One or more documents are unavailable.")
        await self._session.execute(
            delete(ConversationDocument).where(
                ConversationDocument.conversation_id == conversation_id,
                ConversationDocument.user_id == user_id,
            )
        )
        self._session.add_all(
            ConversationDocument(
                conversation_id=conversation_id,
                document_id=document_id,
                user_id=user_id,
            )
            for document_id in unique_ids
        )
        await self._session.flush()
