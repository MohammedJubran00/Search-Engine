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
