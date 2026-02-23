"""Add workspace tables (workspaces, workspace_members, workspace_invites) + user_sessions.workspace_id.

Revision ID: 0009
Revises: 0008
Create Date: 2026-02-23
"""

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- workspaces --
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # -- workspace_members --
    op.create_table(
        "workspace_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_name",
            sa.String(50),
            sa.ForeignKey("roles.name"),
            nullable=False,
        ),
        sa.Column(
            "joined_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_user"),
    )
    op.create_index("ix_wm_user_workspace", "workspace_members", ["user_id", "workspace_id"])

    # -- workspace_invites --
    op.create_table(
        "workspace_invites",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("invite_code", sa.String(64), unique=True, nullable=False),
        sa.Column(
            "role_name",
            sa.String(50),
            sa.ForeignKey("roles.name"),
            nullable=False,
            server_default="viewer",
        ),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("used_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )

    # -- user_sessions.workspace_id (nullable — old sessions work fine) --
    # SQLite: add column without inline FK, then add named FK via batch mode
    with op.batch_alter_table("user_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("workspace_id", sa.Integer(), nullable=True),
        )
        batch_op.create_foreign_key(
            "fk_user_sessions_workspace_id",
            "workspaces",
            ["workspace_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("user_sessions") as batch_op:
        batch_op.drop_constraint("fk_user_sessions_workspace_id", type_="foreignkey")
        batch_op.drop_column("workspace_id")
    op.drop_table("workspace_invites")
    op.drop_index("ix_wm_user_workspace", table_name="workspace_members")
    op.drop_table("workspace_members")
    op.drop_table("workspaces")
