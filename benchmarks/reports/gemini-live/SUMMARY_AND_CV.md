# Real Gemini benchmark: findings and interview guide

## Verified final run

Date: 2026-11-02 in Asia/Hebron (UTC timestamp retained in JSON).
Models: `models/gemini-embedding-001` and `gemini-3.5-flash-lite`.
Corpus: two generated single-page PDFs, two stored chunks, 1536-dimensional
L2-normalized vectors. No private documents. Fresh PostgreSQL schema, isolated
queue and temporary storage; cleanup succeeded. No application migration.

| Measurement | Samples | Median | Range |
|---|---:|---:|---:|
| Full retrieval pipeline | 3 | 323.72 ms | 310.02–329.00 ms |
| Real query embedding | 3 | 314.84 ms | 303.12–317.00 ms |
| Exact pgvector search | 3 | 3.67 ms | 3.46–5.70 ms |
| PDF indexing through committed vectors | 2 | 374.00 ms | 296.98–451.02 ms |
| Real generation method | 2 | 32.42 s | 30.07–34.77 s |
| Document SSE first complete answer | 2 | 34.53 s | 32.18–36.87 s |

Final-run stream completion: 2/2 (100%), not an accuracy or availability metric.
Across the earlier isolated failed generation and final successful generations:
2/3 application answer requests completed (66.7%). These differing configurations
are kept separate; the aggregate is disclosure, not a controlled reliability estimate.

The failed initial shared-schema attempt stopped before generation because index
readiness validation failed. Interference from a concurrently running public
worker was suspected. Isolation was strengthened for subsequent runs.

SDK detail: the installed LangChain Google client documents `max_retries=0` as
restoring default Google retries; `max_retries=1` allows one initial attempt.
The second attempt used zero, so its failed generation is NOT a proven no-retry
transport sample. The final run used SDK attempts=1. Logical operation counts
are not billable request counts; underlying embedding SDK retries were not traced.

Final run recorded 7 embedding operations (2 documents + 3 retrieval queries +
2 answer queries), 2 generation operations, and 18 token-count operations.
Three application answer requests were attempted across the entire investigation,
including the earlier failed one. No further provider calls were made to format
reports or run unit tests. No Tavily requests were part of these benchmarks.

## What the measurements support

Query embedding consumed **97.1%** of total measured direct retrieval time:
sum(query embedding durations) / sum(total retrieval durations) * 100.
Generation consumed **93.9%** of total measured answer-stream duration:
sum(generation method durations) / sum(stream durations) * 100.
These are profiling shares, NOT speed improvements. No before/after experiment
was performed. This corpus is too small to support ANN scaling claims.

The evidence points to provider latency as the dominant measured component.
Investigate generation/model settings and true streaming before optimizing SQL
for this tiny workload. Measure any change in a separate controlled experiment.
The mock report is not a baseline for improvement percentages: providers and
datasets differ. Do not divide mock versus live latencies to claim a speedup.

## Recommended CV wording

Use one performance sentence, retaining the small-test qualification:

> Built a JWT-isolated PDF RAG pipeline using Gemini and PostgreSQL/pgvector with
> 1,536-dimensional normalized embeddings; measured 324 ms median end-to-end
> retrieval latency in a controlled 3-query, 2-document live-provider benchmark.

A stronger architecture/testing bullet that does not overstate this sample:

> Developed reproducible mock and live-provider benchmarks covering PDF indexing,
> semantic retrieval, and SSE answer availability, with isolated test data,
> stage-level timing, failure reporting, and JSON/CSV/Markdown evidence.

Optional profiling sentence, if space permits and the sample size stays visible:

> Profiled a small live Gemini RAG workload and attributed 97.1% of measured
> retrieval time to query embedding, separating provider latency from SQL search.

Do NOT put these on the CV:

- “100% accuracy” or “100% uptime”: neither was measured.
- “Improved performance by X%”: no before/after baseline exists.
- “Supports 10 concurrent Gemini users”: only the earlier mock HTTP batches used concurrency.
- “34-second TTFT”: this app emits a complete document answer in one delta,
  not native model token streaming.
- P95/P99/SLA claims from two or three live samples.

## How to explain this in an interview

**What did you benchmark?** Real Gemini embedding and grounded generation calls,
actual PostgreSQL cosine ordering, and the real authenticated Document Chat SSE
endpoint over loopback HTTP. Two generated PDFs kept customer data out of the test.

**Where were the timers?** `time.perf_counter()` before/after the production
index service, embedding method, repository `search`, generation method and HTTP
stream. Wrappers measured real methods; they did not replace responses. Retrieval
total includes ownership/readiness checks, query embedding and SQL work. SQL time
includes repository execution and mapping, not just database executor CPU.

**How did you measure first content?** Read SSE incrementally with httpx.
Conversation metadata is not content. The first nonblank `delta` sets the content
timestamp. Completion requires content, successful HTTP and terminal `done`.
Document Chat sends one completed-answer delta, so first-content time is almost
the full answer time. The first metadata event must not be advertised as model TTFT.

**Why median?** Sort measured values and take the middle value; with two values,
the median is their midpoint. Two or three samples cannot characterize tail latency.
No warmup was used, so first-call overhead remains included.

**How did you avoid leaking data or spending without bounds?** Fresh private schema,
new test user, generated PDFs, disabled embedded worker, sequential requests,
512-token output cap and one generation SDK attempt. Record token-count calls
too. Stop on a failed stream. Retain failed reports, then clean up only owned data.

**Did you measure accuracy?** No. Successful completion and valid source labels
do not establish answer correctness. A separate human-reviewed labeled corpus
and relevance/faithfulness evaluation are needed.

**What failed?** Shared queue isolation initially failed readiness validation.
An isolated run then failed its first generation. Both attempts are retained.
After correcting the test SDK retry setting, the final two answer requests
completed; this does not prove that retries caused the earlier failure or that
the service is reliably available in production.

Reproduction: `uv run python -m benchmarks.live_gemini --allow-paid --requests 2`.
This incurs provider usage. The immutable evidence for this measured run is in
the same commit; re-running will yield new timings and overwrite the output path
unless `--output` is changed.
