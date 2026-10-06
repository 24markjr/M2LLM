"""evidence locker and append-only chain of custody (Phase 43)

`evidence_items` (an item per distinct SHA-256, numbered from a sequence) and `custody_events`,
which a trigger makes append-only: UPDATE, DELETE and TRUNCATE all raise. A history that can be
edited is not evidence of anything.

Revision ID: a43e0c1d0001
Revises: 00c052316938
Create Date: 2026-10-06 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a43e0c1d0001"
down_revision: str | Sequence[str] | None = "00c052316938"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE SEQUENCE evidence_number_seq START 1")
    op.create_table(
        "evidence_items",
        sa.Column("evidence_id", sa.String(length=16), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("parser", sa.String(length=32), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("collected_by", sa.String(length=128), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("classification", sa.String(length=16), nullable=False),
        sa.Column("integrity", sa.String(length=16), nullable=False),
        sa.Column("integrity_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("case_id", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("evidence_id"),
        sa.UniqueConstraint("sha256"),
    )
    op.create_index(op.f("ix_evidence_items_name"), "evidence_items", ["name"], unique=False)
    op.create_index(op.f("ix_evidence_items_case_id"), "evidence_items", ["case_id"], unique=False)
    op.create_table(
        "custody_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("evidence_id", sa.String(length=16), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.evidence_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_custody_events_evidence_id"), "custody_events", ["evidence_id"])
    op.create_index(op.f("ix_custody_events_action"), "custody_events", ["action"])
    op.create_index(op.f("ix_custody_events_at"), "custody_events", ["at"])
    op.execute(
        """
        CREATE FUNCTION custody_events_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'custody_events is append-only: % is not allowed', TG_OP;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER custody_events_no_change BEFORE UPDATE OR DELETE ON custody_events "
        "FOR EACH ROW EXECUTE FUNCTION custody_events_append_only()"
    )
    op.execute(
        "CREATE TRIGGER custody_events_no_truncate BEFORE TRUNCATE ON custody_events "
        "FOR EACH STATEMENT EXECUTE FUNCTION custody_events_append_only()"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS custody_events_no_truncate ON custody_events")
    op.execute("DROP TRIGGER IF EXISTS custody_events_no_change ON custody_events")
    op.execute("DROP FUNCTION IF EXISTS custody_events_append_only()")
    op.drop_index(op.f("ix_custody_events_at"), table_name="custody_events")
    op.drop_index(op.f("ix_custody_events_action"), table_name="custody_events")
    op.drop_index(op.f("ix_custody_events_evidence_id"), table_name="custody_events")
    op.drop_table("custody_events")
    op.drop_index(op.f("ix_evidence_items_case_id"), table_name="evidence_items")
    op.drop_index(op.f("ix_evidence_items_name"), table_name="evidence_items")
    op.drop_table("evidence_items")
    op.execute("DROP SEQUENCE IF EXISTS evidence_number_seq")
