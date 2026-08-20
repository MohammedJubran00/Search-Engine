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



from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.search_engine.main import app as graph_app # عشان ما نخلطه مع: app = FastAPI() ( لا نستخدم نفس الاسم)
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
    result= graph_app.invoke(
        {
            "session_id": request.session_id,
            "query":request.query
        })
    return {
        "answer": to_answer_text(result["answer"])
    }

    