"""Kanban models: projects, tasks, dependencies, checklist."""

import enum
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
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


class KanbanTaskStatus(str, enum.Enum):
    """Status values for kanban tasks."""

    draft = "draft"
    todo = "todo"
    in_progress = "in_progress"
    review = "review"
    done = "done"


class KanbanProject(Base):
    """Kanban project linked to a GitHub repository."""

    __tablename__ = "kanban_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    github_owner: Mapped[str] = mapped_column(String(100))
    github_repo: Mapped[str] = mapped_column(String(100))
    github_token: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    label_mapping: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    last_synced: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
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

    tasks: Mapped[list["KanbanTask"]] = relationship(
        "KanbanTask", back_populates="project", cascade="all, delete-orphan", lazy="noload"
    )

    _DEFAULT_LABEL_MAPPING = {
        "todo": "status:todo",
        "in_progress": "status:in_progress",
        "review": "status:review",
    }

    def get_label_mapping(self) -> dict:
        if self.label_mapping:
            try:
                result: dict = json.loads(self.label_mapping)
                return result
            except (json.JSONDecodeError, TypeError):
                pass
        return dict(self._DEFAULT_LABEL_MAPPING)

    def get_reverse_label_mapping(self) -> dict:
        return {v: k for k, v in self.get_label_mapping().items()}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "github_owner": self.github_owner,
            "github_repo": self.github_repo,
            "has_token": bool(self.github_token),
            "webhook_secret_set": bool(self.webhook_secret),
            "label_mapping": self.get_label_mapping(),
            "sync_enabled": self.sync_enabled,
            "last_synced": self.last_synced.isoformat() if self.last_synced else None,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class KanbanTask(Base):
    """Kanban task card."""

    __tablename__ = "kanban_tasks"
    __table_args__ = (
        UniqueConstraint("project_id", "github_issue_number", name="uq_task_project_issue"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="draft", server_default="draft", index=True
    )
    is_private: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    assignee: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_by: Mapped[str] = mapped_column(String(100), index=True)
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    start_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    due_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    project_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("kanban_projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    github_issue_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    project: Mapped[Optional["KanbanProject"]] = relationship(
        "KanbanProject", back_populates="tasks", lazy="noload"
    )
    checklist: Mapped[list["KanbanChecklistItem"]] = relationship(
        "KanbanChecklistItem", back_populates="task", cascade="all, delete-orphan", lazy="noload"
    )
    dependencies_as_blocker: Mapped[list["KanbanTaskDependency"]] = relationship(
        "KanbanTaskDependency",
        foreign_keys="KanbanTaskDependency.blocker_id",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    dependencies_as_dependent: Mapped[list["KanbanTaskDependency"]] = relationship(
        "KanbanTaskDependency",
        foreign_keys="KanbanTaskDependency.dependent_id",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "is_private": self.is_private,
            "assignee": self.assignee,
            "created_by": self.created_by,
            "owner_id": self.owner_id,
            "start_date": self.start_date,
            "due_date": self.due_date,
            "position": self.position,
            "tags": json.loads(self.tags) if self.tags else [],
            "project_id": self.project_id,
            "github_issue_number": self.github_issue_number,
            "checklist": [c.to_dict() for c in self.checklist] if self.checklist else [],
            "blockers": [d.blocker_id for d in self.dependencies_as_dependent]
            if self.dependencies_as_dependent
            else [],
            "dependents": [d.dependent_id for d in self.dependencies_as_blocker]
            if self.dependencies_as_blocker
            else [],
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class KanbanTaskDependency(Base):
    """Dependency link between two kanban tasks (blocker blocks dependent)."""

    __tablename__ = "kanban_task_dependencies"

    blocker_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("kanban_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    dependent_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("kanban_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )


class KanbanChecklistItem(Base):
    """Checklist item inside a kanban task."""

    __tablename__ = "kanban_checklist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("kanban_tasks.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(String(500))
    is_done: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    task: Mapped["KanbanTask"] = relationship("KanbanTask", back_populates="checklist")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "text": self.text,
            "is_done": self.is_done,
            "position": self.position,
        }
