"""Login endpoint tests. Refresh, logout, and /me are not covered here."""

from fastapi.testclient import TestClient

from tests.test_signup import SIGNUP_URL, _signup_payload

LOGIN_URL = "/api/auth/login"


def test_login_success(client: TestClient) -> None:
    payload = _signup_payload()
    signup = client.post(SIGNUP_URL, json=payload)
    assert signup.status_code == 201

    response = client.post(
        LOGIN_URL,
        json={"email": payload["email"], "password": payload["password"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["access_token"] != body["refresh_token"]
    assert "password" not in body


def test_login_wrong_password(client: TestClient) -> None:
    payload = _signup_payload()
    signup = client.post(SIGNUP_URL, json=payload)
    assert signup.status_code == 201

    response = client.post(
        LOGIN_URL,
        json={"email": payload["email"], "password": "WrongPass1!"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_login_unknown_email(client: TestClient) -> None:
    response = client.post(
        LOGIN_URL,
        json={"email": "nobody-login@example.com", "password": "Str0ng!Pass"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."
