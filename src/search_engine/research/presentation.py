"""Validated structured presentation derived from an existing answer without another call."""

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PresentationItem(BaseModel):
    label: str | None = None
    text: str
    completed: bool | None = None


class AnswerPresentation(BaseModel):
    type: Literal["standard", "comparison", "timeline", "steps", "checklist"]
    headers: list[str] = Field(default_factory=list, max_length=12)
    rows: list[list[str]] = Field(default_factory=list, max_length=50)
    items: list[PresentationItem] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_shape(self) -> "AnswerPresentation":
        if self.type == "comparison":
            if not self.headers or not self.rows:
                raise ValueError("Comparison presentation requires headers and rows.")
            if any(len(row) != len(self.headers) for row in self.rows):
                raise ValueError("Every comparison row must match the headers.")
        elif self.type in {"timeline", "steps", "checklist"}:
            if not self.items:
                raise ValueError("List presentation requires items.")
        return self


_CHECKLIST = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(.+?)\s*$")
_STEP = re.compile(r"^\s*(\d+)[.)]\s+(.+?)\s*$")
_TIMELINE = re.compile(
    r"^\s*[-*]\s+((?:19|20)\d{2}(?:-\d{2}-\d{2})?|[A-Z][a-z]+\s+(?:19|20)\d{2})\s*[:—-]\s*(.+?)\s*$"
)


def derive_answer_presentation(answer: str) -> AnswerPresentation:
    """Recognize bounded Markdown structures; return standard on any ambiguity."""
    try:
        lines = [line.rstrip() for line in answer.splitlines()]
        comparison = _comparison(lines)
        if comparison is not None:
            return comparison

        checklist = [match for line in lines if (match := _CHECKLIST.match(line))]
        if checklist:
            return AnswerPresentation(
                type="checklist",
                items=[
                    PresentationItem(
                        text=match.group(2).strip(),
                        completed=match.group(1).casefold() == "x",
                    )
                    for match in checklist[:50]
                ],
            )

        timeline = [match for line in lines if (match := _TIMELINE.match(line))]
        if len(timeline) >= 2:
            return AnswerPresentation(
                type="timeline",
                items=[
                    PresentationItem(
                        label=match.group(1).strip(),
                        text=match.group(2).strip(),
                    )
                    for match in timeline[:50]
                ],
            )

        steps = [match for line in lines if (match := _STEP.match(line))]
        if len(steps) >= 2:
            return AnswerPresentation(
                type="steps",
                items=[
                    PresentationItem(
                        label=match.group(1),
                        text=match.group(2).strip(),
                    )
                    for match in steps[:50]
                ],
            )
    except (TypeError, ValueError):
        pass
    return AnswerPresentation(type="standard")


def _comparison(lines: list[str]) -> AnswerPresentation | None:
    for index in range(len(lines) - 2):
        header = _table_cells(lines[index])
        separator = _table_cells(lines[index + 1])
        if not header or len(header) < 2 or len(separator) != len(header):
            continue
        if not all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in separator):
            continue
        rows: list[list[str]] = []
        for line in lines[index + 2 :]:
            cells = _table_cells(line)
            if not cells:
                break
            if len(cells) != len(header):
                return None
            rows.append(cells)
            if len(rows) == 50:
                break
        if rows:
            return AnswerPresentation(type="comparison", headers=header[:12], rows=rows)
    return None


def _table_cells(line: str) -> list[str]:
    clean = line.strip()
    if "|" not in clean:
        return []
    return [cell.strip() for cell in clean.strip("|").split("|")]
