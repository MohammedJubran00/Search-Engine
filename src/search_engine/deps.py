"""FastAPI dependencies for the current authenticated user.

Why it exists: chat routes need the user from the access token. Decoding
belongs in `core.security`; loading the row belongs in `UserRepository`.
This module only wires HTTP Bearer → those two.

Responsibility: require `Authorization: Bearer <access_token>` and return
the `User`. 401 if the token is missing, invalid, or the user is gone.

Communicates with: `core.security.decode_access_token`, `UserRepository`,
and `database.get_db`. Not a `/me` endpoint.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.core.security import InvalidAccessTokenError, decode_access_token
from src.search_engine.database.database import get_db
from src.search_engine.models.user import User
from src.search_engine.repositories.user_repository import UserRepository

_NOT_AUTHENTICATED = "Not authenticated."


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_NOT_AUTHENTICATED,
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_NOT_AUTHENTICATED,
        )
    return token.strip()


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Return the user identified by `JWT.sub`. Identity is never taken from the body."""
    token = _bearer_token(authorization)
    try:
        user_id = decode_access_token(token)
    except InvalidAccessTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_NOT_AUTHENTICATED,
        ) from None

    user = await UserRepository(db).get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_NOT_AUTHENTICATED,
        )
    return user
