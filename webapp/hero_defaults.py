from __future__ import annotations

from collections.abc import Callable


DEFAULT_HERO_NAME = "Spectre"


def default_hero_id(hero_ids: list[int], resolve_hero_name: Callable[[int], str]) -> int:
    return next(
        (hero_id for hero_id in hero_ids if resolve_hero_name(hero_id) == DEFAULT_HERO_NAME),
        hero_ids[0],
    )
