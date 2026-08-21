"""Alembic migration environment.

Why it exists: schema changes go through Alembic, not `create_all()`.

Responsibility: load `Base.metadata` and run migrations against PostgreSQL
using the sync URL from application settings.

Communicates with: `core.config`, `database.database.Base`, and `models.user`
(imported so the `users` table is on metadata).
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from src.search_engine.core.config import settings
from src.search_engine.database.database import Base
from src.search_engine.models.user import User  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL without connecting to the database."""
    context.configure(
        url=settings.sync_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live PostgreSQL connection."""
    connectable = create_engine(
        settings.sync_database_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
