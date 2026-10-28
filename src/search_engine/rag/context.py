"""Citation-aware, token-bounded context construction for RAG generation."""

import re
from collections.abc import Awaitable, Callable, Sequence

from src.search_engine.core.config import settings
from src.search_engine.rag.answering import BuiltContext, SourceReference
from src.search_engine.rag.contracts import RetrievedChunk

TokenCounter = Callable[[str], Awaitable[int]]


class InvalidContextBudgetError(ValueError):
    """Raised when no safe context budget is available."""


class RagContextBuilder:
    """Build bounded evidence blocks while retaining multiple ranked sources."""

    def __init__(
        self,
        *,
        max_sources: int = settings.rag_answer_max_sources,
        excerpt_characters: int = settings.rag_answer_evidence_excerpt_characters,
    ) -> None:
        if max_sources < 1:
            raise ValueError("Maximum RAG sources must be positive.")
        if excerpt_characters < 1:
            raise ValueError("Evidence excerpt size must be positive.")
        self._max_sources = max_sources
        self._excerpt_characters = excerpt_characters

    async def build(
        self,
        chunks: Sequence[RetrievedChunk],
        *,
        token_counter: TokenCounter,
        available_tokens: int,
    ) -> BuiltContext:
        if available_tokens < 1:
            raise InvalidContextBudgetError("No token budget remains for evidence.")

        unique: list[RetrievedChunk] = []
        seen: set[str] = set()
        duplicate_count = 0
        for chunk in chunks:
            clean = chunk.text.strip()
            if not clean:
                continue
            fingerprint = " ".join(clean.split()).casefold()
            if fingerprint in seen:
                duplicate_count += 1
                continue
            seen.add(fingerprint)
            unique.append(chunk)
            if len(unique) == self._max_sources:
                break

        blocks: list[str] = []
        sources: list[SourceReference] = []
        remaining = available_tokens
        truncated_count = 0

        for index, chunk in enumerate(unique):
            label = f"S{index + 1}"
            candidates_left = len(unique) - index
            fair_budget = max(1, remaining // candidates_left)
            header = _source_header(label, chunk)
            footer = "\n</source>"
            wrapper_tokens = await token_counter(header + footer)
            text_budget = fair_budget - wrapper_tokens
            if text_budget < 1:
                continue

            clean_text = chunk.text.strip()
            full_tokens = await token_counter(clean_text)
            included = clean_text
            if full_tokens > text_budget:
                included = await _truncate_at_safe_boundary(
                    clean_text,
                    token_counter=token_counter,
                    max_tokens=text_budget,
                )
                truncated_count += 1
            if not included:
                continue

            block = f"{header}{included}{footer}"
            block_tokens = await token_counter(block)
            if block_tokens > remaining:
                continue
            blocks.append(block)
            remaining -= block_tokens
            sources.append(
                SourceReference(
                    label=label,
                    document_id=chunk.document_id,
                    chunk_id=chunk.chunk_id,
                    filename=chunk.filename,
                    page_number=chunk.page_number,
                    rank=chunk.rank,
                    cosine_similarity=chunk.cosine_similarity,
                    evidence_excerpt=_excerpt(included, self._excerpt_characters),
                )
            )

        context = "\n\n".join(blocks)
        actual_tokens = await token_counter(context) if context else 0
        if actual_tokens > available_tokens:
            raise InvalidContextBudgetError("Constructed context exceeded its budget.")
        return BuiltContext(
            text=context,
            sources=tuple(sources),
            token_count=actual_tokens,
            available_tokens=available_tokens,
            duplicate_chunks_skipped=duplicate_count,
            truncated_source_count=truncated_count,
        )


def _source_header(label: str, chunk: RetrievedChunk) -> str:
    page = str(chunk.page_number) if chunk.page_number is not None else "unknown"
    return (
        f'<source label="{label}" document_id="{chunk.document_id}" '
        f'chunk_id="{chunk.chunk_id}" page="{page}">\n'
    )


async def _truncate_at_safe_boundary(
    text: str,
    *,
    token_counter: TokenCounter,
    max_tokens: int,
) -> str:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?؟])\s+", text) if part.strip()]
    sentence_result = await _largest_prefix(sentences, token_counter, max_tokens)
    if sentence_result:
        return sentence_result
    words = text.split()
    return await _largest_prefix(words, token_counter, max_tokens)


async def _largest_prefix(
    parts: Sequence[str],
    token_counter: TokenCounter,
    max_tokens: int,
) -> str:
    low, high = 0, len(parts)
    best = ""
    while low < high:
        middle = (low + high + 1) // 2
        candidate = " ".join(parts[:middle]).strip()
        if await token_counter(candidate) <= max_tokens:
            best = candidate
            low = middle
        else:
            high = middle - 1
    return best


def _excerpt(text: str, maximum: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= maximum:
        return clean
    prefix = clean[: maximum + 1]
    boundary = prefix.rfind(" ")
    return (prefix[:boundary] if boundary > 0 else clean[:maximum]).rstrip() + "…"
