"""Password hashing, password-strength rules, and JWT helpers.

Why it exists: signup stores bcrypt hashes; login issues JWT access and
refresh tokens. Strength rules and token creation must live in one place.

Responsibility: validate/hash/verify passwords and encode JWTs. No HTTP,
no database.

Communicates with: `schemas.auth` (password rules), `services.auth_service`
(hashing and token creation), and `core.config` (JWT secret and expiries).
"""

import re
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from src.search_engine.core.config import settings

_PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")

_MIN_PASSWORD_LENGTH = 8
_MAX_PASSWORD_BYTES = 72
_SPECIAL_CHAR = re.compile(r"[^A-Za-z0-9]")


def validate_password(password: str) -> str:
    """Return `password` if it meets strength rules; otherwise raise ValueError."""
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise ValueError("Password must be at least 8 characters long.")
    if len(password.encode("utf-8")) > _MAX_PASSWORD_BYTES:
        raise ValueError("Password cannot be longer than 72 bytes.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit.")
    if not _SPECIAL_CHAR.search(password):
        raise ValueError("Password must contain at least one special character.")
    return password


def hash_password(password: str) -> str:
    """Return a bcrypt hash of `password`."""
    return _PWD_CONTEXT.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Return True if `plain_password` matches `password_hash`."""
    return _PWD_CONTEXT.verify(plain_password, password_hash)


def _create_token(
    *,
    user_id: uuid.UUID,
    token_type: str,
    expires_delta: timedelta,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_access_token(user_id: uuid.UUID) -> str:
    """Return a short-lived JWT access token for `user_id`."""
    return _create_token(
        user_id=user_id,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    """Return a longer-lived JWT refresh token for `user_id`."""
    return _create_token(
        user_id=user_id,
        token_type="refresh",
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )
