from __future__ import annotations

import importlib

from utils.config import Settings, get_match_store_path
from utils.match_store import MatchStoreProtocol, SQLiteMatchStore

_LAST_STORE_WARNING: str | None = None


def build_match_store(settings: Settings) -> MatchStoreProtocol:
    global _LAST_STORE_WARNING
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
