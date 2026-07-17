"""Classify geospatial records before public exposure.

Revision ID: 20260715_0013
Revises: 20260715_0012
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260715_0013"
down_revision: Union[str, Sequence[str], None] = "20260715_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("territories", sa.Column("visibility", sa.String(length=20), nullable=False, server_default="internal"))
    op.add_column("stations", sa.Column("visibility", sa.String(length=20), nullable=False, server_default="internal"))
    op.create_index("ix_territories_org_public", "territories", ["organization_id", "status", "visibility"])
    op.create_index("ix_stations_org_public", "stations", ["organization_id", "status", "visibility"])


def downgrade() -> None:
    op.drop_index("ix_stations_org_public", table_name="stations")
    op.drop_index("ix_territories_org_public", table_name="territories")
    op.drop_column("stations", "visibility")
    op.drop_column("territories", "visibility")
