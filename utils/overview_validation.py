from __future__ import annotations


def overview_looks_stale(overview: object) -> bool:
    if not isinstance(overview, list) or not overview:
        return False

    has_avg_damage_key = any(isinstance(row, dict) and "avg_damage" in row for row in overview)
    has_avg_net_worth_key = any(isinstance(row, dict) and "avg_net_worth" in row for row in overview)
    if not has_avg_damage_key or not has_avg_net_worth_key:
        return True

    positive_damage_rows = 0
    multi_match_rows = 0
    for row in overview:
        if not isinstance(row, dict):
            continue
        matches = int(row.get("matches") or 0)
        avg_damage = float(row.get("avg_damage") or 0.0)
        avg_net_worth = float(row.get("avg_net_worth") or 0.0)
        max_hero_damage = int(row.get("max_hero_damage") or 0)
        if matches > 1:
            multi_match_rows += 1
        if avg_damage > 0:
            positive_damage_rows += 1

        if matches >= 3 and avg_damage <= 0 and avg_net_worth <= 0 and max_hero_damage <= 0:
            return True

    return multi_match_rows > 0 and positive_damage_rows == 0
