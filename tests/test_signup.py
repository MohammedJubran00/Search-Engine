"""Signup endpoint tests. Login is not covered in this milestone."""

import uuid

from fastapi.testclient import TestClient

SIGNUP_URL = "/api/auth/signup"


def _signup_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "full_name": "Ada Lovelace",
        "email": f"ada-{uuid.uuid4().hex}@example.com",
        "password": "Str0ng!Pass",
    }
    payload.update(overrides)
    return payload


def test_signup_success(client: TestClient) -> None:
    response = client.post(SIGNUP_URL, json=_signup_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["full_name"] == "Ada Lovelace"
    assert body["email"].endswith("@example.com")
    assert body["is_verified"] is False
    assert "id" in body
    assert "password" not in body
    assert "password_hash" not in body


def test_signup_duplicate_email(client: TestClient) -> None:
    payload = _signup_payload(email="duplicate.signup@example.com")
    first = client.post(SIGNUP_URL, json=payload)
    assert first.status_code in {201, 409}

    second = client.post(SIGNUP_URL, json=payload)
    assert second.status_code == 409
    assert "email" in second.json()["detail"].lower()


def test_signup_invalid_password(client: TestClient) -> None:
    response = client.post(
        SIGNUP_URL,
        json=_signup_payload(password="weak"),
    )

    assert response.status_code == 400
    assert "password" in response.json()["error"].lower()


def test_signup_invalid_email(client: TestClient) -> None:
    response = client.post(
        SIGNUP_URL,
        json=_signup_payload(email="not-an-email"),
    )

    assert response.status_code == 400
    assert "email" in response.json()["error"].lower()
