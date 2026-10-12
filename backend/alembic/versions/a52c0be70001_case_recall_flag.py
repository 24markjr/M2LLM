"""opt-in recall of similar cases (Phase 52, decision D19)

Revision ID: a52c0be70001
Revises: a50a0d17e001
Create Date: 2026-10-11 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a52c0be70001"
down_revision: str | Sequence[str] | None = "a50a0d17e001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "cases",
        sa.Column("recall_similar", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("cases", "recall_similar")
