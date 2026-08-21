"""HTTP routes for the current user's conversations.

Why it exists: the Chat UI needs to restore history without posting a
question. Ownership is enforced by `ChatService` using `JWT.sub`.

Responsibility: `GET /latest` only. Creating threads happens in `/chat`.

Communicates with: `deps.get_current_user`, `services.chat_service`,
and `schemas.chat`.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.database.database import get_db
from src.search_engine.deps import get_current_user
from src.search_engine.models.user import User
from src.search_engine.schemas.chat import (
    ConversationMessageOut,
    LatestConversationResponse,
)
from src.search_engine.services.chat_service import ChatService

router = APIRouter()


@router.get("/latest", response_model=LatestConversationResponse)
async def get_latest_conversation(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LatestConversationResponse:
    """Return this user's most recent conversation, or an empty chat."""
    latest = await ChatService(db).get_latest_for_user(user.id)
    if latest is None:
        return LatestConversationResponse()

    conversation, messages = latest
    return LatestConversationResponse(
        conversation_id=conversation.id,
        messages=[ConversationMessageOut.model_validate(item) for item in messages],
    )
