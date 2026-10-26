"""Google Drive sources: a folder or selected files kept in sync with the platform.

A source (`GoogleDriveProject`) feeds one or both of:
- `rag` — every readable file becomes a markdown document in the source's
  knowledge collection;
- `prices` — the raw files go to SUPPLIER_PRICES_DIR and the supplier price
  parser rebuilds the offers from them.

Suppliers replace their files in a shared folder whenever they like, so a
source is re-checked daily: Drive's modifiedTime per file is compared with what
was synced last (`files_state`), and nothing is downloaded when nothing moved.

Downloads use the Google account of the user who created the source.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path


try:
    from sqlalchemy import select
except ImportError:
    from sqlalchemy.future import select  # type: ignore[assignment]

from db.database import AsyncSessionLocal
from modules.core.events import DatasetSynced
from modules.knowledge.models import GoogleDriveProject, KnowledgeCollection


logger = logging.getLogger(__name__)

PURPOSES = ("rag", "prices", "both")

# In-process guard: the DB status can stay "syncing" forever after a crash,
# which used to lock the sync button with a 409 until someone edited the row.
_running: set[int] = set()


def is_running(project_id: int) -> bool:
    return project_id in _running


def feeds_rag(purpose: str | None) -> bool:
    return (purpose or "rag") in ("rag", "both")


def feeds_prices(purpose: str | None) -> bool:
    return purpose in ("prices", "both")


async def _load(project_id: int) -> GoogleDriveProject | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GoogleDriveProject).where(GoogleDriveProject.id == project_id)
        )
        return result.scalar_one_or_none()


async def _update(project_id: int, **fields) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GoogleDriveProject).where(GoogleDriveProject.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            return
        for key, value in fields.items():
            setattr(project, key, value)
        await session.commit()


async def _price_names_owned_by_others(project_id: int) -> set[str]:
    """Local price files written by other Drive sources — not ours to archive."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GoogleDriveProject).where(GoogleDriveProject.id != project_id)
        )
        others = result.scalars().all()
    names: set[str] = set()
    for other in others:
        if not feeds_prices(other.purpose) or not other.files_state:
            continue
        for entry in json.loads(other.files_state).values():
            if entry.get("local"):
                names.add(entry["local"])
    return names


def _price_files_present(state: dict) -> bool:
    from modules.procurement.suppliers.registry import SUPPLIER_PRICES_DIR

    base = Path(SUPPLIER_PRICES_DIR)
    locals_ = [e["local"] for e in state.values() if e.get("local")]
    return all((base / name).is_file() for name in locals_)


async def _deliver_prices(
    project_id: int,
    token: str,
    files: list[dict],
    report: dict,
    previously_owned: set[str] | None = None,
) -> dict:
    """Download price files and install them. Returns {file_id: local_name}."""
    from app.services.google_drive_sync_service import download_raw_file, price_file_name
    from modules.procurement.suppliers.drive_files import install_price_files, supplier_report
    from modules.procurement.suppliers.registry import SUPPLIER_PRICES_DIR

    # Same name in two subfolders: the newer one wins, the admin is told.
    by_name: dict[str, dict] = {}
    duplicates: list[str] = []
    skipped = report.setdefault("skipped", [])
    for f in files:
        name = price_file_name(f)
        if not name:
            skipped.append({"name": f["name"], "reason": "не прайс (нужен xlsx/xls/pdf)"})
            continue
        prev = by_name.get(name)
        if prev:
            duplicates.append(name)
            if (f.get("modifiedTime") or "") <= (prev.get("modifiedTime") or ""):
                continue
        by_name[name] = f
    if not by_name:
        # An emptied or un-shared folder must not wipe the prices we have
        raise RuntimeError(
            "В источнике нет файлов прайсов (xlsx/xls/pdf) — папку прайсов не трогаю"
        )

    # Everything is downloaded before the folder is touched: a failed download
    # must not leave the parser with an emptied folder.
    downloaded: list[tuple[str, bytes, str | None]] = []
    local_by_id: dict[str, str] = {}
    for name, f in by_name.items():
        data = await download_raw_file(token, f)
        if data is None:
            raise RuntimeError(f"Не удалось скачать «{f['name']}» с Google Диска")
        downloaded.append((name, data, f.get("modifiedTime")))
        local_by_id[f["id"]] = name

    keep = await _price_names_owned_by_others(project_id)
    result = await asyncio.to_thread(install_price_files, downloaded, keep, previously_owned)

    present = sorted(
        p.name
        for p in Path(SUPPLIER_PRICES_DIR).iterdir()
        if p.is_file() and not p.name.startswith(".")
    )
    report["prices"] = {
        **supplier_report(present),
        "installed": result["installed"],
        "archived": result["archived"],
        "conflicts": result["conflicts"],
        "duplicates": sorted(set(duplicates)),
    }
    return local_by_id


