"""Persist Cabinet decisions with ownership and deadlines.

Revision ID: 20260714_0012
Revises: 20260714_0011
Create Date: 2026-07-14 23:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260714_0012"
down_revision: Union[str, Sequence[str], None] = "20260714_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cabinet_decisions",
        sa.Column("decision_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("risk_key", sa.String(length=240), nullable=False),
        sa.Column("territory", sa.String(length=160), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("responsible_action", sa.String(length=500), nullable=False),
        sa.Column("responsible_role", sa.String(length=160), nullable=False),
        sa.Column("deadline_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("updated_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.organization_id"]),
    )
    op.create_index("ix_cabinet_decisions_org_risk", "cabinet_decisions", ["organization_id", "risk_key"])
    op.create_index("ix_cabinet_decisions_org_status_deadline", "cabinet_decisions", ["organization_id", "status", "deadline_utc"])


def downgrade() -> None:
    op.drop_index("ix_cabinet_decisions_org_status_deadline", table_name="cabinet_decisions")
    op.drop_index("ix_cabinet_decisions_org_risk", table_name="cabinet_decisions")
    op.drop_table("cabinet_decisions")
