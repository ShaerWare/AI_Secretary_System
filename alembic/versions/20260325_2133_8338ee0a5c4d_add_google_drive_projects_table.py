"""add google_drive_projects table

Revision ID: 8338ee0a5c4d
Revises: ed1d201ecb55
Create Date: 2026-03-25 21:33:31.416445
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


revision: str = "8338ee0a5c4d"
down_revision: Union[str, None] = "ed1d201ecb55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "google_drive_projects",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("folder_id", sa.String(200), nullable=False, server_default="root"),
        sa.Column("folder_name", sa.String(500), nullable=True),
        sa.Column(
            "collection_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_collections.id"),
            nullable=True,
        ),
        sa.Column("sync_status", sa.String(20), server_default="idle"),
        sa.Column("sync_error", sa.Text(), nullable=True),
        sa.Column("last_synced", sa.DateTime(), nullable=True),
        sa.Column("file_count", sa.Integer(), server_default="0"),
        sa.Column("total_size_bytes", sa.Integer(), server_default="0"),
        sa.Column("include_mime_types", sa.Text(), nullable=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column("created", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    op.drop_table("google_drive_projects")
