"""Add country to users (drives default-assistant provisioning).

Users get country-specific default assistants (lawyer/accountant) based on this
field: "ru" (default) or "kz". Backfill everyone to "ru", then flip the two
Kazakhstan users (stalker, stalkerelectric) to "kz" — matching the historical
hard-coded rule in scripts/seed_legal_assistants.py.

Revision ID: 0026_add_user_country
Revises: 0025_widget_web_search
Create Date: 2026-07-22
"""

from typing import Union

import sqlalchemy as sa

from alembic import op


revision: str = "0026_add_user_country"
down_revision: Union[str, None] = "0025_widget_web_search"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "country",
                sa.String(length=2),
                nullable=False,
                server_default="ru",
            )
        )
    # Kazakhstan users (until a self-serve country selector lands, the rule is
    # hard-coded, same as the legacy seed script).
    op.execute("UPDATE users SET country = 'kz' WHERE username IN ('stalker', 'stalkerelectric')")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("country")
