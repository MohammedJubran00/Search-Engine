# Real Gemini RAG benchmark

Run status: completed

Real Gemini embeddings and grounded answer generation, PostgreSQL/pgvector, and socket HTTP. The exact generated corpus, page sizes, retrieval queries and answer request counts are recorded below. Sequential, no warmup; application embedding retries disabled, generation SDK attempts=1. All samples, including cold first calls, are retained. No Tavily or general/deep agent calls.

| Measurement | N | Median ms | Range ms |
|---|---:|---:|---:|
| retrieval_total | 6 | 324.17 | 298.76–331.47 |
| query_embedding | 6 | 315.43 | 293.25–319.91 |
| vector_search | 6 | 2.64 | 2.51–12.90 |
| document_indexing | 3 | 533.73 | 504.88–1185.89 |
| first_content | 2 | 4695.70 | 4388.88–5002.52 |
| stream_duration | 2 | 4696.15 | 4389.22–5003.09 |

Document Chat emits one complete-answer delta: first content is answer availability, NOT native model TTFT. Persistence timing excludes the final commit. Total indexing includes it. SSE duration includes authentication, ownership validation, token counting, retrieval, generation and persistence. Direct retrieval includes ownership/readiness checks, real query embedding and SQL ordering.

## Limitations

At most 3 answer requests: no stable P95/P99, capacity, SLA, improvement percentage or real-world accuracy claim. The two-document corpus is deliberately tiny. Completion percentage is smoke-test completion, not answer accuracy. No billing price estimate; actual billing is external. Mock results are separate and cannot be used as a before/after baseline.

## Full evidence

