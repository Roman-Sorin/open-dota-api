import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    api_key: str | None
    stratz_token: str | None
    database_url: str | None
    base_url: str = "https://api.opendota.com/api"
    stratz_base_url: str = "https://api.stratz.com/graphql"
    timeout_seconds: float = 20.0
    cache_ttl_hours: int = 24


load_dotenv()


def get_settings() -> Settings:
    return Settings(
        api_key=os.getenv("OPENDOTA_API_KEY"),
        stratz_token=os.getenv("STRATZ_API_TOKEN"),
        database_url=os.getenv("DATABASE_URL"),
        stratz_base_url=os.getenv("STRATZ_BASE_URL", "https://api.stratz.com/graphql"),
        timeout_seconds=float(os.getenv("OPENDOTA_TIMEOUT", "20")),
        cache_ttl_hours=int(os.getenv("CACHE_TTL_HOURS", "24")),
    )


def get_cache_dir() -> Path:
    return Path(".cache")


def get_match_store_path() -> Path:
    return get_cache_dir() / "matches.sqlite3"


def is_persistent_match_store_configured() -> bool:
    return bool(os.getenv("DATABASE_URL"))
