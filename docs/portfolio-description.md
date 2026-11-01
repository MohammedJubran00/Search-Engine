# Portfolio project description

## AI Research Assistant

I built a locally runnable full-stack research assistant with two evidence
paths: grounded question answering over private user-owned documents and
bounded web research for general questions. The backend uses FastAPI, async
SQLAlchemy, PostgreSQL/pgvector, LangGraph, Gemini, and Tavily; the frontend
uses React 19, Vite, and SSE.

Users authenticate with typed JWTs, upload PDF/DOCX/TXT files, explicitly
confirm paid indexing, and receive answers linked to authenticated chunks,
filenames, pages, and excerpts. Retrieval filters by owner before ranking, and
document answers must validate source labels or abstain when evidence is weak.

General Chat preserves bounded context and accepts citations only from actual
search-tool output. Deep Research creates typed subquestions with deduplicated
search, iteration, and time budgets. The UI shows plans, citations, source
notes, numeric conflicts, structured comparisons/timelines, document state,
and private content-free usage metrics.

Quality work includes PDF boilerplate suppression, deterministic retrieval
metrics, citation/abstention fixtures, prompt-injection boundaries, IDOR tests,
resource limits, provider-failure handling, and a Git-ignored bilingual human
evaluation protocol. Automated tests use fake providers and incur no API cost.

The project has not been deployed or claimed as production-ready. Stateless
JWT revocation, localStorage tokens, process-local rate limits, unsandboxed file
parsing, and absent private benchmark results are documented limitations.
