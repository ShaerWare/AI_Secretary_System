"""Add username and first_name to bot_subscribers.

Revision ID: 0015
Revises: 0014
Create Date: 2026-03-04
"""

from typing import Union

import sqlalchemy as sa

from alembic import op


revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    with op.batch_alter_table("bot_subscribers") as batch_op:
        batch_op.add_column(sa.Column("username", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("first_name", sa.String(100), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bot_subscribers") as batch_op:
        batch_op.drop_column("first_name")
        batch_op.drop_column("username")
