"""Validated answer presentation without additional model calls."""

import pytest
from pydantic import ValidationError

from src.search_engine.research.presentation import (
    AnswerPresentation,
    derive_answer_presentation,
)


def test_comparison_table_is_parsed_and_validated() -> None:
    result = derive_answer_presentation(
        "| Cloud | Strength |\n| --- | --- |\n| AWS | Breadth |\n| Azure | Microsoft stack |"
    )
    assert result.type == "comparison"
    assert result.headers == ["Cloud", "Strength"]
    assert result.rows[1] == ["Azure", "Microsoft stack"]


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("- [ ] Review sources\n- [x] Define scope", "checklist"),
        ("- 2025: Prototype\n- 2026: Launch", "timeline"),
        ("1. Install dependencies\n2. Start the server", "steps"),
        ("A normal prose answer.", "standard"),
    ],
)
def test_supported_presentations_and_standard_fallback(answer: str, expected: str) -> None:
    assert derive_answer_presentation(answer).type == expected


def test_invalid_structured_shape_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AnswerPresentation(
            type="comparison",
            headers=["A", "B"],
            rows=[["only one cell"]],
        )
