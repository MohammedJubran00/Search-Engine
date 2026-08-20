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
from pydantic import BaseModel

from src.search_engine.main import app as graph_app # عشان ما نخلطه مع: app = FastAPI() ( لا نستخدم نفس الاسم)
app = FastAPI()

class ChatRequest(BaseModel):
    query: str


@app.get("/")
def root():
    return {"message": "AI Search Engine API is running"}


@app.post("/chat")
def chat(request:ChatRequest):
    result= graph_app.invoke(
        {
            "query":request.query
        })
    return {
        "answer":result["answer"]
    }

    