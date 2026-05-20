from __future__ import annotations

import importlib
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from utils.config import Settings, get_match_store_path
from utils.match_store import MatchStoreProtocol, SQLiteMatchStore

_LAST_STORE_WARNING: str | None = None


def build_match_store(settings: Settings) -> MatchStoreProtocol:
    global _LAST_STORE_WARNING
    db_path = get_match_store_path()
    if settings.google_drive_service_account_json and settings.google_drive_folder_id:
        try:
            drive_module = importlib.import_module("utils.google_drive_snapshot")
            drive_module = importlib.reload(drive_module)
            manager = drive_module.GoogleDriveSnapshotManager(
                service_account_json=settings.google_drive_service_account_json,
                folder_id=settings.google_drive_folder_id,
                snapshot_name=settings.google_drive_snapshot_name or "matches.sqlite3",
                local_db_path=db_path,
                min_upload_interval_seconds=settings.google_drive_min_upload_interval_seconds,
            )
            if not db_path.exists():
                manager.restore_if_available()
            store, recovery_warning = _open_sqlite_store_with_recovery(
                db_path,
                commit_hook=manager.sync_if_due,
                close_hook=manager.sync_if_due,
                restore_callback=manager.restore_if_available,
            )
            _LAST_STORE_WARNING = recovery_warning
            return store
        except Exception as exc:  # noqa: BLE001
            _LAST_STORE_WARNING = (
                "Failed to connect to Google Drive snapshot storage; app is using local SQLite only for now. "
                f"Original error: {exc.__class__.__name__}: {exc}"
            )
            store, recovery_warning = _open_sqlite_store_with_recovery(db_path)
            if recovery_warning:
                _LAST_STORE_WARNING = f"{_LAST_STORE_WARNING} {recovery_warning}"
            return store
    if settings.database_url:
        try:
            postgres_module = importlib.import_module("utils.postgres_match_store")
            postgres_module = importlib.reload(postgres_module)
            _LAST_STORE_WARNING = None
            return postgres_module.PostgresMatchStore(settings.database_url)
        except Exception as exc:  # noqa: BLE001
            _LAST_STORE_WARNING = (
                "Failed to connect to DATABASE_URL; app is using local SQLite fallback for now. "
                f"Original error: {exc.__class__.__name__}: {exc}"
            )
    else:
        _LAST_STORE_WARNING = None
    store, recovery_warning = _open_sqlite_store_with_recovery(db_path)
    if recovery_warning:
        _LAST_STORE_WARNING = recovery_warning if _LAST_STORE_WARNING is None else f"{_LAST_STORE_WARNING} {recovery_warning}"
    return store


def _open_sqlite_store_with_recovery(
    db_path: Path,
    *,
    commit_hook=None,
    close_hook=None,
    restore_callback=None,
) -> tuple[MatchStoreProtocol, str | None]:
    try:
        return SQLiteMatchStore(db_path, commit_hook=commit_hook, close_hook=close_hook), None
    except sqlite3.DatabaseError as exc:
        quarantined_path = _quarantine_sqlite_file(db_path)
        restore_error: str | None = None
        restored = False
        if callable(restore_callback):
            try:
                restored = bool(restore_callback())
            except Exception as restore_exc:  # noqa: BLE001
                restore_error = f"{restore_exc.__class__.__name__}: {restore_exc}"

        try:
            store = SQLiteMatchStore(db_path, commit_hook=commit_hook, close_hook=close_hook)
        except sqlite3.DatabaseError:
            second_quarantine_path = _quarantine_sqlite_file(db_path)
            store = SQLiteMatchStore(db_path, commit_hook=commit_hook, close_hook=close_hook)
            warning = (
                "Detected a corrupted local SQLite cache and replaced it with a fresh empty cache. "
                f"Broken cache moved to `{second_quarantine_path.name}`. "
                f"Original error: {exc.__class__.__name__}: {exc}"
            )
            if restore_error:
                warning = f"{warning} Snapshot restore also failed: {restore_error}"
            return store, warning

        warning = (
            "Detected a corrupted local SQLite cache and recovered the app startup path. "
            f"Broken cache moved to `{quarantined_path.name}`. "
            f"Original error: {exc.__class__.__name__}: {exc}"
        )
        if restored:
            warning = f"{warning} Restored the latest persisted snapshot."
        elif restore_error:
            warning = f"{warning} Snapshot restore failed: {restore_error} Using a fresh local cache instead."
        else:
            warning = f"{warning} Using a fresh local cache instead."
        return store, warning


def _quarantine_sqlite_file(db_path: Path) -> Path:
    if not db_path.exists():
        return db_path.with_name(f"{db_path.stem}.missing{db_path.suffix}")
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    quarantined_path = db_path.with_name(f"{db_path.stem}.corrupt-{timestamp}{db_path.suffix}")
    db_path.replace(quarantined_path)
    return quarantined_path


def get_last_store_warning() -> str | None:
    return _LAST_STORE_WARNING
