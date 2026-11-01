# RAG module boundary

This package implements the document-grounded path used by the authenticated
FastAPI chat routes. It remains separate from web research: Document Chat never
silently falls back to Tavily.

Planned flow:

1. Validate an authenticated user's PDF, DOCX, or UTF-8 TXT upload by size,
   extension, MIME type, and file signature.
2. Store it beneath `RAG_STORAGE_DIR` using a generated identifier, never a
   client-supplied path.
3. Parse text with PyMuPDF, python-docx, or the standard library.
4. Split text with `langchain-text-splitters` using the configured character
   size and overlap.
5. Queue a durable indexing job and generate vectors in the API-started worker
   (or a dedicated consumer when embedded execution is disabled).
6. Store document/chunk metadata and vectors in PostgreSQL with pgvector.
7. Require `user_id` in every document and similarity query; optional document
   filters are applied in addition to that ownership predicate.
8. Feed retrieved context into the grounded answer service and existing SSE
   path; Tavily remains exclusive to General/Deep Research modes.

The protocols in `contracts.py` keep parser, embedding, and persistence details
replaceable while matching the project's existing service/repository layering.

## Phase 1 schema decisions

- Documents are owned directly by users and are not tied to conversations. This
  keeps a document reusable across a user's conversations and matches the
  existing ownership-aware retrieval contract.
- Document deletion cascades to its chunks; user deletion cascades to owned
  documents. Chunk order is unique per document and uses a zero-based index.
- `gemini-embedding-001` is configured for 1,536-dimensional output. This is a
  supported, recommended size that permits direct pgvector `vector` HNSW or
  IVFFlat indexing while using half the vector storage of 3,072 dimensions.
- Chunk embeddings are nullable while an upload is queued and until its worker
  job generates them. The schema freezes the vector dimension at 1,536; changing
  the configured model or dimension later requires a coordinated migration and
  re-embedding of stored chunks.

## Phase 4 embedding requirements

The embedding provider uses all of the following settings together:

- `RAG_EMBEDDING_MODEL=models/gemini-embedding-001`
- `RAG_EMBEDDING_DIMENSIONS=1536` as the API output dimensionality
- `RAG_EMBEDDING_DOCUMENT_TASK_TYPE=RETRIEVAL_DOCUMENT` for chunks
- `RAG_EMBEDDING_QUERY_TASK_TYPE=RETRIEVAL_QUERY` for search queries
- `RAG_EMBEDDING_NORMALIZE=true`

`gemini-embedding-001` does not automatically normalize reduced-dimension
outputs. Phase 4 must L2-normalize every document and query vector after the
embedding response and before persistence or similarity search. It must reject
a zero-norm or incorrectly sized result rather than storing or querying it.
Document and query vectors must always use the same model, dimension, and
normalization procedure.

The installed `langchain-google-genai` embedding class accepts task type and
output dimensionality per operation. The implementation passes the
document and query task settings to their respective operations; it must not
set one global task type that overrides both paths.

## Phase 2 upload and parsing semantics

Authenticated uploads are streamed with a hard byte limit into an opaque,
server-generated file beneath `RAG_STORAGE_DIR`. Client filenames are metadata
only and are rejected if they contain path components. PDF, DOCX, and UTF-8 TXT
content is checked by signature/container/decoding and then parsed in a worker
thread. Uploaded files are private and are not mounted as static assets.
DOCX validation also limits total expanded archive bytes to
`RAG_MAX_DOCX_UNCOMPRESSED_BYTES` before parsing.

`processing_status=completed` means only that the original file was stored and its
text was successfully extracted. It does not mean chunked, embedded, or
indexed. Rejected, empty, corrupt, and scanned/image-only documents leave no
database row or stored file. `pending`, `processing`, and `failed` remain
available for later asynchronous ingestion; this synchronous workflow moves a
new row through pending and processing in its transaction, committing only the
completed state.

## Phase 3 chunking semantics

