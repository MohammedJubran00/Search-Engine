"""Public, user-scoped operational metrics contract."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class UsageSnapshot(BaseModel):
    retention: Literal["process_local_bounded"]
    request_count: int = Field(ge=0)
    active_requests: int = Field(ge=0)
    daily_request_count: int = Field(ge=0)
    daily_request_limit: int = Field(ge=1)
    average_response_seconds: float = Field(ge=0)
    average_retrieval_seconds: float = Field(ge=0)
    average_generation_seconds: float = Field(ge=0)
    average_tavily_seconds: float = Field(ge=0)
    average_searches: float = Field(ge=0)
    average_sources: float = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    embedding_requests: int = Field(ge=0)
    error_count: int = Field(ge=0)
    quota_error_count: int = Field(ge=0)
    modes: dict[str, int]
    recent: list[dict[str, Any]]
