from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from src.search_engine.api import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
