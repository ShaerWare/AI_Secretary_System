"""Widen password_hash for bcrypt and make salt nullable

Revision ID: 0006
Revises: 0005
Create Date: 2026-02-22
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "password_hash",
            type_=sa.String(255),
            existing_type=sa.String(128),
        )
        batch_op.alter_column(
            "salt",
            nullable=True,
            existing_type=sa.String(64),
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "password_hash",
            type_=sa.String(128),
            existing_type=sa.String(255),
        )
        batch_op.alter_column(
            "salt",
            nullable=False,
            existing_type=sa.String(64),
        )
