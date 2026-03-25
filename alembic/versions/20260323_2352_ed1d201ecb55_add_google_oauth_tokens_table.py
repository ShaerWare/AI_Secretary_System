"""add google_oauth_tokens table

Revision ID: ed1d201ecb55
Revises: f145b30530c0
Create Date: 2026-03-23 23:52:45.375702
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


revision: str = "ed1d201ecb55"
down_revision: Union[str, None] = "f145b30530c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "google_oauth_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expiry", sa.DateTime(), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("google_email", sa.String(255), nullable=True),
        sa.Column("created", sa.DateTime(), nullable=True),
        sa.Column("updated", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_google_oauth_tokens_user_id", "google_oauth_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_table("google_oauth_tokens")