async def _ensure_collection(project: GoogleDriveProject) -> KnowledgeCollection:
    """The source's knowledge collection; created when a prices-only source never had one."""
    async with AsyncSessionLocal() as session:
        if project.collection_id:
            result = await session.execute(
                select(KnowledgeCollection).where(KnowledgeCollection.id == project.collection_id)
            )
            collection = result.scalar_one_or_none()
            if collection:
                return collection
        collection = new_collection(project.name, project.folder_name or project.folder_id)
        session.add(collection)
        await session.flush()
        result = await session.execute(
            select(GoogleDriveProject).where(GoogleDriveProject.id == project.id)
        )
        row = result.scalar_one()
        row.collection_id = collection.id
        await session.commit()
        await session.refresh(collection)
        return collection


def new_collection(name: str, source_label: str) -> KnowledgeCollection:
    slug = f"gdrive-{name.lower().replace(' ', '-')[:50]}"
    return KnowledgeCollection(
        name=f"Google Drive: {name}",
        slug=slug,
        description=f"Synced from Google Drive: {source_label}",
        base_dir=f"data/google-drive/{slug}",
        workspace_id=1,
    )


async def _feed_rag(project: GoogleDriveProject, token: str, files: list[dict], report: dict):
    from app.services.google_drive_sync_service import convert_files_to_markdown

    collection = await _ensure_collection(project)
    Path(collection.base_dir).mkdir(parents=True, exist_ok=True)
    documents, skipped = await convert_files_to_markdown(token, files, collection.base_dir)
    report["rag"] = {"documents": len(documents), "skipped": skipped}
    if not documents and files:
        # Publishing an empty list would delete every document of the collection
        raise RuntimeError("Ни один файл не удалось прочитать — коллекцию не трогаю")

    from app.dependencies import ServiceContainer

    container = ServiceContainer.get_instance()
    if container and container.event_bus:
        await container.event_bus.publish(
            DatasetSynced(
                source="google_drive",
                collection_slug=collection.slug,
                action="synced",
                collection_name=collection.name,
                collection_description=collection.description or "",
                base_dir=collection.base_dir,
                documents=documents,
                delete_collection=False,
            )
        )
    return documents


async def sync_project(project_id: int, *, force: bool = False, parse_prices: bool = True) -> dict:
    """Check one source and re-sync it if anything on Drive changed.

    `force` re-downloads even when nothing changed. `parse_prices=False` only
    delivers price files — the nightly supplier task parses right after.
    Returns {"changed": bool, "error": str | None}.
    """
    if project_id in _running:
        return {"changed": False, "error": "already running"}
    _running.add(project_id)
    try:
        return await _sync_project(project_id, force=force, parse_prices=parse_prices)
    finally:
        _running.discard(project_id)


