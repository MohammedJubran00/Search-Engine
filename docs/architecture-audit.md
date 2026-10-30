# Architecture and Security Baseline

Audit date: 2026-10-31

Branch: `codex/rag-phase7`

Audited commit: `ebe1ef1` plus the preserved, uncommitted Phase 7/7.5 working tree

## Scope and baseline

This audit records the implementation that exists now. It does not redesign the
application, call Gemini or Tavily, apply migrations, or modify runtime behavior.

The working tree was already dirty when this task began: 30 tracked files were
modified and 4 frontend files were untracked. Those changes implement substantial
Phase 7/7.5 chat, attachment, 100 MiB upload, and manual-indexing work. They were
preserved and are not part of the Task 01 commit.

Verification results:

- Backend: `uv run pytest -q` — 147 passed, 0 failed, 2 deprecation warnings.
- Frontend utility tests: `npm test` — 4 passed, 0 failed.
- Frontend lint: `npm run lint` — passed.
- Frontend production build: `npm run build` — passed.
- Alembic: one linear head, `f7a9c2d4e6b8`.
- Local database: already at `f7a9c2d4e6b8 (head)` before this audit; no migration
  was applied.

The warnings are a Google GenAI Python 3.17 compatibility deprecation and the
LangGraph `create_react_agent` move to `langchain.agents.create_agent`.

## Current architecture

### Backend and persistence

- `src/search_engine/api.py` owns the FastAPI application, global error mapping,
  General/Document Chat dispatch, and JSON/SSE chat responses.
- Auth, conversations, and documents have separate routers. Services contain the
  main use cases and repositories contain ownership-scoped SQLAlchemy queries.
- PostgreSQL stores users, conversations, messages, document metadata, indexing
  state, chunks, and 1536-dimensional pgvector embeddings.
- The migration chain is linear: users -> conversations/messages -> pgvector ->
  documents/chunks -> indexing state and chunk offsets.
- Conversation message metadata is encoded in a versioned JSON envelope inside
  the existing message text column. Legacy plain-text messages remain readable.

### Authentication and sessions

- Signup validates email and password strength and stores bcrypt hashes.
- Login issues short-lived access JWTs and longer-lived refresh JWTs. Protected
  routes derive identity from `JWT.sub`; request bodies do not supply user IDs.
- The frontend retries one 401 through the refresh endpoint and then redirects to
  login. Logout requires an access token and clears browser tokens.
- Access and refresh tokens are stored in `localStorage`. Refresh tokens are
  stateless and are not revoked or tracked server-side.

### General Chat, LangGraph, Tavily, and SSE

- General Chat defaults to the existing LangGraph ReAct agent using Gemini and a
  Tavily tool. The streaming route forwards model deltas as SSE and persists the
  completed assistant answer.
- Agent history is held in the process-local `main.sessions` dictionary. Database
  messages and LangGraph memory are separate sources of state: persisted history
  can be displayed after restart, but it is not reconstructed into agent context.
- Tavily results are flattened into prompt text; source metadata is not currently
  persisted or returned as validated web citations.

### Document lifecycle and RAG

- Authenticated PDF, DOCX, and TXT uploads use generated private storage names,
  streamed bounded writes, metadata validation, parser limits, rollback cleanup,
  and ownership-scoped list/get/delete operations.
- PDF parsing preserves pages and conservatively removes verified repeated edge
  boilerplate. DOCX expanded-size protection is independent of upload size.
- Explicit indexing re-parses, structure-chunks, requests batched Gemini retrieval
  embeddings, L2-normalizes vectors, and atomically replaces a document generation.
- Retrieval uses exact pgvector cosine distance with mandatory user ownership,
  completed-index checks, optional document filters, stable ordering, and bounded
  controls.
- Grounded generation builds bounded evidence, treats document text as untrusted,
  validates citation labels against retrieved chunks, and supports explicit
  insufficient-evidence answers.
- Document Chat routes directly to `RagAnswerService`; no model is used to classify
  chat mode. The current working tree adds explicit attachment metadata and manual
  browser indexing without automatic embedding on upload.

### Frontend

- Login and signup are static JavaScript pages. The authenticated application is
  React 19 with a Vite proxy for `/api` and `/chat`.
- The React application restores the latest conversation, streams chat responses,
  displays document management, and refreshes JWTs through one shared fetch helper.
- The current uncommitted work adds explicit chat modes, composer attachments,
  existing-document attachment, persisted attachment cards, citations, and an
  explicit "Prepare for AI" action.

### Evaluations

- The backend suite covers auth, ownership, upload/parsing, chunking, embeddings,
  atomic indexing, retrieval, RAG context/generation, citations, abstention, PDF
  boilerplate, and chat routing with fake providers.
- Synthetic labeled retrieval and answer fixtures cover relevance, citation, and
  abstention mechanics, including Arabic cases. They are not claimed as real-world
  quality results.
- Frontend coverage is currently limited to four Node tests for chat payload/SSE
  helpers and document-size validation. There is no component or browser E2E suite.

## Security findings

### High priority

