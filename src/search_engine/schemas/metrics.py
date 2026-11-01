"""Persistent user-scoped usage dashboard contract."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class DailyUsage(BaseModel):
    date: str
    requests: int = Field(ge=0)


class UsageSnapshot(BaseModel):
    retention: Literal["persistent"]
    request_count: int = Field(ge=0)
    daily_request_count: int = Field(ge=0)
    monthly_request_count: int = Field(ge=0)
    successful_requests: int = Field(ge=0)
    failed_requests: int = Field(ge=0)
    average_response_seconds: float = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    embedding_tokens: int = Field(ge=0)
    gemini_generation_requests: int = Field(ge=0)
    gemini_embedding_requests: int = Field(ge=0)
    tavily_searches: int = Field(ge=0)
    estimated_cost_usd: str
    usage_by_conversation: dict[str, int]
    daily_usage: list[DailyUsage]
    recent: list[dict[str, Any]]
