"""Ações de mitigação e adaptação climática.

Revision ID: c7a19b4e5d20
Revises: d4568a161c0c
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7a19b4e5d20"
down_revision: Union[str, Sequence[str], None] = "d4568a161c0c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mitigation_actions",
        sa.Column("action_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("risk_theme", sa.String(length=40), nullable=False),
        sa.Column("territory", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("responsible_role", sa.String(length=160), nullable=False),
        sa.Column("action_type", sa.String(length=20), nullable=False, server_default="mitigacao"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="media"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="planejada"),
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deadline_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estimated_cost_brl", sa.Float(), nullable=True),
        sa.Column("indicator", sa.String(length=300), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("updated_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.organization_id"]),
    )
    op.create_index(
        "ix_mitigation_actions_org_status", "mitigation_actions", ["organization_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_mitigation_actions_org_status", table_name="mitigation_actions")
    op.drop_table("mitigation_actions")
