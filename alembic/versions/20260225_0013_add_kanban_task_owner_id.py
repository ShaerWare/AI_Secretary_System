"""Add owner_id FK to kanban_tasks, backfill from created_by.

Revision ID: 0013
Revises: 0012
Create Date: 2026-02-25
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add owner_id column (nullable — GitHub-synced tasks have no local owner)
    with op.batch_alter_table("kanban_tasks") as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_kanban_tasks_owner_id", "users", ["owner_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_index("ix_kanban_tasks_owner_id", ["owner_id"])

    # Backfill owner_id from created_by → users.username
    op.execute(
        """
        UPDATE kanban_tasks SET owner_id = (
            SELECT id FROM users WHERE users.username = kanban_tasks.created_by
        )
        WHERE EXISTS (
            SELECT 1 FROM users WHERE users.username = kanban_tasks.created_by
        )
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("kanban_tasks") as batch_op:
        batch_op.drop_index("ix_kanban_tasks_owner_id")
        batch_op.drop_constraint("fk_kanban_tasks_owner_id", type_="foreignkey")
        batch_op.drop_column("owner_id")
