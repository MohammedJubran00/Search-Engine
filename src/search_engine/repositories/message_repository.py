"""Database access for the `messages` table.

Why it exists: SQL must not live in FastAPI routes. Messages are loaded
only through a conversation id that the conversation repository already
scoped to the current user.

Responsibility: insert and list turns for one conversation. No HTTP.

Communicates with: `models.message` and `models.conversation`.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.models.message import MESSAGE_ROLES, Message


class MessageRepository:
    """Read and write `messages` through one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
    ) -> Message:
        """Insert one turn. `role` must be user or assistant."""
        if role not in MESSAGE_ROLES:
            raise ValueError("Message role must be 'user' or 'assistant'.")

        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
        self._session.add(message)
        await self._session.flush()
        await self._session.refresh(message)
        return message

    async def list_for_conversation(self, conversation_id: uuid.UUID) -> list[Message]:
        """Return turns in chronological order."""
        result = await self._session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        return list(result.scalars().all())
