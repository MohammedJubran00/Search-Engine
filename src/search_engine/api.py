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
import time
import logging
import uuid
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.search_engine.auth_router import router as auth_router
from src.search_engine.conversation_router import router as conversation_router
from src.search_engine.core.config import settings
from src.search_engine.database.database import get_db
from src.search_engine.deps import get_current_user, get_usage_request
from src.search_engine.document_router import router as document_router
from src.search_engine.metrics_router import router as metrics_router
from src.search_engine.indexing_worker import run as run_indexing_worker
from src.search_engine.preferences_router import router as preferences_router
from src.search_engine.main import app as graph_app  # عشان ما نخلطه مع: app = FastAPI() ( لا نستخدم نفس الاسم)
from src.search_engine.main import AgentStreamMetadata, stream_agent
from src.search_engine.models.user import User
from src.search_engine.schemas.chat import ChatRequest, ChatResponse
from src.search_engine.services.chat_service import ChatService, ConversationNotFoundError
from src.search_engine.services.document_service import (
    DocumentNotFoundError,
    DocumentService,
)
from src.search_engine.rag.answering import RagAnswerResult, SourceReference
from src.search_engine.rag.generation import RagGenerationError
from src.search_engine.research.presentation import derive_answer_presentation
from src.search_engine.services.rag_answer_service import RagAnswerService
from src.search_engine.services.observability_service import UsageRecord
from src.search_engine.repositories.usage_repository import UsageRepository
from src.search_engine.services.retrieval_service import (
    RetrievalDocumentAccessError,
    RetrievalDocumentUnavailableError,
    RetrievalError,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Run the durable queue consumer automatically with this API process."""
    worker = None
    if settings.indexing_worker_embedded_enabled:
        worker = asyncio.create_task(
            run_indexing_worker(), name="document-indexing-worker"
        )
        logger.info("Embedded document indexing worker started")
    try:
        yield
    finally:
        if worker is not None:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(
    conversation_router,
    prefix="/api/conversations",
    tags=["conversations"],
)
app.include_router(document_router, prefix="/api/documents", tags=["documents"])
app.include_router(metrics_router, prefix="/api/metrics", tags=["metrics"])
app.include_router(preferences_router, prefix="/api/preferences", tags=["preferences"])


def error_response(status_code: int, message: str) -> JSONResponse:
    # Keep every error body on the same contract the frontend can display:
    # { "error": "Human readable message" }
    return JSONResponse(status_code=status_code, content={"error": message})


@app.exception_handler(RequestValidationError)
async def handle_invalid_request(request: Request, exc: RequestValidationError):
    # FastAPI would otherwise return 422 with { "detail": [...] }.
    # Map missing/invalid fields to HTTP 400 and our { "error": ... } shape.
    safe_errors = [
        {"location": list(error.get("loc", ())), "type": error.get("type", "invalid")}
        for error in exc.errors()
    ]
    logger.warning("Invalid request body fields: %s", safe_errors)

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
_EMPTY_QUERY = "Please enter a question."
_CONVERSATION_NOT_FOUND = "Conversation not found."
_DOCUMENT_UNAVAILABLE = "One or more selected documents are unavailable."
_DOCUMENT_NOT_INDEXED = "One or more selected documents are not indexed and available."
_RETRIEVAL_FAILED = "Document retrieval is temporarily unavailable. Please try again."
_GENERATION_FAILED = "The document answer could not be generated. Please try again."
_RESEARCH_TIMEOUT = "Deep Research reached its execution time limit."


def graph_thread_id(conversation_id: uuid.UUID) -> str:
    """LangGraph in-memory key. Not an identity claim — ownership was already checked."""
    return str(conversation_id)


def citation_payload(source: SourceReference) -> dict:
    return {
        "label": source.label,
        "document_id": str(source.document_id),
        "chunk_id": str(source.chunk_id),
        "filename": source.filename,
        "page_number": source.page_number,
        "evidence_excerpt": source.evidence_excerpt,
    }


def web_citation_payload(source: dict) -> dict:
    """Copy only the normalized provenance fields returned by the search tool."""
    return {
        "origin": "web",
        "title": source.get("title", "Web source"),
        "url": source.get("url", ""),
        "evidence_excerpt": source.get("evidence_excerpt", ""),
        "published_date": source.get("published_date"),
        "retrieved_at": source.get("retrieved_at"),
        "publisher": source.get("publisher"),
        "author": source.get("author"),
        "source_type": source.get("source_type", "unspecified"),
        "quality_notes": source.get("quality_notes", []),
    }


async def resolve_chat_attachments(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    document_ids: list[uuid.UUID],
) -> list[dict]:
    """Resolve visible attachment metadata without trusting client filenames."""
    if not document_ids:
        return []
    service = DocumentService(db)
    attachments: list[dict] = []
    for document_id in document_ids:
        try:
            document = await service.get_for_user(
                document_id=document_id,
                user_id=user_id,
            )
        except DocumentNotFoundError as exc:
            raise RetrievalDocumentAccessError(
                "One or more requested documents are unavailable."
            ) from exc
        if document.indexing_status != "completed":
            raise RetrievalDocumentUnavailableError(
                "One or more selected documents are not indexed and available."
            )
        attachments.append(
            {
                "document_id": str(document.id),
                "filename": document.original_filename,
                "content_type": document.content_type,
                "file_size": document.file_size,
                "processing_status": document.processing_status,
                "indexing_status": document.indexing_status,
            }
        )
    return attachments


async def answer_document_turn(
    *,
    db: AsyncSession,
    service: ChatService,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    query: str,
    document_ids: list[uuid.UUID],
    response_depth: str = "auto",
    response_language: str = "auto",
) -> RagAnswerResult:
    result = await RagAnswerService(db).answer(
        user_id=user_id,
        question=query,
        document_ids=document_ids or None,
        response_depth=response_depth,
        response_language=response_language,
    )
    await persist_document_answer(service, user_id, conversation_id, result)
    return result


async def persist_document_answer(service: ChatService, user_id: uuid.UUID, conversation_id: uuid.UUID, result: RagAnswerResult) -> None:
    presentation = derive_answer_presentation(result.answer).model_dump()
    await service.add_assistant_message(
        user_id=user_id,
        conversation_id=conversation_id,
        content=result.answer,
        mode="documents",
        status=result.status.value,
        citations=[citation_payload(source) for source in result.citations],
        presentation=presentation,
    )


def document_error_response(exc: Exception) -> JSONResponse:
    if isinstance(exc, RetrievalDocumentAccessError):
        return error_response(404, _DOCUMENT_UNAVAILABLE)
    if isinstance(exc, RetrievalDocumentUnavailableError):
        return error_response(409, _DOCUMENT_NOT_INDEXED)
    if isinstance(exc, RetrievalError):
        return error_response(503, _RETRIEVAL_FAILED)
    return error_response(503, _GENERATION_FAILED)


def record_rag_usage(usage: UsageRecord, result: RagAnswerResult) -> None:
    usage.retrieved_chunk_count = result.retrieved_chunk_count
    usage.source_count = len(result.sources)
    usage.citation_count = len(result.citations)
    usage.generation_seconds = float(result.generation_seconds or 0)
    usage.retrieval_seconds = float(result.metadata.get("retrieval_seconds", 0))
    usage.input_tokens = int(result.usage.get("input_tokens", 0))
    usage.output_tokens = int(result.usage.get("output_tokens", 0))


def record_research_usage(
    usage: UsageRecord,
    *,
    citations: list[dict],
    plan: list[str],
    summary: dict | None,
) -> None:
    usage.source_count = len(citations)
    usage.citation_count = len(citations)
    usage.research_iterations = len(plan)
    if summary:
        usage.search_count = int(summary.get("search_count", 0) or 0)
        usage.tavily_seconds = float(summary.get("tavily_seconds", 0) or 0)


@app.get("/")
def root():
    return {"message": "AI Search Engine API is running"}


@app.post("/chat")
async def chat(
    request: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    usage: UsageRecord = Depends(get_usage_request),
):
    usage.mode = request.mode
    usage.research_mode = request.research_mode
    query = (request.query or "").strip()
    if not query:
        return error_response(400, _EMPTY_QUERY)

    service = ChatService(db)
    effective_document_ids = list(request.document_ids)
    if (
        request.mode == "documents"
        and not effective_document_ids
        and request.conversation_id is not None
    ):
        try:
            effective_document_ids = await service.get_associated_document_ids(
                user_id=user.id, conversation_id=request.conversation_id
            )
        except ConversationNotFoundError:
            return error_response(404, _CONVERSATION_NOT_FOUND)
    general_history: list[tuple[str, str]] = []
    if request.mode == "general" and request.conversation_id is not None:
        try:
            general_history = await service.get_bounded_general_history(
                user_id=user.id,
                conversation_id=request.conversation_id,
            )
        except ConversationNotFoundError:
            return error_response(404, _CONVERSATION_NOT_FOUND)
    try:
        attachments = await resolve_chat_attachments(
            db=db,
            user_id=user.id,
            document_ids=effective_document_ids if request.mode == "documents" else [],
        )
    except (RetrievalDocumentAccessError, RetrievalDocumentUnavailableError) as exc:
        return document_error_response(exc)
    try:
        conversation = await service.start_user_turn(
            user_id=user.id,
            conversation_id=request.conversation_id,
            query=query,
            mode=request.mode,
            document_ids=effective_document_ids,
            attachments=attachments,
            conversation_mode=(
                "documents" if request.mode == "documents"
                else "deep" if request.research_mode == "deep" else "general"
            ),
            documents_verified=True,
        )
    except ConversationNotFoundError:
        return error_response(404, _CONVERSATION_NOT_FOUND)
    usage.conversation_id = conversation.id

    if request.mode == "documents":
        # Persist the user turn before RAG releases its read transaction.
        await db.commit()
        try:
            result = await answer_document_turn(
                db=db,
                service=service,
                user_id=user.id,
                conversation_id=conversation.id,
                query=query,
                document_ids=effective_document_ids,
                response_depth=request.response_depth,
                response_language=request.response_language,
            )
        except (RetrievalError, RagGenerationError) as exc:
            usage.mark_error(quota="quota" in str(exc).lower())
            logger.warning(
                "Document chat failed for conversation_id=%s error_type=%s",
                conversation.id,
                type(exc).__name__,
            )
            return document_error_response(exc)
        record_rag_usage(usage, result)
        await UsageRepository(db).add(
            request_id=usage.request_id, user_id=user.id,
            conversation_id=conversation.id, provider="gemini",
            operation="generation", status="success", model=settings.rag_answer_model,
            input_tokens=result.usage.get("input_tokens"),
            output_tokens=result.usage.get("output_tokens"),
            latency_ms=round(float(result.generation_seconds or 0) * 1000),
        )
        return ChatResponse(
            answer=result.answer,
            conversation_id=conversation.id,
            mode="documents",
            status=result.status.value,
            citations=[citation_payload(source) for source in result.citations],
            presentation=derive_answer_presentation(result.answer),
        )

    thread_id = graph_thread_id(conversation.id)

    try:
        invocation = asyncio.to_thread(
            graph_app.invoke,
            {
                "session_id": thread_id,
                "query": query,
                "history": general_history,
                "research_mode": request.research_mode,
                "response_depth": request.response_depth,
                "response_language": request.response_language,
            },
        )
        result = (
            await asyncio.wait_for(
                invocation,
                timeout=settings.research_max_execution_seconds,
            )
            if request.research_mode == "deep"
            else await invocation
        )
    except TimeoutError:
        usage.mark_error()
        return error_response(504, _RESEARCH_TIMEOUT)
    except Exception:
        usage.mark_error()
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

    web_citations = [
        web_citation_payload(item)
        for item in (result.get("web_sources", []) if isinstance(result, dict) else [])
        if isinstance(item, dict)
    ]
    research_plan = [
        item
        for item in (result.get("research_plan", []) if isinstance(result, dict) else [])
        if isinstance(item, str)
    ]
    research_summary = (
        result.get("research_summary")
        if isinstance(result, dict) and isinstance(result.get("research_summary"), dict)
        else None
    )
    record_research_usage(
        usage,
        citations=web_citations,
        plan=research_plan,
        summary=research_summary,
    )
    usage_repo = UsageRepository(db)
    await usage_repo.add(
        request_id=usage.request_id, user_id=user.id,
        conversation_id=conversation.id, provider="gemini", operation="generation",
        status="success", model=settings.general_chat_model,
        request_count=2 if request.research_mode == "deep" else 1,
        estimated=True,
    )
    if research_summary and research_summary.get("search_count"):
        await usage_repo.add(
            request_id=usage.request_id, user_id=user.id,
            conversation_id=conversation.id, provider="tavily", operation="search",
            status="success", request_count=int(research_summary["search_count"]),
            latency_ms=round(float(research_summary.get("tavily_seconds", 0)) * 1000),
        )
    evidence_conflicts = [
        item
        for item in (
            result.get("evidence_conflicts", []) if isinstance(result, dict) else []
        )
        if isinstance(item, dict)
    ]
    presentation = derive_answer_presentation(answer).model_dump()
    try:
        await service.add_assistant_message(
            user_id=user.id,
            conversation_id=conversation.id,
            content=answer,
            mode="general",
            web_citations=web_citations,
            research_plan=research_plan,
            research_summary=research_summary,
            evidence_conflicts=evidence_conflicts,
            presentation=presentation,
        )
    except ConversationNotFoundError:
        return error_response(404, _CONVERSATION_NOT_FOUND)

    return ChatResponse(
        answer=answer,
        conversation_id=conversation.id,
        web_citations=web_citations,
        research_plan=research_plan,
        research_summary=research_summary,
        evidence_conflicts=evidence_conflicts,
        presentation=presentation,
    )


def sse_event(payload: dict) -> str:
    # Server-Sent Events: one JSON object per "data:" line, blank line flush.
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    usage: UsageRecord = Depends(get_usage_request),
):
    usage.mode = request.mode
    usage.research_mode = request.research_mode
    query = (request.query or "").strip()
    if not query:
        return error_response(400, _EMPTY_QUERY)

    service = ChatService(db)
    effective_document_ids = list(request.document_ids)
    if (
        request.mode == "documents"
        and not effective_document_ids
        and request.conversation_id is not None
    ):
        try:
            effective_document_ids = await service.get_associated_document_ids(
                user_id=user.id, conversation_id=request.conversation_id
            )
        except ConversationNotFoundError:
            return error_response(404, _CONVERSATION_NOT_FOUND)
    general_history: list[tuple[str, str]] = []
    if request.mode == "general" and request.conversation_id is not None:
        try:
            general_history = await service.get_bounded_general_history(
                user_id=user.id,
                conversation_id=request.conversation_id,
            )
        except ConversationNotFoundError:
            return error_response(404, _CONVERSATION_NOT_FOUND)
    try:
        attachments = await resolve_chat_attachments(
            db=db,
            user_id=user.id,
            document_ids=effective_document_ids if request.mode == "documents" else [],
        )
    except (RetrievalDocumentAccessError, RetrievalDocumentUnavailableError) as exc:
        return document_error_response(exc)
    try:
        conversation = await service.start_user_turn(
            user_id=user.id,
            conversation_id=request.conversation_id,
            query=query,
            mode=request.mode,
            document_ids=effective_document_ids,
            attachments=attachments,
            conversation_mode=(
                "documents" if request.mode == "documents"
                else "deep" if request.research_mode == "deep" else "general"
            ),
            documents_verified=True,
        )
    except ConversationNotFoundError:
        return error_response(404, _CONVERSATION_NOT_FOUND)
    usage.conversation_id = conversation.id

    conversation_id = conversation.id
    user_id = user.id
    thread_id = graph_thread_id(conversation_id)

    if request.mode == "documents":
        await db.commit()

        async def generate_document_answer():
            try:
                yield sse_event({"conversation_id": str(conversation_id)})
                result = None
                answer_stream = RagAnswerService(db).stream_answer(
                    user_id=user_id,
                    question=query,
                    document_ids=effective_document_ids,
                    response_depth=request.response_depth,
                    response_language=request.response_language,
                )
                try:
                    async for event in answer_stream:
                        if isinstance(event, str):
                            yield sse_event({'delta': event, 'provisional': True})
                        else:
                            result = event
                finally:
                    await answer_stream.aclose()
                if result is None:
                    raise RagGenerationError('Document stream did not complete.')
                persistence_started = time.perf_counter()
                await persist_document_answer(service, user_id, conversation_id, result)
                record_rag_usage(usage, result)
                await UsageRepository(db).add(
                    request_id=usage.request_id, user_id=user_id,
                    conversation_id=conversation_id, provider="gemini",
                    operation="generation", status="success", model=settings.rag_answer_model,
                    input_tokens=result.usage.get("input_tokens"),
                    output_tokens=result.usage.get("output_tokens"),
                    latency_ms=round(float(result.generation_seconds or 0) * 1000),
                )
                citations = [citation_payload(source) for source in result.citations]
                presentation = derive_answer_presentation(result.answer).model_dump()
                await db.commit()
                result.metadata['persistence_seconds'] = time.perf_counter()-persistence_started
                # Final attribution only: never re-send the accumulated answer.
                yield sse_event(
                    {
                        "mode": "documents",
                        "status": result.status.value,
                        "citations": citations,
                        "presentation": presentation,
                    }
                )
                yield sse_event(
                    {
                        "done": True,
                        "conversation_id": str(conversation_id),
                        "mode": "documents",
                        "status": result.status.value,
                    }
                )
            except asyncio.CancelledError:
                usage.mark_error()
                await db.rollback()
                raise
            except (RetrievalError, RagGenerationError) as exc:
                await db.rollback()
                usage.mark_error(quota="quota" in str(exc).lower())
                logger.warning(
                    "Streaming document chat failed for conversation_id=%s error_type=%s",
                    conversation_id,
                    type(exc).__name__,
                )
                response = document_error_response(exc)
                yield sse_event({"error": json.loads(response.body)["error"], 'discard_partial': True})
            except Exception as exc:
                await db.rollback()
                usage.mark_error()
                logger.warning('Document streaming failure error_type=%s', type(exc).__name__)
                yield sse_event({'error': 'The document answer could not be completed. Please try again.', 'discard_partial': True})

        return StreamingResponse(
            generate_document_answer(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def generate():
        try:
            yield sse_event({"conversation_id": str(conversation_id)})
            iterator = stream_agent(
                thread_id,
                query,
                history=general_history,
                research_mode=request.research_mode,
                response_depth=request.response_depth,
                response_language=request.response_language,
            )
            yielded = False
            answer = ""
            web_citations: list[dict] = []
            research_plan: list[str] = []
            research_summary: dict | None = None
            evidence_conflicts: list[dict] = []
            research_deadline = (
                asyncio.get_running_loop().time() + settings.research_max_execution_seconds
            )

            while True:
                next_item = asyncio.to_thread(next, iterator, _STREAM_END)
                if request.research_mode == "deep":
                    remaining = research_deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        yield sse_event({"error": _RESEARCH_TIMEOUT})
                        usage.mark_error()
                        return
                    try:
                        delta = await asyncio.wait_for(next_item, timeout=remaining)
                    except TimeoutError:
                        yield sse_event({"error": _RESEARCH_TIMEOUT})
                        usage.mark_error()
                        return
                else:
                    delta = await next_item
                if delta is _STREAM_END:
                    break
                if isinstance(delta, AgentStreamMetadata):
                    web_citations = [
                        web_citation_payload(item) for item in delta.web_sources
                    ]
                    research_plan = list(delta.research_plan)
                    research_summary = delta.research_summary
                    evidence_conflicts = list(delta.evidence_conflicts)
                    continue
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
                record_research_usage(
                    usage,
                    citations=web_citations,
                    plan=research_plan,
                    summary=research_summary,
                )
                usage_repo = UsageRepository(db)
                await usage_repo.add(
                    request_id=usage.request_id, user_id=user_id,
                    conversation_id=conversation_id, provider="gemini",
                    operation="generation", status="success",
                    model=settings.general_chat_model,
                    request_count=2 if request.research_mode == "deep" else 1,
                    estimated=True,
                )
                if research_summary and research_summary.get("search_count"):
                    await usage_repo.add(
                        request_id=usage.request_id, user_id=user_id,
                        conversation_id=conversation_id, provider="tavily",
                        operation="search", status="success",
                        request_count=int(research_summary["search_count"]),
                        latency_ms=round(float(research_summary.get("tavily_seconds", 0)) * 1000),
                    )
                presentation = derive_answer_presentation(answer).model_dump()
                await service.add_assistant_message(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    content=answer,
                    mode="general",
                    web_citations=web_citations,
                    research_plan=research_plan,
                    research_summary=research_summary,
                    evidence_conflicts=evidence_conflicts,
                    presentation=presentation,
                )
            except ConversationNotFoundError:
                yield sse_event({"error": _CONVERSATION_NOT_FOUND})
                return

            if web_citations or research_plan or presentation["type"] != "standard":
                yield sse_event(
                    {
                        "mode": "general",
                        "web_citations": web_citations,
                        "research_plan": research_plan,
                        "research_summary": research_summary,
                        "evidence_conflicts": evidence_conflicts,
                        "presentation": presentation,
                    }
                )
            yield sse_event({"done": True, "conversation_id": str(conversation_id)})
        except Exception:
            usage.mark_error()
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


