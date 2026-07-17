"""Add segregated approval and publication metadata to recommendations.

Revision ID: 20260715_0012
Revises: 20260714_0012
Create Date: 2026-07-15 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260715_0012"
down_revision: Union[str, Sequence[str], None] = "20260714_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("recommendation_revisions", sa.Column("approved_by", sa.String(length=160), nullable=True))
    op.add_column("recommendation_revisions", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("recommendation_revisions", sa.Column("published_by", sa.String(length=160), nullable=True))
    op.add_column("recommendation_revisions", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("recommendation_revisions", "published_at")
    op.drop_column("recommendation_revisions", "published_by")
    op.drop_column("recommendation_revisions", "approved_at")
    op.drop_column("recommendation_revisions", "approved_by")
