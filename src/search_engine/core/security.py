"""Password hashing and password-strength rules.

Why it exists: signup must store bcrypt hashes, not plaintext, and strength
rules must live in one place.

Responsibility: validate password rules and hash passwords. No JWT in this
task. No HTTP, no database.

Communicates with: `schemas.auth` (validation) and `services.auth_service`
(hashing before insert).
"""

import re

from passlib.context import CryptContext

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
