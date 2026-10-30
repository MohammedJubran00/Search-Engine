"""Authenticated, per-user operational metrics endpoint."""

from fastapi import APIRouter, Depends

from src.search_engine.deps import get_current_user
from src.search_engine.models.user import User
from src.search_engine.schemas.metrics import UsageSnapshot
from src.search_engine.services.observability_service import observability

router = APIRouter()


@router.get("", response_model=UsageSnapshot)
async def get_usage_metrics(user: User = Depends(get_current_user)) -> UsageSnapshot:
    return UsageSnapshot.model_validate(await observability.snapshot(user.id))
