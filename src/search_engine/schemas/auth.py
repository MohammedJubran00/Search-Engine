"""Pydantic request and response schemas for authentication.

Why it exists: FastAPI needs typed request bodies and safe response shapes
that never include `password_hash`.

Responsibility: validate signup, login, and refresh input. No hashing, no SQL.

Communicates with: `core.security.validate_password` and `auth_router`.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from src.search_engine.core.security import validate_password


def normalize_email(value: object) -> object:
    """Lowercase and trim an email string; leave other values unchanged."""
    if isinstance(value, str):
        return value.strip().lower()
    return value


class SignupRequest(BaseModel):
    """Body for `POST /api/auth/signup`."""

    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Full name is required.")
        return name

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, value: object) -> object:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        return validate_password(value)


class UserPublic(BaseModel):
    """Public user fields. Never includes password hashes."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    full_name: str
    email: str
    is_verified: bool
    created_at: datetime
    updated_at: datetime


class SignupResponse(UserPublic):
    """Public user fields returned after signup. No password."""


class LoginRequest(BaseModel):
    """Body for `POST /api/auth/login`."""

    email: EmailStr
    password: str = Field(min_length=1)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, value: object) -> object:
        return normalize_email(value)


class LoginResponse(BaseModel):
    """JWT pair returned after a successful login. No password."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Body for `POST /api/auth/refresh`."""

    refresh_token: str = Field(min_length=1)
