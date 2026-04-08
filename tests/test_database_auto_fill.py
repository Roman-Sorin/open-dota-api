from __future__ import annotations

from webapp.database_auto_fill import next_auto_phase, normalize_auto_phase


def test_normalize_auto_phase_defaults_to_display() -> None:
    assert normalize_auto_phase(None) == "display"
    assert normalize_auto_phase("unexpected") == "display"
    assert normalize_auto_phase("run") == "run"


def test_next_auto_phase_toggles_between_display_and_run() -> None:
    assert next_auto_phase("display") == "run"
    assert next_auto_phase("run") == "display"
