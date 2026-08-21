"""Signup business rules.

Why it exists: duplicate-email checks and hashing must not live in the
router or the repository.

Responsibility: `signup` only in this task. Raises `DuplicateEmailError`
when the email is taken. Does not issue JWT tokens.

Communicates with: `UserRepository`, `core.security.hash_password`, and
`auth_router`.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.core.security import hash_password
from src.search_engine.models.user import User
from src.search_engine.repositories.user_repository import UserRepository


class DuplicateEmailError(Exception):
    """Raised when signup uses an email that already exists."""


class AuthService:
    """Authentication use cases for the current session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)

    async def signup(self, *, full_name: str, email: str, password: str) -> User:
        """Create a user with a hashed password. Does not log the user in."""
        if await self._users.get_by_email(email):
            raise DuplicateEmailError

        try:
            return await self._users.create(
                full_name=full_name,
                email=email,
                password_hash=hash_password(password),
            )
        except IntegrityError as exc:
            await self._session.rollback()
            raise DuplicateEmailError from exc
