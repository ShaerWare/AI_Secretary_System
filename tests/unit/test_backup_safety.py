"""Tests for backup safety: WAL checkpoint, sales DBs, sidecars, restore cleanup."""

import json
import sqlite3
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.backup_service import BackupService


@pytest.fixture()
def backup_env(tmp_path):
    """Create a temporary backup environment with data/ and backups/ dirs."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    backups_dir = tmp_path / "backups"
    backups_dir.mkdir()

    # Create main DB with some data (WAL mode)
    main_db = data_dir / "secretary.db"
    conn = sqlite3.connect(str(main_db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO test VALUES (1)")
    conn.commit()
    conn.close()

    # Create a sales DB
    sales_db = data_dir / "sales.db"
    conn = sqlite3.connect(str(sales_db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO users VALUES (42)")
    conn.commit()
    conn.close()

    # Create a WA sales DB
    wa_sales_db = data_dir / "wa_sales_1.db"
    conn = sqlite3.connect(str(wa_sales_db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE users (user_id TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO users VALUES ('phone123')")
    conn.commit()
    conn.close()

    service = BackupService()
    service.data_dir = data_dir
    service.db_path = main_db
    service.backups_dir = backups_dir

    return service, tmp_path, data_dir


def test_checkpoint_wal_clears_wal_file(backup_env):
    """_checkpoint_wal() should flush WAL data into the main DB file."""
    service, _, data_dir = backup_env
    main_db = data_dir / "secretary.db"

    # Write data without closing — leaves data in WAL
    conn = sqlite3.connect(str(main_db))
    conn.execute("INSERT INTO test VALUES (2)")
    conn.commit()
    conn.close()

    wal_file = data_dir / "secretary.db-wal"
    # WAL file might exist with data
    service._checkpoint_wal(main_db)

    # After TRUNCATE checkpoint, WAL file should be empty or absent
    if wal_file.exists():
        assert wal_file.stat().st_size == 0


def test_checkpoint_wal_nonexistent_db(backup_env):
    """_checkpoint_wal() on non-existent path should not raise."""
    service, _, _ = backup_env
    service._checkpoint_wal(Path("/nonexistent/db.sqlite"))


def test_backup_includes_sales_dbs(backup_env):
    """Backup ZIP should contain main DB + all sales DBs from data/."""
    service, _, _ = backup_env

    with patch("app.services.backup_service.BASE_DIR", service.data_dir.parent):
        result = service.create_backup(description="test")

    backup_path = Path(result["path"])
    with zipfile.ZipFile(backup_path) as zf:
        names = zf.namelist()
        assert "data/secretary.db" in names
        assert "data/sales.db" in names
        assert "data/wa_sales_1.db" in names
        assert "manifest.json" in names


def test_backup_includes_wal_sidecars(backup_env):
    """Non-empty WAL/SHM sidecars should be included in backup."""
    service, _, data_dir = backup_env

    # Create a non-empty WAL sidecar for sales.db
    wal_sidecar = data_dir / "sales.db-wal"
    wal_sidecar.write_bytes(b"fake wal data")

    # Skip checkpoint so the fake sidecar survives
    with (
        patch("app.services.backup_service.BASE_DIR", service.data_dir.parent),
        patch.object(service, "_checkpoint_wal"),
    ):
        result = service.create_backup()

    with zipfile.ZipFile(Path(result["path"])) as zf:
        names = zf.namelist()
        assert "data/sales.db-wal" in names


def test_backup_skips_empty_sidecars(backup_env):
    """Empty WAL/SHM sidecars should NOT be included in backup."""
    service, _, data_dir = backup_env

    # Create an empty WAL sidecar
    wal_sidecar = data_dir / "sales.db-wal"
    wal_sidecar.write_bytes(b"")

    with patch("app.services.backup_service.BASE_DIR", service.data_dir.parent):
        result = service.create_backup()

    with zipfile.ZipFile(Path(result["path"])) as zf:
        names = zf.namelist()
        assert "data/sales.db-wal" not in names


def test_manifest_version_1_1(backup_env):
    """Manifest should have version 1.1."""
    service, _, _ = backup_env

    with patch("app.services.backup_service.BASE_DIR", service.data_dir.parent):
        result = service.create_backup()

    assert result["manifest"]["version"] == "1.1"

    with zipfile.ZipFile(Path(result["path"])) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["version"] == "1.1"


def test_restore_cleans_stale_wal(backup_env):
    """Restore should remove stale WAL/SHM files before extracting."""
    service, _, data_dir = backup_env

    # Create backup first
    with patch("app.services.backup_service.BASE_DIR", service.data_dir.parent):
        result = service.create_backup()

    # Simulate stale WAL/SHM files on disk
    stale_wal = data_dir / "secretary.db-wal"
    stale_shm = data_dir / "secretary.db-shm"
    stale_wal.write_bytes(b"stale wal data")
    stale_shm.write_bytes(b"stale shm data")

    # Restore
    with patch("app.services.backup_service.BASE_DIR", service.data_dir.parent):
        restore_result = service.restore_backup(result["filename"])

    assert restore_result["success"] is True
    # Stale files should be removed (checkpoint after backup made them empty)
    if stale_wal.exists():
        assert stale_wal.stat().st_size == 0
    if stale_shm.exists():
        assert stale_shm.stat().st_size == 0


def test_restore_handles_sales_dbs(backup_env):
    """Restore should extract sales DBs from backup."""
    service, _, data_dir = backup_env

    with patch("app.services.backup_service.BASE_DIR", service.data_dir.parent):
        result = service.create_backup()

    # Remove sales DBs to simulate fresh restore
    (data_dir / "sales.db").unlink()
    (data_dir / "wa_sales_1.db").unlink()

    with patch("app.services.backup_service.BASE_DIR", service.data_dir.parent):
        restore_result = service.restore_backup(result["filename"])

    assert restore_result["success"] is True
    assert "data/sales.db" in restore_result["restored_files"]
    assert "data/wa_sales_1.db" in restore_result["restored_files"]

    # Verify restored DBs are valid
    conn = sqlite3.connect(str(data_dir / "sales.db"))
    row = conn.execute("SELECT user_id FROM users").fetchone()
    assert row[0] == 42
    conn.close()


def test_restore_creates_bak_files(backup_env):
    """Restore should create .bak copies of existing DBs."""
    service, _, data_dir = backup_env

    with patch("app.services.backup_service.BASE_DIR", service.data_dir.parent):
        result = service.create_backup()

    with patch("app.services.backup_service.BASE_DIR", service.data_dir.parent):
        service.restore_backup(result["filename"])

    assert (data_dir / "secretary.db.bak").exists()
    assert (data_dir / "sales.db.bak").exists()


def test_get_system_info_includes_sales_dbs(backup_env):
    """get_system_info() should report sales databases."""
    service, _, _ = backup_env
    info = service.get_system_info()

    assert "sales_databases" in info
    names = [db["name"] for db in info["sales_databases"]]
    assert "sales.db" in names
    assert "wa_sales_1.db" in names