`RAG_CHUNK_SIZE` and `RAG_CHUNK_OVERLAP` are Python character counts (Unicode
code points), not tokens or UTF-8 bytes. The production chunker uses recursive
structure-aware separators in this order: blank lines, line breaks, English
and Arabic sentence punctuation, spaces, then individual characters as the
last-resort safety fallback. This keeps paragraphs, headings, sentences,
Arabic text, numbers, and technical terms intact whenever the configured size
allows it without adding a tokenizer dependency.

PDF pages are chunked independently. Blank pages produce no chunks, and every
nonblank PDF chunk retains its original one-based `page_number`. This avoids
ambiguous cross-page citations. DOCX and TXT chunks deliberately omit page
numbers. All chunks use a stable, zero-based document-wide index and record
the source filename, content type, and page-local character start/end offsets
in metadata. Chunking does not persist data or change the Phase 2 meaning of
the document `completed` status.

Before chunking, PDF parsing conservatively removes verified running
boilerplate. Only single-line text blocks inside the configured top or bottom
page margins are candidates. A candidate must recur on at least
`RAG_PDF_BOILERPLATE_MIN_PAGES` and the configured majority of document pages.
Terminal page numbers are generalized only for standalone numbers or familiar
page/footer delimiters, preventing numbered headings such as `Section 2` from
being treated as a footer. There is no global minimum chunk-length filter.
Unique page-edge text, body-position headings, dates, numbers, and short
meaningful content remain. Parser metadata records removed pattern and line
counts without recording the removed text.

Changing this preprocessing changes chunk text, indexes, offsets, and
embeddings. Previously indexed PDFs must be explicitly re-indexed to receive
the improvement; uploads and existing indexes are never changed automatically.

Inspect a trusted local document without API calls or persistence:

```powershell
.venv\Scripts\python.exe -m src.search_engine.rag.inspect_chunks path\to\file.pdf
```

The default output shows lengths, page metadata, quality flags, and short
previews. Add `--show-text` only when full local document content is safe to
print. Use `--chunk-size` and `--chunk-overlap` to compare configurations.

## Phase 4 indexing semantics

Upload parsing and vector indexing have independent lifecycle state. The
existing `documents.processing_status=completed` still means that secure
storage and text extraction succeeded. `document_index_states.status` tracks
only vector indexing with `not_indexed`, `queued`, `processing`, `completed`,
and `failed` states. A monotonically increasing generation prevents two workers
from finalizing the same document concurrently.

Successful uploads create an idempotent PostgreSQL `indexing_jobs` row and move
the vector lifecycle to `queued`. Run
`uv run python -m src.search_engine.indexing_worker` under a process supervisor.
The worker claims work with `FOR UPDATE SKIP LOCKED`, records actual stages and
completed/total chunk counts, and records each Gemini embedding request attempt
as a content-free usage event. The HTTP retry endpoint only queues work; it
never performs paid calls inline.

Indexing first commits a short ownership-scoped generation claim. Parsing,
chunking, and Gemini calls then run without an open database transaction. The
final transaction validates every vector, deletes the prior chunk set, inserts
the complete replacement, and marks that generation completed. A failure
rolls back that transaction, records a safe failure status, and leaves a prior
valid index intact. Uploads enqueue this workflow automatically.

Gemini document requests use `RETRIEVAL_DOCUMENT`; retrieval queries use
`RETRIEVAL_QUERY`. Reduced 1,536-dimensional
vectors are validated for count, finite values, and nonzero norm, then L2
normalized. Requests use configurable batches up to Gemini's 100-text limit,
bounded concurrency, exponential retry for transient capacity/rate errors,
and per-call duplicate text elimination.

The current Alembic head must be reviewed and applied before indexing.
After that, explicitly index an existing document from a trusted local shell:

```powershell
.venv\Scripts\python.exe -m src.search_engine.rag.index_document `
  <document-uuid> <owner-user-uuid>
