import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    api_key: str | None
    base_url: str = "https://api.opendota.com/api"
    timeout_seconds: float = 20.0
    cache_ttl_hours: int = 24


load_dotenv()


def get_settings() -> Settings:
    return Settings(
        api_key=os.getenv("OPENDOTA_API_KEY"),
        timeout_seconds=float(os.getenv("OPENDOTA_TIMEOUT", "20")),
        cache_ttl_hours=int(os.getenv("CACHE_TTL_HOURS", "24")),
    )


def get_cache_dir() -> Path:
    return Path(".cache")
