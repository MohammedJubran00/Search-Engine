"""Typed application settings loaded from environment variables.

Why it exists: database credentials and other config must not be hardcoded,
and the existing `.env` `DATABASE_URL` cannot be parsed safely because the
password contains `@`.

Responsibility: expose a single `settings` object. Build the async SQLAlchemy
URL from `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`.

Communicates with: `database.database` (reads `settings.database_url`).
Does not talk to FastAPI routes or the LangGraph agent.
"""

from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime settings. Extra keys in `.env` (API keys, unused URL) are ignored."""

    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str

    def _postgres_url(self, driver: str) -> str:
        password = quote_plus(self.db_password)
        return (
            f"{driver}://{self.db_user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def database_url(self) -> str:
        """Async PostgreSQL URL with the password percent-encoded."""
        return self._postgres_url("postgresql+asyncpg")

    @property
    def sync_database_url(self) -> str:
        """Sync PostgreSQL URL for Alembic migrations."""
        return self._postgres_url("postgresql+psycopg")


settings = Settings()
