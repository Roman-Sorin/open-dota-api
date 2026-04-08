from __future__ import annotations

def normalize_auto_phase(value: str | None) -> str:
    return "run" if value == "run" else "display"


def next_auto_phase(current_phase: str) -> str:
    return "run" if normalize_auto_phase(current_phase) != "run" else "display"
