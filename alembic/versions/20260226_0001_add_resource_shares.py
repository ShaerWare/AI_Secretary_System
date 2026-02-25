"""Add resource_shares table for bot/widget/whatsapp instance sharing.

Revision ID: 0014
Revises: 0013
Create Date: 2026-02-26
"""

from typing import Union

import sqlalchemy as sa

from alembic import op


revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "resource_shares",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("resource_type", sa.String(30), nullable=False),
        sa.Column("resource_id", sa.String(50), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("permission", sa.String(10), nullable=False, server_default="view"),
        sa.Column("shared_by", sa.Integer(), nullable=True),
        sa.Column("shared_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shared_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resource_shares_resource_type", "resource_shares", ["resource_type"])
    op.create_index("ix_resource_shares_resource_id", "resource_shares", ["resource_id"])
    op.create_index("ix_resource_shares_user_id", "resource_shares", ["user_id"])
    op.create_index(
        "ix_resource_shares_type_resource_user",
        "resource_shares",
        ["resource_type", "resource_id", "user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_resource_shares_type_resource_user", table_name="resource_shares")
    op.drop_index("ix_resource_shares_user_id", table_name="resource_shares")
    op.drop_index("ix_resource_shares_resource_id", table_name="resource_shares")
    op.drop_index("ix_resource_shares_resource_type", table_name="resource_shares")
    op.drop_table("resource_shares")
