"""customer organisations: cases, evidence and the audit log belong to one (v4 Phase 1c)

Everything that exists already belongs to `default`, the organisation of every account so far.
An evidence item was unique by SHA-256 across the installation; now it is unique within an
organisation, so the same file uploaded by two customers is two items, each with its own custody.

Revision ID: c1a0a07e0002
Revises: b1a0a07e0001
Create Date: 2026-10-27 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1a0a07e0002"
down_revision: str | Sequence[str] | None = "b1a0a07e0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    for table in ("cases", "evidence_items", "audit_log"):
        op.add_column(
            table, sa.Column("org_id", sa.String(64), nullable=False, server_default="default")
        )
        op.create_index(f"ix_{table}_org_id", table, ["org_id"])
    op.drop_constraint("evidence_items_sha256_key", "evidence_items", type_="unique")
    op.create_unique_constraint(
        "uq_evidence_items_org_sha256", "evidence_items", ["org_id", "sha256"]
    )


def downgrade() -> None:
    """Downgrade schema. Fails, as it should, if two organisations hold the same bytes."""
    op.drop_constraint("uq_evidence_items_org_sha256", "evidence_items", type_="unique")
    op.create_unique_constraint("evidence_items_sha256_key", "evidence_items", ["sha256"])
    for table in ("cases", "evidence_items", "audit_log"):
        op.drop_index(f"ix_{table}_org_id", table_name=table)
        op.drop_column(table, "org_id")