async def _sync_project(project_id: int, *, force: bool, parse_prices: bool) -> dict:
    from app.services.google_drive_sync_service import (
        files_fingerprint,
        list_source_files,
        state_changed,
    )
    from modules.google.service import google_oauth_service

    project = await _load(project_id)
    if not project:
        return {"changed": False, "error": "not found"}

    now = datetime.utcnow()
    await _update(project_id, sync_status="syncing", sync_error=None)
    try:
        creds = await google_oauth_service.get_valid_credentials(project.user_id)
        if not creds:
            raise ValueError(
                "Google-аккаунт владельца источника не подключён — переподключите в Настройках"
            )
        token = creds["access_token"]
        file_ids = json.loads(project.file_ids) if project.file_ids else None
        files, missing = await list_source_files(token, project.folder_id, file_ids)

        old_state = json.loads(project.files_state) if project.files_state else None
        new_state = files_fingerprint(files)
        unchanged = not state_changed(old_state, new_state)
        if unchanged and feeds_prices(project.purpose) and old_state:
            # Someone cleaned the folder by hand — deliver again
            unchanged = _price_files_present(old_state)
        if unchanged and not force:
            await _update(project_id, sync_status="idle", last_checked=now)
            logger.info("Drive source %s: no changes on Drive", project_id)
            return {"changed": False, "error": None}

        report: dict = {"missing": missing, "skipped": []}
        if feeds_prices(project.purpose):
            owned = {e["local"] for e in (old_state or {}).values() if e.get("local")}
            local_by_id = await _deliver_prices(project_id, token, files, report, owned)
            for fid, local in local_by_id.items():
                new_state[fid]["local"] = local
        if feeds_rag(project.purpose):
            project = await _load(project_id) or project
            await _feed_rag(project, token, files, report)

        if feeds_prices(project.purpose) and parse_prices:
            from modules.procurement.suppliers.adapter import sync_all_suppliers

            report["parsed"] = await sync_all_suppliers()

        total_size = sum(int(f.get("size") or 0) for f in files)
        error = None
        if missing:
            error = f"Нет доступа к {len(missing)} выбранным файлам (удалены или закрыт доступ)"
        await _update(
            project_id,
            sync_status="error" if error else "idle",
            sync_error=error,
            last_synced=now,
            last_checked=now,
            file_count=len(files),
            total_size_bytes=total_size,
            files_state=json.dumps(new_state, ensure_ascii=False),
            sync_report=json.dumps(report, ensure_ascii=False),
        )
        logger.info("Drive source %s synced: %d files", project_id, len(files))
        return {"changed": True, "error": error}
    except Exception as e:
        logger.error(f"Google Drive sync failed for project {project_id}: {e}")
        await _update(project_id, sync_status="error", sync_error=str(e)[:500], last_checked=now)
        return {"changed": False, "error": str(e)}


async def sync_due_sources(*, prices: bool, parse_prices: bool) -> list[dict]:
    """Run the daily check for every auto-synced source of one kind.

    prices=True — sources that feed price files; False — RAG-only sources.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GoogleDriveProject).where(GoogleDriveProject.auto_sync.is_(True))
        )
        projects = result.scalars().all()
    ids = [p.id for p in projects if feeds_prices(p.purpose) == prices]
    results = []
    for project_id in ids:
        results.append(
            {"id": project_id, **await sync_project(project_id, parse_prices=parse_prices)}
        )
    return results


async def pull_price_sources() -> list[dict]:
    """Deliver fresh price files from Drive; called right before the nightly parse."""
    return await sync_due_sources(prices=True, parse_prices=False)


async def drive_rag_daily_sync() -> None:
    """Daily check of RAG-only Drive sources at 23:15 UTC.

    Price sources are checked by `procurement-supplier-sync` itself, right
    before it parses — a separate schedule could deliver files after the parse.
    """
    await asyncio.sleep(300)
    while True:
        now = datetime.utcnow()
        target = now.replace(hour=23, minute=15, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        try:
            results = await sync_due_sources(prices=False, parse_prices=False)
            changed = sum(1 for r in results if r.get("changed"))
            logger.info("Drive RAG daily sync: %d sources, %d changed", len(results), changed)
        except Exception as e:
            logger.warning("Drive RAG daily sync error: %s", e)
            await asyncio.sleep(3600)
