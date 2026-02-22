"""Add kanban_projects table and extend kanban_tasks

Revision ID: 0008
Revises: 0007
Create Date: 2026-02-22
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kanban_projects",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("github_owner", sa.String(100), nullable=False),
        sa.Column("github_repo", sa.String(100), nullable=False),
        sa.Column("github_token", sa.String(500), nullable=True),
        sa.Column("webhook_secret", sa.String(255), nullable=True),
        sa.Column("label_mapping", sa.Text, nullable=True),
        sa.Column("sync_enabled", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("last_synced", sa.DateTime, nullable=True),
        sa.Column(
            "created",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_kanban_projects_name", "kanban_projects", ["name"])

    # SQLite requires batch mode for adding columns with FK constraints
    with op.batch_alter_table("kanban_tasks") as batch_op:
        batch_op.add_column(
            sa.Column("project_id", sa.Integer, nullable=True),
        )
        batch_op.add_column(
            sa.Column("github_issue_number", sa.Integer, nullable=True),
        )
        batch_op.create_index("ix_kanban_tasks_project_id", ["project_id"])
        batch_op.create_unique_constraint(
            "uq_task_project_issue", ["project_id", "github_issue_number"]
        )
        batch_op.create_foreign_key(
            "fk_kanban_tasks_project_id",
            "kanban_projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("kanban_tasks") as batch_op:
        batch_op.drop_constraint("fk_kanban_tasks_project_id", type_="foreignkey")
        batch_op.drop_constraint("uq_task_project_issue", type_="unique")
        batch_op.drop_index("ix_kanban_tasks_project_id")
        batch_op.drop_column("github_issue_number")
        batch_op.drop_column("project_id")
    op.drop_table("kanban_projects")
