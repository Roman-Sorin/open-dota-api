from __future__ import annotations

from utils.helpers import format_duration


HERO_MATCHES_COLUMN = "All"
HERO_WINS_COLUMN = "Won"
HERO_LOSSES_COLUMN = "Lost"
HERO_OVERVIEW_COLUMN_ORDER = [
    "Icon",
    "Hero",
    HERO_MATCHES_COLUMN,
    HERO_WINS_COLUMN,
    HERO_LOSSES_COLUMN,
    "WR",
    "Avg K/D/A",
    "KDA",
    "Dur",
    "NW",
    "Dmg",
    "Max K",
    "Max Dmg",
    "Rad WR",
    "Dire WR",
]


def _format_avg_kda(row: dict[str, object]) -> str:
    return (
        f"{round(float(row.get('avg_kills', 0.0)))}/"
        f"{round(float(row.get('avg_deaths', 0.0)))}/"
        f"{round(float(row.get('avg_assists', 0.0)))}"
    )


def _format_one_decimal(value: object) -> str:
    return f"{float(value or 0.0):.1f}"


def build_hero_overview_row(row: dict[str, object]) -> dict[str, object]:
    return {
        "Icon": row.get("hero_image", ""),
        "Hero": row["hero"],
        HERO_MATCHES_COLUMN: int(row.get("matches", 0)),
        HERO_WINS_COLUMN: int(row.get("wins", 0)),
        HERO_LOSSES_COLUMN: int(row.get("losses", 0)),
        "WR": f"{round(float(row.get('winrate', 0.0)))}%",
        "Avg K/D/A": _format_avg_kda(row),
        "KDA": _format_one_decimal(row.get("kda", 0.0)),
        "Dur": format_duration(int(round(float(row.get("avg_duration_seconds", 0.0))))),
        "NW": round(float(row.get("avg_net_worth", 0.0))),
        "Dmg": round(float(row.get("avg_damage", 0.0))),
        "Max K": int(row.get("max_kills", 0)),
        "Max Dmg": int(row.get("max_hero_damage", 0)),
        "Rad WR": f"{round(float(row.get('radiant_wr', 0.0)))}%",
        "Dire WR": f"{round(float(row.get('dire_wr', 0.0)))}%",
    }
