"""Pydantic request and response schemas for authentication.

Why it exists: FastAPI needs typed request bodies and safe response shapes
that never include `password_hash`.

Responsibility: validate signup input. No hashing, no SQL.

Communicates with: `core.security.validate_password` and `auth_router`.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from src.search_engine.core.security import validate_password


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
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        return validate_password(value)


class SignupResponse(BaseModel):
    """Public user fields returned after signup. No password."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    full_name: str
    email: str
    is_verified: bool
    created_at: datetime
    updated_at: datetime
