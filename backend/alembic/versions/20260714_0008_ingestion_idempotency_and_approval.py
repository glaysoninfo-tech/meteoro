"""Add durable ingestion idempotency and approval segregation.

Revision ID: 20260714_0008
Revises: 20260714_0007
Create Date: 2026-07-14 20:00:00
"""

from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260714_0008"
down_revision: Union[str, Sequence[str], None] = "20260714_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ingestion_runs",
        sa.Column("records_deduplicated", sa.Integer(), nullable=False, server_default="0"),
    )

    _add_fingerprint_constraint(
        table_name="observations",
        id_column="observation_id",
        constraint_name="uq_observations_source_fingerprint",
    )
    _add_fingerprint_constraint(
        table_name="official_alerts",
        id_column="official_alert_id",
        constraint_name="uq_official_alerts_source_fingerprint",
    )
    _add_fingerprint_constraint(
        table_name="incident_reports",
        id_column="report_id",
        constraint_name="uq_incident_reports_source_fingerprint",
    )
    _ensure_authority_approver_role()


def downgrade() -> None:
    _drop_fingerprint_constraint(
        table_name="incident_reports",
        constraint_name="uq_incident_reports_source_fingerprint",
    )
    _drop_fingerprint_constraint(
        table_name="official_alerts",
        constraint_name="uq_official_alerts_source_fingerprint",
    )
    _drop_fingerprint_constraint(
        table_name="observations",
        constraint_name="uq_observations_source_fingerprint",
    )
    with op.batch_alter_table("ingestion_runs") as batch_op:
        batch_op.drop_column("records_deduplicated")


def _add_fingerprint_constraint(table_name: str, id_column: str, constraint_name: str) -> None:
    op.add_column(table_name, sa.Column("record_fingerprint", sa.String(length=64), nullable=True))
    op.execute(
        sa.text(
            f"UPDATE {table_name} "
            f"SET record_fingerprint = 'legacy:' || {id_column} "
            "WHERE record_fingerprint IS NULL"
        )
    )
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column("record_fingerprint", existing_type=sa.String(length=64), nullable=False)
        batch_op.create_unique_constraint(constraint_name, ["source_id", "record_fingerprint"])


def _drop_fingerprint_constraint(table_name: str, constraint_name: str) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.drop_constraint(constraint_name, type_="unique")
        batch_op.drop_column("record_fingerprint")


def _ensure_authority_approver_role() -> None:
    bind = op.get_bind()
    roles = sa.table(
        "roles",
        sa.column("role_id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("scope", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    exists = bind.execute(
        sa.select(roles.c.role_id).where(roles.c.name == "authority_approver")
    ).scalar_one_or_none()
    if exists is None:
        bind.execute(
            roles.insert().values(
                role_id="00000000-0000-0000-0000-000000000005",
                name="authority_approver",
                description="Autoridade aprovadora de protocolos",
                scope="organization",
                created_at=datetime.now(tz=timezone.utc),
            )
        )
