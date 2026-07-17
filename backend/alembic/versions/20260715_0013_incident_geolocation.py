"""Preserve supplied incident point geometry for the operational map.

Revision ID: 20260715_0013
Revises: 20260715_0012
Create Date: 2026-07-15 13:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260715_0013"
down_revision: Union[str, Sequence[str], None] = "20260715_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("incident_reports", sa.Column("location_geojson", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("incident_reports", "location_geojson")