```

This command makes real Gemini requests and consumes project quota. It prints
only identifiers and counts, never source text, vectors, or credentials.
If a worker crashed after claiming a generation, rerun with
`--supersede-processing` only after confirming that worker is stale. The new
generation invalidates the old worker, so it cannot overwrite recovered data.

## Phase 5 retrieval semantics

Semantic retrieval is an internal service and local CLI only. It is not
connected to FastAPI, chat, LangGraph, Tavily, SSE, or the frontend. The query
uses the existing `GeminiEmbeddingProvider` with `RETRIEVAL_QUERY`, 1,536
dimensions, and the same L2 normalization as stored document vectors.

PostgreSQL performs exact pgvector cosine search. Every query joins chunks to
their document and indexing state, requires the authenticated `user_id`,
requires `document_index_states.status='completed'`, and excludes null
embeddings. Optional document filters are ownership-checked before Gemini is
called. Equal distances are ordered deterministically by document ID, chunk
index, and chunk ID.

Scores use:

```text
cosine_similarity = 1 - cosine_distance
```

Similarity is not a probability and does not prove that an answer exists.
There is no universal default threshold. A minimum similarity can be supplied
for an evaluated use case; otherwise results are ranked without filtering.
Top-K defaults to `RAG_RETRIEVAL_TOP_K` and is bounded by
`RAG_RETRIEVAL_MAX_TOP_K`.

Inspect real retrieval locally (this can consume Gemini quota):

```powershell
.venv\Scripts\python.exe -m src.search_engine.rag.inspect_retrieval `
  --user-id <owner-uuid> `
  --document-id <document-uuid> `
  --query "What are the project's main goals?" `
  --top-k 5
```

The default prints short previews. Add `--show-text` only for trusted local
content. Compare labeled configurations with:

```powershell
.venv\Scripts\python.exe -m src.search_engine.rag.evaluate_retrieval `
  --dataset path\to\golden.jsonl `
  --user-id <owner-uuid> `
  --top-k 3 --top-k 5 `
  --min-similarity 0.2 --min-similarity 0.4
```

The golden JSON Lines format requires an ID, question, expected document IDs,
answerability, expected evidence, and explicit relevant chunk IDs or
document/page labels. Metrics include Hit@K, Recall@K, Precision@K, MRR, and
unanswerable-query false positives. These metrics use labels—not similarity as
a relevance judgment—and retrieval failures are reported separately.

### Exact search versus HNSW

Exact search is the Phase 5 correctness baseline. The inspected development
dataset has 42 embedded chunks across one document, far below a size where an
ANN index is justified. At 1,536 dimensions pgvector HNSW is compatible with
`vector_cosine_ops`, but it increases build time, memory, write cost, and can
trade recall for latency. Ownership and document filters are also applied
after approximate candidate selection unless query/index design accounts for
them. Re-evaluate with measured corpus size, latency, recall, and filtered
query behavior before proposing a migration such as an HNSW cosine index.

## Phase 6 grounded answer generation

`RagAnswerService` is the grounded orchestration service used by Document Chat. It accepts a
trusted user UUID, calls `SemanticRetrievalService` exactly once, ends the
read-only database transaction, builds bounded evidence, and then calls a
dedicated deterministic Gemini chat client. It is connected to FastAPI/SSE and
the frontend, but deliberately remains independent of LangGraph and Tavily.

The context builder removes empty and normalized-identical chunks, keeps rank
order, assigns stable `S1`, `S2`, ... labels, and uses fair per-source token
shares so one oversized chunk does not crowd out all other evidence. It cuts
at sentence or word boundaries and keeps document ID, chunk ID, filename,
page, rank, similarity, and a bounded evidence excerpt. The effective context
limit is the lowest of `RAG_ANSWER_MAX_CONTEXT_TOKENS` and the remaining
`RAG_ANSWER_MAX_INPUT_TOKENS` after reserving the counted system prompt,
counted question, configured output allowance, and safety margin.

Token counts use the configured Gemini model's compatible `count_tokens`
operation. Real use can therefore make quota-bearing token-count requests in
addition to one query-embedding request and one answer-generation request.
Tests inject a fake counter and never call Gemini.

Generation uses a system message separate from the user question and source
blocks. The prompt tells the model to treat source text as untrusted data,
ignore embedded instructions, use no outside knowledge or web search, and
abstain when evidence is insufficient. This separation reduces prompt-
injection risk but cannot guarantee that a generative model will never be
misled. The service also validates the JSON response, rejects unknown source
labels, requires a real citation for an answered result, and forbids citations
on abstentions. A citation is a verification pointer to retrieved evidence,
not automatic proof that every generated claim is entailed.

The result contains `answered` or `insufficient_evidence`, answer text, mapped
citations, eligible source references, retrieval/context counts, safe numeric
usage metadata when Gemini supplies it, and generation timing. Retrieval and
generation failures remain exceptions of their respective families; they are
not converted into fabricated answers. No universal similarity threshold is
treated as proof of answerability.

Example result shape:

```json
{
  "status": "answered",
  "answer": "The project aims to improve service speed [S1].",
  "citations": [
    {
      "label": "S1",
      "document_id": "...",
      "chunk_id": "...",
      "filename": "project.pdf",
      "page_number": 2,
      "evidence_excerpt": "The project aims to improve service speed."
    }
  ]
}
```

Run an explicitly authorized real-document smoke test only from a trusted
local shell (this can consume Gemini quota or incur charges):

```powershell
.venv\Scripts\python.exe -m src.search_engine.rag.ask_document `
  --user-id <owner-uuid> `
  --document-id <document-uuid> `
  --question "What are the main objectives of this project?"
```

