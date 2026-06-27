"""Add web_search_enabled to widget_instances.

Lets a website widget assistant use the agentic web_search tool (modules/chat
/facade.py), the same way chat sessions do. Off by default.

Revision ID: 0025_widget_web_search
Revises: 0024_usage_log_user_id
Create Date: 2026-06-27
"""

from typing import Union

import sqlalchemy as sa

from alembic import op


revision: str = "0025_widget_web_search"
down_revision: Union[str, None] = "0024_usage_log_user_id"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    with op.batch_alter_table("widget_instances") as batch:
        batch.add_column(
            sa.Column(
                "web_search_enabled",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("widget_instances") as batch:
        batch.drop_column("web_search_enabled")
