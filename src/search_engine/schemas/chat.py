"""Pydantic schemas for authenticated chat persistence.

Why it exists: `/chat` must not take `user_id` or treat `session_id` as
identity. The body is only the question and an optional conversation id.

Responsibility: request/response shapes. No SQL, no JWT, no LangGraph.
"""

import uuid

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Body for `POST /chat` and `POST /chat/stream`."""

    query: str
    conversation_id: uuid.UUID | None = None


class ChatResponse(BaseModel):
    """JSON body for a completed non-streaming chat turn."""

    answer: str
    conversation_id: uuid.UUID


class ConversationMessageOut(BaseModel):
    """One persisted turn returned to the Chat UI."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    role: str
    content: str


class LatestConversationResponse(BaseModel):
    """The current user's most recently updated thread, or an empty chat."""

    conversation_id: uuid.UUID | None = None
    messages: list[ConversationMessageOut] = Field(default_factory=list)
