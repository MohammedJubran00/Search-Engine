"""Gemini generation boundary tests without external calls."""

import asyncio
import json

import pytest
from langchain_core.messages import AIMessage

from src.search_engine.rag.answering import AnswerStatus
from src.search_engine.rag.generation import (
    GeminiRagGenerationProvider,
    InvalidGenerationResponseError,
    RagGenerationError,
    RagGenerationTimeoutError,
)


class FakeClient:
    def __init__(self, response: AIMessage | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error

    def get_num_tokens(self, text: str) -> int:
        if self.error:
            raise self.error
        return len(text.split())

    async def ainvoke(self, messages):
        if self.error:
            raise self.error
        return self.response


def test_provider_parses_structured_answer_and_safe_usage() -> None:
    response = AIMessage(
        content=json.dumps(
            {"status": "answered", "answer": "Supported [S1].", "citations": ["S1"]}
        ),
        usage_metadata={"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
    )
    provider = GeminiRagGenerationProvider(client=FakeClient(response))  # type: ignore[arg-type]
    draft = asyncio.run(provider.generate(system_prompt="trusted", user_prompt="evidence"))
    assert draft.status is AnswerStatus.ANSWERED
    assert draft.citation_labels == ("S1",)
    assert draft.usage == {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14}


def test_provider_rejects_malformed_output() -> None:
    provider = GeminiRagGenerationProvider(client=FakeClient(AIMessage(content="not json")))  # type: ignore[arg-type]
    with pytest.raises(InvalidGenerationResponseError):
        asyncio.run(provider.generate(system_prompt="trusted", user_prompt="evidence"))


def test_provider_sanitizes_api_failures() -> None:
    provider = GeminiRagGenerationProvider(client=FakeClient(error=RuntimeError("secret")))  # type: ignore[arg-type]
    with pytest.raises(RagGenerationError, match="generation failed") as caught:
        asyncio.run(provider.generate(system_prompt="trusted", user_prompt="evidence"))
    assert "secret" not in str(caught.value)


class SlowClient(FakeClient):
    async def ainvoke(self, messages):
        await asyncio.sleep(0.05)
        return self.response


def test_provider_enforces_generation_timeout() -> None:
    provider = GeminiRagGenerationProvider(
        client=SlowClient(AIMessage(content="{}")),  # type: ignore[arg-type]
        timeout_seconds=0.001,
    )
    with pytest.raises(RagGenerationTimeoutError):
        asyncio.run(provider.generate(system_prompt="trusted", user_prompt="evidence"))
