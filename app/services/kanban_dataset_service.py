"""Kanban Dataset Service — transforms kanban tasks into markdown for RAG indexing.

Pure functions: no DB access, no side effects (except file I/O in get/clean helpers).
Same pattern as crm_dataset_service.py and woocommerce_dataset_service.py.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


KANBAN_DIR = Path("data/kanban-dataset")


def get_project_dir(project_slug: str) -> Path:
    """Get the directory for a specific kanban project's dataset."""
    safe_slug = re.sub(r"[^\w\-]", "-", project_slug).strip("-")
    return KANBAN_DIR / safe_slug


def _format_date(date_str: Optional[str]) -> str:
    """Format date string for display."""
    if not date_str:
        return "—"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y")
    except (ValueError, AttributeError):
        return date_str


def _parse_tags(tags: Any) -> list[str]:
    """Parse tags from various formats (JSON string, list, None)."""
    if not tags:
        return []
    if isinstance(tags, str):
        try:
            parsed = json.loads(tags)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            return [tags]
    if isinstance(tags, list):
        return tags
    return []


def _status_label(status: str) -> str:
    """Convert status code to human-readable label."""
    labels = {
        "draft": "Черновик",
        "todo": "К выполнению",
        "in_progress": "В работе",
        "review": "На проверке",
        "done": "Готово",
    }
    return labels.get(status, status)


def _build_task_section(task: dict[str, Any]) -> str:
    """Build a ## section for a single kanban task."""
    task_id = task.get("id", "")
    title = task.get("title", "Без названия")
    status = task.get("status", "todo")
    status_text = _status_label(status)

    lines = [f"## Задача #{task_id}: {title} — {status_text}", ""]
    lines.append(f"- **ID**: {task_id}")
    lines.append(f"- **Статус**: {status_text}")

    if task.get("assignee"):
        lines.append(f"- **Исполнитель**: {task['assignee']}")

    if task.get("created_by"):
        lines.append(f"- **Автор**: {task['created_by']}")

    if task.get("start_date"):
        lines.append(f"- **Начало**: {_format_date(task['start_date'])}")

    if task.get("due_date"):
        lines.append(f"- **Срок**: {_format_date(task['due_date'])}")

    tags = _parse_tags(task.get("tags"))
    if tags:
        lines.append(f"- **Теги**: {', '.join(tags)}")

    if task.get("github_issue_number"):
        lines.append(f"- **GitHub Issue**: #{task['github_issue_number']}")

    if task.get("description"):
        lines.append("")
        lines.append("### Описание")
        lines.append("")
        lines.append(task["description"])

    checklist = task.get("checklist", [])
    if checklist:
        lines.append("")
        lines.append("### Чеклист")
        lines.append("")
        for item in checklist:
            check = "x" if item.get("is_done") else " "
            lines.append(f"- [{check}] {item.get('text', '')}")

    blockers = task.get("blockers", [])
    dependents = task.get("dependents", [])
    if blockers or dependents:
        lines.append("")
        lines.append("### Зависимости")
        lines.append("")
        if blockers:
            lines.append(f"- **Блокируется**: {', '.join(f'#{b}' for b in blockers)}")
        if dependents:
            lines.append(f"- **Блокирует**: {', '.join(f'#{d}' for d in dependents)}")

    return "\n".join(lines)


def build_status_document(
    project_name: str,
    status: str,
    tasks: list[dict[str, Any]],
    sync_time: str,
) -> str:
    """Build markdown document for one status column with all its tasks."""
    status_text = _status_label(status)
    count = len(tasks)

    lines = [
        f"# {project_name}: {status_text} ({count} задач)",
        "",
        f"Данные из канбан-доски. Последнее обновление: {sync_time}",
        "",
    ]

    if not tasks:
        lines.append("Задач в этом статусе нет.")
        return "\n".join(lines)

    for task in tasks:
        lines.append(_build_task_section(task))
        lines.append("")

    return "\n".join(lines)


def build_project_summary(
    project_name: str,
    project_info: dict[str, Any],
    tasks: list[dict[str, Any]],
    sync_time: str,
) -> str:
    """Build summary document with aggregate stats."""
    total = len(tasks)

    # Count by status
    status_counts: dict[str, int] = {}
    for task in tasks:
        s = task.get("status", "todo")
        status_counts[s] = status_counts.get(s, 0) + 1

    lines = [
        f"# {project_name}: Сводка по задачам",
        "",
        f"Данные из канбан-доски. Последнее обновление: {sync_time}",
        "",
        "## Общая статистика",
        "",
        f"- **Всего задач**: {total}",
    ]

    if project_info.get("github_owner") and project_info.get("github_repo"):
        lines.append(
            f"- **Репозиторий**: {project_info['github_owner']}/{project_info['github_repo']}"
        )

    lines.append("")

    # Status breakdown
    if status_counts:
        lines.append("| Статус | Количество |")
        lines.append("|--------|-----------|")
        for status_code in ["todo", "in_progress", "review", "done", "draft"]:
            if status_code in status_counts:
                lines.append(f"| {_status_label(status_code)} | {status_counts[status_code]} |")
        lines.append("")

    # Assignee breakdown
    assignee_counts: dict[str, int] = {}
    for task in tasks:
        a = task.get("assignee") or "Не назначен"
        assignee_counts[a] = assignee_counts.get(a, 0) + 1

    if assignee_counts:
        lines.append("## По исполнителям")
        lines.append("")
        for assignee, count in sorted(assignee_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- **{assignee}**: {count} задач")
        lines.append("")

    # Overdue tasks
    now = datetime.utcnow().strftime("%Y-%m-%d")
    overdue = [
        t
        for t in tasks
        if t.get("due_date") and t["due_date"] < now and t.get("status") not in ("done",)
    ]
    if overdue:
        lines.append("## Просроченные задачи")
        lines.append("")
        for t in overdue:
            lines.append(f"- #{t['id']} {t['title']} — срок {_format_date(t['due_date'])}")
        lines.append("")

    # Recent tasks (last 10 updated)
    sorted_tasks = sorted(
        tasks,
        key=lambda x: x.get("updated") or x.get("created") or "",
        reverse=True,
    )
    recent = sorted_tasks[:10]
    if recent:
        lines.append("## Последние обновлённые задачи")
        lines.append("")
        for t in recent:
            status_text = _status_label(t.get("status", "todo"))
            lines.append(f"- #{t['id']} {t['title']} — {status_text}")
        lines.append("")

    return "\n".join(lines)


def clean_kanban_files(project_slug: str) -> list[str]:
    """Remove all kanban dataset files for a project. Returns removed filenames."""
    project_dir = get_project_dir(project_slug)
    removed = []
    if not project_dir.exists():
        return removed
    for f in project_dir.glob("*.md"):
        removed.append(f.name)
        f.unlink()
    # Remove directory if empty
    try:
        project_dir.rmdir()
    except OSError:
        pass
    return removed
