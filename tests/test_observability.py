import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from src.search_engine.core.config import settings
from src.search_engine.services.observability_service import (
    ObservabilityService,
    UsageLimitError,
)
from tests.auth_helpers import auth_headers


def test_observability_is_content_free_and_user_scoped() -> None:
    service = ObservabilityService()
    owner = uuid.uuid4()
    other = uuid.uuid4()

    async def exercise() -> tuple[dict, dict]:
        record = await service.begin(owner)
        record.mode = "documents"
        record.source_count = 3
        record.input_tokens = 42
        await service.finish(record)
        return await service.snapshot(owner), await service.snapshot(other)

    owned, isolated = asyncio.run(exercise())
    assert owned["request_count"] == 1
    assert owned["modes"]["documents"] == 1
    assert owned["input_tokens"] == 42
    assert isolated["request_count"] == 0
    forbidden = {"prompt", "query", "answer", "content", "document_text", "user_id"}
    assert not forbidden.intersection(owned["recent"][0])


def test_observability_enforces_concurrent_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "usage_max_concurrent_requests", 1)
    service = ObservabilityService()
    user_id = uuid.uuid4()

    async def exercise() -> None:
        first = await service.begin(user_id)
        with pytest.raises(UsageLimitError, match="Concurrent"):
            await service.begin(user_id)
        await service.finish(first)

    asyncio.run(exercise())


def test_observability_enforces_daily_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "usage_daily_request_limit", 1)
    service = ObservabilityService()
    user_id = uuid.uuid4()

    async def exercise() -> None:
        record = await service.begin(user_id)
        await service.finish(record)
        with pytest.raises(UsageLimitError, match="Daily"):
            await service.begin(user_id)

    asyncio.run(exercise())


def test_metrics_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/metrics").status_code == 401


def test_metrics_endpoint_is_private_to_current_user(client: TestClient) -> None:
    first_headers = auth_headers(client)
    first = client.get("/api/metrics", headers=first_headers)
    assert first.status_code == 200
    assert first.json()["retention"] == "process_local_bounded"

    second_headers = auth_headers(client)
    second = client.get("/api/metrics", headers=second_headers)
    assert second.status_code == 200
    assert second.json()["request_count"] == 0
