from __future__ import annotations

from datetime import date


def build_filter_request_key(
    player_id: int,
    days: int | None,
    active_patches: list[str] | None,
    active_start_date: date | None,
) -> tuple[object, ...]:
    normalized_patches = tuple(sorted(str(patch) for patch in (active_patches or [])))
    return (
        int(player_id),
        days,
        active_start_date.isoformat() if active_start_date else None,
        normalized_patches,
    )


def build_hero_request_key(
    player_id: int,
    hero_id: int,
    days: int | None,
    active_patches: list[str] | None,
    active_start_date: date | None,
) -> tuple[object, ...]:
    return (
        *build_filter_request_key(
            player_id=player_id,
            days=days,
            active_patches=active_patches,
            active_start_date=active_start_date,
        ),
        int(hero_id),
    )


def build_hero_snapshot_request_key(
    player_id: int,
    hero_id: int,
    days: int | None,
    active_patches: list[str] | None,
    active_start_date: date | None,
    dashboard_loaded_at: str | None,
) -> tuple[object, ...]:
    return (
        *build_hero_request_key(
            player_id=player_id,
            hero_id=hero_id,
            days=days,
            active_patches=active_patches,
            active_start_date=active_start_date,
        ),
        dashboard_loaded_at or "no-dashboard-snapshot",
    )
