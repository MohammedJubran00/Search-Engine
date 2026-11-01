# Reproducible research assistant benchmarks

## Repository audit and measurement plan

The production ASGI app is `src/search_engine/api.py`. `/chat` invokes the
LangGraph agent; `/chat/stream` streams `stream_agent` in general/deep mode.
Document mode uses `RagAnswerService.answer` and emits a single completed-answer
delta. Metadata and progress are not content. A successful stream requires the
terminal `done` event as well as content.

JWT auth is under `/api/auth`; conversations and documents are owner scoped.
The suite measures authenticated GETs for `/api/auth/me`, `/api/documents`, and
`/api/conversations` through real loopback sockets. Authentication setup is
outside timed request batches. Request latency includes HTTP and database work.
These are not model generation latency measurements.

`DocumentService` validates/stores/parses uploads and queues a durable job.
`DocumentIndexingService` parses, chunks, embeds, atomically replaces vectors and
commits index state. `SemanticRetrievalService` validates ownership and index
readiness, embeds queries, and delegates exact cosine ordering to
`DocumentRetrievalRepository`. The vector dimension is 1536. No ANN path was
found. Actual index definitions and representative filter/vector EXPLAIN plans
are captured in each run. No index speed improvement is claimed.

Provider telemetry lives in usage events and the observability service. It is
not a substitute for benchmarking: external latency is excluded by default.
Existing pytest suites cover ownership, parsing, chunking, embeddings, retrieval,
grounded generation, chat and persistent state. Frontend tests are independent.

## Safe local execution (PowerShell)

From the repository root, with existing database schema already provisioned:

```powershell
uv run python -m benchmarks.run --requests 10 --warmup 2 --concurrency 1 5 10
uv run pytest -q tests/test_benchmark_metrics.py
```

The equivalent existing-environment command is
`.venv\Scripts\python.exe -m benchmarks.run`.

No migrations run. The runner binds an ephemeral loopback port, disables the
embedded indexing consumer, redirects file storage to a temporary directory,
and replaces all exercised agent/generation/embedding boundaries with fakes.
It creates a uniquely identified test user and synthetic TXT document; cleanup
deletes only that newly created user and its dependent records. Existing user
documents are never indexed. Run against a dedicated benchmark database for
stronger performance isolation; co-located activity can affect these numbers.
No API keys, token values, emails, source text or user IDs are written to reports.

Warmup is excluded for GET and general/deep streaming. Indexing is one cold
sample. Document streaming and retrieval are not warmed separately. Concurrency
is a bounded thread pool, with a 200-request maximum per batch and 50-worker
maximum. These limits are configurations, not proven supported capacities.
HTTP timeout is 30 seconds. Ctrl+C stops the runner; after a forced termination,
inspect isolated test records because finally-based cleanup cannot be guaranteed.

The generated JSON retains raw timing samples for streams and retrieval.
CSV stores each named measurement as structured JSON. Markdown includes the
readable API latency table, full evidence, skipped sections and resume guidance.
Percentiles use linear interpolation; throughput is requests divided by batch
wall time. Small batches are smoke measurements, not stable tail-latency or
capacity evidence. TTFT means first nonempty assistant delta; document-mode
TTFT is completed-answer availability, not model token emission.

## Retrieval quality

`labels.template.jsonl` is deliberately unverified. Annotate owned test corpus
questions with `relevant_ids` (document OR chunk IDs consistently), question,
optional expected answer and metadata. Set `verified=true` only after manual
review. Predictions are a JSON map from question ID to ranked IDs.

```powershell
uv run python -m benchmarks.evaluate labels.jsonl predictions.json
```

Hit, recall, precision and reciprocal rank are averaged at K=1,3,5,10. Precision
uses K as denominator, including missing retrieved positions. Duplicate IDs do
not earn repeated credit. Questions with no positive labels must be evaluated
separately; this evaluator rejects them. Missing prediction IDs fail explicitly.
This does not measure answer correctness or faithfulness. Synthetic embeddings
are never used to claim semantic accuracy.

## Explicit live-provider probe (not executed)

Use a separately controlled loopback test server with the embedded worker disabled,
an isolated test account and only synthetic prepared documents. Supply the test
JWT via an environment variable, never a command-line token:

```powershell
uv run python -m benchmarks.provider_stream --url http://127.0.0.1:8000 --allow-paid --isolated-test-server --requests 1 --mode general
```

`BENCHMARK_TEST_TOKEN` must already contain the test token. The probe limits runs
to 1..3 requests and supports `general`, `deep`, and `documents` modes. Document
mode also requires `--document-id`. Deep mode can issue multiple paid tool calls
within one request: inspect server budgets before using it. This tool never
uploads or reindexes documents. Record the server provider/model configuration
separately; a client cannot certify what provider a server actually used.

## Limits and next measurements

The root reports are local mocked-provider evidence, not production evidence.
CPU and Windows working set cover the application and harness in one process;
the RAM peak covers process lifetime, not just measured batches. PostgreSQL and provider
resources are excluded. GPU, forced stream interruption, separate
real LangGraph execution latency and independently timed parse versus chunking
are not measured by the mock runner. No ANN baseline exists. No manually
verified retrieval labels were supplied.

The tiny fixture cannot establish scale behavior. Increase synthetic dataset
size before testing database scaling, and gather repeated runs on a quiet host
before proposing optimizations. Do not infer speedups from these smoke samples.

## Real Gemini small-sample benchmark

`live_gemini.py` runs separately from the mock suite and writes to
`reports/gemini-live/`. It uses actual configured Gemini clients with no response
substitution: two generated one-page PDFs, three direct retrieval questions,
and up to three sequential grounded Document Chat requests over socket HTTP.

```powershell
uv run python -m benchmarks.live_gemini --allow-paid --requests 2
uv run pytest -q tests/test_benchmark_metrics.py tests/test_live_benchmark.py
```

This command incurs provider usage. It creates a fresh private PostgreSQL schema
with ORM tables (no application migrations), a temporary upload directory and a
new test user. Its queue is invisible to workers using the public schema.
It removes only that generated schema and its own temporary files afterwards.
Configured models and vector dimensions are retained. Output is limited to 512
tokens, application embedding retries are disabled, and generation SDK attempts
are set to 1 (one initial request, no retry). The installed SDK treats attempts=0
as defaults, not as disabling retries. Embedding SDK internal wire attempts are
not measured. Requests are sequential. Token-count operations
are real too and reported separately; operation counts are not billing receipts.

No warmup calls are made. Cold starts remain in the samples. Timers use monotonic
`perf_counter`; instrumentation wraps real method calls without replacing their
results. The HTTP stream is read incrementally, ignoring metadata for first-content
timing and requiring the final done event. Document Chat exposes a completed-answer
delta, so its first-content latency must not be described as native model TTFT.
Only median/range are emphasized for three samples. No robust tail-latency,
production capacity, quality-accuracy, or improvement percentage is claimed.

The initial shared-schema attempt is retained separately in
`reports/gemini-live-attempt1/`: its two real embeddings succeeded but retrieval
failed readiness validation before generation. Shared worker interference was
suspected; subsequent runs use strict schema isolation. The second attempt is
retained in `reports/gemini-live-attempt2/`: real retrieval succeeded but its first
generation failed. Its configured retries=0 did not disable SDK default retries.
Final evidence and actual success/failure counts are in `reports/gemini-live/`.
Do not combine attempts or select their fastest samples. Failures remain part
of the overall reliability history and are not erased by a subsequent success.
