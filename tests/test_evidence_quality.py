"""Transparent source-quality and conservative conflict-detection tests."""

import pytest

from src.search_engine.research.evidence import (
    add_source_quality_signals,
    detect_numeric_claim_relationships,
)


def _source(title: str, url: str, excerpt: str) -> dict:
    return {
        "origin": "web",
        "title": title,
        "url": url,
        "evidence_excerpt": excerpt,
        "published_date": "2026-10-30",
        "author": None,
        "source_type": "unspecified",
    }


def test_quality_signals_are_explanations_not_a_universal_score() -> None:
    sources = add_source_quality_signals(
        [
            _source(
                "Acme funding announcement",
                "https://company.example/news",
                "Acme announced its funding round.",
            ),
            _source(
                "Coverage",
                "https://news.example/story",
                "Reporting about the Acme funding round.",
            ),
        ],
        query="Acme funding round",
    )

    assert sources[0]["publisher"] == "company.example"
    assert sources[0]["source_type"] == "unspecified"
    assert sources[0]["quality_notes"]
    assert "credibility_score" not in sources[0]
    assert any("not proof" in note for note in sources[0]["quality_notes"])


@pytest.mark.parametrize(
    ("right_value", "right_year", "expected"),
    [
        ("80", "2026", "potential_conflict"),
        ("50", "2026", "confirmed_agreement"),
        ("80", "2025", "different_time_periods"),
    ],
)
def test_numeric_claims_distinguish_conflict_agreement_and_time_periods(
    right_value: str,
    right_year: str,
    expected: str,
) -> None:
    sources = [
        _source(
            "Source A",
            "https://a.example/report",
            "Acme Series A funding round in 2026 raised $50 million for expansion.",
        ),
        _source(
            "Source B",
            "https://b.example/report",
            f"Acme Series A funding round in {right_year} raised ${right_value} million for expansion.",
        ),
    ]

    relationships = detect_numeric_claim_relationships(sources)

    assert len(relationships) == 1
    assert relationships[0]["status"] == expected
    assert len(relationships[0]["claims"]) == 2


def test_different_units_or_weak_context_do_not_create_a_conflict() -> None:
    sources = [
        _source("A", "https://a.example", "Acme funding was $50 million."),
        _source("B", "https://b.example", "Unrelated rainfall was 80%."),
    ]
    assert detect_numeric_claim_relationships(sources) == []
