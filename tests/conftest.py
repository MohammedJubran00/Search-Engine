from collections.abc import Generator

import asyncio

import pytest
from fastapi.testclient import TestClient

from src.search_engine.api import app
from src.search_engine.database.database import engine


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
    asyncio.run(engine.dispose())
