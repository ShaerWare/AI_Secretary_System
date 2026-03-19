"""Add is_default_mobile to chat_session_shares.

Revision ID: 0016
Revises: 0015
Create Date: 2026-03-19
"""

from typing import Union

import sqlalchemy as sa

from alembic import op


revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    with op.batch_alter_table("chat_session_shares") as batch_op:
        batch_op.add_column(
            sa.Column("is_default_mobile", sa.Boolean(), server_default="0", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("chat_session_shares") as batch_op:
        batch_op.drop_column("is_default_mobile")
