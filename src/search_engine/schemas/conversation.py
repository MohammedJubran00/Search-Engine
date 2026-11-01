"""Conversation management contracts."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.search_engine.schemas.chat import ConversationMessageOut


ConversationMode = Literal["general", "documents", "deep"]


class ConversationSummary(BaseModel):
    model_config = {"from_attributes": True}
    id: uuid.UUID
    title: str
    mode: ConversationMode
    created_at: datetime
    updated_at: datetime


class ConversationPage(BaseModel):
    items: list[ConversationSummary]
    total: int
    limit: int
    offset: int


class ConversationCreate(BaseModel):
    title: str = Field(default="New chat", max_length=255)
    mode: ConversationMode = "general"


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    mode: ConversationMode | None = None


class ConversationDocumentsUpdate(BaseModel):
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


class ConversationDetail(ConversationSummary):
    messages: list[ConversationMessageOut]
    document_ids: list[uuid.UUID]
