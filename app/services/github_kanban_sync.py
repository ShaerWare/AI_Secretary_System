"""Bidirectional GitHub Issues <-> Kanban sync service."""

import json
import logging
from typing import Optional

import httpx

from db.integration import async_kanban_manager, async_kanban_project_manager


logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _github_headers(token: str) -> dict:
    """Standard GitHub API headers."""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AI-Secretary-Kanban-Sync",
    }


def _issue_to_task_fields(issue: dict, project: dict) -> dict:
    """Map a GitHub issue to KanbanTask fields."""
    reverse_mapping = project.get("_reverse_label_mapping", {})

    # Determine status from issue state + labels
    labels = [lbl["name"] for lbl in issue.get("labels", [])]
    status_labels = []
    other_labels = []
    for lbl in labels:
        if lbl in reverse_mapping:
            status_labels.append(reverse_mapping[lbl])
        else:
            other_labels.append(lbl)

    if issue.get("state") == "closed":
        status = "done"
    elif status_labels:
        status = status_labels[0]
    else:
        status = "todo"

    # Assignee
    assignee = None
    if issue.get("assignee"):
        assignee = issue["assignee"].get("login")

    # Tags: non-status labels
    tags_json = json.dumps(other_labels, ensure_ascii=False) if other_labels else None

    return {
        "title": issue["title"],
        "description": issue.get("body") or None,
        "status": status,
        "is_private": False,
        "assignee": assignee,
        "created_by": issue.get("user", {}).get("login", "github"),
        "tags": tags_json,
    }


async def sync_all_issues(project_id: int) -> dict:
    """Fetch ALL issues from GitHub and upsert into kanban.

    Returns {created: int, updated: int, total: int}.
    """
    project = await async_kanban_project_manager.get_project_with_token(project_id)
    if not project or not project.get("github_token"):
        raise ValueError("Project not found or no GitHub token configured")

    owner = project["github_owner"]
    repo = project["github_repo"]
    token = project["github_token"]
    headers = _github_headers(token)

    created = 0
    updated = 0
    total = 0
    page = 1

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            url = f"{GITHUB_API}/repos/{owner}/{repo}/issues"
            params = {"state": "all", "per_page": 100, "page": page}
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            issues = resp.json()

            if not issues:
                break

            for issue in issues:
                # Skip pull requests (GitHub returns PRs in issues endpoint)
                if issue.get("pull_request"):
                    continue

                issue_number = issue["number"]
                total += 1
                fields = _issue_to_task_fields(issue, project)

                existing = await async_kanban_manager.find_by_github_issue(project_id, issue_number)
                await async_kanban_manager.upsert_from_github(project_id, issue_number, **fields)
                if existing:
                    updated += 1
                else:
                    created += 1

            if len(issues) < 100:
                break
            page += 1

    await async_kanban_project_manager.update_last_synced(project_id)
    logger.info(f"Synced {owner}/{repo}: created={created}, updated={updated}, total={total}")
    return {"created": created, "updated": updated, "total": total}


async def push_status_to_github(project_id: int, issue_number: int, new_status: str) -> bool:
    """Push a status change to GitHub: update labels + close/reopen as needed."""
    project = await async_kanban_project_manager.get_project_with_token(project_id)
    if not project or not project.get("github_token"):
        return False

    owner = project["github_owner"]
    repo = project["github_repo"]
    token = project["github_token"]
    headers = _github_headers(token)
    label_mapping = project.get("_label_mapping", {})

    # All status labels we manage
    managed_labels = set(label_mapping.values())

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get current issue
        issue_url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}"
        resp = await client.get(issue_url, headers=headers)
        if resp.status_code != 200:
            logger.error(f"Failed to get issue #{issue_number}: {resp.status_code}")
            return False

        issue = resp.json()
        current_labels = [lbl["name"] for lbl in issue.get("labels", [])]

        # Remove old status labels, add new one
        new_labels = [lbl for lbl in current_labels if lbl not in managed_labels]
        new_status_label = label_mapping.get(new_status)
        if new_status_label and new_status != "done":
            new_labels.append(new_status_label)

        # Update labels
        resp = await client.patch(
            issue_url,
            headers=headers,
            json={"labels": new_labels},
        )
        if resp.status_code != 200:
            logger.error(f"Failed to update labels on #{issue_number}: {resp.status_code}")
            return False

        # Close or reopen based on status
        current_state = issue.get("state", "open")
        if new_status == "done" and current_state == "open":
            await client.patch(issue_url, headers=headers, json={"state": "closed"})
        elif new_status != "done" and current_state == "closed":
            await client.patch(issue_url, headers=headers, json={"state": "open"})

    logger.info(f"Pushed status '{new_status}' to {owner}/{repo}#{issue_number}")
    return True


async def handle_issue_webhook(payload: dict, project: dict) -> Optional[dict]:
    """Handle a GitHub issue webhook event. Returns upserted task dict or None."""
    action = payload.get("action", "")
    issue = payload.get("issue")
    if not issue:
        return None

    supported_actions = {
        "opened",
        "edited",
        "closed",
        "reopened",
        "labeled",
        "unlabeled",
        "assigned",
    }
    if action not in supported_actions:
        return None

    issue_number = issue["number"]
    project_id = project["id"]
    fields = _issue_to_task_fields(issue, project)

    result = await async_kanban_manager.upsert_from_github(project_id, issue_number, **fields)
    logger.info(f"Webhook: {action} issue #{issue_number} -> task #{result.get('id')}")
    return result
