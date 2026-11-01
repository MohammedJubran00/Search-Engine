# Document Chat native streaming: controlled Gemini comparison

Measured on 2026-11-02, Asia/Hebron. These are preliminary local integration
measurements, not production readiness, capacity, SLA or accuracy claims.

## Root causes and actual route

Document Chat does **not** pass through LangGraph. Its previous route was:

`React → authorizedFetch → FastAPI → RagAnswerService → Gemini.ainvoke → complete JSON validation → persistence → one full-answer SSE delta → React Markdown`

General/Deep Research already uses LangGraph `stream_mode="messages"` and
`AIMessageChunk`. That path and Tavily were not rewritten. The browser already
accumulated content; the document provider and document SSE route were the buffers.

The new document route uses Gemini `astream`, incrementally decodes the JSON
`answer` string and forwards genuine provider fragments. It never divides an
already completed answer. Reasoning blocks, status fields and JSON syntax are
not assistant content. Final shape/source validation still runs before commit.

Token counting was a second bottleneck. The original two-source historical run
made nine remote counts per answer: system + question + three counts per source
(wrapper, text, block) + final context = 9, or 18 for two requests. The expanded
baseline selected five chunks: 2 + 3×5 + 1 = 18 per answer, 36 total.
The complete-context fast path now counts all evidence once. System and question
remain separately counted: three per answer, six total. This is **83.3% fewer
logical token-count operations in this measured pair**. Request-local memoization
avoids repeated counts during fallback; oversized context still uses the bounded
truncation algorithm and final budget check. No global document/answer cache.

## Conditions and equivalence

- Three generated text PDFs: 1, 3 and 8 pages; 1,322 / 3,173 / 7,587 bytes;
  7,529 source characters and 12 indexed chunks in total.
- Six direct retrieval queries per branch; two sequential answer requests per
  branch, using the same questions in the same order. No warmup.
- Real `models/gemini-embedding-001`, L2-normalized 1536-dimensional vectors,
  exact pgvector search, top_k=5. Real `gemini-3.5-flash-lite` generation.
- Same 512-token benchmark output cap, concise English responses, SDK attempt=1,
  Python/dependency versions and machine. The production output limit is unchanged.
- Corpus SHA256 and both UUID-normalized full prompt SHA256 values match exactly.
  Only random document/chunk UUIDs are normalized; evidence, order, wording and
  instructions are included in the hash. No evidence was truncated after the change.
- Separate private schemas, test users, queues and temporary files; cleanup
  succeeded for both runs. No private documents, Tavily, migrations or ANN changes.
- Four generation operations, 22 embedding operations and 42 token-count
  operations in the paired experiment. These are logical SDK operations, not
  independently traced wire attempts or billing receipts. No paid abort/load test.

The buffered baseline was captured on production revision `192470c`, with the
expanded measurement harness, **before editing the production path**. The original
`gemini-live` reports remain untouched historical references. The earlier 34.53 s
answer latency was not reproduced: the fresh buffered baseline was 4.70 s.
It would be invalid to advertise a 34.53→1.93 s improvement from this experiment.

## Verified before/after results

| Measurement | Before | After | Samples per branch |
|---|---:|---:|---:|
| Median first actual assistant content | 4,695.70 ms | 1,780.49 ms | 2 |
| Median full stream duration | 4,696.15 ms | 1,931.80 ms | 2 |
| Median direct retrieval pipeline | 324.17 ms | 319.38 ms | 6 |
| Median query embedding | 315.43 ms | 311.96 ms | 6 |
| Median repository vector search | 2.64 ms | 2.67 ms | 6 |
| Failed answer requests | 0/2 | 0/2 | 2 |
| Nonblank content chunks per answer | 1, 1 | 2, 2 | 2 |
| Token-count operations | 36 | 6 | 2 answers |

Observed first-content reduction: **62.1%**. Observed total-duration reduction:
**58.9%**. Formula: `(median_before - median_after) / median_before × 100`.
These percentages describe only this tiny controlled sample. They are not
confidence intervals, production speed guarantees or evidence of index improvement.
The small retrieval/SQL differences are treated as variation, not optimizations.

The largest contributor is count-call consolidation, not streaming alone:
token-count method time averaged 3.132 s per answer before versus 0.480 s after.
Full generation averaged 1.043 s before versus 0.969 s after; that small change
cannot establish a provider speed improvement. Streaming exposed the first answer
fragment about 0.15 s before completion for these short answers. Longer-answer
streaming benefit has not been quantified with paid calls in this sample.

## Stage measurements after the change

