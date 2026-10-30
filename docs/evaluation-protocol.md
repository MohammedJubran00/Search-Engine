# Private human-labeled evaluation protocol

The committed JSONL fixtures under `tests/fixtures/` are synthetic regression
cases. They are not real-provider results and must be reported separately from
an evaluation over user-owned documents.

Store a private benchmark beneath `evaluations/private/`; Git ignores every
file in that directory. Do not paste proprietary document text into source,
test snapshots, logs, or issue reports. Each retrieval JSONL record follows the
existing `load_golden_dataset` contract:

```json
{"id":"en-project-goal","question":"What is the primary goal?","expected_document_ids":["UUID"],"relevant_chunk_ids":["UUID"],"relevant_pages":[],"expected_evidence":["short reviewer-authored description"],"answerable":true}
```

Build at least a small bilingual set with English and Arabic queries and label:

- answerable facts, paraphrases, multi-chunk answers, dates, and numbers;
- similar-document distractors and repeated page boilerplate;
- questions absent from the documents, where no chunk should be returned;
- required answer citations, faithfulness, and expected abstention.

For retrieval, report Hit@K, Recall@K, Precision@K, MRR, and false positives
using explicit chunk/page/document labels. For generation, two human reviewers
should independently record citation accuracy, claim faithfulness, and correct
abstention, then resolve disagreements. Preserve the raw labels and exact local
revision used. Never infer relevance from similarity scores and never invent a
result when Gemini, Tavily, or the private corpus was not actually run.

Research evaluation should separately cover factual questions, comparisons,
multi-step research, missing/contradictory/outdated evidence, follow-ups, tool
failure, and prompt injection embedded in web excerpts. Automated tests use
fake providers for those boundaries; real provider checks require explicit
approval because they may incur cost.

Current status: the private benchmark has not been populated or executed. This
repository therefore reports only synthetic regression results.
