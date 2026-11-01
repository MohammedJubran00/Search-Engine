# Real Gemini RAG benchmark

Run status: completed

Real Gemini embeddings and grounded answer generation, PostgreSQL/pgvector, and socket HTTP. Two generated single-page PDFs; three direct retrieval queries. The number of answer requests is recorded below. Sequential, no warmup; application embedding retries disabled, generation SDK attempts=1. All samples, including cold first calls, are retained. No Tavily or general/deep agent calls.

| Measurement | N | Median ms | Range ms |
|---|---:|---:|---:|
| retrieval_total | 3 | 323.72 | 310.02–329.00 |
| query_embedding | 3 | 314.84 | 303.12–317.00 |
| vector_search | 3 | 3.67 | 3.46–5.70 |
| document_indexing | 2 | 374.00 | 296.98–451.02 |
| first_content | 2 | 34527.46 | 32182.83–36872.09 |
| stream_duration | 2 | 34528.21 | 32183.26–36873.16 |

Document Chat emits one complete-answer delta: first content is answer availability, NOT native model TTFT. Persistence timing excludes the final commit. Total indexing includes it. SSE duration includes authentication, ownership validation, token counting, retrieval, generation and persistence. Direct retrieval includes ownership/readiness checks, real query embedding and SQL ordering.

## Limitations

At most 3 answer requests: no stable P95/P99, capacity, SLA, improvement percentage or real-world accuracy claim. The two-document corpus is deliberately tiny. Completion percentage is smoke-test completion, not answer accuracy. No billing price estimate; actual billing is external. Mock results are separate and cannot be used as a before/after baseline.

## Full evidence

