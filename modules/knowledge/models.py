"""Knowledge base models: collections, documents, FAQ, GitHub repos, Google Drive."""

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


class FAQEntry(Base):
    """FAQ question-answer pair with fuzzy matching support"""

    __tablename__ = "faq_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    answer: Mapped[str] = mapped_column(Text)
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "keywords": json.loads(self.keywords) if self.keywords else [],
            "enabled": self.enabled,
            "hit_count": self.hit_count,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }

    @classmethod
    def from_legacy(cls, question: str, answer: str) -> "FAQEntry":
        """Create from legacy JSON format (question: answer)"""
        return cls(question=question.lower(), answer=answer, enabled=True)


class KnowledgeCollection(Base):
    """Knowledge base collection (container for documents)."""

    __tablename__ = "knowledge_collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    base_dir: Mapped[str] = mapped_column(
        String(200), default="wiki-pages", server_default="wiki-pages"
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    created: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    documents: Mapped[list["KnowledgeDocument"]] = relationship(
        "KnowledgeDocument", back_populates="collection", lazy="noload"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "enabled": self.enabled,
            "base_dir": self.base_dir,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class KnowledgeDocument(Base):
    """Knowledge base document tracked in wiki-pages/."""

    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    source_type: Mapped[str] = mapped_column(String(50), default="manual")  # manual, import, wiki
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    section_count: Mapped[int] = mapped_column(Integer, default=0)
    collection_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("knowledge_collections.id"), nullable=True, index=True
    )
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    created: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    collection: Mapped[Optional["KnowledgeCollection"]] = relationship(
        "KnowledgeCollection", back_populates="documents"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "title": self.title,
            "source_type": self.source_type,
            "file_size_bytes": self.file_size_bytes,
            "section_count": self.section_count,
            "collection_id": self.collection_id,
            "owner_id": self.owner_id,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


# Default file patterns for GitHub repo sync
GITHUB_DEFAULT_INCLUDE = [
    "*.md",
    "*.py",
    "*.ts",
    "*.tsx",
    "*.vue",
    "*.go",
    "*.js",
    "*.jsx",
    "*.rs",
    "*.java",
    "*.yaml",
    "*.yml",
    "*.toml",
    "*.sh",
    "*.sql",
    "*.html",
    "*.css",
]
GITHUB_DEFAULT_EXCLUDE = [
    "node_modules",
    ".git",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "*.lock",
    "*.min.js",
    "*.min.css",
    "package-lock.json",
]


class GitHubRepoProject(Base):
    """GitHub repository connected as a knowledge base collection."""

    __tablename__ = "github_repo_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    github_owner: Mapped[str] = mapped_column(String(100), nullable=False)
    github_repo: Mapped[str] = mapped_column(String(100), nullable=False)
    github_token: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    branch: Mapped[str] = mapped_column(String(100), default="main", server_default="main")
    collection_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("knowledge_collections.id"), nullable=True
    )
    sync_status: Mapped[str] = mapped_column(String(20), default="idle", server_default="idle")
    sync_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_synced: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_commit_sha: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    include_patterns: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exclude_patterns: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_size_bytes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    created: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    def get_include_patterns(self) -> list[str]:
        if self.include_patterns:
            try:
                result: list[str] = json.loads(self.include_patterns)
                return result
            except (json.JSONDecodeError, TypeError):
                pass
        return list(GITHUB_DEFAULT_INCLUDE)

    def get_exclude_patterns(self) -> list[str]:
        if self.exclude_patterns:
            try:
                result: list[str] = json.loads(self.exclude_patterns)
                return result
            except (json.JSONDecodeError, TypeError):
                pass
        return list(GITHUB_DEFAULT_EXCLUDE)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "github_owner": self.github_owner,
            "github_repo": self.github_repo,
            "has_token": bool(self.github_token),
            "branch": self.branch,
            "collection_id": self.collection_id,
            "sync_status": self.sync_status,
            "sync_error": self.sync_error,
            "last_synced": self.last_synced.isoformat() if self.last_synced else None,
            "last_commit_sha": self.last_commit_sha,
            "include_patterns": self.get_include_patterns(),
            "exclude_patterns": self.get_exclude_patterns(),
            "file_count": self.file_count,
            "total_size_bytes": self.total_size_bytes,
            "workspace_id": self.workspace_id,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class RSSFeed(Base):
    """RSS/Atom feed subscription wired to a knowledge collection.

    Each item from the feed becomes one KnowledgeDocument under the linked
    collection. Items are deduplicated by `guid`. The full-article path is
    optional — if `fetch_full_text` is True, the sync task fetches the item
    URL and converts HTML to markdown; otherwise only `title + summary` from
    the RSS entry is stored.
    """

    __tablename__ = "rss_feeds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    collection_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("knowledge_collections.id"), nullable=True, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    fetch_full_text: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    verify_ssl: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    last_etag: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_modified: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    last_synced: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sync_status: Mapped[str] = mapped_column(String(20), default="idle", server_default="idle")
    item_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    created: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "collection_id": self.collection_id,
            "enabled": self.enabled,
            "fetch_full_text": self.fetch_full_text,
            "verify_ssl": self.verify_ssl,
            "last_synced": self.last_synced.isoformat() if self.last_synced else None,
            "last_error": self.last_error,
            "sync_status": self.sync_status,
            "item_count": self.item_count,
            "workspace_id": self.workspace_id,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class RSSFeedItem(Base):
    """Persistent record of a single RSS item — used for dedup across syncs."""

    __tablename__ = "rss_feed_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rss_feeds.id", ondelete="CASCADE"), nullable=False, index=True
    )
    guid: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    link: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    document_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("knowledge_documents.id", ondelete="SET NULL"), nullable=True
    )
    pub_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "feed_id": self.feed_id,
            "guid": self.guid,
            "title": self.title,
            "link": self.link,
            "document_id": self.document_id,
            "pub_date": self.pub_date.isoformat() if self.pub_date else None,
            "created": self.created.isoformat() if self.created else None,
        }


class GoogleDriveProject(Base):
    """Google Drive folder connected as a knowledge base collection."""

    __tablename__ = "google_drive_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    folder_id: Mapped[str] = mapped_column(String(200), nullable=False, server_default="root")
    folder_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    collection_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("knowledge_collections.id"), nullable=True
    )
    sync_status: Mapped[str] = mapped_column(String(20), default="idle", server_default="idle")
    sync_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_synced: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    file_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_size_bytes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    include_mime_types: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    created: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "user_id": self.user_id,
            "folder_id": self.folder_id,
            "folder_name": self.folder_name,
            "collection_id": self.collection_id,
            "sync_status": self.sync_status,
            "sync_error": self.sync_error,
            "last_synced": self.last_synced.isoformat() if self.last_synced else None,
            "file_count": self.file_count,
            "total_size_bytes": self.total_size_bytes,
            "workspace_id": self.workspace_id,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }
