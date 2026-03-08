from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any


class JsonFileCache:
    def __init__(self, cache_dir: Path, ttl_hours: int = 24) -> None:
        self.cache_dir = cache_dir
        self.ttl = timedelta(hours=ttl_hours)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = key.replace("/", "_")
        return self.cache_dir / f"{safe}.json"

    def get(self, key: str) -> Any | None:
        path = self._path(key)
        if not path.exists():
            return None

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            created = datetime.fromisoformat(raw["created_at"])
            if datetime.now(tz=timezone.utc) - created > self.ttl:
                return None
            return raw["payload"]
        except Exception:
            return None

    def set(self, key: str, payload: Any) -> None:
        path = self._path(key)
        body = {
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "payload": payload,
        }
        path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
