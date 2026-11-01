"""Authenticated settings that have real application behavior."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.database.database import get_db
from src.search_engine.deps import get_current_user
from src.search_engine.models.user import User
from src.search_engine.models.user_preference import UserPreference
from src.search_engine.schemas.preferences import UserPreferences, UserPreferencesUpdate

router = APIRouter()


async def _get_or_create(db: AsyncSession, user_id) -> UserPreference:
    preferences = await db.get(UserPreference, user_id)
    if preferences is None:
        preferences = UserPreference(user_id=user_id)
        db.add(preferences)
        await db.flush()
    return preferences


@router.get("", response_model=UserPreferences)
async def get_preferences(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> UserPreferences:
    return UserPreferences.model_validate(await _get_or_create(db, user.id))


@router.put("", response_model=UserPreferences)
async def update_preferences(
    payload: UserPreferencesUpdate,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> UserPreferences:
    preferences = await _get_or_create(db, user.id)
    for key, value in payload.model_dump().items():
        setattr(preferences, key, value)
    await db.flush()
    return UserPreferences.model_validate(preferences)