`tests/fixtures/rag_answer_golden.jsonl` contains small English, Arabic,
abstention, conflict, and prompt-injection cases for human review. They define
expected behavior but do not claim benchmark scores. Remaining limitations
include model fallibility, retrieval misses, imperfect relevance calibration,
and excerpts that require a human to verify in the original document.

## Phase 7 chat integration

The existing `/chat` and `/chat/stream` contracts now accept an explicit
`mode` of `general` (the backward-compatible default) or `documents`.
`document_ids` is optional in document mode: an empty selection searches all
indexed documents owned by the authenticated user. General mode rejects a
document scope so context cannot accidentally cross modes. Selection is
bounded by `RAG_CHAT_MAX_DOCUMENT_SELECTION`.

Routing is deterministic at the FastAPI boundary. General mode continues to
use the unchanged LangGraph/Gemini/Tavily path. Document mode calls
`RagAnswerService` directly with the JWT-derived user ID and never falls back
to Tavily or general model knowledge. No classifier, second query embedding,
or second answer-generation request is added. Selected IDs are checked for
ownership and for a completed usable index before any Gemini request.

Document-mode JSON responses add `mode`, `status`, and validated `citations`.
For SSE, general mode retains native token deltas. Document mode uses Gemini
`astream` and incrementally decodes only the JSON `answer` string, including
fragmented Unicode escapes. It does not split an already completed answer.
Content deltas are provisional until the final JSON shape and source labels
validate. Only then is the complete assistant message committed, followed by
attribution metadata and `done`; the answer is not sent a second time.
No partial assistant message is saved on generation/validation failure or
cancellation before that commit. The UI clears invalid partial text, marks
stopped text as unsaved, requires terminal completion, and retains final
citations. A disconnect after a successful commit can still leave the valid
answer saved even if the client misses `done`.

Common complete evidence is counted once with the actual provider tokenizer;
oversized evidence retains the bounded truncation algorithm and final budget
check. Token counts are memoized only within a request. Model, production output
budget, evidence and grounding instructions remain unchanged. Native stream
requests use one SDK attempt to avoid replaying emitted content. The SDK treats
attempts=0 as defaults rather than disabling retries.

