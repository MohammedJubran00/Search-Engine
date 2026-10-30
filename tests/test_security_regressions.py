import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.search_engine.core.config import Settings, settings
from src.search_engine.schemas.chat import WebCitation
from tests.auth_helpers import auth_headers


def test_cors_allows_configured_frontend_and_rejects_unknown_origin(client: TestClient) -> None:
    allowed = settings.cors_origins[0]
    response = client.get("/", headers={"Origin": allowed})
    assert response.headers["access-control-allow-origin"] == allowed

    rejected = client.get("/", headers={"Origin": "https://attacker.example"})
    assert "access-control-allow-origin" not in rejected.headers


def test_validation_logs_never_include_submitted_secret(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "DO-NOT-LOG-THIS-PASSWORD"
    caplog.set_level(logging.WARNING, logger="src.search_engine.api")
    response = client.post(
        "/chat",
        json={"query": {"password": secret}},
        headers=auth_headers(client),
    )
    assert response.status_code == 400
    assert secret not in caplog.text
    assert "Invalid request body fields" in caplog.text


def test_unsafe_citation_urls_are_rejected() -> None:
    with pytest.raises(ValidationError):
        WebCitation(title="Injected", url="javascript:alert(1)")
    with pytest.raises(ValidationError):
        WebCitation(title="Inline data", url="data:text/html,<script>alert(1)</script>")


def test_chat_query_has_a_resource_bound(client: TestClient) -> None:
    response = client.post(
        "/chat",
        json={"query": "x" * (settings.rag_retrieval_max_query_characters + 1)},
        headers=auth_headers(client),
    )
    assert response.status_code == 400


def test_jwt_configuration_rejects_weak_secret_and_algorithm() -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_secret_key="short")
    with pytest.raises(ValidationError):
        Settings(jwt_algorithm="none")
