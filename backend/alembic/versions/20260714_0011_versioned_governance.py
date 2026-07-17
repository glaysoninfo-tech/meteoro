"""Version protocols, rules and recommendations with auditable snapshots.

Revision ID: 20260714_0011
Revises: 20260714_0010
Create Date: 2026-07-14 23:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260714_0011"
down_revision: Union[str, Sequence[str], None] = "20260714_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("before_state_json", sa.Text(), nullable=True))
    op.add_column("audit_events", sa.Column("after_state_json", sa.Text(), nullable=True))
    op.add_column("audit_events", sa.Column("reason", sa.Text(), nullable=True))

    op.add_column("protocol_templates", sa.Column("protocol_family_id", sa.String(length=36), nullable=True))
    op.add_column("protocol_templates", sa.Column("revision_number", sa.Integer(), nullable=True))
    op.add_column("protocol_templates", sa.Column("supersedes_protocol_id", sa.String(length=36), nullable=True))
    op.add_column("protocol_templates", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column("protocol_templates", sa.Column("created_by", sa.String(length=160), nullable=True))
    op.add_column("protocol_templates", sa.Column("change_reason", sa.Text(), nullable=True))
    op.execute(
        "UPDATE protocol_templates SET protocol_family_id = protocol_id, revision_number = 1, "
        "content_hash = 'legacy:' || protocol_id, created_by = 'legacy' "
        "WHERE protocol_family_id IS NULL"
    )
    with op.batch_alter_table("protocol_templates") as batch_op:
        batch_op.alter_column("protocol_family_id", existing_type=sa.String(length=36), nullable=False)
        batch_op.alter_column("revision_number", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("content_hash", existing_type=sa.String(length=64), nullable=False)
        batch_op.alter_column("created_by", existing_type=sa.String(length=160), nullable=False)
        batch_op.create_foreign_key(
            "fk_protocol_templates_supersedes",
            "protocol_templates",
            ["supersedes_protocol_id"],
            ["protocol_id"],
        )
        batch_op.create_unique_constraint(
            "uq_protocol_family_revision", ["protocol_family_id", "revision_number"]
        )
    op.create_index("ix_protocol_family_revision", "protocol_templates", ["protocol_family_id", "revision_number"])

    op.create_table(
        "data_quality_rule_revisions",
        sa.Column("rule_revision_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("rule_family_id", sa.String(length=36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("supersedes_rule_revision_id", sa.String(length=36), nullable=True),
        sa.Column("rule_name", sa.String(length=160), nullable=False),
        sa.Column("scope_json", sa.Text(), nullable=False),
        sa.Column("condition_json", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.organization_id"]),
        sa.ForeignKeyConstraint(["supersedes_rule_revision_id"], ["data_quality_rule_revisions.rule_revision_id"]),
        sa.UniqueConstraint("rule_family_id", "revision_number", name="uq_rule_family_revision"),
    )
    op.create_index("ix_rule_revisions_org_status", "data_quality_rule_revisions", ["organization_id", "status"])

    op.create_table(
        "recommendation_revisions",
        sa.Column("recommendation_revision_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("recommendation_family_id", sa.String(length=36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("supersedes_recommendation_revision_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("audience", sa.String(length=80), nullable=False),
        sa.Column("criteria_json", sa.Text(), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.organization_id"]),
        sa.ForeignKeyConstraint(["supersedes_recommendation_revision_id"], ["recommendation_revisions.recommendation_revision_id"]),
        sa.UniqueConstraint("recommendation_family_id", "revision_number", name="uq_recommendation_family_revision"),
    )
    op.create_index("ix_recommendations_org_status", "recommendation_revisions", ["organization_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_recommendations_org_status", table_name="recommendation_revisions")
    op.drop_table("recommendation_revisions")
    op.drop_index("ix_rule_revisions_org_status", table_name="data_quality_rule_revisions")
    op.drop_table("data_quality_rule_revisions")
    op.drop_index("ix_protocol_family_revision", table_name="protocol_templates")
    with op.batch_alter_table("protocol_templates") as batch_op:
        batch_op.drop_constraint("uq_protocol_family_revision", type_="unique")
        batch_op.drop_constraint("fk_protocol_templates_supersedes", type_="foreignkey")
        batch_op.drop_column("change_reason")
        batch_op.drop_column("created_by")
        batch_op.drop_column("content_hash")
        batch_op.drop_column("supersedes_protocol_id")
        batch_op.drop_column("revision_number")
        batch_op.drop_column("protocol_family_id")
    op.drop_column("audit_events", "reason")
    op.drop_column("audit_events", "after_state_json")
    op.drop_column("audit_events", "before_state_json")
