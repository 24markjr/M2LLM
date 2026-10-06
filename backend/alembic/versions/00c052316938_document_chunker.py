"""document chunker (Phase 41)

Records which chunker cut a stored document, so changing `CONTEXT_CHUNKER` re-chunks text whose
hash is unchanged instead of keeping the old chunks as "unchanged". Existing rows were all cut by
the line chunker, the only default there has been.

Revision ID: 00c052316938
Revises: c6e375938463
Create Date: 2026-10-06 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "00c052316938"
down_revision: str | Sequence[str] | None = "c6e375938463"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "documents",
        sa.Column("chunker", sa.String(length=16), nullable=False, server_default="lines"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("documents", "chunker")
