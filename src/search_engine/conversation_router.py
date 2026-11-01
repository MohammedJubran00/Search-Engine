"""Authenticated conversation management and persistent document scope."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.database.database import get_db
from src.search_engine.deps import get_current_user
from src.search_engine.models.user import User
from src.search_engine.schemas.chat import ConversationMessageOut, LatestConversationResponse
from src.search_engine.schemas.conversation import (
    ConversationCreate, ConversationDetail, ConversationDocumentsUpdate,
    ConversationPage, ConversationSummary, ConversationUpdate,
)
from src.search_engine.services.chat_service import ChatService, ConversationNotFoundError

router = APIRouter()


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Conversation not found.")


@router.get("", response_model=ConversationPage)
async def list_conversations(
    search: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> ConversationPage:
    items, total = await ChatService(db).list_conversations(
        user_id=user.id, search=search, limit=limit, offset=offset
    )
    return ConversationPage(
        items=[ConversationSummary.model_validate(item) for item in items],
        total=total, limit=limit, offset=offset,
    )


@router.post("", response_model=ConversationSummary, status_code=201)
async def create_conversation(
    payload: ConversationCreate, user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationSummary:
    item = await ChatService(db).create_conversation(
        user_id=user.id, title=payload.title, mode=payload.mode
    )
    return ConversationSummary.model_validate(item)


@router.get("/latest", response_model=LatestConversationResponse)
async def get_latest_conversation(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> LatestConversationResponse:
    latest = await ChatService(db).get_latest_for_user(user.id)
    if latest is None:
        return LatestConversationResponse()
    conversation, messages = latest
    return LatestConversationResponse(
        conversation_id=conversation.id,
        messages=[ConversationMessageOut.model_validate(item) for item in messages],
    )


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    message_limit: int = Query(default=100, ge=1, le=200),
    message_offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> ConversationDetail:
    try:
        conversation, messages, document_ids = await ChatService(db).get_conversation(
            user_id=user.id, conversation_id=conversation_id,
            message_limit=message_limit, message_offset=message_offset,
        )
    except ConversationNotFoundError:
        raise _not_found() from None
    return ConversationDetail(
        **ConversationSummary.model_validate(conversation).model_dump(),
        messages=[ConversationMessageOut.model_validate(item) for item in messages],
        document_ids=document_ids,
    )


@router.patch("/{conversation_id}", response_model=ConversationSummary)
async def update_conversation(
    conversation_id: uuid.UUID, payload: ConversationUpdate,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> ConversationSummary:
    try:
        item = await ChatService(db).update_conversation(
            user_id=user.id, conversation_id=conversation_id,
            title=payload.title, mode=payload.mode,
        )
    except ConversationNotFoundError:
        raise _not_found() from None
    return ConversationSummary.model_validate(item)


@router.put("/{conversation_id}/documents", response_model=list[uuid.UUID])
async def update_conversation_documents(
    conversation_id: uuid.UUID, payload: ConversationDocumentsUpdate,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> list[uuid.UUID]:
    try:
        return await ChatService(db).replace_conversation_documents(
            user_id=user.id, conversation_id=conversation_id,
            document_ids=payload.document_ids,
        )
    except ConversationNotFoundError:
        raise _not_found() from None


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID, user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await ChatService(db).delete_conversation(
            user_id=user.id, conversation_id=conversation_id
        )
    except ConversationNotFoundError:
        raise _not_found() from None
    return Response(status_code=204)
