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
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.models.conversation import Conversation
from src.search_engine.models.message import Message
from src.search_engine.core.config import settings
from src.search_engine.repositories.conversation_repository import ConversationRepository
from src.search_engine.repositories.conversation_document_repository import ConversationDocumentRepository
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
    web_citations: tuple[dict[str, Any], ...] = ()
    research_plan: tuple[str, ...] = ()
    research_summary: dict[str, Any] | None = None
    evidence_conflicts: tuple[dict[str, Any], ...] = ()
    presentation: dict[str, Any] = field(
        default_factory=lambda: {"type": "standard"}
    )
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
        self._session = session
        self._conversations = ConversationRepository(session)
        self._messages = MessageRepository(session)
        self._conversation_documents = ConversationDocumentRepository(session)

    async def start_user_turn(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        query: str,
        mode: Literal["general", "documents"] = "general",
        document_ids: Sequence[uuid.UUID] = (),
        attachments: Sequence[Mapping[str, Any]] = (),
        conversation_mode: str | None = None,
        documents_verified: bool = False,
    ) -> Conversation:
        """Create or load an owned conversation and store the user message."""
        title = title_from_query(query)
        if conversation_id is None:
            conversation = await self._conversations.create(
                user_id=user_id,
                title=title,
                mode=conversation_mode or mode,
            )
        else:
            conversation = await self._conversations.get_by_id_for_user(
                conversation_id,
                user_id,
            )
            if conversation is None:
                raise ConversationNotFoundError
            await self._conversations.mark_updated(conversation, title=title)
            if conversation_mode:
                conversation.mode = conversation_mode

        if mode == "documents" and document_ids:
            await self._conversation_documents.replace(
                conversation_id=conversation.id,
                user_id=user_id,
                document_ids=document_ids,
                verify_ownership=not documents_verified,
            )

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

    async def get_associated_document_ids(
        self, *, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> list[uuid.UUID]:
        conversation = await self._conversations.get_by_id_for_user(conversation_id, user_id)
        if conversation is None:
            raise ConversationNotFoundError
        return await self._conversation_documents.list_ids(conversation_id, user_id)

    async def add_assistant_message(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        content: str,
        mode: Literal["general", "documents"] = "general",
        status: str | None = None,
        citations: Sequence[Mapping[str, Any]] = (),
        web_citations: Sequence[Mapping[str, Any]] = (),
        research_plan: Sequence[str] = (),
        research_summary: Mapping[str, Any] | None = None,
        evidence_conflicts: Sequence[Mapping[str, Any]] = (),
        presentation: Mapping[str, Any] | None = None,
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
                web_citations=web_citations,
                research_plan=research_plan,
                research_summary=research_summary,
                evidence_conflicts=evidence_conflicts,
                presentation=presentation,
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

    async def list_conversations(
        self, *, user_id: uuid.UUID, search: str | None, limit: int, offset: int
    ) -> tuple[list[Conversation], int]:
        return await self._conversations.page_for_user(
            user_id, search=search, limit=limit, offset=offset
        )

    async def create_conversation(
        self, *, user_id: uuid.UUID, title: str, mode: str
    ) -> Conversation:
        return await self._conversations.create(user_id=user_id, title=title.strip(), mode=mode)

    async def get_conversation(
        self, *, user_id: uuid.UUID, conversation_id: uuid.UUID,
        message_limit: int = 100, message_offset: int = 0,
    ) -> tuple[Conversation, list[PersistedChatMessage], list[uuid.UUID]]:
        conversation = await self._conversations.get_by_id_for_user(conversation_id, user_id)
        if conversation is None:
            raise ConversationNotFoundError
        rows = await self._messages.page_for_conversation(
            conversation_id, limit=message_limit, offset=message_offset
        )
        return (
            conversation,
            [_decode_message(row) for row in rows],
            await self._conversation_documents.list_ids(conversation_id, user_id),
        )

    async def update_conversation(
        self, *, user_id: uuid.UUID, conversation_id: uuid.UUID,
        title: str | None, mode: str | None,
    ) -> Conversation:
        conversation = await self._conversations.get_by_id_for_user(conversation_id, user_id)
        if conversation is None:
            raise ConversationNotFoundError
        if title is not None:
            conversation.title = title.strip()
        if mode is not None:
            conversation.mode = mode
        await self._conversations.mark_updated(conversation)
        return conversation

    async def delete_conversation(self, *, user_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
        if not await self._conversations.delete_for_user(conversation_id, user_id):
            raise ConversationNotFoundError

    async def replace_conversation_documents(
        self, *, user_id: uuid.UUID, conversation_id: uuid.UUID,
        document_ids: Sequence[uuid.UUID],
    ) -> list[uuid.UUID]:
        conversation = await self._conversations.get_by_id_for_user(conversation_id, user_id)
        if conversation is None:
            raise ConversationNotFoundError
        try:
            await self._conversation_documents.replace(
                conversation_id=conversation_id, user_id=user_id, document_ids=document_ids
            )
        except LookupError as exc:
            raise ConversationNotFoundError from exc
        return await self._conversation_documents.list_ids(conversation_id, user_id)

    async def get_bounded_general_history(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        max_messages: int = settings.general_chat_history_max_messages,
        max_characters: int = settings.general_chat_history_max_characters,
    ) -> list[tuple[str, str]]:
        """Return recent persisted General Chat turns without another model call."""
        return await self._get_bounded_history(
            user_id=user_id, conversation_id=conversation_id, mode="general",
            max_messages=max_messages, max_characters=max_characters,
        )

    async def get_bounded_document_history(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        max_messages: int = 6,
        max_characters: int = 3000,
    ) -> list[tuple[str, str]]:
        """Return only this user's recent document turns before the new turn is saved."""
        return await self._get_bounded_history(
            user_id=user_id, conversation_id=conversation_id, mode="documents",
            max_messages=max_messages, max_characters=max_characters,
        )

    async def _get_bounded_history(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        mode: str,
        max_messages: int,
        max_characters: int,
    ) -> list[tuple[str, str]]:
        if max_messages < 1 or max_characters < 1:
            raise ValueError("History limits must be positive.")
        conversation = await self._conversations.get_by_id_for_user(
            conversation_id,
            user_id,
        )
        if conversation is None:
            raise ConversationNotFoundError
        rows = await self._messages.list_for_conversation(conversation.id)
        decoded = [
            item
            for item in (_decode_message(row) for row in rows)
            if item.mode == mode and item.role in {"user", "assistant"}
        ]
        selected: list[tuple[str, str]] = []
        remaining = max_characters
        for item in reversed(decoded):
            if len(selected) == max_messages or remaining < 1:
                break
            content = item.content.strip()
            if not content:
                continue
            if len(content) > remaining:
                content = content[-remaining:]
            selected.append((item.role, content))
            remaining -= len(content)
        selected.reverse()
        return selected


def _encode_message(
    *,
    content: str,
    mode: str,
    status: str | None = None,
    citations: Sequence[Mapping[str, Any]] = (),
    web_citations: Sequence[Mapping[str, Any]] = (),
    research_plan: Sequence[str] = (),
    research_summary: Mapping[str, Any] | None = None,
    evidence_conflicts: Sequence[Mapping[str, Any]] = (),
    presentation: Mapping[str, Any] | None = None,
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
        "web_citations": [dict(item) for item in web_citations],
        "research_plan": list(research_plan),
        "research_summary": dict(research_summary) if research_summary else None,
        "evidence_conflicts": [dict(item) for item in evidence_conflicts],
        "presentation": dict(presentation) if presentation else {"type": "standard"},
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
        web_citations = payload.get("web_citations", [])
        research_plan = payload.get("research_plan", [])
        research_summary = payload.get("research_summary")
        evidence_conflicts = payload.get("evidence_conflicts", [])
        presentation = payload.get("presentation", {"type": "standard"})
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
        if not isinstance(web_citations, list) or not all(
            isinstance(item, dict) for item in web_citations
        ):
            raise ValueError
        if not isinstance(research_plan, list) or not all(
            isinstance(item, str) for item in research_plan
        ):
            raise ValueError
        if research_summary is not None and not isinstance(research_summary, dict):
            raise ValueError
        if not isinstance(evidence_conflicts, list) or not all(
            isinstance(item, dict) for item in evidence_conflicts
        ):
            raise ValueError
        if not isinstance(presentation, dict):
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
        web_citations=tuple(web_citations),
        research_plan=tuple(research_plan),
        research_summary=research_summary,
        evidence_conflicts=tuple(evidence_conflicts),
        presentation=presentation,
        document_ids=parsed_document_ids,
        attachments=tuple(attachments),
    )
