"""Add branch_message_id to chat_session_shares for per-branch sharing

Revision ID: 0004
Revises: 0003
Create Date: 2026-02-20
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_session_shares",
        sa.Column("branch_message_id", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_session_shares", "branch_message_id")
