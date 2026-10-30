"""Transparent source signals and conservative numeric-claim comparison."""

import re
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

_WORD = re.compile(r"[A-Za-z0-9\u0600-\u06ff]+")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_AMOUNT = re.compile(
    r"(?P<currency>[$€£]|USD|EUR|GBP)?\s*"
    r"(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>billion|million|thousand|bn|m|k|%)?",
    re.IGNORECASE,
)
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "was",
    "is", "were", "are", "at", "by", "with", "from", "as", "that", "this",
}


def add_source_quality_signals(
    sources: Sequence[dict],
    *,
    query: str,
) -> list[dict]:
    """Attach explainable metadata without declaring any publisher correct."""
    query_terms = _terms(query)
    publishers = {
        urlparse(str(source.get("url", ""))).netloc.casefold()
        for source in sources
        if source.get("url")
    }
    result: list[dict] = []
    for source in sources:
        enriched = dict(source)
        parsed = urlparse(str(source.get("url", "")))
        publisher = parsed.netloc.casefold()
        evidence = str(source.get("evidence_excerpt", ""))
        title = str(source.get("title", ""))
        overlap = sorted(query_terms & _terms(f"{title} {evidence}"))
        notes = [f"Publisher domain: {publisher or 'unavailable'}."]
        notes.append(
            "Direct evidence excerpt is available."
            if evidence.strip()
            else "No evidence excerpt was supplied."
        )
        notes.append(
            "Publication date was supplied by the search provider."
            if source.get("published_date")
            else "Publication date was not supplied."
        )
        notes.append(
            f"Shares {len(overlap)} distinct term(s) with the search question."
        )
        if len(publishers) > 1:
            notes.append(
                f"Result set includes {len(publishers)} distinct publisher domains; "
                "this is not proof of independent corroboration."
            )
        enriched.update(
            {
                "publisher": publisher or None,
                "author": source.get("author"),
                "source_type": source.get("source_type") or "unspecified",
                "quality_notes": notes,
            }
        )
        result.append(enriched)
    return result


def detect_numeric_claim_relationships(sources: Sequence[dict]) -> list[dict]:
    """Compare like-for-like numeric claims only when context is sufficiently similar."""
    claims: list[dict] = []
    for source in sources:
        text = str(source.get("evidence_excerpt", ""))
        for match in _AMOUNT.finditer(text):
            raw = match.group(0).strip()
            unit = _normalize_unit(match.group("unit"))
            currency = _normalize_currency(match.group("currency"))
            if not raw or (not unit and not currency):
                continue
            try:
                value = Decimal(match.group("value"))
            except InvalidOperation:
                continue
            start, end = max(0, match.start() - 80), min(len(text), match.end() + 80)
            context = text[start:end]
            claims.append(
                {
                    "value": str(value.normalize()),
                    "currency": currency,
                    "unit": unit,
                    "years": sorted(set(_YEAR.findall(context))),
                    "context_terms": sorted(_terms(context) - _terms(raw)),
                    "source_title": source.get("title"),
                    "source_url": source.get("url"),
                    "evidence_excerpt": context.strip(),
                }
            )

    relationships: list[dict] = []
    for index, left in enumerate(claims):
        for right in claims[index + 1 :]:
            if left["source_url"] == right["source_url"]:
                continue
            if left["currency"] != right["currency"] or left["unit"] != right["unit"]:
                continue
            overlap = set(left["context_terms"]) & set(right["context_terms"])
            if len(overlap) < 2:
                continue
            left_years, right_years = set(left["years"]), set(right["years"])
            if left_years and right_years and left_years.isdisjoint(right_years):
                status = "different_time_periods"
            elif left["value"] == right["value"]:
                status = "confirmed_agreement"
            else:
                status = "potential_conflict"
            relationships.append(
                {
                    "status": status,
                    "reason": _relationship_reason(status),
                    "shared_context_terms": sorted(overlap)[:8],
                    "claims": [
                        {key: left[key] for key in _public_claim_keys()},
                        {key: right[key] for key in _public_claim_keys()},
                    ],
                }
            )
    return relationships


def _terms(text: str) -> set[str]:
    return {
        word.casefold()
        for word in _WORD.findall(text)
        if len(word) > 1 and word.casefold() not in _STOP_WORDS
    }


def _normalize_unit(value: str | None) -> str | None:
    if not value:
        return None
    return {
        "bn": "billion",
        "m": "million",
        "k": "thousand",
    }.get(value.casefold(), value.casefold())


def _normalize_currency(value: str | None) -> str | None:
    if not value:
        return None
    return {"$": "USD", "€": "EUR", "£": "GBP"}.get(value.upper(), value.upper())


def _public_claim_keys() -> tuple[str, ...]:
    return (
        "value",
        "currency",
        "unit",
        "years",
        "source_title",
        "source_url",
        "evidence_excerpt",
    )


def _relationship_reason(status: str) -> str:
    if status == "potential_conflict":
        return "Comparable claims use the same unit and time context but report different values."
    if status == "confirmed_agreement":
        return "Comparable claims from different sources report the same value."
    return "The values refer to different explicit time periods and are not treated as a conflict."
