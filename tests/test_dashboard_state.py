from datetime import date

from webapp.dashboard_state import build_filter_request_key, build_hero_request_key


def test_filter_request_key_normalizes_patch_order() -> None:
    key_a = build_filter_request_key(
        player_id=123,
        days=None,
        active_patches=["7.40c", "7.40"],
        active_start_date=date(2026, 3, 1),
    )
    key_b = build_filter_request_key(
        player_id=123,
        days=None,
        active_patches=["7.40", "7.40c"],
        active_start_date=date(2026, 3, 1),
    )

    assert key_a == key_b


def test_hero_request_key_changes_with_hero_and_filters() -> None:
    base_key = build_hero_request_key(
        player_id=123,
        hero_id=1,
        days=30,
        active_patches=[],
        active_start_date=None,
    )

    different_hero_key = build_hero_request_key(
        player_id=123,
        hero_id=2,
        days=30,
        active_patches=[],
        active_start_date=None,
    )
    different_filter_key = build_hero_request_key(
        player_id=123,
        hero_id=1,
        days=60,
        active_patches=[],
        active_start_date=None,
    )

    assert base_key != different_hero_key
    assert base_key != different_filter_key
