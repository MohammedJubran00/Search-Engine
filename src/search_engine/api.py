# HTTP Requests
#      ↓
# FastAPI
#      ↓
# استدعاء LangGraph
#      ↓
# JSON Response

from fastapi import FastAPI
app = FastAPI()


@app.get("/")
def root():
    return {"message": "AI Search Engine API is running"}