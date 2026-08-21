"""HTTP routes for authentication.

Why it exists: FastAPI needs a router for `/api/auth/*` without turning
`api.py` into a package (that would break `uvicorn src.search_engine.api:app`).

Responsibility: map HTTP to `AuthService`. Signup only in this task.

Communicates with: `schemas.auth`, `services.auth_service`, and
`database.get_db`. Chat routes stay in `api.py` and stay public.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.database.database import get_db
from src.search_engine.schemas.auth import SignupRequest, SignupResponse
from src.search_engine.services.auth_service import AuthService, DuplicateEmailError

router = APIRouter()


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
