"""Add identity provider fields to users

Revision ID: 20260714_0002
Revises: 20260714_0001
Create Date: 2026-07-14 12:55:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260714_0002"
down_revision: Union[str, Sequence[str], None] = "20260714_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "identity_provider",
            sa.String(length=30),
            nullable=False,
            server_default="local",
        ),
    )
    op.add_column(
        "users",
        sa.Column("identity_provider_subject", sa.String(length=160), nullable=True),
    )
    op.create_index(
        "ix_users_identity_provider_subject",
        "users",
        ["identity_provider_subject"],
        unique=True,
    )

def downgrade() -> None:
    op.drop_index("ix_users_identity_provider_subject", table_name="users")
    op.drop_column("users", "identity_provider_subject")
    op.drop_column("users", "identity_provider")
