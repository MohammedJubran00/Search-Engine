"""HTTP routes for authentication.

Why it exists: FastAPI needs a router for `/api/auth/*` without turning
`api.py` into a package (that would break `uvicorn src.search_engine.api:app`).

Responsibility: map HTTP to `AuthService`. Signup and login only.
Refresh, logout, and `/me` are later tasks.

Communicates with: `schemas.auth`, `services.auth_service`, and
`database.get_db`. Chat identity is `deps.get_current_user` in `api.py`.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.database.database import get_db
from src.search_engine.schemas.auth import (
    LoginRequest,
    LoginResponse,
    SignupRequest,
    SignupResponse,
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
