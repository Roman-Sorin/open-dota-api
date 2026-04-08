from __future__ import annotations

import importlib

from utils.config import Settings, get_match_store_path
from utils.match_store import MatchStoreProtocol, SQLiteMatchStore

_LAST_STORE_WARNING: str | None = None


def build_match_store(settings: Settings) -> MatchStoreProtocol:
    global _LAST_STORE_WARNING
    if settings.google_drive_service_account_json and settings.google_drive_folder_id:
        try:
            drive_module = importlib.import_module("utils.google_drive_snapshot")
            drive_module = importlib.reload(drive_module)
            db_path = get_match_store_path()
            manager = drive_module.GoogleDriveSnapshotManager(
                service_account_json=settings.google_drive_service_account_json,
                folder_id=settings.google_drive_folder_id,
                snapshot_name=settings.google_drive_snapshot_name or "matches.sqlite3",
                local_db_path=db_path,
                min_upload_interval_seconds=settings.google_drive_min_upload_interval_seconds,
            )
            if not db_path.exists():
                manager.restore_if_available()
            _LAST_STORE_WARNING = None
            return SQLiteMatchStore(
                db_path,
                commit_hook=manager.sync_if_due,
                close_hook=manager.sync_if_due,
            )
        except Exception as exc:  # noqa: BLE001
            _LAST_STORE_WARNING = (
                "Failed to connect to Google Drive snapshot storage; app is using local SQLite only for now. "
                f"Original error: {exc.__class__.__name__}: {exc}"
            )
            return SQLiteMatchStore(get_match_store_path())
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
    return SQLiteMatchStore(get_match_store_path())


def get_last_store_warning() -> str | None:
    return _LAST_STORE_WARNING
