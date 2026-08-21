"""Authentication business rules.

Why it exists: duplicate-email checks, credential checks, hashing, and JWT
issuance must not live in the router or the repository.

Responsibility: `signup` and `login`. Login issues tokens but does not
implement refresh/logout. Raises `DuplicateEmailError` or
`InvalidCredentialsError`.

Communicates with: `UserRepository`, `core.security`, and `auth_router`.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from src.search_engine.models.user import User
from src.search_engine.repositories.user_repository import UserRepository


class DuplicateEmailError(Exception):
    """Raised when signup uses an email that already exists."""


class InvalidCredentialsError(Exception):
    """Raised when login email or password is wrong. Same message for both."""


@dataclass(frozen=True)
class AuthTokens:
    """Access and refresh JWT pair issued at login."""

    access_token: str
    refresh_token: str


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

    async def login(self, *, email: str, password: str) -> AuthTokens:
        """Verify credentials and return JWTs. Does not leak whether the email exists."""
        user = await self._users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError
        user_id: UUID = user.id
        return AuthTokens(
            access_token=create_access_token(user_id),
            refresh_token=create_refresh_token(user_id),
        )
