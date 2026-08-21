"""Database access for the `users` table.

Why it exists: SQL must not live in FastAPI routes or the auth service.

Responsibility: load and insert `User` rows. No password hashing, no HTTP.

Communicates with: `models.user` and `services.auth_service`.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.models.user import User


class UserRepository:
    """Read and write `users` through one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        """Return the user with this email, or None."""
        result = await self._session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Return the user with this id, or None."""
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        full_name: str,
        email: str,
        password_hash: str,
    ) -> User:
        """Insert a user and flush so `id` and timestamps are available."""
        user = User(
            full_name=full_name,
            email=email,
            password_hash=password_hash,
        )
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user
