"""Sessões rotativas e revogáveis do operador (refresh tokens).

Revision ID: d4568a161c0c
Revises: 20260715_0014
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4568a161c0c"
down_revision: Union[str, Sequence[str], None] = "20260715_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("token_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_token_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.organization_id"]),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_hash"),
    )
    op.create_index("ix_refresh_tokens_user_expiry", "refresh_tokens", ["user_id", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_expiry", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
