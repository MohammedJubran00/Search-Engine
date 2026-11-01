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

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.models.conversation import Conversation
from src.search_engine.models.message import Message


class ConversationRepository:
    """Read and write `conversations` through one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, user_id: uuid.UUID, title: str = "", mode: str = "general"
    ) -> Conversation:
        """Insert a conversation owned by `user_id`."""
        conversation = Conversation(user_id=user_id, title=title, mode=mode)
        self._session.add(conversation)
        await self._session.flush()
        await self._session.refresh(conversation)
        return conversation

    async def list_for_user(self, user_id: uuid.UUID) -> list[Conversation]:
        """Return this user's conversations, newest first."""
        result = await self._session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id, select(Message.id).where(Message.conversation_id == Conversation.id).exists())
            .order_by(Conversation.updated_at.desc())
        )
        return list(result.scalars().all())

    async def page_for_user(
        self,
        user_id: uuid.UUID,
        *,
        search: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Conversation], int]:
        predicate = [Conversation.user_id == user_id, select(Message.id).where(Message.conversation_id == Conversation.id).exists()]
        if search:
            predicate.append(Conversation.title.ilike(f"%{search}%"))
        rows = await self._session.execute(
            select(Conversation)
            .where(*predicate)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .limit(limit)
            .offset(offset)
        )
        total = await self._session.scalar(
            select(func.count()).select_from(Conversation).where(*predicate)
        )
        return list(rows.scalars().all()), int(total or 0)

    async def delete_for_user(self, conversation_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        await self._session.flush()
        return bool(result.rowcount)

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
        if title and conversation.title in {"", "New chat"}:
            conversation.title = title
        conversation.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
