"""cases, their investigations and their evidence (Phase 44)

Revision ID: a44c0de50001
Revises: a43e0c1d0001
Create Date: 2026-10-07 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a44c0de50001"
down_revision: str | Sequence[str] | None = "a43e0c1d0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE SEQUENCE case_number_seq START 1")
    op.create_table(
        "cases",
        sa.Column("case_id", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("owner", sa.String(length=128), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("case_id"),
    )
    op.create_index(op.f("ix_cases_severity"), "cases", ["severity"], unique=False)
    op.create_index(op.f("ix_cases_status"), "cases", ["status"], unique=False)
    op.create_table(
        "case_investigations",
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("case_id", sa.String(length=24), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("findings", sa.Integer(), nullable=False),
        sa.Column("verified", sa.Integer(), nullable=False),
        sa.Column("contradictions", sa.Integer(), nullable=False),
        sa.Column("open_gaps", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        op.f("ix_case_investigations_case_id"), "case_investigations", ["case_id"], unique=False
    )
    op.create_table(
        "case_evidence",
        sa.Column("case_id", sa.String(length=24), nullable=False),
        sa.Column("evidence_id", sa.String(length=16), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("added_by", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"]),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.evidence_id"]),
        sa.PrimaryKeyConstraint("case_id", "evidence_id"),
    )
    op.create_index(
        op.f("ix_case_evidence_evidence_id"), "case_evidence", ["evidence_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_case_evidence_evidence_id"), table_name="case_evidence")
    op.drop_table("case_evidence")
    op.drop_index(op.f("ix_case_investigations_case_id"), table_name="case_investigations")
    op.drop_table("case_investigations")
    op.drop_index(op.f("ix_cases_status"), table_name="cases")
    op.drop_index(op.f("ix_cases_severity"), table_name="cases")
    op.drop_table("cases")
    op.execute("DROP SEQUENCE IF EXISTS case_number_seq")
