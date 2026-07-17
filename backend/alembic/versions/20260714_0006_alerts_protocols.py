"""Add official alerts and protocols tables

Revision ID: 20260714_0006
Revises: 20260714_0005
Create Date: 2026-07-14 17:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260714_0006"
down_revision: Union[str, Sequence[str], None] = "20260714_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "official_alerts",
        sa.Column("official_alert_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("ingestion_run_id", sa.String(length=36), nullable=True),
        sa.Column("raw_asset_id", sa.String(length=36), nullable=True),
        sa.Column("external_alert_id", sa.String(length=120), nullable=True),
        sa.Column("issuer", sa.String(length=120), nullable=False),
        sa.Column("alert_code", sa.String(length=60), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("issued_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("territory_codes_json", sa.Text(), nullable=True),
        sa.Column("geometry_geojson", sa.Text(), nullable=True),
        sa.Column("original_payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.organization_id"],
            name="fk_official_alerts_organization_id_organizations",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.source_id"],
            name="fk_official_alerts_source_id_sources",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.ingestion_run_id"],
            name="fk_official_alerts_ingestion_run_id_ingestion_runs",
        ),
        sa.ForeignKeyConstraint(
            ["raw_asset_id"],
            ["raw_assets.raw_asset_id"],
            name="fk_official_alerts_raw_asset_id_raw_assets",
        ),
    )
    op.create_index(
        "ix_official_alerts_org_status",
        "official_alerts",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_official_alerts_validity",
        "official_alerts",
        ["valid_from_utc", "valid_to_utc"],
    )

    op.create_table(
        "protocol_templates",
        sa.Column("protocol_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("protocol_name", sa.String(length=160), nullable=False),
        sa.Column("version", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("trigger_type", sa.String(length=30), nullable=False),
        sa.Column("trigger_config_json", sa.Text(), nullable=True),
        sa.Column("action_steps_json", sa.Text(), nullable=False),
        sa.Column("requires_authority_approval", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.organization_id"],
            name="fk_protocol_templates_organization_id_organizations",
        ),
    )
    op.create_index(
        "ix_protocol_templates_org_status",
        "protocol_templates",
        ["organization_id", "status"],
    )

    op.create_table(
        "protocol_activations",
        sa.Column("activation_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("protocol_id", sa.String(length=36), nullable=False),
        sa.Column("official_alert_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("trigger_reason", sa.Text(), nullable=True),
        sa.Column("initiated_by", sa.String(length=160), nullable=False),
        sa.Column("approved_by", sa.String(length=160), nullable=True),
        sa.Column("closed_by", sa.String(length=160), nullable=True),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closure_notes", sa.Text(), nullable=True),
        sa.Column("action_log_json", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.organization_id"],
            name="fk_protocol_activations_organization_id_organizations",
        ),
        sa.ForeignKeyConstraint(
            ["protocol_id"],
            ["protocol_templates.protocol_id"],
            name="fk_protocol_activations_protocol_id_protocol_templates",
        ),
        sa.ForeignKeyConstraint(
            ["official_alert_id"],
            ["official_alerts.official_alert_id"],
            name="fk_protocol_activations_official_alert_id_official_alerts",
        ),
    )
    op.create_index(
        "ix_protocol_activations_org_status",
        "protocol_activations",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_protocol_activations_started",
        "protocol_activations",
        ["started_at_utc"],
    )


def downgrade() -> None:
    op.drop_index("ix_protocol_activations_started", table_name="protocol_activations")
    op.drop_index("ix_protocol_activations_org_status", table_name="protocol_activations")
    op.drop_table("protocol_activations")

    op.drop_index("ix_protocol_templates_org_status", table_name="protocol_templates")
    op.drop_table("protocol_templates")

    op.drop_index("ix_official_alerts_validity", table_name="official_alerts")
    op.drop_index("ix_official_alerts_org_status", table_name="official_alerts")
    op.drop_table("official_alerts")
