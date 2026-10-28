"""Schema checks for the human-reviewed Phase 6 answer-quality cases."""

import json
from pathlib import Path


def test_answer_golden_cases_are_human_verifiable() -> None:
    path = Path(__file__).parent / "fixtures" / "rag_answer_golden.jsonl"
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(cases) >= 5
    assert {case["expected_status"] for case in cases} == {
        "answered",
        "insufficient_evidence",
    }
    for case in cases:
        labels = {source["label"] for source in case["evidence"]}
        assert set(case["required_citations"]) <= labels
        assert case["review"].strip()
