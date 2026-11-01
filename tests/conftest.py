from collections.abc import Generator

import asyncio

import pytest
from fastapi.testclient import TestClient

from src.search_engine.api import app
from src.search_engine.core.config import settings
from src.search_engine.database.database import engine


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    # Provider calls are explicitly tested with fakes. The production default
    # starts the durable consumer automatically, but unit tests never spend quota.
    monkeypatch.setattr(settings, "indexing_worker_embedded_enabled", False)
    with TestClient(app) as test_client:
        yield test_client
    asyncio.run(engine.dispose())
