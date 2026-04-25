"""Add chat_session_prompts table — named per-session system prompts.

Revision ID: 0022_chat_session_prompts
Revises: 0021_mobile_push
Create Date: 2026-04-25
"""

from typing import Union

import sqlalchemy as sa

from alembic import op


revision: str = "0022_chat_session_prompts"
down_revision: Union[str, None] = "0021_mobile_push"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "chat_session_prompts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.String(length=50),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="0", nullable=False),
        sa.Column(
            "created",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_chat_session_prompts_session_id",
        "chat_session_prompts",
        ["session_id"],
    )
    op.create_index(
        "ix_chat_session_prompts_session_active",
        "chat_session_prompts",
        ["session_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_session_prompts_session_active", table_name="chat_session_prompts")
    op.drop_index("ix_chat_session_prompts_session_id", table_name="chat_session_prompts")
    op.drop_table("chat_session_prompts")
