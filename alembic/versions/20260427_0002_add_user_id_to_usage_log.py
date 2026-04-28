"""Add user_id to usage_log for per-user token tracking.

Revision ID: 0024_usage_log_user_id
Revises: 0023_rss_feeds
Create Date: 2026-04-27
"""

from typing import Union

import sqlalchemy as sa

from alembic import op


revision: str = "0024_usage_log_user_id"
down_revision: Union[str, None] = "0023_rss_feeds"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    with op.batch_alter_table("usage_log") as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_index("ix_usage_log_user_id", "usage_log", ["user_id"])
    op.create_index("ix_usage_log_user_timestamp", "usage_log", ["user_id", "timestamp"])


def downgrade() -> None:
    op.drop_index("ix_usage_log_user_timestamp", table_name="usage_log")
    op.drop_index("ix_usage_log_user_id", table_name="usage_log")
    with op.batch_alter_table("usage_log") as batch:
        batch.drop_column("user_id")
