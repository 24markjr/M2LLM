"""pin a case to the top of the list (Phase U1)

Revision ID: au1c0a5e0001
Revises: a52c0be70001
Create Date: 2026-10-13 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "au1c0a5e0001"
down_revision: str | Sequence[str] | None = "a52c0be70001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "cases", sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("cases", "pinned")
