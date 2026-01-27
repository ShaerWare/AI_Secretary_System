"""Initial database schema

Revision ID: 0001
Revises:
Create Date: 2026-01-26

Creates all initial tables for AI Secretary System:
- chat_sessions: Chat session metadata
- chat_messages: Individual chat messages
- faq_entries: FAQ question-answer pairs
- tts_presets: Custom TTS voice presets
- system_config: Key-value system configuration
- telegram_sessions: Telegram user sessions
- audit_log: System audit trail
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Chat sessions table
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False, default="Новый чат"),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("created", sa.DateTime(), nullable=False),
        sa.Column("updated", sa.DateTime(), nullable=False),
    )

    # Chat messages table
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(50),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("edited", sa.Boolean(), default=False),
        sa.Column("created", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])
    op.create_index("ix_chat_messages_session_created", "chat_messages", ["session_id", "created"])

    # FAQ entries table
    op.create_table(
        "faq_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("question", sa.String(500), nullable=False, unique=True),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("keywords", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), default=True),
        sa.Column("hit_count", sa.Integer(), default=0),
        sa.Column("created", sa.DateTime(), nullable=False),
        sa.Column("updated", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_faq_entries_question", "faq_entries", ["question"])

    # TTS presets table
    op.create_table(
        "tts_presets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("params", sa.Text(), nullable=False),
        sa.Column("builtin", sa.Boolean(), default=False),
        sa.Column("created", sa.DateTime(), nullable=False),
        sa.Column("updated", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tts_presets_name", "tts_presets", ["name"])

    # System config table
    op.create_table(
        "system_config",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated", sa.DateTime(), nullable=False),
    )

    # Telegram sessions table
    op.create_table(
        "telegram_sessions",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column(
            "chat_session_id",
            sa.String(50),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("username", sa.String(100), nullable=True),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("created", sa.DateTime(), nullable=False),
        sa.Column("updated", sa.DateTime(), nullable=False),
    )

    # Audit log table
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("user_id", sa.String(100), nullable=True),
        sa.Column("user_ip", sa.String(45), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
    )
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_timestamp_action", "audit_log", ["timestamp", "action"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("telegram_sessions")
    op.drop_table("system_config")
    op.drop_table("tts_presets")
    op.drop_table("faq_entries")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