1. **Validation logging can capture secrets.** The global FastAPI validation
   handler logs `exc.errors()`. Pydantic error entries may contain rejected input,
   including passwords or refresh tokens. Logging must be changed to retain only
   safe field/type information before production-style use.
2. **Refresh tokens cannot be revoked.** Logout only clears client storage, token
   rotation does not invalidate the previous refresh token, and there is no server
   session/token-family record. A stolen refresh token remains valid until expiry.
3. **No abuse or resource controls.** Login, refresh, chat, upload, indexing, Gemini,
   and Tavily routes have no per-user/IP rate limit or global concurrency ceiling.
   Existing request, retrieval, and generation bounds help but do not prevent brute
   force, quota exhaustion, or concurrent resource exhaustion.

### Medium priority

4. **Browser tokens are exposed to same-origin script.** Both JWTs are in
   `localStorage`, increasing the impact of a stored or dependency-based XSS. The UI
   uses React/Markdown rather than raw HTML, but a production-style session design
   should evaluate secure HttpOnly/SameSite cookies and CSRF protection.
5. **CORS allows every origin.** The API config uses `allow_origins=["*"]`. This is
   convenient locally but should become an explicit environment-backed allowlist.
6. **General Chat memory is process-local and unbounded.** It is lost on restart,
   differs across workers, has no deterministic token/history bound, and can grow
   without limit. It also prevents reliable persisted follow-up behavior.
7. **Private prompts are logged in one provider failure path.** Tavily failures log
   the raw query. Provider exception details are also returned as tool text and may
   be repeated by the model. Use sanitized operational events and generic tool
   failures.
8. **Web evidence has weaker trust boundaries than RAG evidence.** Web pages are
   inserted as plain tool text without structured provenance validation or an
   explicit instruction that retrieved content cannot override system policy.

### Existing protections confirmed

- No tracked `.env`, uploaded documents, private keys, credential files, or obvious
  provider-key patterns were found. Only placeholder `.env.example` files are
  tracked, and `.env` plus `data/uploads/` are ignored.
- Passwords are bcrypt-hashed and authentication failures do not reveal whether an
  email exists.
- Document, retrieval, indexing, and conversation lookups are scoped by the
  authenticated user; foreign and missing resources share non-disclosing errors.
- Upload filenames cannot contain paths, storage names are generated, partial files
  are cleaned up, and storage paths are excluded from public schemas.
- RAG provider errors are sanitized and retrieved document text is bounded and
  explicitly separated as untrusted evidence.

## Gap analysis and implementation map

| Roadmap area | Current state | Next scoped work |
| --- | --- | --- |
| Task 02: chat attachments | Substantially implemented but uncommitted | Review the preserved diff, add component/history rendering tests, then commit only Task 02 scope. |
| Task 03: large files/manual indexing | Substantially implemented but mixed into the same working tree | Separate Task 03 files/hunks from Task 02, validate cancellation/large-document behavior, and make its own commit. |
| Task 04: adaptive RAG | Exact retrieval and grounded answers are complete | Add measured token-based full-context eligibility, deterministic bounded history, and comparative fake-provider evaluation. |
| Task 05: web citations/follow-ups | Tavily text is available to the agent | Preserve structured result metadata, validate URLs, persist citations, and replace process-only follow-up state. |
| Tasks 06-07: research planning | Not implemented | Add optional bounded typed planning and conditional multi-step research without touching Document Chat. |
| Task 08: credibility/conflicts | Not implemented | Add transparent evidence attributes and deterministic comparable-claim checks before optional model verification. |
| Task 09: structured answers | Markdown only | Add validated presentation schemas and accessible React renderers with safe fallback. |
| Task 10: observability/quotas | Basic logs and local config bounds only | Add privacy-preserving per-user metrics, server-side ceilings, and an ownership-protected dashboard. |
| Task 11: E2E/security | Strong backend unit/service coverage; thin frontend coverage | Add browser/component/accessibility tests, rate-limit/security regressions, and private real-document benchmark instructions. |
| Task 12: polish/docs | Root README is materially stale | Update it only after features are complete; it currently incorrectly says RAG is not implemented. |

## Recommended priority order

1. Preserve and split the current Task 02/03 work into their required scoped
   commits; do not accidentally include this audit or unrelated changes.
2. Remove sensitive validation/query logging and add bounded request/concurrency
   controls before expanding provider-driven workflows.
3. Replace process-local General Chat memory with deterministic context assembled
   from owned persisted messages and an explicit token budget.
4. Add validated web provenance/citations before multi-step planning increases the
   volume of untrusted web evidence.
5. Implement the remaining roadmap tasks sequentially, keeping mocked providers as
   the automated default and requiring approval for every real-provider test.

## Task 01 conclusion

The project has a solid, tested authenticated RAG core and clean ownership boundaries.
It is not yet a complete production-style research assistant: reliable multi-thread
conversation management, durable bounded agent context, verified web citations,
planning, multi-step research, source conflict analysis, structured answers,
observability, rate controls, and browser E2E coverage remain. No schema change is
needed for this audit.
