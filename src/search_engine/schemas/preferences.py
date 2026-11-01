"""Functional user preference API contracts."""

from typing import Literal

from pydantic import BaseModel


class UserPreferences(BaseModel):
    model_config = {"from_attributes": True}

    response_language: Literal["auto", "en", "ar"] = "auto"
    response_depth: Literal["auto", "concise", "balanced", "detailed"] = "auto"
    default_mode: Literal["general", "documents", "deep"] = "general"
    theme: Literal["dark", "light", "system"] = "dark"


class UserPreferencesUpdate(UserPreferences):
    pass
