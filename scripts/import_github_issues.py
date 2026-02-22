"""Import GitHub issues into the Kanban board.

Usage:
    cd /opt/ai-secretary
    venv/bin/python scripts/import_github_issues.py [--dry-run]

Mapping:
    CLOSED → done (public)
    OPEN   → todo (public)

Features:
    - Labels → tags
    - Body → description (truncated to 5000 chars)
    - Checklist items (- [ ] / - [x]) → kanban checklist items
    - "Depends on #N" / "Part of #N" → kanban dependencies
    - createdAt → start_date
    - closedAt → due_date (for closed issues)
    - Skips already-imported issues (checks title prefix "GH-#N:")
"""

import asyncio
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main():
    dry_run = "--dry-run" in sys.argv

    # ---- Fetch issues from GitHub ----
    print("Fetching GitHub issues...")
    result = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--state",
            "all",
            "--limit",
            "300",
            "--json",
            "number,title,state,labels,body,createdAt,closedAt,assignees",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error fetching issues: {result.stderr}")
        sys.exit(1)

    issues = json.loads(result.stdout)
    issues.sort(key=lambda x: x["number"])  # ascending by number
    print(f"Found {len(issues)} issues ({sum(1 for i in issues if i['state'] == 'OPEN')} open, {sum(1 for i in issues if i['state'] == 'CLOSED')} closed)")

    if dry_run:
        print("\n=== DRY RUN — no changes will be made ===\n")

    # ---- Init DB ----
    if not dry_run:
        from db.database import AsyncSessionLocal, init_db
        from db.repositories.kanban import KanbanRepository

        await init_db()

    # ---- Check for existing imported tasks ----
    existing_gh_numbers = set()
    if not dry_run:
        from sqlalchemy import select

        from db.models import KanbanTask

        async with AsyncSessionLocal() as session:
            result_db = await session.execute(
                select(KanbanTask.title).where(KanbanTask.title.like("GH-#%:%"))
            )
            for (title,) in result_db.all():
                match = re.match(r"GH-#(\d+):", title)
                if match:
                    existing_gh_numbers.add(int(match.group(1)))

    if existing_gh_numbers:
        print(f"Already imported: {len(existing_gh_numbers)} issues (will skip)")

    # ---- Parse and create tasks ----
    # First pass: create all tasks, remember gh_number → kanban_id mapping
    gh_to_kanban = {}
    created = 0
    skipped = 0

    for issue in issues:
        num = issue["number"]
        if num in existing_gh_numbers:
            skipped += 1
            continue

        title = f"GH-#{num}: {issue['title']}"
        if len(title) > 500:
            title = title[:497] + "..."

        # Status mapping
        status = "done" if issue["state"] == "CLOSED" else "todo"

        # Labels → tags
        tags = [label["name"] for label in issue.get("labels", [])]

        # Dates
        created_at = issue.get("createdAt", "")
        closed_at = issue.get("closedAt")
        start_date = created_at[:10] if created_at else None
        due_date = closed_at[:10] if closed_at else None

        # Assignee
        assignees = issue.get("assignees", [])
        assignee = assignees[0]["login"] if assignees else None

        # Description: first 5000 chars of body
        body = issue.get("body") or ""
        description = body[:5000] if body else None

        # Extract checklist items from body
        checklist_items = []
        for match in re.finditer(r"^- \[([ xX])\] (.+)$", body, re.MULTILINE):
            is_done = match.group(1).lower() == "x"
            text = match.group(2).strip()[:500]
            checklist_items.append({"text": text, "is_done": is_done})

        # Print summary
        tags_str = ", ".join(tags) if tags else "-"
        ck_str = f", {len(checklist_items)} checklist items" if checklist_items else ""
        print(f"  {'[DRY]' if dry_run else '[CREATE]'} #{num} → {status} | tags: [{tags_str}]{ck_str}")

        if dry_run:
            gh_to_kanban[num] = num  # placeholder
            created += 1
            continue

        # Create task directly via DB
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            tags_json = json.dumps(tags, ensure_ascii=False) if tags else None

            task_dict = await repo.create_task(
                title=title,
                description=description,
                assignee=assignee,
                start_date=start_date,
                due_date=due_date,
                tags=tags_json,
                created_by="github-import",
            )
            task_id = task_dict["id"]

            # Update status (create always makes draft+private)
            await repo.update_task(
                task_id,
                status=status,
                is_private=False,
            )

            # Add checklist items
            for idx, item in enumerate(checklist_items):
                ci = await repo.add_checklist_item(task_id, item["text"], idx)
                if item["is_done"]:
                    await repo.toggle_checklist_item(ci["id"])

            gh_to_kanban[num] = task_id
            created += 1

    print(f"\nCreated: {created}, Skipped (already imported): {skipped}")

    # ---- Second pass: dependencies ----
    dep_pattern = re.compile(
        r"(?:depends?\s+on|part\s+of|blocked\s+by|blocks|after)\s+#(\d+)", re.IGNORECASE
    )

    dep_count = 0
    for issue in issues:
        num = issue["number"]
        if num not in gh_to_kanban:
            continue

        body = issue.get("body") or ""
        refs = dep_pattern.findall(body)
        for ref_str in refs:
            ref_num = int(ref_str)
            if ref_num not in gh_to_kanban:
                continue
            if ref_num == num:
                continue

            blocker_id = gh_to_kanban[ref_num]
            dependent_id = gh_to_kanban[num]

            if dry_run:
                print(f"  [DRY] dependency: #{ref_num} blocks #{num}")
                dep_count += 1
                continue

            try:
                async with AsyncSessionLocal() as session:
                    repo = KanbanRepository(session)
                    await repo.add_dependency(blocker_id, dependent_id)
                dep_count += 1
            except (ValueError, Exception) as e:
                print(f"  [WARN] dependency #{ref_num}→#{num}: {e}")

    print(f"Dependencies created: {dep_count}")
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
