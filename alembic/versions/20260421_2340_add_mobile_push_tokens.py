"""Add mobile_push_tokens table for FCM registration.

Revision ID: 0021_mobile_push
Revises: 8338ee0a5c4d
Create Date: 2026-04-21
"""

from typing import Union

import sqlalchemy as sa

from alembic import op


revision: str = "0021_mobile_push"
down_revision: Union[str, None] = "8338ee0a5c4d"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "mobile_push_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token", sa.String(length=500), nullable=False),
        sa.Column("platform", sa.String(length=20), server_default="android", nullable=False),
        sa.Column("app_version", sa.String(length=20), nullable=True),
        sa.Column("build_number", sa.String(length=20), nullable=True),
        sa.Column(
            "created", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False
        ),
        sa.Column(
            "last_seen", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False
        ),
    )
    op.create_index("ix_mobile_push_tokens_user_id", "mobile_push_tokens", ["user_id"])
    op.create_index("ix_mobile_push_tokens_token", "mobile_push_tokens", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_mobile_push_tokens_token", table_name="mobile_push_tokens")
    op.drop_index("ix_mobile_push_tokens_user_id", table_name="mobile_push_tokens")
    op.drop_table("mobile_push_tokens")
