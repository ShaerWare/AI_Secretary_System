"""Backup and restore service for system data."""

import hashlib
import json
import logging
import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


# Base paths
BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "data"
BACKUPS_DIR = BASE_DIR / "backups"
VOICES_DIR = BASE_DIR / "Анна"  # Default voice samples directory
ADAPTERS_DIR = BASE_DIR / "finetune" / "adapters"

# Ensure backups directory exists
BACKUPS_DIR.mkdir(exist_ok=True)


def _calculate_checksum(file_path: Path) -> str:
    """Calculate MD5 checksum of a file."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def _get_dir_size(path: Path) -> int:
    """Get total size of directory in bytes."""
    total = 0
    if path.exists():
        for entry in path.rglob("*"):
            if entry.is_file():
                total += entry.stat().st_size
    return total


class BackupService:
    """Service for creating and restoring system backups."""

    def __init__(self):
        self.backups_dir = BACKUPS_DIR
        self.data_dir = DATA_DIR
        self.db_path = DATA_DIR / "secretary.db"

    def _checkpoint_wal(self, db_path: Path) -> None:
        """Force WAL checkpoint so .db file contains all committed data."""
        if not db_path.exists():
            return
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
        except Exception as e:
            logger.warning("WAL checkpoint failed for %s: %s", db_path, e)

    def _backup_db_file(
        self, zf: zipfile.ZipFile, db_path: Path, arcname: str, manifest: dict
    ) -> None:
        """Backup a database file with its WAL/SHM sidecars."""
        if not db_path.exists():
            return
        self._checkpoint_wal(db_path)
        zf.write(db_path, arcname)
        manifest["files"][arcname] = {
            "size": db_path.stat().st_size,
            "checksum": _calculate_checksum(db_path),
        }
        # Include WAL/SHM sidecars as safety net
        for ext in ("-wal", "-shm"):
            sidecar = db_path.parent / (db_path.name + ext)
            if sidecar.exists() and sidecar.stat().st_size > 0:
                sidecar_arcname = arcname + ext
                zf.write(sidecar, sidecar_arcname)
                manifest["files"][sidecar_arcname] = {
                    "size": sidecar.stat().st_size,
                    "checksum": _calculate_checksum(sidecar),
                }

    def create_backup(
        self,
        include_voices: bool = False,
        include_adapters: bool = False,
        description: str = "",
    ) -> dict:
        """
        Create a backup archive.

        Args:
            include_voices: Include voice sample files
            include_adapters: Include LoRA adapter files
            description: Optional description for the backup

        Returns:
            dict with backup info (filename, size, manifest)
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{timestamp}.zip"
        backup_path = self.backups_dir / backup_name

        manifest = {
            "version": "1.1",
            "created_at": datetime.utcnow().isoformat(),
            "description": description,
            "includes": {
                "database": True,
                "voices": include_voices,
                "adapters": include_adapters,
            },
            "files": {},
        }

        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Always include main database (with WAL checkpoint + sidecars)
            self._backup_db_file(zf, self.db_path, "data/secretary.db", manifest)

            # Discover and backup sales databases
            for sales_db in sorted(self.data_dir.glob("*sales*.db")):
                arcname = f"data/{sales_db.name}"
                if arcname not in manifest["files"]:
                    self._backup_db_file(zf, sales_db, arcname, manifest)

            # Include voice samples if requested
            if include_voices and VOICES_DIR.exists():
                for voice_dir in [VOICES_DIR, BASE_DIR / "Марина"]:
                    if voice_dir.exists():
                        for file in voice_dir.rglob("*"):
                            if file.is_file() and file.suffix.lower() in (
                                ".wav",
                                ".mp3",
                                ".ogg",
                            ):
                                arcname = f"voices/{voice_dir.name}/{file.name}"
                                zf.write(file, arcname)
                                manifest["files"][arcname] = {
                                    "size": file.stat().st_size,
                                    "checksum": _calculate_checksum(file),
                                }

            # Include LoRA adapters if requested
            if include_adapters and ADAPTERS_DIR.exists():
                for adapter_dir in ADAPTERS_DIR.iterdir():
                    if adapter_dir.is_dir():
                        for file in adapter_dir.rglob("*"):
                            if file.is_file():
                                arcname = (
                                    f"adapters/{adapter_dir.name}/{file.relative_to(adapter_dir)}"
                                )
                                zf.write(file, arcname)
                                manifest["files"][arcname] = {
                                    "size": file.stat().st_size,
                                    "checksum": _calculate_checksum(file),
                                }

            # Write manifest
            manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False)
            zf.writestr("manifest.json", manifest_json)

        return {
            "filename": backup_name,
            "path": str(backup_path),
            "size": backup_path.stat().st_size,
            "created_at": manifest["created_at"],
            "manifest": manifest,
        }

    def list_backups(self) -> list[dict]:
        """List all available backups with metadata."""
        backups = []

        for backup_file in sorted(self.backups_dir.glob("backup_*.zip"), reverse=True):
            try:
                with zipfile.ZipFile(backup_file, "r") as zf:
                    if "manifest.json" in zf.namelist():
                        manifest = json.loads(zf.read("manifest.json"))
                    else:
                        manifest = {"version": "unknown", "created_at": None}

                backups.append(
                    {
                        "filename": backup_file.name,
                        "size": backup_file.stat().st_size,
                        "created_at": manifest.get("created_at"),
                        "description": manifest.get("description", ""),
                        "includes": manifest.get(
                            "includes",
                            {"database": True, "voices": False, "adapters": False},
                        ),
                        "file_count": len(manifest.get("files", {})),
                    }
                )
            except (zipfile.BadZipFile, json.JSONDecodeError):
                # Skip corrupted backups
                backups.append(
                    {
                        "filename": backup_file.name,
                        "size": backup_file.stat().st_size,
                        "created_at": None,
                        "description": "Corrupted backup",
                        "includes": {},
                        "file_count": 0,
                        "corrupted": True,
                    }
                )

        return backups

    def get_backup_info(self, filename: str) -> Optional[dict]:
        """Get detailed info about a specific backup."""
        backup_path = self.backups_dir / filename

        if not backup_path.exists():
            return None

        try:
            with zipfile.ZipFile(backup_path, "r") as zf:
                if "manifest.json" in zf.namelist():
                    manifest = json.loads(zf.read("manifest.json"))
                else:
                    manifest = {}

                return {
                    "filename": filename,
                    "path": str(backup_path),
                    "size": backup_path.stat().st_size,
                    "manifest": manifest,
                    "files": zf.namelist(),
                }
        except zipfile.BadZipFile:
            return {"filename": filename, "corrupted": True}

    def validate_backup(self, filename: str) -> dict:
        """Validate backup integrity by checking checksums."""
        backup_path = self.backups_dir / filename

        if not backup_path.exists():
            return {"valid": False, "error": "Backup file not found"}

        try:
            with zipfile.ZipFile(backup_path, "r") as zf:
                if "manifest.json" not in zf.namelist():
                    return {"valid": False, "error": "Missing manifest.json"}

                manifest = json.loads(zf.read("manifest.json"))
                errors = []

                for arcname, info in manifest.get("files", {}).items():
                    if arcname not in zf.namelist():
                        errors.append(f"Missing file: {arcname}")
                        continue

                    # Verify checksum
                    data = zf.read(arcname)
                    actual_checksum = hashlib.md5(data).hexdigest()
                    if actual_checksum != info.get("checksum"):
                        errors.append(f"Checksum mismatch: {arcname}")

                return {
                    "valid": len(errors) == 0,
                    "errors": errors,
                    "files_checked": len(manifest.get("files", {})),
                }

        except zipfile.BadZipFile:
            return {"valid": False, "error": "Corrupted ZIP file"}
        except json.JSONDecodeError:
            return {"valid": False, "error": "Invalid manifest.json"}

    def restore_backup(
        self,
        filename: str,
        restore_database: bool = True,
        restore_voices: bool = False,
        restore_adapters: bool = False,
    ) -> dict:
        """
        Restore from a backup archive.

        Args:
            filename: Backup filename
            restore_database: Restore the SQLite database
            restore_voices: Restore voice sample files
            restore_adapters: Restore LoRA adapter files

        Returns:
            dict with restore status and details
        """
        backup_path = self.backups_dir / filename

        if not backup_path.exists():
            return {"success": False, "error": "Backup file not found"}

        # Validate first
        validation = self.validate_backup(filename)
        if not validation.get("valid"):
            return {
                "success": False,
                "error": f"Backup validation failed: {validation.get('error', validation.get('errors'))}",
            }

        restored_files = []

        try:
            with zipfile.ZipFile(backup_path, "r") as zf:
                manifest = json.loads(zf.read("manifest.json"))

                # Restore databases
                if restore_database:
                    self.data_dir.mkdir(exist_ok=True)

                    # Find all .db files in the archive
                    db_files = [
                        n for n in zf.namelist() if n.startswith("data/") and n.endswith(".db")
                    ]

                    for db_arcname in db_files:
                        db_target = BASE_DIR / db_arcname

                        # Create backup of current file
                        if db_target.exists():
                            shutil.copy2(db_target, db_target.with_suffix(".db.bak"))

                        # Remove stale WAL/SHM sidecars before extracting
                        for ext in ("-wal", "-shm"):
                            stale = db_target.parent / (db_target.name + ext)
                            if stale.exists():
                                stale.unlink()

                        # Extract database
                        zf.extract(db_arcname, BASE_DIR)
                        restored_files.append(db_arcname)

                        # Extract sidecars if present in archive
                        for ext in ("-wal", "-shm"):
                            sidecar_arcname = db_arcname + ext
                            if sidecar_arcname in zf.namelist():
                                zf.extract(sidecar_arcname, BASE_DIR)
                                restored_files.append(sidecar_arcname)

                # Restore voices
                if restore_voices:
                    for arcname in zf.namelist():
                        if arcname.startswith("voices/") and not arcname.endswith("/"):
                            target = BASE_DIR / arcname.replace("voices/", "", 1)
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(arcname) as src, open(target, "wb") as dst:
                                dst.write(src.read())
                            restored_files.append(arcname)

                # Restore adapters
                if restore_adapters:
                    for arcname in zf.namelist():
                        if arcname.startswith("adapters/") and not arcname.endswith("/"):
                            target = ADAPTERS_DIR / arcname.replace("adapters/", "", 1)
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(arcname) as src, open(target, "wb") as dst:
                                dst.write(src.read())
                            restored_files.append(arcname)

            return {
                "success": True,
                "restored_files": restored_files,
                "manifest": manifest,
            }

        except Exception as e:
            return {"success": False, "error": str(e), "restored_files": restored_files}

    def delete_backup(self, filename: str) -> dict:
        """Delete a backup file."""
        backup_path = self.backups_dir / filename

        if not backup_path.exists():
            return {"success": False, "error": "Backup file not found"}

        try:
            backup_path.unlink()
            return {"success": True, "deleted": filename}
        except OSError as e:
            return {"success": False, "error": str(e)}

    def get_backup_path(self, filename: str) -> Optional[Path]:
        """Get full path to backup file for download."""
        backup_path = self.backups_dir / filename
        if backup_path.exists() and backup_path.suffix == ".zip":
            return backup_path
        return None

    def get_system_info(self) -> dict:
        """Get current system info for backup planning."""
        db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
        voices_size = _get_dir_size(VOICES_DIR) + _get_dir_size(BASE_DIR / "Марина")
        adapters_size = _get_dir_size(ADAPTERS_DIR)
        backups_count = len(list(self.backups_dir.glob("backup_*.zip")))
        backups_size = sum(f.stat().st_size for f in self.backups_dir.glob("backup_*.zip"))

        # Discover sales databases
        sales_dbs = []
        for sales_db in sorted(self.data_dir.glob("*sales*.db")):
            sales_dbs.append(
                {
                    "path": str(sales_db),
                    "name": sales_db.name,
                    "size": sales_db.stat().st_size,
                }
            )

        return {
            "database": {
                "path": str(self.db_path),
                "size": db_size,
                "exists": self.db_path.exists(),
            },
            "sales_databases": sales_dbs,
            "voices": {
                "size": voices_size,
                "available": VOICES_DIR.exists() or (BASE_DIR / "Марина").exists(),
            },
            "adapters": {
                "path": str(ADAPTERS_DIR),
                "size": adapters_size,
                "available": ADAPTERS_DIR.exists(),
            },
            "backups": {
                "directory": str(self.backups_dir),
                "count": backups_count,
                "total_size": backups_size,
            },
        }


# Singleton instance
_backup_service: Optional[BackupService] = None


def get_backup_service() -> BackupService:
    """Get or create backup service singleton."""
    global _backup_service
    if _backup_service is None:
        _backup_service = BackupService()
    return _backup_service
