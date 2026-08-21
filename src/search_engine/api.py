# Frontend   the logic for understanding if i forget
#    ↓
# POST /chat
#    ↓
# FastAPI
#    ↓
# LangGraph app.invoke()
#    ↓
# Agent
#    ↓
# Tavily + Gemini
#    ↓
# Answer
#    ↓
# JSON
#    ↓
# Frontend



import asyncio
import json
import logging
import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.search_engine.auth_router import router as auth_router
from src.search_engine.conversation_router import router as conversation_router
from src.search_engine.database.database import get_db
from src.search_engine.deps import get_current_user
from src.search_engine.main import app as graph_app  # عشان ما نخلطه مع: app = FastAPI() ( لا نستخدم نفس الاسم)
from src.search_engine.main import stream_agent
from src.search_engine.models.user import User
from src.search_engine.schemas.chat import ChatRequest, ChatResponse
from src.search_engine.services.chat_service import ChatService, ConversationNotFoundError

logger = logging.getLogger(__name__)

app = FastAPI()

# CORS settings:
# Allow requests from any origin, using any HTTP method,
# and accepting any request headers.
# This allows the frontend to make requests to the API from any origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(
    conversation_router,
    prefix="/api/conversations",
    tags=["conversations"],
)


def error_response(status_code: int, message: str) -> JSONResponse:
    # Keep every error body on the same contract the frontend can display:
    # { "error": "Human readable message" }
    return JSONResponse(status_code=status_code, content={"error": message})


@app.exception_handler(RequestValidationError)
async def handle_invalid_request(request: Request, exc: RequestValidationError):
    # FastAPI would otherwise return 422 with { "detail": [...] }.
    # Map missing/invalid fields to HTTP 400 and our { "error": ... } shape.
    logger.warning("Invalid request body: %s", exc.errors())

    messages = []
    for err in exc.errors():
        loc = err.get("loc", [])
        field = loc[-1] if loc else "request"
        if err.get("type") == "missing":
            messages.append(f"{field} is required.")
        else:
            messages.append(f"{field}: {err.get('msg', 'is invalid')}")

    error_text = " ".join(messages) if messages else "Invalid request. Check query."
    return error_response(400, error_text)


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    # Do not convert HTTPException (401/404) into a generic 500.
    if isinstance(exc, StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    logger.error("Unhandled server error on %s %s", request.method, request.url.path, exc_info=exc)
    return error_response(
        500,
        "Something went wrong while processing your request. Please try again.",
    )


def to_answer_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [to_answer_text(item) for item in content]
        return "\n\n".join(part for part in parts if part)
    if isinstance(content, dict):
        if content.get("type") in {"thinking", "reasoning"}:
            return ""
        if isinstance(content.get("text"), str):
            return content["text"]
        if "content" in content:
            return to_answer_text(content["content"])
        return ""

    block_type = getattr(content, "type", None)
    if block_type in {"thinking", "reasoning"}:
        return ""

    text = getattr(content, "text", None)
    if isinstance(text, str):
        return text

    inner = getattr(content, "content", None)
    if inner is not None and inner is not content:
        return to_answer_text(inner)

    return str(content)


_STREAM_END = object()


def graph_thread_id(conversation_id: uuid.UUID) -> str:
    """LangGraph in-memory key. Not an identity claim — ownership was already checked."""
    return str(conversation_id)


async def persist_user_turn(
    db: AsyncSession,
    user: User,
    conversation_id: uuid.UUID | None,
    query: str,
):
    """Create/load the owned conversation and store the user message."""
    return await ChatService(db).start_user_turn(
        user_id=user.id,
        conversation_id=conversation_id,
        query=query,
    )


@app.get("/")
def root():
    return {"message": "AI Search Engine API is running"}


@app.post("/chat")
async def chat(
    request: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (request.query or "").strip()
    if not query:
        return error_response(400, "Please enter a question.")

    try:
        conversation = await persist_user_turn(
            db,
            user,
            request.conversation_id,
            query,
        )
    except ConversationNotFoundError:
        return error_response(404, "Conversation not found.")

    thread_id = graph_thread_id(conversation.id)

    try:
        result = await asyncio.to_thread(
            graph_app.invoke,
            {
                "session_id": thread_id,
                "query": query,
            },
        )
    except Exception:
        logger.exception("LangGraph invoke failed for conversation_id=%s", conversation.id)
        return error_response(
            500,
            "Something went wrong while generating an answer. Please try again.",
        )

    try:
        answer = to_answer_text(result.get("answer") if isinstance(result, dict) else None)
    except Exception:
        logger.exception("Failed to convert LangGraph answer to text")
        return error_response(
            500,
            "The search engine returned an unreadable answer. Please try again.",
        )

    if not answer:
        logger.error("LangGraph returned an empty answer for conversation_id=%s", conversation.id)
        return error_response(
            500,
            "The search engine returned an empty answer. Please try again.",
        )

    try:
        await ChatService(db).add_assistant_message(
            user_id=user.id,
            conversation_id=conversation.id,
            content=answer,
        )
    except ConversationNotFoundError:
        return error_response(404, "Conversation not found.")

    return ChatResponse(answer=answer, conversation_id=conversation.id)


def sse_event(payload: dict) -> str:
    # Server-Sent Events: one JSON object per "data:" line, blank line flush.
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (request.query or "").strip()
    if not query:
        return error_response(400, "Please enter a question.")

    try:
        conversation = await persist_user_turn(
            db,
            user,
            request.conversation_id,
            query,
        )
    except ConversationNotFoundError:
        return error_response(404, "Conversation not found.")

    conversation_id = conversation.id
    user_id = user.id
    thread_id = graph_thread_id(conversation_id)

    async def generate():
        try:
            yield sse_event({"conversation_id": str(conversation_id)})
            iterator = stream_agent(thread_id, query)
            yielded = False
            answer = ""

            while True:
                delta = await asyncio.to_thread(next, iterator, _STREAM_END)
                if delta is _STREAM_END:
                    break
                if not delta:
                    continue
                yielded = True
                answer += delta
                yield sse_event({"delta": delta})

            if not yielded or not answer.strip():
                yield sse_event(
                    {
                        "error": "The search engine returned an empty answer. Please try again."
                    }
                )
                return

            try:
                await ChatService(db).add_assistant_message(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    content=answer,
                )
            except ConversationNotFoundError:
                yield sse_event({"error": "Conversation not found."})
                return

            yield sse_event({"done": True, "conversation_id": str(conversation_id)})
        except Exception:
            logger.exception("Streaming chat failed for conversation_id=%s", conversation_id)
            yield sse_event(
                {
                    "error": "Something went wrong while generating an answer. Please try again."
                }
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


    