New messages use a versioned JSON envelope in the existing `messages.content`
column. The service decodes it before returning conversation history, while
legacy plain-text rows remain General Chat messages. The envelope associates
the request mode and selected document scope with the user turn and associates
answerability plus server-validated citations with the assistant turn. This
preserves reload attribution without a schema migration. Raw model citation
metadata is never persisted; only labels mapped by Phase 6 to authenticated
retrieval rows are stored.

The document API now includes `indexing_status`; the React panel disables
selection for documents without a completed index. The chat UI defaults to
General Chat, offers explicit Document Chat, clears selected scope when
returning to General Chat, shows answerability, and renders filename/page
citations without displaying internal UUIDs.

Application limits reduce accidental quota use but cannot guarantee zero
billing or override Google account/provider quotas. Real document chat may
perform one query embedding, compatible token-count operations, and one
answer generation. Quota exhaustion returns a safe error and never falls back
to another paid provider. No reranking, caching, or fallback paid service is
added by the chat path.

## Automatic attachment and indexing workflow

Uploads are available from the compact composer and the paginated Document
Library. A user can stage multiple PDF, DOCX, or TXT files, remove them before
upload, attach existing owned uploads, and see separate parsing and indexing
state. A successful upload atomically creates a durable queued job; the
request itself never waits for or makes Gemini calls. Unready attachments block
Document Chat until the supervised worker completes their vectors.

`POST /api/documents/{document_id}/index` is JWT-protected and calls the
idempotent queue service for retry/backward compatibility. Missing and foreign
documents share the same 404 response, an already completed index is returned
without another job, and duplicate active jobs are prevented by a partial
unique database index. No client-supplied user ID is accepted.

The versioned message envelope now also stores server-resolved attachment
metadata on the user turn, so filename, media type, size, and state survive a
reload without trusting client-supplied metadata or adding a migration.

## Private operational metrics

Authenticated users can inspect content-free operational totals at
`GET /api/metrics` or from the frontend Usage panel, which refreshes every
three seconds. Provider and platform events persist in PostgreSQL and are
owner-scoped. They track final request state, latency, actual Tavily calls,
Gemini generation calls, embedding attempts, and provider-reported token usage
when available. They never store prompts, answers, document text, tokens, or
credentials. Process-local request ceilings are still enforced per user with
`USAGE_DAILY_REQUEST_LIMIT` and `USAGE_MAX_CONCURRENT_REQUESTS`.

This is operational telemetry, not a provider billing ledger. Values that the
SDK does not expose remain zero or are explicitly marked estimated; exact
prices, quotas, and credits are never fabricated.
Document-chat citations remain server-validated and evidence excerpts are
collapsed by default in the UI.

The configurable single-file limit is now 100 MiB (`104857600` bytes).
Uploads continue to stream in 64 KiB chunks, enforce the actual byte count on
the server, remove partial files on failure, retain file-signature and DOCX
expanded-size checks, and remain outside public static storage. Proxy or
deployment request-body limits must be configured separately. The expanded
DOCX limit was intentionally not increased.

Indexing is also bounded by `RAG_INDEXING_MAX_CHUNKS` (default `5000`). The
limit is checked after local parsing/chunking and before any embedding request,
so an unexpectedly large document cannot silently consume unbounded provider
quota. Worker failure records the active generation as failed, preserves the
previous valid chunk set, and leaves a safe retry path. Indexing is performed
only by the durable PostgreSQL-backed worker rather than an HTTP request.

## Adaptive document context and bounded conversation history

Document Chat now uses a deterministic, configurable strategy. When exactly
one explicit owned document is selected, its completed stored chunks are loaded
in source order without a query embedding. The full-document path is used only
when both the chunk count (`RAG_FULL_CONTEXT_MAX_CHUNKS`) and measured token
count (`RAG_FULL_CONTEXT_MAX_TOKENS`) fit the answer input budget. Larger
documents, multiple documents, an empty all-document scope, and disabled full
context continue through exact pgvector semantic retrieval. The original file
remains in private storage and neither path re-parses or re-embeds an unchanged
valid index.

