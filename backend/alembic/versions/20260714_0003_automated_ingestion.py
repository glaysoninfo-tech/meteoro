"""Evolve ingestion schema for automated connectors

Revision ID: 20260714_0003
Revises: 20260714_0002
Create Date: 2026-07-14 13:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260714_0003"
down_revision: Union[str, Sequence[str], None] = "20260714_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("access_method", sa.String(length=30), nullable=False, server_default="http"),
    )
    op.add_column(
        "sources",
        sa.Column(
            "authentication_type",
            sa.String(length=30),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column("sources", sa.Column("connector_config_json", sa.Text(), nullable=True))
    op.add_column(
        "sources",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
    )
    op.add_column("sources", sa.Column("last_collection_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sources", sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sources", sa.Column("last_error", sa.Text(), nullable=True))

    op.add_column(
        "ingestion_runs",
        sa.Column("trigger_type", sa.String(length=20), nullable=False, server_default="manual"),
    )
    op.add_column("ingestion_runs", sa.Column("error_summary", sa.Text(), nullable=True))
    op.add_column("ingestion_runs", sa.Column("run_metadata_json", sa.Text(), nullable=True))

    op.create_table(
        "raw_assets",
        sa.Column("raw_asset_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("ingestion_run_id", sa.String(length=36), nullable=False),
        sa.Column("object_uri", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("parser_status", sa.String(length=20), nullable=False, server_default="stored"),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.organization_id"],
            name="fk_raw_assets_organization_id_organizations",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.source_id"],
            name="fk_raw_assets_source_id_sources",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.ingestion_run_id"],
            name="fk_raw_assets_ingestion_run_id_ingestion_runs",
        ),
    )


def downgrade() -> None:
    op.drop_table("raw_assets")
    op.drop_column("ingestion_runs", "run_metadata_json")
    op.drop_column("ingestion_runs", "error_summary")
    op.drop_column("ingestion_runs", "trigger_type")
    op.drop_column("sources", "last_error")
    op.drop_column("sources", "last_success_at")
    op.drop_column("sources", "last_collection_at")
    op.drop_column("sources", "status")
    op.drop_column("sources", "connector_config_json")
    op.drop_column("sources", "authentication_type")
    op.drop_column("sources", "access_method")

