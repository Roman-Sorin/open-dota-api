from __future__ import annotations

import importlib
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_service():
    config_module = importlib.import_module("utils.config")
    cache_module = importlib.import_module("utils.cache")
    exceptions_module = importlib.import_module("utils.exceptions")
    client_module = importlib.import_module("clients.opendota_client")
    stratz_client_module = importlib.import_module("clients.stratz_client")
    match_store_module = importlib.import_module("utils.match_store")
    analytics_module = importlib.import_module("services.analytics_service")

    config_module = importlib.reload(config_module)
    cache_module = importlib.reload(cache_module)
    exceptions_module = importlib.reload(exceptions_module)
    client_module = importlib.reload(client_module)
    stratz_client_module = importlib.reload(stratz_client_module)
    match_store_module = importlib.reload(match_store_module)
    analytics_module = importlib.reload(analytics_module)

    settings = config_module.get_settings()
    client = client_module.OpenDotaClient(
        base_url=settings.base_url,
        timeout_seconds=settings.timeout_seconds,
        api_key=settings.api_key,
    )
    stratz_client = None
    if settings.stratz_token:
        stratz_client = stratz_client_module.StratzClient(
            token=settings.stratz_token,
            base_url=settings.stratz_base_url,
            timeout_seconds=settings.timeout_seconds,
        )
    cache = cache_module.JsonFileCache(
        cache_dir=config_module.get_cache_dir(),
        ttl_hours=settings.cache_ttl_hours,
    )
    match_store = match_store_module.SQLiteMatchStore(config_module.get_match_store_path())
    return analytics_module.DotaAnalyticsService(
        client=client,
        cache=cache,
        match_store=match_store,
        stratz_client=stratz_client,
    )


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