| Stage | Median | Scope |
|---|---:|---|
| Final user-prompt string construction | 0.0026 ms | Python formatting only, excludes context construction |
| Token counting | 480.42 ms | Three real SDK count operations per answer |
| SDK request preparation | 11.32 ms | `_prepare_request`, cold first call 22.33 ms, next 0.30 ms |
| First decoded model answer content | 827.24 ms | From provider method start, not from HTTP request start |
| Full streaming provider method | 968.72 ms | Request preparation, provider/network, decode and final validation |
| Local first-content delivery | 0.35 ms | Model fragment to httpx, includes queue/ASGI/socket/parser; not browser paint |
| Message/usage persistence and commit | 9.10 ms | Server-side after final validation |

The model-stage intervals overlap; do not add them as independent durations.
Context assembly CPU was not isolated from all surrounding preprocessing, and
these fine-grained stage timers were not present in the buffered baseline.
Provider usage after streaming was 1,332/1,326 input tokens and 63/73 output tokens.
No reasoning budget/level was changed. The SDK warned that this model uses fixed
sampling defaults, so temperature=0 is not evidence that its sampling was altered.
This experiment does not establish why the older provider calls took 30–35 s.

## Correctness and failure behavior

Both real after-run conversations were fetched immediately after `done`:
exactly one assistant record, exact byte-for-byte text equality with all received
deltas, and persisted citations. Valid citation labels are mapped to authorized
retrieval sources by the server. Prompt equivalence confirms that the faster
context path did not remove evidence in these requests. Semantic answer accuracy
or faithfulness percentages were not measured.

Only validated complete answers are committed. Partial fragments are provisional;
final failure clears them in React and never stores them as completed answers.
Cancellation closes the bounded producer and upstream iterator. A valid commit
can precede a disconnect that prevents the client from receiving `done`; this
normal commit/network race is not an exactly-once retry guarantee.

The browser now requires terminal completion, preserves AbortError, closes its
reader, handles fragmented UTF-8/CRLF events, and does not overwrite citations
with the final bare `done` metadata. Markdown receives the accumulated text.
Stopped partial text is labeled unsaved. General/Deep Research still uses the
same fetch/SSE contract; authentication/ownership rules are unchanged.

## Executed validation

- `python -m benchmarks.isolated_tests -q`: **214 passed**, in a fresh private
  schema invisible to public workers; fake providers, no paid test requests.
- Frontend `npm test`: **21 passed** (8 API and 13 Vitest).
- `npm run lint` and `npm run build`: passed. Existing large-bundle warning remains.
- New cases cover provider content before complete JSON, every split position for
  Unicode/escaped/Markdown strings, timeout, upstream close on cancellation,
  unknown final source labels, stream/final-text mismatch, no duplicate deltas,
  exact single-message persistence, sanitized failure/no partial assistant save,
  user isolation, final citation preservation and interrupted HTTP content.
- `benchmarks.compare_streaming` checked corpus, prompts, questions, configuration,
  environment, dependencies, sample counts and completed-run status before computing
  observed changes. It refuses percentages when equivalence checks fail.

## Changed code and reproducibility

Production: `rag/streaming_json.py`, `rag/generation.py`, `rag/context.py`,
`services/rag_answer_service.py`, `api.py`; frontend `api/chat.js`, `App.jsx`,
`MessageBubble.jsx`. Supporting changes: test discovery, regression tests,
`benchmarks/live_gemini.py`, `run.py`, `compare_streaming.py`, `isolated_tests.py`
and RAG/benchmark documentation. No `main.py`, migrations, model/dimension changes,
HNSW, answer caching or unrelated production refactor.

```powershell
uv run python -m benchmarks.live_gemini --allow-paid --requests 2 --profile representative --output benchmarks/reports/document-streaming/after
uv run python -m benchmarks.compare_streaming
uv run python -m benchmarks.isolated_tests -q
cd frontend
npm test
npm run lint
npm run build
```

Live commands incur provider usage; comparison/tests do not. To reproduce the
buffered branch, run production revision `192470c` in a separate checkout with
the same measurement harness and local configuration. Raw JSON/CSV/Markdown are
retained in `before/` and `after/`; the comparison is machine readable in
`comparison.json`. Re-runs are new measurements and should use a new output path.

## Remaining limits

Two short answers per branch and synthetic text PDFs are not representative of
large enterprise, OCR, multilingual or long-answer workloads. Runs were sequential,
not randomized/interleaved; provider/network and background machine load remain
confounders. No statistically stable P95/P99, paid concurrency, paid interrupted
generation, browser-paint timing, semantic quality score or index speedup is claimed.
Query embedding and remaining token-count network calls still dominate retrieval
preprocessing; native provider latency remains outside local control. Use larger,
human-reviewed datasets and repeated controlled runs before wider performance claims.
