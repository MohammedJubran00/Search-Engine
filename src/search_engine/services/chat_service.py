"""Persist and load per-user conversations.

Why it exists: FastAPI routes must not contain ownership SQL, and LangGraph
must not decide who the user is. `JWT.sub` is the only identity; a missing
or foreign `conversation_id` is not found.

Responsibility: resolve/create the user's conversation, append turns, load
the latest thread. Does not invoke Gemini.

Communicates with: `ConversationRepository`, `MessageRepository`, and
`api` / `conversation_router`.
"""

import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.models.conversation import Conversation
from src.search_engine.models.message import Message
from src.search_engine.repositories.conversation_repository import ConversationRepository
from src.search_engine.repositories.message_repository import MessageRepository

_TITLE_MAX_LENGTH = 255
_MESSAGE_ENVELOPE_PREFIX = "SE_CHAT_V1:"
_CHAT_MODES = {"general", "documents"}


@dataclass(frozen=True, slots=True)
class PersistedChatMessage:
    """Decoded message content and server-validated attribution."""

    id: uuid.UUID
    role: str
    content: str
    mode: Literal["general", "documents"] = "general"
    status: str | None = None
    citations: tuple[dict[str, Any], ...] = ()
    document_ids: tuple[uuid.UUID, ...] = ()
    attachments: tuple[dict[str, Any], ...] = ()


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
        mode: Literal["general", "documents"] = "general",
        document_ids: Sequence[uuid.UUID] = (),
        attachments: Sequence[Mapping[str, Any]] = (),
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
            content=_encode_message(
                content=query,
                mode=mode,
                document_ids=document_ids,
                attachments=attachments,
            ),
        )
        await self._conversations.mark_updated(conversation)
        return conversation

    async def add_assistant_message(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        content: str,
        mode: Literal["general", "documents"] = "general",
        status: str | None = None,
        citations: Sequence[Mapping[str, Any]] = (),
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
            content=_encode_message(
                content=content,
                mode=mode,
                status=status,
                citations=citations,
            ),
        )
        await self._conversations.mark_updated(conversation)

    async def get_latest_for_user(
        self,
        user_id: uuid.UUID,
    ) -> tuple[Conversation, list[PersistedChatMessage]] | None:
        """Return the newest conversation and its turns, or None."""
        conversations = await self._conversations.list_for_user(user_id)
        if not conversations:
            return None
        latest = conversations[0]
        rows = await self._messages.list_for_conversation(latest.id)
        messages = [_decode_message(message) for message in rows]
        return latest, messages


def _encode_message(
    *,
    content: str,
    mode: str,
    status: str | None = None,
    citations: Sequence[Mapping[str, Any]] = (),
    document_ids: Sequence[uuid.UUID] = (),
    attachments: Sequence[Mapping[str, Any]] = (),
) -> str:
    if mode not in _CHAT_MODES:
        raise ValueError("Invalid chat mode.")
    payload = {
        "content": content,
        "mode": mode,
        "status": status,
        "citations": [dict(item) for item in citations],
        "document_ids": [str(item) for item in document_ids],
        "attachments": [dict(item) for item in attachments],
    }
    return _MESSAGE_ENVELOPE_PREFIX + json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def _decode_message(message: Message) -> PersistedChatMessage:
    if not message.content.startswith(_MESSAGE_ENVELOPE_PREFIX):
        return PersistedChatMessage(
            id=message.id,
            role=message.role,
            content=message.content,
        )
    try:
        payload = json.loads(message.content.removeprefix(_MESSAGE_ENVELOPE_PREFIX))
        content = payload["content"]
        mode = payload["mode"]
        status = payload.get("status")
        citations = payload.get("citations", [])
        document_ids = payload.get("document_ids", [])
        attachments = payload.get("attachments", [])
        if not isinstance(content, str) or mode not in _CHAT_MODES:
            raise ValueError
        if status not in {None, "answered", "insufficient_evidence"}:
            raise ValueError
        if not isinstance(citations, list) or not all(
            isinstance(item, dict) for item in citations
        ):
            raise ValueError
        if not isinstance(attachments, list) or not all(
            isinstance(item, dict) for item in attachments
        ):
            raise ValueError
        parsed_document_ids = tuple(uuid.UUID(item) for item in document_ids)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        # A corrupt envelope is never interpreted as trusted attribution.
        return PersistedChatMessage(
            id=message.id,
            role=message.role,
            content="This stored message could not be read safely.",
        )
    return PersistedChatMessage(
        id=message.id,
        role=message.role,
        content=content,
        mode=mode,
        status=status,
        citations=tuple(citations),
        document_ids=parsed_document_ids,
        attachments=tuple(attachments),
    )
