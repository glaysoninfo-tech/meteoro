"""Add recommendation approval and publication evidence.

Revision ID: 20260715_0012
Revises: 20260714_0011
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260715_0012"
down_revision: Union[str, Sequence[str], None] = "20260714_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("recommendation_revisions", sa.Column("approved_by", sa.String(length=160), nullable=True))
    op.add_column("recommendation_revisions", sa.Column("approved_at_utc", sa.DateTime(timezone=True), nullable=True))
    op.add_column("recommendation_revisions", sa.Column("published_by", sa.String(length=160), nullable=True))
    op.add_column("recommendation_revisions", sa.Column("published_at_utc", sa.DateTime(timezone=True), nullable=True))
    op.add_column("recommendation_revisions", sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_recommendations_org_publication", "recommendation_revisions", ["organization_id", "status", "expires_at_utc"])


def downgrade() -> None:
    op.drop_index("ix_recommendations_org_publication", table_name="recommendation_revisions")
    op.drop_column("recommendation_revisions", "expires_at_utc")
    op.drop_column("recommendation_revisions", "published_at_utc")
    op.drop_column("recommendation_revisions", "published_by")
    op.drop_column("recommendation_revisions", "approved_at_utc")
    op.drop_column("recommendation_revisions", "approved_by")
