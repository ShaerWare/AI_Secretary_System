"""add web_search_enabled to chat_sessions

Revision ID: f145b30530c0
Revises: 0016
Create Date: 2026-03-23 20:48:06.717405
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


revision: str = "f145b30530c0"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.add_column(sa.Column("web_search_enabled", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.drop_column("web_search_enabled")
