# RAG module boundary

This package is preparation for document-grounded chat. It is deliberately not
connected to the current FastAPI routes or LangGraph agent yet.

Planned flow:

1. Validate an authenticated user's PDF, DOCX, or UTF-8 TXT upload by size,
   extension, MIME type, and file signature.
2. Store it beneath `RAG_STORAGE_DIR` using a generated identifier, never a
   client-supplied path.
3. Parse text with PyMuPDF, python-docx, or the standard library.
4. Split text with `langchain-text-splitters` using the configured chunk size
   and overlap.
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
- `gemini-embedding-001` is configured with its default 3,072-dimensional
  output. Google documents 3,072 as a supported and recommended size, and the
  full-size output does not require the manual normalization needed when this
  model is configured for a smaller dimension.
- Chunk embeddings are nullable until the future ingestion phase generates
  them. The schema migration freezes the vector dimension at 3,072; changing
  the configured model or dimension later requires a coordinated migration and
  re-embedding of stored chunks.
