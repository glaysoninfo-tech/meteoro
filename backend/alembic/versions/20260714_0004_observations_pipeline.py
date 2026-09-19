"""Add normalized observations table

Revision ID: 20260714_0004
Revises: 20260714_0003
Create Date: 2026-07-14 15:40:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260714_0004"
down_revision: Union[str, Sequence[str], None] = "20260714_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "observations",
        sa.Column("observation_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("ingestion_run_id", sa.String(length=36), nullable=False),
        sa.Column("raw_asset_id", sa.String(length=36), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("variable_code", sa.String(length=40), nullable=False),
        sa.Column("value_original", sa.Float(), nullable=False),
        sa.Column("unit_original", sa.String(length=30), nullable=False),
        sa.Column("value_canonical", sa.Float(), nullable=False),
        sa.Column("unit_canonical", sa.String(length=30), nullable=False),
        sa.Column("quality_status", sa.String(length=20), nullable=False),
        sa.Column("quality_score", sa.Integer(), nullable=False),
        sa.Column("quality_flag_code", sa.String(length=50), nullable=True),
        sa.Column("quality_description", sa.Text(), nullable=True),
        sa.Column("location_code", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.organization_id"],
            name="fk_observations_organization_id_organizations",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.source_id"],
            name="fk_observations_source_id_sources",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.ingestion_run_id"],
            name="fk_observations_ingestion_run_id_ingestion_runs",
        ),
        sa.ForeignKeyConstraint(
            ["raw_asset_id"],
            ["raw_assets.raw_asset_id"],
            name="fk_observations_raw_asset_id_raw_assets",
        ),
    )
    op.create_index(
        "ix_observations_org_source_time",
        "observations",
        ["organization_id", "source_id", "observed_at_utc"],
    )
    op.create_index(
        "ix_observations_ingestion_run",
        "observations",
        ["ingestion_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_observations_ingestion_run", table_name="observations")
    op.drop_index("ix_observations_org_source_time", table_name="observations")
    op.drop_table("observations")

