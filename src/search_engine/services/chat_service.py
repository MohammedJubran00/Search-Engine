"""Persist and load per-user conversations.

Why it exists: FastAPI routes must not contain ownership SQL, and LangGraph
must not decide who the user is. `JWT.sub` is the only identity; a missing
or foreign `conversation_id` is not found.

Responsibility: resolve/create the user's conversation, append turns, load
the latest thread. Does not invoke Gemini.

Communicates with: `ConversationRepository`, `MessageRepository`, and
`api` / `conversation_router`.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.models.conversation import Conversation
from src.search_engine.models.message import Message
from src.search_engine.repositories.conversation_repository import ConversationRepository
from src.search_engine.repositories.message_repository import MessageRepository

_TITLE_MAX_LENGTH = 255


class ConversationNotFoundError(Exception):
    """Raised when the conversation does not exist or is not owned by this user."""


def title_from_query(query: str) -> str:
    """Use the first question as the thread title, within the column limit."""
    collapsed = " ".join(query.split())
    if len(collapsed) <= _TITLE_MAX_LENGTH:
        return collapsed
    return collapsed[:_TITLE_MAX_LENGTH]


class ChatService:
    """Conversation use cases scoped to one user."""

    def __init__(self, session: AsyncSession) -> None:
        self._conversations = ConversationRepository(session)
        self._messages = MessageRepository(session)

    async def start_user_turn(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        query: str,
    ) -> Conversation:
        """Create or load an owned conversation and store the user message."""
        title = title_from_query(query)
        if conversation_id is None:
            conversation = await self._conversations.create(
                user_id=user_id,
                title=title,
            )
        else:
            conversation = await self._conversations.get_by_id_for_user(
                conversation_id,
                user_id,
            )
            if conversation is None:
                raise ConversationNotFoundError
            await self._conversations.mark_updated(conversation, title=title)

        await self._messages.create(
            conversation_id=conversation.id,
            role="user",
            content=query,
        )
        await self._conversations.mark_updated(conversation)
        return conversation

    async def add_assistant_message(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        content: str,
    ) -> None:
        """Store the assistant answer only if the conversation still belongs to the user."""
        conversation = await self._conversations.get_by_id_for_user(
            conversation_id,
            user_id,
        )
        if conversation is None:
            raise ConversationNotFoundError
        await self._messages.create(
            conversation_id=conversation.id,
            role="assistant",
            content=content,
        )
        await self._conversations.mark_updated(conversation)

    async def get_latest_for_user(
        self,
        user_id: uuid.UUID,
    ) -> tuple[Conversation, list[Message]] | None:
        """Return the newest conversation and its turns, or None."""
        conversations = await self._conversations.list_for_user(user_id)
        if not conversations:
            return None
        latest = conversations[0]
        messages = await self._messages.list_for_conversation(latest.id)
        return latest, messages
