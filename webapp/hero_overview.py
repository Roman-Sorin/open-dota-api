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
HERO_DETAIL_METRIC_ORDER = [
    "Matches",
    "Won Matches",
    "Lost Matches",
    "Winrate",
    "Avg K/D/A",
    "KDA",
    "Avg Duration",
    "Avg Net Worth",
    "Avg Damage",
    "Max Kills",
    "Max Damage",
    "Radiant WR",
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


def _format_percent(value: object) -> str:
    return f"{round(float(value or 0.0))}%"


HERO_SHARED_METRICS: list[tuple[str, str, callable]] = [
    (HERO_MATCHES_COLUMN, "Matches", lambda row: int(row.get("matches", 0))),
    (HERO_WINS_COLUMN, "Won Matches", lambda row: int(row.get("wins", 0))),
    (HERO_LOSSES_COLUMN, "Lost Matches", lambda row: int(row.get("losses", 0))),
    ("WR", "Winrate", lambda row: _format_percent(row.get("winrate", 0.0))),
    ("Avg K/D/A", "Avg K/D/A", _format_avg_kda),
    ("KDA", "KDA", lambda row: _format_one_decimal(row.get("kda", 0.0))),
    ("Dur", "Avg Duration", lambda row: format_duration(int(round(float(row.get("avg_duration_seconds", 0.0)))))),
    ("NW", "Avg Net Worth", lambda row: round(float(row.get("avg_net_worth", 0.0)))),
    ("Dmg", "Avg Damage", lambda row: round(float(row.get("avg_damage", 0.0)))),
    ("Max K", "Max Kills", lambda row: int(row.get("max_kills", 0))),
    ("Max Dmg", "Max Damage", lambda row: int(row.get("max_hero_damage", 0))),
    ("Rad WR", "Radiant WR", lambda row: _format_percent(row.get("radiant_wr", 0.0))),
    ("Dire WR", "Dire WR", lambda row: _format_percent(row.get("dire_wr", 0.0))),
]


def build_hero_overview_row(row: dict[str, object]) -> dict[str, object]:
    overview_row = {
        "Icon": row.get("hero_image", ""),
        "Hero": row["hero"],
    }
    for column_label, _, value_builder in HERO_SHARED_METRICS:
        overview_row[column_label] = value_builder(row)
    return overview_row


def build_hero_detail_cards(row: dict[str, object]) -> list[tuple[str, str]]:
    return [(card_label, str(value_builder(row))) for _, card_label, value_builder in HERO_SHARED_METRICS]
