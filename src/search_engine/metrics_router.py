"""Authenticated, per-user operational metrics endpoint."""

from fastapi import APIRouter, Depends

from src.search_engine.deps import get_current_user
from src.search_engine.models.user import User
from src.search_engine.schemas.metrics import UsageSnapshot
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.database.database import get_db
from src.search_engine.repositories.usage_repository import UsageRepository

router = APIRouter()


@router.get("", response_model=UsageSnapshot)
async def get_usage_metrics(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UsageSnapshot:
    return UsageSnapshot.model_validate(await UsageRepository(db).snapshot(user.id))
