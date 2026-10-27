# AI Search Engine

FastAPI/LangGraph chat application using Gemini, Tavily, PostgreSQL, async
SQLAlchemy, JWT authentication, persisted conversations, and SSE streaming.

## Development setup

1. Install Python 3.14 and PostgreSQL.
2. Copy `.env.example` to `.env` and replace placeholders. Never commit `.env`.
3. Install the project with `uv sync`.
4. Enable pgvector and apply schema migrations with `uv run alembic upgrade head`.
5. Run the API with `uv run uvicorn src.search_engine.api:app --reload`.
6. In `frontend`, install with `npm ci` and run with `npm run dev`.

The PostgreSQL server must have the pgvector extension files installed. The
Alembic migration runs `CREATE EXTENSION IF NOT EXISTS vector`; the database
role therefore needs permission to create that extension. Managed PostgreSQL
providers may require enabling pgvector in their console first. No production
infrastructure is changed by this repository preparation.

## RAG preparation status

The environment includes PDF (`pymupdf`), DOCX (`python-docx`), configurable
text splitting (`langchain-text-splitters`), and PostgreSQL vector support
(`pgvector`). Gemini embeddings will reuse the installed
`langchain-google-genai`/`google-genai` integration.

Only contracts and configuration have been added under
`src/search_engine/rag`. Upload routes, file persistence, document/chunk tables,
embedding calls, retrieval, prompt grounding, and Tavily fallback policy are
not implemented yet.

## Recommended RAG implementation sequence

1. Add document and chunk ORM models/migrations with indexed `user_id` foreign
   keys and a vector column matching `RAG_EMBEDDING_DIMENSIONS`.
2. Add authenticated upload/list/delete endpoints with strict PDF, DOCX, and
   TXT validation and generated storage names.
3. Implement parsers and the configured recursive text splitter.
4. Add batched Gemini document/query embeddings with retry and quota handling.
5. Implement a pgvector repository whose queries always include `user_id` and
   optional document IDs before similarity ordering.
6. Build an ingestion service with explicit status/error tracking and cleanup.
7. Add retrieval to the existing chat service and SSE path, including citations
   and a deliberate Tavily fallback rule.
8. Add unit, ownership/isolation, parser, retrieval, streaming, and end-to-end
   tests before enabling the feature in the frontend.
