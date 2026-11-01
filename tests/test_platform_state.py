"""Persistent platform state, ownership, preferences, and browser integration."""

import asyncio
import threading

from fastapi.testclient import TestClient

from src.search_engine.core.config import settings
from tests.auth_helpers import auth_headers


def test_api_lifespan_starts_automatic_indexing_consumer(monkeypatch) -> None:
    import src.search_engine.api as api_module

    started = threading.Event()

    async def fake_worker() -> None:
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(api_module.settings, "indexing_worker_embedded_enabled", True)
    monkeypatch.setattr(api_module, "run_indexing_worker", fake_worker)
    with TestClient(api_module.app):
        assert started.wait(timeout=1)


def test_conversation_crud_search_and_user_isolation(client: TestClient) -> None:
    owner = auth_headers(client)
    other = auth_headers(client)

    created = client.post(
        "/api/conversations",
        headers=owner,
        json={"title": "Vector benchmark", "mode": "deep"},
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    listing = client.get("/api/conversations?search=vector", headers=owner)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["mode"] == "deep"
    assert client.get("/api/conversations?search=vector", headers=other).json()["total"] == 0
    assert client.get(f"/api/conversations/{conversation_id}", headers=other).status_code == 404

    renamed = client.patch(
        f"/api/conversations/{conversation_id}",
        headers=owner,
        json={"title": "Updated benchmark", "mode": "general"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Updated benchmark"
    assert renamed.json()["mode"] == "general"

    assert client.delete(f"/api/conversations/{conversation_id}", headers=other).status_code == 404
    assert client.delete(f"/api/conversations/{conversation_id}", headers=owner).status_code == 204
    assert client.get(f"/api/conversations/{conversation_id}", headers=owner).status_code == 404


def test_conversation_document_scope_is_persistent_and_owner_scoped(
    client: TestClient, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "rag_storage_dir", tmp_path)
    owner = auth_headers(client)
    other = auth_headers(client)
    conversation = client.post(
        "/api/conversations", headers=owner,
        json={"title": "Document review", "mode": "documents"},
    ).json()
    document = client.post(
        "/api/documents/upload", headers=owner,
        files={"file": ("scope.txt", b"Persistent source scope", "text/plain")},
    ).json()

    associated = client.put(
        f"/api/conversations/{conversation['id']}/documents",
        headers=owner, json={"document_ids": [document["id"]]},
    )
    assert associated.status_code == 200
    assert associated.json() == [document["id"]]
    detail = client.get(f"/api/conversations/{conversation['id']}", headers=owner)
    assert detail.json()["document_ids"] == [document["id"]]
    assert client.put(
        f"/api/conversations/{conversation['id']}/documents",
        headers=other, json={"document_ids": [document["id"]]},
    ).status_code == 404


def test_preferences_are_functional_persistent_and_user_scoped(client: TestClient) -> None:
    owner = auth_headers(client)
    other = auth_headers(client)
    desired = {
        "response_language": "ar", "response_depth": "detailed",
        "default_mode": "documents", "theme": "light",
    }
    updated = client.put("/api/preferences", headers=owner, json=desired)
    assert updated.status_code == 200
    assert updated.json() == desired
    assert client.get("/api/preferences", headers=owner).json() == desired
    assert client.get("/api/preferences", headers=other).json() != desired
    assert client.get("/api/preferences").status_code == 401


def test_cors_allows_state_changing_frontend_methods(client: TestClient) -> None:
    response = client.options(
        "/api/preferences",
        headers={
            "Origin": settings.cors_origins[0],
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    allowed = response.headers["access-control-allow-methods"]
    assert "PUT" in allowed
    assert "PATCH" in allowed
