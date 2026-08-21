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



import json
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from src.search_engine.main import app as graph_app # عشان ما نخلطه مع: app = FastAPI() ( لا نستخدم نفس الاسم)
from src.search_engine.main import stream_agent

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

class ChatRequest(BaseModel):
    session_id: str
    query: str


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

    error_text = " ".join(messages) if messages else "Invalid request. Check session_id and query."
    return error_response(400, error_text)


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    # Last-resort net: any uncaught exception should become a 500 JSON
    # response instead of taking the Uvicorn worker down.
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


@app.get("/")
def root():
    return {"message": "AI Search Engine API is running"}


@app.post("/chat")
def chat(request:ChatRequest):
    session_id = (request.session_id or "").strip()
    query = (request.query or "").strip()

    # Reject empty input here so we never start LangGraph / Gemini / Tavily
    # for a question that cannot succeed.
    if not session_id:
        return error_response(400, "session_id is required.")
    if not query:
        return error_response(400, "Please enter a question.")

    try:
        # Isolate LangGraph execution so Gemini, Tavily, or graph failures
        # become an HTTP 500 instead of a FastAPI crash.
        result = graph_app.invoke(
            {
                "session_id": session_id,
                "query": query,
            }
        )
    except Exception:
        logger.exception("LangGraph invoke failed for session_id=%s", session_id)
        return error_response(
            500,
            "Something went wrong while generating an answer. Please try again.",
        )

    try:
        answer = to_answer_text(result.get("answer") if isinstance(result, dict) else None)
    except Exception:
        # Conversion is separate so a malformed model payload cannot crash /chat.
        logger.exception("Failed to convert LangGraph answer to text")
        return error_response(
            500,
            "The search engine returned an unreadable answer. Please try again.",
        )

    if not answer:
        logger.error("LangGraph returned an empty answer for session_id=%s", session_id)
        return error_response(
            500,
            "The search engine returned an empty answer. Please try again.",
        )

    return {
        "answer": answer
    }


def sse_event(payload: dict) -> str:
    # Server-Sent Events: one JSON object per "data:" line, blank line flush.
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/chat/stream")
def chat_stream(request: ChatRequest):
    session_id = (request.session_id or "").strip()
    query = (request.query or "").strip()

    # Same input rules as /chat so streaming cannot start on an empty prompt.
    if not session_id:
        return error_response(400, "session_id is required.")
    if not query:
        return error_response(400, "Please enter a question.")

    def generate():
        # Generator keeps the HTTP connection open and flushes each token
        # so the React client can render the answer as it is produced.
        try:
            yielded = False
            for delta in stream_agent(session_id, query):
                if not delta:
                    continue
                yielded = True
                yield sse_event({"delta": delta})

            if not yielded:
                yield sse_event(
                    {
                        "error": "The search engine returned an empty answer. Please try again."
                    }
                )
                return

            yield sse_event({"done": True})
        except Exception:
            logger.exception("Streaming chat failed for session_id=%s", session_id)
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

    