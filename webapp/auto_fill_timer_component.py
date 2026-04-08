from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit.components.v1 as components


_COMPONENT_DIR = Path(__file__).resolve().parent / "components" / "auto_fill_timer"
_auto_fill_timer = components.declare_component("auto_fill_timer", path=str(_COMPONENT_DIR))


def render_auto_fill_timer(
    *,
    enabled: bool,
    delay_seconds: int,
    next_phase: str,
    cycle_token: str,
    key: str,
) -> dict[str, Any] | None:
    value = _auto_fill_timer(
        enabled=enabled,
        delay_seconds=int(delay_seconds),
        next_phase=str(next_phase),
        cycle_token=str(cycle_token),
        key=key,
        default=None,
    )
    return value if isinstance(value, dict) else None
