"""Add confirmation, incident and action lifecycle.

Revision ID: 20260715_0014
Revises: 20260715_0013
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260715_0014"
down_revision: Union[str, Sequence[str], None] = "20260715_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("incident_reports", sa.Column("confirmation_status", sa.String(length=20), nullable=False, server_default="unverified"))
    op.add_column("incident_reports", sa.Column("confirmed_by", sa.String(length=160), nullable=True))
    op.add_column("incident_reports", sa.Column("confirmed_at_utc", sa.DateTime(timezone=True), nullable=True))
    op.add_column("incident_reports", sa.Column("confirmation_evidence_json", sa.Text(), nullable=True))
    op.create_index("ix_incident_reports_confirmation", "incident_reports", ["organization_id", "confirmation_status"])
    op.create_table(
        "incidents",
        sa.Column("incident_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("incident_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("responsible_name", sa.String(length=160), nullable=False),
        sa.Column("due_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_by", sa.String(length=160), nullable=False),
        sa.Column("closed_by", sa.String(length=160), nullable=True),
        sa.Column("opened_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closure_notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.organization_id"]),
        sa.ForeignKeyConstraint(["report_id"], ["incident_reports.report_id"]),
        sa.UniqueConstraint("report_id", name="uq_incidents_report"),
    )
    op.create_index("ix_incidents_org_status", "incidents", ["organization_id", "status", "opened_at_utc"])
    op.create_table(
        "incident_actions",
        sa.Column("action_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("responsible_name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("due_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.organization_id"]),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.incident_id"]),
    )
    op.create_index("ix_incident_actions_status", "incident_actions", ["incident_id", "status", "due_at_utc"])


def downgrade() -> None:
    op.drop_index("ix_incident_actions_status", table_name="incident_actions")
    op.drop_table("incident_actions")
    op.drop_index("ix_incidents_org_status", table_name="incidents")
    op.drop_table("incidents")
    op.drop_index("ix_incident_reports_confirmation", table_name="incident_reports")
    op.drop_column("incident_reports", "confirmation_evidence_json")
    op.drop_column("incident_reports", "confirmed_at_utc")
    op.drop_column("incident_reports", "confirmed_by")
    op.drop_column("incident_reports", "confirmation_status")
