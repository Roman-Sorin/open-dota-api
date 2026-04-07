from __future__ import annotations

import os
import subprocess
from pathlib import Path

from clients.opendota_client import OpenDotaClient
from services.analytics_service import DotaAnalyticsService
from utils.cache import JsonFileCache
from utils.config import get_cache_dir, get_match_store_path, get_settings
from utils.match_store import SQLiteMatchStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_service() -> DotaAnalyticsService:
    settings = get_settings()
    client = OpenDotaClient(
        base_url=settings.base_url,
        timeout_seconds=settings.timeout_seconds,
        api_key=settings.api_key,
    )
    cache = JsonFileCache(cache_dir=get_cache_dir(), ttl_hours=settings.cache_ttl_hours)
    match_store = SQLiteMatchStore(get_match_store_path())
    return DotaAnalyticsService(client=client, cache=cache, match_store=match_store)


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
