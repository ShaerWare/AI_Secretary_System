"""Add workspace_id to 13 resource tables.

Revision ID: 0010
Revises: 0009
Create Date: 2026-02-23
"""

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

# Tables that get workspace_id + their composite index columns.
# Format: (table_name, index_name, index_columns)
_TABLES = [
    ("chat_sessions", "ix_chat_sessions_ws", ["workspace_id", "owner_id"]),
    ("bot_instances", "ix_bot_instances_ws", ["workspace_id", "owner_id"]),
    ("widget_instances", "ix_widget_instances_ws", ["workspace_id", "owner_id"]),
    ("whatsapp_instances", "ix_whatsapp_instances_ws", ["workspace_id", "owner_id"]),
    ("cloud_llm_providers", "ix_cloud_llm_providers_ws", ["workspace_id", "owner_id"]),
    ("tts_presets", "ix_tts_presets_ws", ["workspace_id", "owner_id"]),
    ("knowledge_documents", "ix_knowledge_documents_ws", ["workspace_id", "owner_id"]),
    ("knowledge_collections", "ix_knowledge_collections_ws", ["workspace_id", "id"]),
    ("claude_code_sessions", "ix_claude_code_sessions_ws", ["workspace_id", "owner_id"]),
    ("faq_entries", "ix_faq_entries_ws", ["workspace_id", "id"]),
    ("kanban_tasks", "ix_kanban_tasks_ws", ["workspace_id", "id"]),
    ("kanban_projects", "ix_kanban_projects_ws", ["workspace_id", "id"]),
    ("amocrm_config", "ix_amocrm_config_ws", ["workspace_id", "id"]),
]


def upgrade() -> None:
    for table, ix_name, ix_cols in _TABLES:
        # Plain ADD COLUMN — no FK constraint at DB level (ORM enforces it).
        # Avoids both batch_alter_table issues (server_default recreation) and
        # SQLite's lack of ALTER ADD CONSTRAINT support.
        op.add_column(
            table,
            sa.Column("workspace_id", sa.Integer(), nullable=False, server_default="1"),
        )
        op.create_index(ix_name, table, ix_cols)


def downgrade() -> None:
    for table, ix_name, _ix_cols in reversed(_TABLES):
        op.drop_index(ix_name, table_name=table)
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column("workspace_id")
