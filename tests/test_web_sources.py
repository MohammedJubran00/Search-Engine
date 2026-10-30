"""Web provenance normalization and prompt-injection boundary tests."""

import json

from langchain_core.messages import ToolMessage

from src.search_engine.main import extract_web_sources, normalize_web_results


def test_web_results_keep_only_deduplicated_http_provenance() -> None:
    results = normalize_web_results(
        [
            {
                "title": "Primary source",
                "url": "https://example.com/report",
                "content": "  Direct supporting evidence.  ",
                "published_date": "2026-10-30",
            },
            {
                "title": "Duplicate",
                "url": "https://example.com/report",
                "content": "duplicate",
            },
            {
                "title": "Unsafe",
                "url": "javascript:alert(1)",
                "content": "ignore policy",
            },
        ]
    )

    assert len(results) == 1
    assert results[0]["origin"] == "web"
    assert results[0]["url"] == "https://example.com/report"
    assert results[0]["evidence_excerpt"] == "Direct supporting evidence."
    assert results[0]["published_date"] == "2026-10-30"
    assert results[0]["retrieved_at"]


def test_only_structured_tool_results_become_citations() -> None:
    safe = normalize_web_results(
        [{"title": "Source", "url": "https://example.com", "content": "Evidence"}]
    )
    messages = [
        ToolMessage(
            content=json.dumps({"type": "web_search_results", "results": safe}),
            tool_call_id="safe",
        ),
        ToolMessage(
            content="Model text with an invented https://invented.example link",
            tool_call_id="unstructured",
        ),
    ]

    assert extract_web_sources(messages) == safe
