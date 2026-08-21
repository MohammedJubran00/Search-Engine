"""Shared authenticated-client helpers for API tests."""

from fastapi.testclient import TestClient

from tests.test_login import LOGIN_URL
from tests.test_signup import SIGNUP_URL, _signup_payload


def signup_and_login(client: TestClient) -> tuple[dict[str, object], dict[str, str]]:
    payload = _signup_payload()
    signup = client.post(SIGNUP_URL, json=payload)
    assert signup.status_code == 201
    login = client.post(
        LOGIN_URL,
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert login.status_code == 200
    return payload, login.json()


def auth_headers(client: TestClient) -> dict[str, str]:
    _, tokens = signup_and_login(client)
    return {"Authorization": f"Bearer {tokens['access_token']}"}
