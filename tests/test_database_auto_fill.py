from __future__ import annotations

from webapp.database_auto_fill import AUTO_PHASE_QUERY_PARAM, build_auto_reload_script, next_auto_phase, normalize_auto_phase


def test_normalize_auto_phase_defaults_to_display() -> None:
    assert normalize_auto_phase(None) == "display"
    assert normalize_auto_phase("unexpected") == "display"
    assert normalize_auto_phase("run") == "run"


def test_next_auto_phase_toggles_between_display_and_run() -> None:
    assert next_auto_phase("display") == "run"
    assert next_auto_phase("run") == "display"


def test_build_auto_reload_script_preserves_query_param_name_and_next_phase() -> None:
    script = build_auto_reload_script(delay_seconds=15, next_phase_value="run")

    assert AUTO_PHASE_QUERY_PARAM in script
    assert "nextPhase = 'run'" in script
    assert "15000" in script
