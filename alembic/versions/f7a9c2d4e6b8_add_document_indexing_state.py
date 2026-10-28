"""add document indexing state and chunk character ranges

Revision ID: f7a9c2d4e6b8
Revises: d4f6a8b1c2e3
Create Date: 2026-10-27 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f7a9c2d4e6b8"
down_revision: Union[str, Sequence[str], None] = "d4f6a8b1c2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add independent indexing lifecycle and page-local citation offsets."""
    op.add_column(
        "document_chunks",
        sa.Column("char_start", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("char_end", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_document_chunks_character_range",
        "document_chunks",
        "(char_start IS NULL AND char_end IS NULL) OR "
        "(char_start >= 0 AND char_end >= char_start)",
    )
    op.create_table(
        "document_index_states",
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="not_indexed",
            nullable=False,
        ),
        sa.Column(
            "generation",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "generation >= 0",
            name="ck_document_index_states_generation_nonnegative",
        ),
        sa.CheckConstraint(
            "status IN ('not_indexed', 'processing', 'completed', 'failed')",
            name="ck_document_index_states_status",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("document_id"),
    )


def downgrade() -> None:
    """Remove indexing lifecycle and citation offsets."""
    op.drop_table("document_index_states")
    op.drop_constraint(
        "ck_document_chunks_character_range",
        "document_chunks",
        type_="check",
    )
    op.drop_column("document_chunks", "char_end")
    op.drop_column("document_chunks", "char_start")
