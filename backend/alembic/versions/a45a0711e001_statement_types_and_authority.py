"""statement types on findings, source authority on evidence items (Phase 45)

Revision ID: a45a0711e001
Revises: a44c0de50001
Create Date: 2026-10-11 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a45a0711e001"
down_revision: str | Sequence[str] | None = "a44c0de50001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "findings",
        sa.Column("statement_type", sa.String(length=24), nullable=False, server_default="UNKNOWN"),
    )
    op.add_column(
        "evidence_items",
        sa.Column("authority", sa.String(length=32), nullable=False, server_default="UNASSESSED"),
    )
    op.add_column(
        "evidence_items",
        sa.Column("authority_reason", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("evidence_items", "authority_reason")
    op.drop_column("evidence_items", "authority")
    op.drop_column("findings", "statement_type")
