from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REFERENCE_DATA_DIR = Path(__file__).resolve().parents[1] / "reference_data"


def load_bundled_reference_payload(name: str) -> Any | None:
    path = REFERENCE_DATA_DIR / name
    if not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
