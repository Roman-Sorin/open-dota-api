from __future__ import annotations

from utils.config import Settings, get_match_store_path
from utils.match_store import MatchStoreProtocol, SQLiteMatchStore
from utils.postgres_match_store import PostgresMatchStore

_LAST_STORE_WARNING: str | None = None


def build_match_store(settings: Settings) -> MatchStoreProtocol:
    global _LAST_STORE_WARNING
    if settings.database_url:
        try:
            _LAST_STORE_WARNING = None
            return PostgresMatchStore(settings.database_url)
        except Exception as exc:  # noqa: BLE001
            _LAST_STORE_WARNING = (
                "Failed to connect to DATABASE_URL; app is using local SQLite fallback for now. "
                f"Original error: {exc.__class__.__name__}"
            )
    else:
        _LAST_STORE_WARNING = None
    return SQLiteMatchStore(get_match_store_path())


def get_last_store_warning() -> str | None:
    return _LAST_STORE_WARNING
