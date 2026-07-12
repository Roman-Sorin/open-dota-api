from __future__ import annotations

import importlib
import json
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_service():
    config_module = importlib.import_module("utils.config")
    cache_module = importlib.import_module("utils.cache")
    exceptions_module = importlib.import_module("utils.exceptions")
    client_module = importlib.import_module("clients.opendota_client")
    match_store_module = importlib.import_module("utils.match_store")
    store_factory_module = importlib.import_module("utils.store_factory")
    analytics_module = importlib.import_module("services.analytics_service")

    config_module = importlib.reload(config_module)
    cache_module = importlib.reload(cache_module)
    exceptions_module = importlib.reload(exceptions_module)
    client_module = importlib.reload(client_module)
    match_store_module = importlib.reload(match_store_module)
    store_factory_module = importlib.reload(store_factory_module)
    analytics_module = importlib.reload(analytics_module)

    settings = config_module.get_settings()
    client = client_module.OpenDotaClient(
        base_url=settings.base_url,
        timeout_seconds=settings.timeout_seconds,
        api_key=settings.api_key,
    )
    cache = cache_module.JsonFileCache(
        cache_dir=config_module.get_cache_dir(),
        ttl_hours=settings.cache_ttl_hours,
    )
    match_store = store_factory_module.build_match_store(settings)
    return analytics_module.DotaAnalyticsService(
        client=client,
        cache=cache,
        match_store=match_store,
    )


def get_store_warning() -> str | None:
    store_factory_module = importlib.import_module("utils.store_factory")
    return store_factory_module.get_last_store_warning()


def get_google_drive_snapshot_status() -> dict[str, object]:
    config_module = importlib.import_module("utils.config")
    config_module = importlib.reload(config_module)
    settings = config_module.get_settings()
    db_path = config_module.get_match_store_path()
    meta_path = config_module.get_match_store_meta_path()

    meta: dict[str, object] = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            meta = {}

    return {
        "google_drive_configured": bool(settings.google_drive_service_account_json and settings.google_drive_folder_id),
        "database_url_configured": bool(settings.database_url),
        "snapshot_name": settings.google_drive_snapshot_name or "matches.sqlite3",
        "min_upload_interval_seconds": int(settings.google_drive_min_upload_interval_seconds),
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
        "db_size_bytes": db_path.stat().st_size if db_path.exists() else 0,
        "db_last_modified_at": db_path.stat().st_mtime if db_path.exists() else None,
        "meta_path": str(meta_path),
        "meta_exists": meta_path.exists(),
        "file_id": str(meta.get("file_id") or ""),
        "last_uploaded_at": str(meta.get("last_uploaded_at") or ""),
        "meta_snapshot_name": str(meta.get("snapshot_name") or ""),
    }


def get_app_version() -> str:
    env_candidates = (
        os.getenv("APP_VERSION"),
        os.getenv("GIT_COMMIT"),
        os.getenv("COMMIT_SHA"),
        os.getenv("VERCEL_GIT_COMMIT_SHA"),
        os.getenv("GITHUB_SHA"),
    )
    for candidate in env_candidates:
        if candidate:
            return candidate[:7]

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:  # noqa: BLE001
        return "unknown"

    version = result.stdout.strip()
    return version or "unknown"
