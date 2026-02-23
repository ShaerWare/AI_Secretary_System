"""Add user_identities table and make users.username/password_hash nullable.

Revision ID: 0011
Revises: 0010
Create Date: 2026-02-23
"""

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Users table: make username/password_hash nullable + add email.
    # All changes in one batch_alter_table call to minimise table recreations.
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("username", nullable=True)
        batch_op.alter_column("password_hash", nullable=True)
        batch_op.add_column(sa.Column("email", sa.String(255), nullable=True))

    # email unique index (separate from batch to avoid SQLite constraint issues)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # 2. Create user_identities table.
    op.create_table(
        "user_identities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_uid", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column(
            "created",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("last_seen", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("provider", "provider_uid", name="uq_identity_provider_uid"),
    )
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])
    op.create_index(
        "ix_user_identities_provider_uid",
        "user_identities",
        ["provider", "provider_uid"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_identities_provider_uid", table_name="user_identities")
    op.drop_index("ix_user_identities_user_id", table_name="user_identities")
    op.drop_table("user_identities")

    op.drop_index("ix_users_email", table_name="users")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("email")
        batch_op.alter_column("username", nullable=False)
        batch_op.alter_column("password_hash", nullable=False)
