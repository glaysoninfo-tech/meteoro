"""Add incident reports table for inspection and citizen complaints

Revision ID: 20260714_0005
Revises: 20260714_0004
Create Date: 2026-07-14 16:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260714_0005"
down_revision: Union[str, Sequence[str], None] = "20260714_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "incident_reports",
        sa.Column("report_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("ingestion_run_id", sa.String(length=36), nullable=False),
        sa.Column("raw_asset_id", sa.String(length=36), nullable=False),
        sa.Column("reported_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_origin", sa.String(length=20), nullable=False),
        sa.Column("category_code", sa.String(length=60), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location_code", sa.String(length=120), nullable=True),
        sa.Column("address_text", sa.Text(), nullable=True),
        sa.Column("reporter_name", sa.String(length=120), nullable=True),
        sa.Column("reporter_contact", sa.String(length=120), nullable=True),
        sa.Column("external_protocol", sa.String(length=120), nullable=True),
        sa.Column("triage_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("triaged_by", sa.String(length=160), nullable=True),
        sa.Column("triage_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.organization_id"],
            name="fk_incident_reports_organization_id_organizations",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.source_id"],
            name="fk_incident_reports_source_id_sources",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.ingestion_run_id"],
            name="fk_incident_reports_ingestion_run_id_ingestion_runs",
        ),
        sa.ForeignKeyConstraint(
            ["raw_asset_id"],
            ["raw_assets.raw_asset_id"],
            name="fk_incident_reports_raw_asset_id_raw_assets",
        ),
    )
    op.create_index(
        "ix_incident_reports_org_time",
        "incident_reports",
        ["organization_id", "reported_at_utc"],
    )
    op.create_index(
        "ix_incident_reports_source",
        "incident_reports",
        ["source_id"],
    )
    op.create_index(
        "ix_incident_reports_run",
        "incident_reports",
        ["ingestion_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_incident_reports_run", table_name="incident_reports")
    op.drop_index("ix_incident_reports_source", table_name="incident_reports")
    op.drop_index("ix_incident_reports_org_time", table_name="incident_reports")
    op.drop_table("incident_reports")
