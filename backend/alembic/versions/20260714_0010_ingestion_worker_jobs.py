"""Add durable ingestion jobs for the Redis worker.

Revision ID: 20260714_0010
Revises: 20260714_0009
Create Date: 2026-07-14 22:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260714_0010"
down_revision: Union[str, Sequence[str], None] = "20260714_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column("job_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("trigger_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("run_metadata_json", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.String(length=160), nullable=True),
        sa.Column("ingestion_run_id", sa.String(length=36), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.organization_id"],
            name="fk_ingestion_jobs_organization_id_organizations",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.source_id"],
            name="fk_ingestion_jobs_source_id_sources",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.ingestion_run_id"],
            name="fk_ingestion_jobs_run_id_ingestion_runs",
        ),
    )
    op.create_index("ix_ingestion_jobs_status_created", "ingestion_jobs", ["status", "created_at"])
    op.create_index("ix_ingestion_jobs_source_status", "ingestion_jobs", ["source_id", "status"])
    op.create_index("ix_ingestion_jobs_org_created", "ingestion_jobs", ["organization_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_org_created", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_source_status", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_status_created", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
