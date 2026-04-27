"""Add rss_feeds and rss_feed_items tables for RSS knowledge ingestion.

Revision ID: 0023_rss_feeds
Revises: 0022_chat_session_prompts
Create Date: 2026-04-27
"""

from typing import Union

import sqlalchemy as sa

from alembic import op


revision: str = "0023_rss_feeds"
down_revision: Union[str, None] = "0022_chat_session_prompts"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "rss_feeds",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("url", sa.String(500), nullable=False, unique=True),
        sa.Column(
            "collection_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_collections.id"),
            nullable=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("fetch_full_text", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("verify_ssl", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("last_etag", sa.String(500), nullable=True),
        sa.Column("last_modified", sa.String(200), nullable=True),
        sa.Column("last_synced", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sync_status", sa.String(20), nullable=False, server_default="idle"),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
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
    op.create_index("ix_rss_feeds_collection_id", "rss_feeds", ["collection_id"])

    op.create_table(
        "rss_feed_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "feed_id",
            sa.Integer(),
            sa.ForeignKey("rss_feeds.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("guid", sa.String(500), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("link", sa.String(1000), nullable=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("pub_date", sa.DateTime(), nullable=True),
        sa.Column("created", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("feed_id", "guid", name="uq_rss_feed_items_feed_guid"),
    )
    op.create_index("ix_rss_feed_items_feed_id", "rss_feed_items", ["feed_id"])
    op.create_index("ix_rss_feed_items_guid", "rss_feed_items", ["guid"])


def downgrade() -> None:
    op.drop_index("ix_rss_feed_items_guid", table_name="rss_feed_items")
    op.drop_index("ix_rss_feed_items_feed_id", table_name="rss_feed_items")
    op.drop_table("rss_feed_items")
    op.drop_index("ix_rss_feeds_collection_id", table_name="rss_feeds")
    op.drop_table("rss_feeds")
