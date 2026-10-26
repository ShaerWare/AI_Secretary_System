"""Price files delivered from a Google Drive source into SUPPLIER_PRICES_DIR.

A delivery replaces files supplier by supplier: an old file goes to
`_archive/<timestamp>/` when a delivered file takes its place — same name, or
the same supplier pattern (a new «axima.xlsx» retires «аксима-7.xlsx»). The
parser takes the newest file per pattern, so a stale list left beside the new
one could still win if dates are off. Files of suppliers the delivery does not
cover stay: the shared Drive folder holds four suppliers out of seven, and
wiping the rest would cost SunWell its 20 000-row dealer list with nothing to
replace it. Files this source delivered earlier and no longer has are retired
too. Files written by another Drive source are never touched. Archive, not
delete: a bad delivery is undone by moving the files back.

`supplier_report` tells the admin which file every supplier got. A file whose
name matches no pattern is silently ignored by the parser, and the supplier
keeps last week's offers — the report is the only place that shows it.
"""

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from modules.procurement.suppliers.parser import matches_pattern
from modules.procurement.suppliers.registry import SUPPLIER_PRICES_DIR, SUPPLIERS


logger = logging.getLogger(__name__)

ARCHIVE_DIR = "_archive"


def _mtime(modified_time: str | None) -> float | None:
    if not modified_time:
        return None
    try:
        return datetime.fromisoformat(modified_time.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _patterns() -> list:
    """Every (supplier, price/stock) file pattern."""
    return [cfg[f] for cfg in SUPPLIERS for f in ("price_file", "stock_file") if cfg.get(f)]


def _retired(name: str, incoming: set[str], previously_owned: set[str]) -> bool:
    """Does the delivery make this existing file obsolete?"""
    if name in incoming or name in previously_owned:
        return True
    return any(
        matches_pattern(name, pattern) and any(matches_pattern(n, pattern) for n in incoming)
        for pattern in _patterns()
    )


def install_price_files(
    files: list[tuple[str, bytes, str | None]],
    keep: set[str],
    previously_owned: set[str] | None = None,
) -> dict:
    """Install `files` = [(name, data, drive_modifiedTime)], retiring what they replace.

    `keep` — names owned by other Drive sources, never archived or overwritten.
    `previously_owned` — names this source delivered last time.
    Returns {"installed": [...], "archived": [...], "conflicts": [...]}.
    """
    base = Path(SUPPLIER_PRICES_DIR)
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive = base / ARCHIVE_DIR / stamp
    incoming = {name for name, _data, _mod in files if name not in keep}

    archived: list[str] = []
    for path in sorted(base.iterdir()):
        if not path.is_file() or path.name.startswith(".") or path.name in keep:
            continue
        if not _retired(path.name, incoming, previously_owned or set()):
            continue
        archive.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(archive / path.name))
        archived.append(path.name)

    installed: list[str] = []
    conflicts: list[str] = []
    for name, data, modified in files:
        if name in keep:
            conflicts.append(name)
            continue
        target = base / name
        tmp = base / f".{name}.part"
        tmp.write_bytes(data)
        tmp.replace(target)
        ts = _mtime(modified)
        if ts:
            os.utime(target, (ts, ts))
        installed.append(name)

    logger.info(
        "price files: installed %d, archived %d to %s", len(installed), len(archived), archive
    )
    return {"installed": installed, "archived": archived, "conflicts": conflicts}


def supplier_report(filenames: list[str]) -> dict:
    """Which file each supplier will be parsed from, and which files nobody reads."""
    used: dict[str, int] = {}
    suppliers = []
    for cfg in SUPPLIERS:
        entry = {"key": cfg["key"], "name": cfg["name"]}
        for field in ("price_file", "stock_file"):
            pattern = cfg.get(field)
            if not pattern:
                continue
            hits = sorted(n for n in filenames if matches_pattern(n, pattern))
            for n in hits:
                used[n] = used.get(n, 0) + 1
            entry[field] = {"pattern": pattern, "files": hits}
        suppliers.append(entry)
    unmatched = sorted(n for n in filenames if n not in used)
    # One file read as two suppliers' data — a pattern is too broad
    ambiguous = sorted(n for n, count in used.items() if count > 1)
    return {"suppliers": suppliers, "unmatched": unmatched, "ambiguous": ambiguous}
