"""SQLAlchemy ORM models.

Import model modules so `Base.metadata` includes every table for Alembic.
"""

from src.search_engine.models.user import User

__all__ = ["User"]