```json
{
  "status": "completed",
  "dependencies": {
    "langchain-google-genai": "4.3.4",
    "google-genai": "2.19.0",
    "sqlalchemy": "2.0.52",
    "pgvector": "0.5.1",
    "httpx": "0.28.1"
  },
  "planned_answer_requests": 2,
  "retry_caveat": "Generation SDK attempts=1; application embedding retries=0. Embedding SDK internal wire attempts were not measured. Counts describe logical operations, not billing or wire attempts.",
  "attempt_history": "Attempt 1: two real document embeddings, retrieval readiness failure before generation. Attempt 2: real retrieval succeeded, one generation/stream failed. Final isolated run: two streams succeeded. Across attempts, 2 of 3 application answer requests succeeded; provider wire-attempt count is unknown.",
  "recorded_at": "2026-11-01T22:06:21.067350+00:00",
  "mode": "REAL Gemini, local isolated generated data",
  "database_isolation": "Fresh private schema with separate queue; removed after run",
  "config": {
    "embedding_model": "models/gemini-embedding-001",
    "generation_model": "gemini-3.5-flash-lite",
    "dimensions": 1536,
    "normalization": true,
    "output_token_limit": 512,
    "application_embedding_retries": 0,
    "generation_sdk_attempts": 1,
    "concurrency": 1,
    "warmup": 0,
    "top_k": 5
  },
  "environment": {
    "os": "Windows-11-10.0.26200-SP0",
    "python": "3.14.6"
  },
  "fixtures": [
    {
      "filename": "cedar.pdf",
      "title": "Project Cedar: Restaurant Reservations",
      "text": "Project Cedar automates table reservations. Its goals are to reduce booking errors, prevent double bookings, and improve the speed of confirming restaurant reservations."
    },
    {
      "filename": "harbor.pdf",
      "title": "Project Harbor: Warehouse Inventory",
      "text": "Project Harbor tracks warehouse inventory. Its goals are to detect low stock, reduce stock counting errors, and notify warehouse staff when items need replenishment."
    }
  ],
  "questions": [
    "What are the main goals of Project Cedar?",
    "How does Project Harbor help warehouse staff?",
    "Which project prevents double bookings, and which detects low stock?"
  ],
  "uploads": [
    {
      "seconds": 0.07079779999912716,
      "bytes": 1010,
      "pages": 1
    },
    {
      "seconds": 0.029318599998077843,
      "bytes": 1008,
      "pages": 1
    }
  ],
  "indexing": [
    {
      "seconds": 0.4510175000032177,
      "chunks": 1,
      "embedding_seconds": 0.4147726999945007,
      "persistence_seconds": 0.021106799998960923,
      "parse_extract_chunk_seconds": 0.003413200000068173
    },
    {
      "seconds": 0.29697979999764357,
      "chunks": 1,
      "embedding_seconds": 0.28227850000257604,
      "persistence_seconds": 0.006953399999474641,
      "parse_extract_chunk_seconds": 0.0033518999989610165
    }
  ],
  "retrieval": [
    {
      "seconds": 0.3290008999974816,
      "embedding_seconds": 0.31483899999875575,
      "vector_search_seconds": 0.0057043999986490235,
      "retrieved_chunks": 2
    },
    {
      "seconds": 0.3100237000035122,
      "embedding_seconds": 0.30311950000032084,
      "vector_search_seconds": 0.0036697999967145734,
      "retrieved_chunks": 2
    },
    {
      "seconds": 0.3237163000012515,
      "embedding_seconds": 0.31700090000231285,
      "vector_search_seconds": 0.003462199994828552,
      "retrieved_chunks": 2
    }
  ],
  "streams": [
    {
      "seconds": 32.183260199999495,
      "ok": true,
      "chunks": 1,
      "first_event_seconds": 0.16130409999459516,
      "ttft_seconds": 32.182830599995214,
      "interrupted": false
    },
    {
      "seconds": 36.873158400005195,
      "ok": true,
      "chunks": 1,
      "first_event_seconds": 0.13317730000562733,
      "ttft_seconds": 36.87208760000067,
      "interrupted": false
    }
  ],
  "calls": {
    "embedding_operations": {
      "count": 7,
      "seconds": [
        0.4143421000044327,
        0.2818905000021914,
        0.31453719999990426,
        0.30275670000264654,
        0.31671449999703327,
        0.38370209999993676,
        0.4040439000018523
      ]
    },
    "generation_operations": {
      "count": 2,
      "seconds": [
        30.067420900006255,
        34.772821500002465
      ]
    },
    "token_count_operations": {
      "count": 18,
      "seconds": [
        0.20501659999717958,
        0.0999800999998115,
        0.10990039999887813,
        0.2849227000042447,
        0.1049736999993911,
        0.26841979999881005,
        0.10861479999584844,
        0.2711607000019285,
        0.09960770000179764,
        0.19246189999830676,
        0.0979661000019405,
        0.09580889999779174,
        0.28404040000168607,
        0.1005315000002156,
        0.283190399997693,
        0.09742729999561561,
        0.2850177000000258,
        0.10544230000232346
      ]
    }
  },
  "cleanup": true,
  "memory": {
    "working_set_bytes": 221802496,
    "peak_process_lifetime_working_set_bytes": 222109696
  },
  "aggregates": {
    "retrieval_total": {
      "samples": 3,
      "mean_ms": 320.9136333340818,
      "median_ms": 323.7163000012515,
      "min_ms": 310.0237000035122,
      "max_ms": 329.0008999974816
    },
    "query_embedding": {
      "samples": 3,
      "mean_ms": 311.65313333379646,
      "median_ms": 314.83899999875575,
      "min_ms": 303.11950000032084,
      "max_ms": 317.00090000231285
    },
    "vector_search": {
      "samples": 3,
      "mean_ms": 4.278799996730716,
      "median_ms": 3.6697999967145734,
      "min_ms": 3.462199994828552,
      "max_ms": 5.7043999986490235
    },
    "document_indexing": {
      "samples": 2,
      "mean_ms": 373.99865000043064,
      "median_ms": 373.99865000043064,
      "min_ms": 296.97979999764357,
      "max_ms": 451.0175000032177
    },
    "first_content": {
      "samples": 2,
      "mean_ms": 34527.45909999794,
      "median_ms": 34527.45909999794,
      "min_ms": 32182.830599995214,
      "max_ms": 36872.08760000067
    },
    "stream_duration": {
      "samples": 2,
      "mean_ms": 34528.209300002345,
      "median_ms": 34528.209300002345,
      "min_ms": 32183.260199999495,
      "max_ms": 36873.158400005195
    }
  },
  "stream_successes": 2,
  "stream_requests": 2
}
```
