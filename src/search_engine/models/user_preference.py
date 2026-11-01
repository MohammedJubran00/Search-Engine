"""Functional UI and answer preferences for one user."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.search_engine.database.database import Base


class UserPreference(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        CheckConstraint("response_language IN ('auto', 'en', 'ar')", name="ck_preferences_language"),
        CheckConstraint("response_depth IN ('auto', 'concise', 'balanced', 'detailed')", name="ck_preferences_depth"),
        CheckConstraint("default_mode IN ('general', 'documents', 'deep')", name="ck_preferences_mode"),
        CheckConstraint("theme IN ('dark', 'light', 'system')", name="ck_preferences_theme"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    response_language: Mapped[str] = mapped_column(String(16), nullable=False, default="auto", server_default="auto")
    response_depth: Mapped[str] = mapped_column(String(16), nullable=False, default="auto", server_default="auto")
    default_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="general", server_default="general")
    theme: Mapped[str] = mapped_column(String(16), nullable=False, default="dark", server_default="dark")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
