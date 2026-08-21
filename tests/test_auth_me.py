"""Current-user, refresh, and logout endpoints."""

from fastapi.testclient import TestClient

from tests.test_login import LOGIN_URL
from tests.test_signup import SIGNUP_URL, _signup_payload

ME_URL = "/api/auth/me"
REFRESH_URL = "/api/auth/refresh"
LOGOUT_URL = "/api/auth/logout"


def _signup_and_login(client: TestClient) -> tuple[dict[str, object], dict[str, str]]:
    payload = _signup_payload()
    signup = client.post(SIGNUP_URL, json=payload)
    assert signup.status_code == 201
    login = client.post(
        LOGIN_URL,
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert login.status_code == 200
    return payload, login.json()


def test_me_requires_access_token(client: TestClient) -> None:
    response = client.get(ME_URL)
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated."


def test_me_returns_public_profile(client: TestClient) -> None:
    payload, tokens = _signup_and_login(client)
    response = client.get(
        ME_URL,
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == payload["full_name"]
    assert body["email"] == payload["email"]
    assert body["is_verified"] is False
    assert "password" not in body
    assert "password_hash" not in body


def test_refresh_issues_new_tokens(client: TestClient) -> None:
    _, tokens = _signup_and_login(client)
    response = client.post(
        REFRESH_URL,
        json={"refresh_token": tokens["refresh_token"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]

    me = client.get(
        ME_URL,
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200


def test_access_token_cannot_refresh(client: TestClient) -> None:
    _, tokens = _signup_and_login(client)
    response = client.post(
        REFRESH_URL,
        json={"refresh_token": tokens["access_token"]},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated."


def test_refresh_rejects_garbage_token(client: TestClient) -> None:
    response = client.post(REFRESH_URL, json={"refresh_token": "not-a-jwt"})
    assert response.status_code == 401


def test_logout_requires_access_token(client: TestClient) -> None:
    response = client.post(LOGOUT_URL)
    assert response.status_code == 401


def test_logout_returns_no_content(client: TestClient) -> None:
    _, tokens = _signup_and_login(client)
    response = client.post(
        LOGOUT_URL,
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 204
    assert response.content == b""
