"""Claude Code models: sessions and projects."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class ClaudeCodeSession(Base):
    """Claude Code CLI session for web UI."""

    __tablename__ = "claude_code_sessions"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    cli_session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="New session")
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active"
    )  # active, completed, error, aborted
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    total_turns: Mapped[int] = mapped_column(Integer, default=0)
    max_turns: Mapped[int] = mapped_column(Integer, default=50)
    working_directory: Mapped[str] = mapped_column(String(500), default="/opt/ai-secretary")
    chat_session_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    kanban_task_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("kanban_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    events_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
            "cli_session_id": self.cli_session_id,
            "title": self.title,
            "owner_id": self.owner_id,
            "status": self.status,
            "model": self.model,
            "total_turns": self.total_turns,
            "max_turns": self.max_turns,
            "working_directory": self.working_directory,
            "chat_session_id": self.chat_session_id,
            "kanban_task_id": self.kanban_task_id,
            "events_json": self.events_json,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }

    def to_summary(self) -> dict:
        """Lightweight dict without events_json (for sidebar lists)."""
        return {
            "id": self.id,
            "cli_session_id": self.cli_session_id,
            "title": self.title,
            "owner_id": self.owner_id,
            "status": self.status,
            "model": self.model,
            "total_turns": self.total_turns,
            "chat_session_id": self.chat_session_id,
            "kanban_task_id": self.kanban_task_id,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class ClaudeCodeProject(Base):
    """Claude Code project directory (local or SSH remote)."""

    __tablename__ = "claude_code_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    path: Mapped[str] = mapped_column(String(500))
    type: Mapped[str] = mapped_column(String(20), default="local")  # "local" or "ssh"
    ssh_host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ssh_user: Mapped[str] = mapped_column(String(100), default="root")
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    ssh_key_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
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
            "path": self.path,
            "type": self.type,
            "ssh_host": self.ssh_host,
            "ssh_user": self.ssh_user,
            "ssh_port": self.ssh_port,
            "ssh_key_path": self.ssh_key_path,
            "owner_id": self.owner_id,
            "workspace_id": self.workspace_id,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }
