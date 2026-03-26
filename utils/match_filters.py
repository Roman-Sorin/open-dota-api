from __future__ import annotations


EXCLUDED_MATCH_IDS = {
    8743652071,
}


def is_excluded_match_id(match_id: int) -> bool:
    return int(match_id) in EXCLUDED_MATCH_IDS
