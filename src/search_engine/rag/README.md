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