```json
{
  "status": "completed",
  "streaming_mode": "buffered_completed_answer",
  "baseline_production_revision": "192470c",
  "provenance": "Captured before production edits; representative measurement harness added without changing the buffered request path. Prompt hashes normalize only random UUIDs.",
  "recorded_at": "2026-11-01T23:16:00.136473+00:00",
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
  "planned_answer_requests": 2,
  "profile": "representative",
  "corpus_sha256": "a0e1a758fc63c50342e6f61ca62d559ecc10bc98dc4426bf7e82c0c419f1bd9a",
  "retry_caveat": "Embedding application retries disabled; underlying embedding SDK retry policy is not instrumented. SDK operation counts are not wire-attempt or billing counts.",
  "environment": {
    "os": "Windows-11-10.0.26200-SP0",
    "python": "3.14.6"
  },
  "dependencies": {
    "langchain-google-genai": "4.3.4",
    "google-genai": "2.19.0",
    "sqlalchemy": "2.0.52",
    "pgvector": "0.5.1",
    "httpx": "0.28.1"
  },
  "fixtures": [
    {
      "filename": "cedar.pdf",
      "title": "Cedar restaurant booking specification",
      "text": "Section 1: Cedar restaurant booking specification.\nCedar prevents double bookings using atomic table allocation. Holds expire after 5 minutes. Staff must confirm reservations; SMS failure must not cancel a confirmed booking.\nProcedure 1: record the operator, timestamp, action, outcome, and reason for any exception. The responsible reviewer checks section 1 before closing the record. Keep the original record, provide a clear correction trail, and escalate unresolved exceptions. Acceptance check 1: demonstrate the stated safety and validation rules with a controlled test."
    },
    {
      "filename": "harbor.pdf",
      "title": "Harbor warehouse operations handbook",
      "text": "Section 1: Harbor warehouse operations handbook.\nHarbor raises a replenishment alert when stock falls below 20 units. Receiving staff scan barcodes and reconcile quantities with the purchase order. A supervisor approves inventory corrections before the audit ledger is updated.\nProcedure 1: record the operator, timestamp, action, outcome, and reason for any exception. The responsible reviewer checks section 1 before closing the record. Keep the original record, provide a clear correction trail, and escalate unresolved exceptions. Acceptance check 1: demonstrate the stated safety and validation rules with a controlled test.\n\nSection 2: Harbor warehouse operations handbook.\nHarbor raises a replenishment alert when stock falls below 20 units. Receiving staff scan barcodes and reconcile quantities with the purchase order. A supervisor approves inventory corrections before the audit ledger is updated.\nProcedure 2: record the operator, timestamp, action, outcome, and reason for any exception. The responsible reviewer checks section 2 before closing the record. Keep the original record, provide a clear correction trail, and escalate unresolved exceptions. Acceptance check 2: demonstrate the stated safety and validation rules with a controlled test.\n\nSection 3: Harbor warehouse operations handbook.\nHarbor raises a replenishment alert when stock falls below 20 units. Receiving staff scan barcodes and reconcile quantities with the purchase order. A supervisor approves inventory corrections before the audit ledger is updated.\nProcedure 3: record the operator, timestamp, action, outcome, and reason for any exception. The responsible reviewer checks section 3 before closing the record. Keep the original record, provide a clear correction trail, and escalate unresolved exceptions. Acceptance check 3: demonstrate the stated safety and validation rules with a controlled test."
    },
    {
      "filename": "quartz.pdf",
      "title": "Quartz campus solar maintenance plan",
      "text": "Section 1: Quartz campus solar maintenance plan.\nQuartz schedules monthly solar inverter inspections and quarterly panel cleaning. Technicians isolate electrical equipment before maintenance. Energy production is reviewed weekly against the previous month, with weather recorded.\nProcedure 1: record the operator, timestamp, action, outcome, and reason for any exception. The responsible reviewer checks section 1 before closing the record. Keep the original record, provide a clear correction trail, and escalate unresolved exceptions. Acceptance check 1: demonstrate the stated safety and validation rules with a controlled test.\n\nSection 2: Quartz campus solar maintenance plan.\nQuartz schedules monthly solar inverter inspections and quarterly panel cleaning. Technicians isolate electrical equipment before maintenance. Energy production is reviewed weekly against the previous month, with weather recorded.\nProcedure 2: record the operator, timestamp, action, outcome, and reason for any exception. The responsible reviewer checks section 2 before closing the record. Keep the original record, provide a clear correction trail, and escalate unresolved exceptions. Acceptance check 2: demonstrate the stated safety and validation rules with a controlled test.\n\nSection 3: Quartz campus solar maintenance plan.\nQuartz schedules monthly solar inverter inspections and quarterly panel cleaning. Technicians isolate electrical equipment before maintenance. Energy production is reviewed weekly against the previous month, with weather recorded.\nProcedure 3: record the operator, timestamp, action, outcome, and reason for any exception. The responsible reviewer checks section 3 before closing the record. Keep the original record, provide a clear correction trail, and escalate unresolved exceptions. Acceptance check 3: demonstrate the stated safety and validation rules with a controlled test.\n\nSection 4: Quartz campus solar maintenance plan.\nQuartz schedules monthly solar inverter inspections and quarterly panel cleaning. Technicians isolate electrical equipment before maintenance. Energy production is reviewed weekly against the previous month, with weather recorded.\nProcedure 4: record the operator, timestamp, action, outcome, and reason for any exception. The responsible reviewer checks section 4 before closing the record. Keep the original record, provide a clear correction trail, and escalate unresolved exceptions. Acceptance check 4: demonstrate the stated safety and validation rules with a controlled test.\n\nSection 5: Quartz campus solar maintenance plan.\nQuartz schedules monthly solar inverter inspections and quarterly panel cleaning. Technicians isolate electrical equipment before maintenance. Energy production is reviewed weekly against the previous month, with weather recorded.\nProcedure 5: record the operator, timestamp, action, outcome, and reason for any exception. The responsible reviewer checks section 5 before closing the record. Keep the original record, provide a clear correction trail, and escalate unresolved exceptions. Acceptance check 5: demonstrate the stated safety and validation rules with a controlled test.\n\nSection 6: Quartz campus solar maintenance plan.\nQuartz schedules monthly solar inverter inspections and quarterly panel cleaning. Technicians isolate electrical equipment before maintenance. Energy production is reviewed weekly against the previous month, with weather recorded.\nProcedure 6: record the operator, timestamp, action, outcome, and reason for any exception. The responsible reviewer checks section 6 before closing the record. Keep the original record, provide a clear correction trail, and escalate unresolved exceptions. Acceptance check 6: demonstrate the stated safety and validation rules with a controlled test.\n\nSection 7: Quartz campus solar maintenance plan.\nQuartz schedules monthly solar inverter inspections and quarterly panel cleaning. Technicians isolate electrical equipment before maintenance. Energy production is reviewed weekly against the previous month, with weather recorded.\nProcedure 7: record the operator, timestamp, action, outcome, and reason for any exception. The responsible reviewer checks section 7 before closing the record. Keep the original record, provide a clear correction trail, and escalate unresolved exceptions. Acceptance check 7: demonstrate the stated safety and validation rules with a controlled test.\n\nSection 8: Quartz campus solar maintenance plan.\nQuartz schedules monthly solar inverter inspections and quarterly panel cleaning. Technicians isolate electrical equipment before maintenance. Energy production is reviewed weekly against the previous month, with weather recorded.\nProcedure 8: record the operator, timestamp, action, outcome, and reason for any exception. The responsible reviewer checks section 8 before closing the record. Keep the original record, provide a clear correction trail, and escalate unresolved exceptions. Acceptance check 8: demonstrate the stated safety and validation rules with a controlled test."
    }
  ],
  "questions": [
    "How does Cedar prevent double bookings, and what happens when a reservation hold expires or SMS fails?",
    "Describe the Harbor replenishment threshold and inventory correction approval process.",
    "How often does Quartz inspect inverters and clean panels?",
    "Who approves warehouse stock corrections?",
    "What must a technician do before maintaining solar equipment?",
    "Does an SMS failure cancel a confirmed restaurant booking?"
  ],
  "uploads": [
    {
      "seconds": 0.05257020000135526,
      "bytes": 1322,
      "pages": 1,
      "characters": 576
    },
    {
      "seconds": 0.032352399997762404,
      "bytes": 3173,
      "pages": 3,
      "characters": 1891
    },
    {
      "seconds": 0.04409289999603061,
      "bytes": 7587,
      "pages": 8,
      "characters": 5062
    }
  ],
  "indexing": [
    {
      "seconds": 0.5048772000009194,
      "chunks": 1,
      "embedding_seconds": 0.4727280000006431,
      "persistence_seconds": 0.017115500006184448,
      "parse_extract_chunk_seconds": 0.004915199999231845
    },
    {
      "seconds": 0.533730099996319,
      "chunks": 3,
      "embedding_seconds": 0.5096735999977682,
      "persistence_seconds": 0.008824399999866728,
      "parse_extract_chunk_seconds": 0.01213570000254549
    },
    {
      "seconds": 1.1858906999987084,
      "chunks": 8,
      "embedding_seconds": 1.1400627000039094,
      "persistence_seconds": 0.013700399998924695,
      "parse_extract_chunk_seconds": 0.027589600002102088
    }
  ],
  "retrieval": [
    {
      "seconds": 0.3314724000010756,
      "embedding_seconds": 0.3121443999989424,
      "vector_search_seconds": 0.012898900000436697,
      "retrieved_chunks": 5
    },
    {
      "seconds": 0.32522989999415586,
      "embedding_seconds": 0.3199084999941988,
      "vector_search_seconds": 0.0025564000025042333,
      "retrieved_chunks": 5
    },
    {
      "seconds": 0.29875999999785563,
      "embedding_seconds": 0.2932520000031218,
      "vector_search_seconds": 0.0029384999943431467,
      "retrieved_chunks": 5
    },
    {
      "seconds": 0.3239964000022155,
      "embedding_seconds": 0.31872049999947194,
      "vector_search_seconds": 0.0025090000053751282,
      "retrieved_chunks": 5
    },
    {
      "seconds": 0.3243471000023419,
      "embedding_seconds": 0.31949209999584127,
      "vector_search_seconds": 0.0027058999985456467,
      "retrieved_chunks": 5
    },
    {
      "seconds": 0.2998825999966357,
      "embedding_seconds": 0.29510299999674316,
      "vector_search_seconds": 0.0025720999983604997,
      "retrieved_chunks": 5
    }
  ],
  "streams": [
    {
      "seconds": 4.389216299998225,
      "ok": true,
      "chunks": 1,
      "first_event_seconds": 0.12945899999613175,
      "ttft_seconds": 4.388877199999115,
      "interrupted": false
    },
    {
      "seconds": 5.0030868999965605,
      "ok": true,
      "chunks": 1,
      "first_event_seconds": 0.10237529999722028,
      "ttft_seconds": 5.002517299995816,
      "interrupted": false
    }
  ],
  "calls": {
    "embedding_operations": {
      "count": 11,
      "seconds": [
        0.47232549999898765,
        0.5085800999950152,
        1.137978300001123,
        0.31171200000244426,
        0.3195133999979589,
        0.292931399999361,
        0.31845919999614125,
        0.31919630000629695,
        0.29484270000102697,
        0.39187089999904856,
        0.39216590000432916
      ]
    },
    "generation_operations": {
      "count": 2,
      "seconds": [
        1.0554928999990807,
        1.031502099998761
      ]
    },
    "token_count_operations": {
      "count": 36,
      "seconds": [
        0.19198440000036499,
        0.10305349999543978,
        0.09761099999741418,
        0.2861966999989818,
        0.10304759999417001,
        0.27193239999905927,
        0.10868559999653371,
        0.10945440000068629,
        0.09289020000142045,
        0.17202199999883305,
        0.20635310000216123,
        0.1601747000022442,
        0.21373010000388604,
        0.09562780000123894,
        0.08859070000471547,
        0.2951526000033482,
        0.10550360000343062,
        0.09979069999826606,
        0.17980510000052163,
        0.2748840999993263,
        0.10998760000074981,
        0.26055320000159554,
        0.10615440000401577,
        0.27680469999904744,
        0.10136239999701502,
        0.275154000002658,
        0.10597960000450257,
        0.266152800002601,
        0.10918650000530761,
        0.26391380000131903,
        0.11585430000559427,
        0.2594963000010466,
        0.1134883999984595,
        0.2624149999974179,
        0.10006870000506751,
        0.2816069000036805
      ]
    }
  },
  "cleanup": true,
  "normalized_prompt_hashes": [
    "2cf54cff90ef7db8f8346763dc8a51ae1a7a57811f33dd7a8d588aa54fad3c7d",
    "d5276ce85ea0dba1f1a54f5a728e6661e22a7295a498e665c0ed4ccc23c88ad0"
  ],
  "memory": {
    "working_set_bytes": 221925376,
    "peak_process_lifetime_working_set_bytes": 222183424
  },
  "aggregates": {
    "retrieval_total": {
      "samples": 6,
      "mean_ms": 317.2813999990467,
      "median_ms": 324.1717500022787,
      "min_ms": 298.75999999785563,
      "max_ms": 331.4724000010756
    },
    "query_embedding": {
      "samples": 6,
      "mean_ms": 309.77008333138656,
      "median_ms": 315.43244999920717,
      "min_ms": 293.2520000031218,
      "max_ms": 319.9084999941988
    },
    "vector_search": {
      "samples": 6,
      "mean_ms": 4.363466666594225,
      "median_ms": 2.638999998453073,
      "min_ms": 2.5090000053751282,
      "max_ms": 12.898900000436697
    },
    "document_indexing": {
      "samples": 3,
      "mean_ms": 741.4993333319823,
      "median_ms": 533.730099996319,
      "min_ms": 504.8772000009194,
      "max_ms": 1185.8906999987084
    },
    "first_content": {
      "samples": 2,
      "mean_ms": 4695.697249997465,
      "median_ms": 4695.697249997465,
      "min_ms": 4388.877199999115,
      "max_ms": 5002.517299995816
    },
    "stream_duration": {
      "samples": 2,
      "mean_ms": 4696.151599997393,
      "median_ms": 4696.151599997393,
      "min_ms": 4389.216299998225,
      "max_ms": 5003.0868999965605
    }
  },
  "stream_successes": 2,
  "stream_requests": 2
}
```
