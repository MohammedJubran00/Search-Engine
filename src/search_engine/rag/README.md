# RAG module boundary

This package is preparation for document-grounded chat. It is deliberately not
connected to the current FastAPI routes or LangGraph agent yet.

Planned flow:

1. Validate an authenticated user's PDF, DOCX, or UTF-8 TXT upload by size,
   extension, MIME type, and file signature.
2. Store it beneath `RAG_STORAGE_DIR` using a generated identifier, never a
   client-supplied path.
3. Parse text with PyMuPDF, python-docx, or the standard library.
4. Split text with `langchain-text-splitters` using the configured character
   size and overlap.
5. Generate vectors with the existing Gemini integration.
6. Store document/chunk metadata and vectors in PostgreSQL with pgvector.
7. Require `user_id` in every document and similarity query; optional document
   filters are applied in addition to that ownership predicate.
8. Feed retrieved context into the existing streaming response path, retaining
   Tavily as a policy-controlled fallback.

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
- Chunk embeddings are nullable until the future ingestion phase generates
  them. The schema migration freezes the vector dimension at 1,536; changing
  the configured model or dimension later requires a coordinated migration and
  re-embedding of stored chunks.

## Phase 4 embedding requirements

The future embedding provider must use all of the following settings together:

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
output dimensionality per operation. A future implementation should pass the
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

For Phase 2, `completed` means only that the original file was stored and its
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
only vector indexing with `not_indexed`, `processing`, `completed`, and
`failed` states. A monotonically increasing generation prevents two workers
from finalizing the same document concurrently.

Indexing first commits a short ownership-scoped generation claim. Parsing,
chunking, and Gemini calls then run without an open database transaction. The
final transaction validates every vector, deletes the prior chunk set, inserts
the complete replacement, and marks that generation completed. A failure
rolls back that transaction, records a safe failure status, and leaves a prior
valid index intact. Uploads do not trigger this workflow automatically.

Gemini document requests use `RETRIEVAL_DOCUMENT`; query support uses
`RETRIEVAL_QUERY` but is not connected to retrieval. Reduced 1,536-dimensional
vectors are validated for count, finite values, and nonzero norm, then L2
normalized. Requests use configurable batches up to Gemini's 100-text limit,
bounded concurrency, exponential retry for transient capacity/rate errors,
and per-call duplicate text elimination.

Migration `f7a9c2d4e6b8` must be reviewed and applied manually before indexing.
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

`RagAnswerService` is a backend-only orchestration service. It accepts a
trusted user UUID, calls `SemanticRetrievalService` exactly once, ends the
read-only database transaction, builds bounded evidence, and then calls a
dedicated deterministic Gemini chat client. It is not connected to FastAPI,
the existing chat routes, LangGraph, Tavily, SSE, or the frontend.

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
For SSE, general mode retains native token deltas. Because Phase 6 produces a
completed answer, document mode emits exactly one full-answer `delta` carrying
the same structured metadata, followed by `done`. This is compatibility
buffering, not model-token streaming, and it never calls Gemini again merely
to simulate streaming. Retrieval/provider errors are sanitized; cancellation
is propagated rather than converted into a misleading success event.

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
to another paid provider. No automatic indexing, reranking, caching, or paid
service was added.

## Phase 7.5 attachment and manual-indexing workflow

The primary upload workflow now lives in the chat composer. A user can stage
multiple PDF, DOCX, or TXT files, remove them before upload, upload them to
private storage, attach existing owned uploads, and see parsing/indexing state.
Uploading remains a local storage and parsing operation; it never starts
Gemini embeddings. Unindexed attachments block sending while preserving the
question draft and expose an explicit **Prepare for AI questions** action.

`POST /api/documents/{document_id}/index` is JWT-protected and calls the
existing retry-safe `DocumentIndexingService` only after the user confirms in
the UI that Gemini quota may be consumed. Missing and foreign documents share
the same 404 response, concurrent work returns 409, provider quota exhaustion
returns a sanitized 503, and an already completed index is returned without
embedding the document again. No client-supplied user ID is accepted.

The versioned message envelope now also stores server-resolved attachment
metadata on the user turn, so filename, media type, size, and state survive a
reload without trusting client-supplied metadata or adding a migration.
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
quota. Cancelling the indexing request records the active generation as failed
and preserves the previous valid chunk set. Indexing remains a synchronous
authenticated request; very large documents can take long enough to hit an
external proxy timeout, so a durable local job worker remains a future option.
