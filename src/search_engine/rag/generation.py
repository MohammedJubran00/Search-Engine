"""Dedicated Gemini boundary for structured, grounded RAG generation."""

import asyncio
import json
from collections.abc import Mapping
from typing import Any, Protocol

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from src.search_engine.core.config import settings
from src.search_engine.rag.answering import AnswerStatus, GenerationDraft

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": [status.value for status in AnswerStatus],
        },
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "answer", "citations"],
    "additionalProperties": False,
}


class RagGenerationError(RuntimeError):
    """Base class for safe answer-generation failures."""


class RagGenerationTimeoutError(RagGenerationError):
    """Raised when Gemini does not answer within the configured deadline."""


class InvalidGenerationResponseError(RagGenerationError):
    """Raised when Gemini returns an invalid structured response."""


class GenerationProvider(Protocol):
    """Minimal generation and token-counting boundary used by the service."""

    async def count_tokens(self, text: str) -> int: ...

    async def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationDraft: ...


class GeminiRagGenerationProvider:
    """Call one controlled Gemini model and validate its JSON response."""

    def __init__(
        self,
        *,
        client: ChatGoogleGenerativeAI | None = None,
        timeout_seconds: float = settings.rag_answer_timeout_seconds,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Generation timeout must be positive.")
        self._timeout_seconds = timeout_seconds
        self._client = client or ChatGoogleGenerativeAI(
            model=settings.rag_answer_model,
            api_key=settings.gemini_api_key,
            temperature=settings.rag_answer_temperature,
            max_tokens=settings.rag_answer_max_output_tokens,
            retries=settings.rag_answer_max_retries,
            request_timeout=timeout_seconds,
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
        )

    async def count_tokens(self, text: str) -> int:
        """Use Gemini's model-compatible tokenizer without logging prompt text."""
        try:
            count = await asyncio.wait_for(
                asyncio.to_thread(self._client.get_num_tokens, text),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            raise RagGenerationTimeoutError("Gemini token counting timed out.") from exc
        except Exception as exc:
            raise RagGenerationError("Gemini token counting failed.") from exc
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise InvalidGenerationResponseError("Gemini returned an invalid token count.")
        return count

    async def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationDraft:
        try:
            response = await asyncio.wait_for(
                self._client.ainvoke(
                    [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                ),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            raise RagGenerationTimeoutError("Gemini answer generation timed out.") from exc
        except Exception as exc:
            raise RagGenerationError("Gemini answer generation failed.") from exc
        return _parse_response(response)


def _parse_response(response: AIMessage) -> GenerationDraft:
    raw = _message_text(response.content).strip()
    if raw.startswith("```"):
        raw = raw.removeprefix("```json").removeprefix("```")
        raw = raw.removesuffix("```").strip()
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise InvalidGenerationResponseError("Gemini returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise InvalidGenerationResponseError("Gemini response must be a JSON object.")

    try:
        status = AnswerStatus(payload["status"])
        answer = payload["answer"]
        citations = payload["citations"]
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidGenerationResponseError("Gemini response fields are invalid.") from exc
    if not isinstance(answer, str) or not answer.strip():
        raise InvalidGenerationResponseError("Gemini returned an empty answer.")
    if not isinstance(citations, list) or any(not isinstance(item, str) for item in citations):
        raise InvalidGenerationResponseError("Gemini citations must be source labels.")
    labels = tuple(dict.fromkeys(label.strip() for label in citations if label.strip()))
    usage = _safe_usage(getattr(response, "usage_metadata", None))
    return GenerationDraft(
        status=status,
        answer=answer.strip(),
        citation_labels=labels,
        usage=usage,
    )


def _message_text(content: str | list[str | dict[str, Any]]) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "".join(parts)


def _safe_usage(metadata: Mapping[str, Any] | None) -> dict[str, int]:
    if not metadata:
        return {}
    result: dict[str, int] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = metadata.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            result[key] = value
    return result
