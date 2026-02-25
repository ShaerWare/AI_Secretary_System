"""Add max_uses and used_count to workspace_invites.

Revision ID: 0012
Revises: 0011
Create Date: 2026-02-25
"""

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workspace_invites") as batch_op:
        batch_op.add_column(sa.Column("max_uses", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("used_count", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("workspace_invites") as batch_op:
        batch_op.drop_column("used_count")
        batch_op.drop_column("max_uses")
