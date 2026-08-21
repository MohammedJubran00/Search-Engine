"""Database access for the `conversations` table.

Why it exists: SQL must not live in FastAPI routes. Isolation is enforced
here by always filtering on `user_id` — callers cannot load another user's
thread by guessing an id.

Responsibility: create, list, and load conversations for one user.
No HTTP, no LangGraph.

Communicates with: `models.conversation` and `services.chat_service`.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.models.conversation import Conversation


class ConversationRepository:
    """Read and write `conversations` through one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, user_id: uuid.UUID, title: str = "") -> Conversation:
        """Insert a conversation owned by `user_id`."""
        conversation = Conversation(user_id=user_id, title=title)
        self._session.add(conversation)
        await self._session.flush()
        await self._session.refresh(conversation)
        return conversation

    async def list_for_user(self, user_id: uuid.UUID) -> list[Conversation]:
        """Return this user's conversations, newest first."""
        result = await self._session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id_for_user(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Conversation | None:
        """Return the conversation only if it belongs to `user_id`."""
        result = await self._session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def mark_updated(
        self,
        conversation: Conversation,
        *,
        title: str | None = None,
    ) -> None:
        """Bump `updated_at`. Set `title` only when the thread has none yet."""
        if title and not conversation.title:
            conversation.title = title
        conversation.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
