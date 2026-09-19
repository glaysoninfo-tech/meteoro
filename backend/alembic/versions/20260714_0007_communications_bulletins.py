"""Add communications recipients and bulletin dispatch tables

Revision ID: 20260714_0007
Revises: 20260714_0006
Create Date: 2026-07-14 19:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260714_0007"
down_revision: Union[str, Sequence[str], None] = "20260714_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "communication_recipients",
        sa.Column("recipient_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("channel_type", sa.String(length=20), nullable=False),
        sa.Column("destination", sa.String(length=300), nullable=False),
        sa.Column("consent_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("consent_reason", sa.Text(), nullable=True),
        sa.Column("consent_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("tags_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.organization_id"],
            name="fk_communication_recipients_organization_id_organizations",
        ),
    )
    op.create_index(
        "ix_comm_recipients_org_channel_active",
        "communication_recipients",
        ["organization_id", "channel_type", "is_active"],
    )
    op.create_index(
        "ix_comm_recipients_org_consent",
        "communication_recipients",
        ["organization_id", "consent_status"],
    )

    op.create_table(
        "bulletin_dispatches",
        sa.Column("dispatch_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("bulletin_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.String(length=160), nullable=False),
        sa.Column("channel_scope_json", sa.Text(), nullable=True),
        sa.Column("report_snapshot_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.organization_id"],
            name="fk_bulletin_dispatches_organization_id_organizations",
        ),
    )
    op.create_index(
        "ix_bulletin_dispatches_org_created",
        "bulletin_dispatches",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_bulletin_dispatches_org_status",
        "bulletin_dispatches",
        ["organization_id", "status"],
    )

    op.create_table(
        "bulletin_deliveries",
        sa.Column("delivery_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("dispatch_id", sa.String(length=36), nullable=False),
        sa.Column("recipient_id", sa.String(length=36), nullable=False),
        sa.Column("channel_type", sa.String(length=20), nullable=False),
        sa.Column("destination", sa.String(length=300), nullable=False),
        sa.Column("delivery_status", sa.String(length=30), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("attempted_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.organization_id"],
            name="fk_bulletin_deliveries_organization_id_organizations",
        ),
        sa.ForeignKeyConstraint(
            ["dispatch_id"],
            ["bulletin_dispatches.dispatch_id"],
            name="fk_bulletin_deliveries_dispatch_id_bulletin_dispatches",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["communication_recipients.recipient_id"],
            name="fk_bulletin_deliveries_recipient_id_communication_recipients",
        ),
    )
    op.create_index(
        "ix_bulletin_deliveries_dispatch_status",
        "bulletin_deliveries",
        ["dispatch_id", "delivery_status"],
    )
    op.create_index(
        "ix_bulletin_deliveries_recipient",
        "bulletin_deliveries",
        ["recipient_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_bulletin_deliveries_recipient", table_name="bulletin_deliveries")
    op.drop_index("ix_bulletin_deliveries_dispatch_status", table_name="bulletin_deliveries")
    op.drop_table("bulletin_deliveries")

    op.drop_index("ix_bulletin_dispatches_org_status", table_name="bulletin_dispatches")
    op.drop_index("ix_bulletin_dispatches_org_created", table_name="bulletin_dispatches")
    op.drop_table("bulletin_dispatches")

    op.drop_index("ix_comm_recipients_org_consent", table_name="communication_recipients")
    op.drop_index(
        "ix_comm_recipients_org_channel_active",
        table_name="communication_recipients",
    )
    op.drop_table("communication_recipients")
