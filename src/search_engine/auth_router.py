"""HTTP routes for authentication.

Why it exists: FastAPI needs a router for `/api/auth/*` without turning
`api.py` into a package (that would break `uvicorn src.search_engine.api:app`).

Responsibility: map HTTP to `AuthService` and `get_current_user`.
Signup, login, refresh, logout, and `/me`.

Communicates with: `schemas.auth`, `services.auth_service`, `deps`, and
`database.get_db`.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.core.security import InvalidTokenError
from src.search_engine.database.database import get_db
from src.search_engine.deps import NOT_AUTHENTICATED, get_current_user
from src.search_engine.models.user import User
from src.search_engine.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    SignupRequest,
    SignupResponse,
    UserPublic,
)
from src.search_engine.services.auth_service import (
    AuthService,
    DuplicateEmailError,
    InvalidCredentialsError,
)

router = APIRouter()

_INVALID_CREDENTIALS = "Invalid email or password."


@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def signup(
    payload: SignupRequest,
    db: AsyncSession = Depends(get_db),
) -> SignupResponse:
    """Register a new user. Returns the public user record, not tokens."""
    service = AuthService(db)
    try:
        user = await service.signup(
            full_name=payload.full_name,
            email=payload.email,
            password=payload.password,
        )
    except DuplicateEmailError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from None
    return SignupResponse.model_validate(user)


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Authenticate a user and return access plus refresh JWTs."""
    service = AuthService(db)
    try:
        tokens = await service.login(email=payload.email, password=payload.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_CREDENTIALS,
        ) from None
    return LoginResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
    )


@router.get("/me", response_model=UserPublic)
async def me(user: User = Depends(get_current_user)) -> UserPublic:
    """Return the authenticated user. Identity comes from the access token."""
    return UserPublic.model_validate(user)


@router.post("/refresh", response_model=LoginResponse)
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Return a new JWT pair from a refresh token. Access tokens are rejected."""
    try:
        tokens = await AuthService(db).refresh(payload.refresh_token)
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=NOT_AUTHENTICATED,
        ) from None
    return LoginResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(_: User = Depends(get_current_user)) -> Response:
    """Confirm the caller is authenticated. The client then drops stored tokens."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)
