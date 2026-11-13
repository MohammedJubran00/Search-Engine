# Query embedding cache — 2026-11-13

## Change

`GeminiEmbeddingProvider.embed_query` now keeps successful normalized query vectors
in a process-local LRU cache (256 entries, 900-second TTL; both configurable).
The key includes model, dimensions, retrieval task type, normalization setting,
and SHA-256 of the exact query. Raw questions and access tokens are not stored
as keys. Document embeddings, answers, and retrieval results are not cached.
Owner and index-readiness checks still run before calling `embed_query` on every
retrieval request. A hit returns a copy of the vector. Failures are not cached.
Separate processes have separate caches; concurrent cold requests can each call
the provider. An application restart clears the cache.

## Measured times

| Stage | Previous real Gemini measurement | New measurement | Interpretation |
|---|---:|---:|---|
| Query embedding, cold | 311.96ms median, N=6 | Not remeasured with Gemini | Previous controlled streaming run; provider/network time |
| Query cache miss, fake provider | N/A | 0.3415ms, N=1 | Local vector validation/normalization; no network |
| Query cache hit, fake provider | N/A | 0.0037ms median, range 0.0033–0.0109ms, N=100 | Hash/lookup/vector copy only |
| Full retrieval, previous real run | 319.38ms median, N=6 | Not remeasured | Includes ownership/readiness, embedding and SQL |
| pgvector, previous real run | 2.67ms median, N=6 | Not remeasured | No change to SQL/index |
| First assistant content, previous real run | 1,780.49ms median, N=2 | Not remeasured | No answer-cache or generation change |
| Total answer, previous real run | 1,931.80ms median, N=2 | Not remeasured | No end-to-end claim from a microbenchmark |

The previous real values are from `document-streaming/after/results.json` and
remain historical. They used distinct queries, which would be cache misses.
The 0.0037ms hit cannot be subtracted directly from those runs to claim a
verified end-to-end improvement. Repeated, identical queries in one process
avoid a provider embedding operation; actual savings depend on live provider
latency and hit rate. No paid Gemini calls were made for this cache report.

## Verification

- `python -m benchmarks.isolated_tests -q tests/test_embeddings.py tests/test_retrieval.py tests/test_retrieval_repository.py tests/test_security_regressions.py`: 39 passed.
- `python -m benchmarks.query_cache`: one fake provider call for one miss and
  100 hits; measured with `time.perf_counter` around `embed_query`.
- Test covers reuse, independent returned vectors and TTL expiry.

To measure live end-to-end benefit, run matched repeated-query miss/hit pairs
against a private corpus and record cache hit, query embedding, full retrieval,
first content, total duration and provider counts. Do not compare those results
to an older provider run with a different workload.
