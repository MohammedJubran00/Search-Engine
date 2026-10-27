"""enable the pgvector PostgreSQL extension

Revision ID: c31f5dd889a1
Revises: b7c4e2a91d03
Create Date: 2026-10-25 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "c31f5dd889a1"
down_revision: Union[str, Sequence[str], None] = "b7c4e2a91d03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enable vector columns and indexes for future RAG migrations."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Keep the shared extension installed; later objects may depend on it."""
    pass