The selected strategy is recorded as `full_document` or `semantic_retrieval`
in internal answer metadata. Both paths retain source chunk IDs, page metadata,
prompt-injection boundaries, validated citations, and explicit abstention. The
automated comparison uses fake providers; no real token, latency, or quality
benchmark is claimed without an approved provider run.

General Chat context is reconstructed from authenticated persisted messages,
not process-local memory. Only recent General Chat turns are included, bounded
deterministically by `GENERAL_CHAT_HISTORY_MAX_MESSAGES` and
`GENERAL_CHAT_HISTORY_MAX_CHARACTERS`. Document Chat turns are excluded. No
silent summarization or additional Gemini call is made.

## Verified web citations and follow-up context

General Chat keeps Tavily results as structured tool provenance: title, original
HTTP(S) URL, bounded evidence excerpt, optional provider publication date, and
the local retrieval timestamp. Unsafe schemes, malformed entries, and duplicate
URLs are discarded. Only this structured tool output can become a displayed or
persisted web citation; links invented in model prose are never promoted to the
source list. Uploaded-document and web citations use distinct UI sections.

The agent prompt treats web pages as untrusted evidence and tells the model to
reuse sufficient persisted conversation context for referential follow-ups.
A new search remains available when the evidence is missing or time-sensitive,
but no separate classifier or routing model call was added.

## Opt-in query planning

General Chat exposes an explicit **Deep Research** mode. Standard questions
continue directly to the existing agent with no planning call. Deep Research
enters a typed LangGraph planner node that produces at most
`RESEARCH_MAX_SUBQUESTIONS`, removes duplicates, preserves the original
question, and passes the visible plan to the search-capable agent for one
synthesis. Planner failure degrades to the original question instead of
breaking the chat. The plan is persisted with the assistant turn and restored
after reload. Document Chat never enters this graph.

## Bounded multi-step research

The General Chat ReAct graph may evaluate evidence and search again, but every
request now receives an isolated wall-clock deadline, graph-recursion limit,
and search-call budget. Standard and Deep Research limits are configured
separately. Normalized duplicate queries reuse the request-local result instead
of calling Tavily again; source URLs remain deduplicated. Tool failure is
reported as partial evidence so the agent can synthesize what remains or
abstain. Exhausted search/time budgets return an explicit stop reason rather
than silently switching providers.

Assistant metadata records actual search calls, partial failures, and the
termination reason. The UI displays this summary and keeps Deep Research
visibly opt-in. SSE cancellation propagates out of the response generator;
provider request timeouts and the outer deadline bound any in-flight call.

## Source quality and evidence relationships

Web citations now expose transparent signals rather than a universal
credibility score: publisher domain, provider-supplied author/source type when
available, publication-date availability, direct-excerpt availability, query
term overlap, and the number of distinct publishers in the result set. These
signals never declare a famous, government, or academic domain automatically
correct, and multiple domains are explicitly not treated as proof of
corroboration.

A deterministic evidence processor compares numeric claims only when currency,
unit, and surrounding subject/event terms are compatible. It reports confirmed
agreement, potential conflict, or different explicit time periods and shows
both source claims without inventing a resolution. Weak-context and mismatched-
unit pairs are left unclassified. No additional Gemini verification call is
enabled.

## Structured answer presentation

The completed answer is passed through a bounded local presentation adapter;
there is no second model call just to create JSON. Valid GFM comparison tables,
dated timelines, numbered steps, and Markdown checklists become a validated
`presentation` object persisted with the assistant turn. Ambiguous or malformed
content falls back to `standard` Markdown. Existing RAG structured generation
continues to validate answer status and citation labels at the provider boundary.

React renders comparison tables, timeline items, steps, and read-only checklists
with accessible native elements. Model text remains plain text/Markdown: raw HTML
and generated code are never executed, unsafe links are rejected, and citations
remain outside the presentation object so claim provenance is not lost.
