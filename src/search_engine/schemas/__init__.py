"""Pydantic request and response schemas for authentication.

Why it exists: FastAPI needs typed request bodies and safe response shapes
that never include `password_hash`.

Responsibility: validate signup input. No hashing, no SQL.

Communicates with: `core.security.validate_password` and `auth_router`.
"""
