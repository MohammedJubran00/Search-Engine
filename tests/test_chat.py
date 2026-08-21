"""Authenticated chat persistence. Gemini/LangGraph are mocked."""

from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from tests.test_login import LOGIN_URL
from tests.test_signup import SIGNUP_URL, _signup_payload


def _login_headers(client: TestClient) -> dict[str, str]:
    payload = _signup_payload()
    signup = client.post(SIGNUP_URL, json=payload)
    assert signup.status_code == 201
    login = client.post(
        LOGIN_URL,
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _refresh_token(client: TestClient) -> str:
    payload = _signup_payload()
    signup = client.post(SIGNUP_URL, json=payload)
    assert signup.status_code == 201
    login = client.post(
        LOGIN_URL,
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert login.status_code == 200
    return login.json()["refresh_token"]


def test_chat_requires_access_token(client: TestClient) -> None:
    response = client.post("/chat", json={"query": "hello"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated."


def test_latest_conversation_requires_access_token(client: TestClient) -> None:
    response = client.get("/api/conversations/latest")
    assert response.status_code == 401


def test_refresh_token_cannot_call_chat(client: TestClient) -> None:
    refresh = _refresh_token(client)
    response = client.post(
        "/chat",
        json={"query": "hello"},
        headers={"Authorization": f"Bearer {refresh}"},
    )
    assert response.status_code == 401


@patch("src.search_engine.api.graph_app.invoke", return_value={"answer": "Paris"})
def test_chat_persists_for_the_authenticated_user(
    mock_invoke,
    client: TestClient,
) -> None:
    headers = _login_headers(client)
    response = client.post(
        "/chat",
        json={"query": "What is the capital of France?", "session_id": "forged-id"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Paris"
    assert body["conversation_id"]
    mock_invoke.assert_called_once()
    graph_input = mock_invoke.call_args.args[0]
    assert graph_input["session_id"] == body["conversation_id"]
    assert graph_input["query"] == "What is the capital of France?"
    assert "forged-id" not in graph_input["session_id"]

    latest = client.get("/api/conversations/latest", headers=headers)
    assert latest.status_code == 200
    data = latest.json()
    assert data["conversation_id"] == body["conversation_id"]
    assert [item["role"] for item in data["messages"]] == ["user", "assistant"]
    assert data["messages"][0]["content"] == "What is the capital of France?"
    assert data["messages"][1]["content"] == "Paris"


@patch("src.search_engine.api.graph_app.invoke", return_value={"answer": "secret-answer"})
def test_user_cannot_use_another_users_conversation(
    mock_invoke,
    client: TestClient,
) -> None:
    owner_headers = _login_headers(client)
    created = client.post(
        "/chat",
        json={"query": "owner question"},
        headers=owner_headers,
    )
    assert created.status_code == 200
    conversation_id = created.json()["conversation_id"]

    other_headers = _login_headers(client)
    stolen = client.post(
        "/chat",
        json={"query": "intruder", "conversation_id": conversation_id},
        headers=other_headers,
    )
    assert stolen.status_code == 404
    assert stolen.json()["error"] == "Conversation not found."

    latest_other = client.get("/api/conversations/latest", headers=other_headers)
    assert latest_other.status_code == 200
    assert latest_other.json()["conversation_id"] is None
    assert latest_other.json()["messages"] == []

    latest_owner = client.get("/api/conversations/latest", headers=owner_headers)
    assert latest_owner.json()["conversation_id"] == conversation_id
    assert latest_owner.json()["messages"][0]["content"] == "owner question"


@patch("src.search_engine.api.graph_app.invoke", return_value={"answer": "ok"})
def test_unknown_conversation_is_not_found(mock_invoke, client: TestClient) -> None:
    headers = _login_headers(client)
    response = client.post(
        "/chat",
        json={"query": "hello", "conversation_id": str(uuid4())},
        headers=headers,
    )
    assert response.status_code == 404
    mock_invoke.assert_not_called()


@patch(
    "src.search_engine.api.stream_agent",
    side_effect=lambda session_id, query: iter(["Hel", "lo"]),
)
def test_stream_persists_assistant_answer(mock_stream, client: TestClient) -> None:
    headers = _login_headers(client)
    response = client.post(
        "/chat/stream",
        json={"query": "stream this"},
        headers=headers,
    )
    assert response.status_code == 200
    assert b"Hel" in response.content
    assert b"lo" in response.content
    mock_stream.assert_called_once()

    latest = client.get("/api/conversations/latest", headers=headers)
    data = latest.json()
    assert [item["role"] for item in data["messages"]] == ["user", "assistant"]
    assert data["messages"][1]["content"] == "Hello"
