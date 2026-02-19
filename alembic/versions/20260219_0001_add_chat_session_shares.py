"""Add chat_session_shares table for internal chat sharing

Revision ID: 0003
Revises: 0002
Create Date: 2026-02-19
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_session_shares",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(50), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("permission", sa.String(10), server_default="read", nullable=False),
        sa.Column("shared_by", sa.Integer(), nullable=True),
        sa.Column(
            "shared_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shared_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_chat_session_shares_session_user",
        "chat_session_shares",
        ["session_id", "user_id"],
        unique=True,
    )
    op.create_index(
        "ix_chat_session_shares_session_id",
        "chat_session_shares",
        ["session_id"],
    )
    op.create_index(
        "ix_chat_session_shares_user_id",
        "chat_session_shares",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_session_shares_user_id", table_name="chat_session_shares")
    op.drop_index("ix_chat_session_shares_session_id", table_name="chat_session_shares")
    op.drop_index("ix_chat_session_shares_session_user", table_name="chat_session_shares")
    op.drop_table("chat_session_shares")
