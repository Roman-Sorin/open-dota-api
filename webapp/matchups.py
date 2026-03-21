from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from models.dtos import MatchSummary
from utils.helpers import calculate_kda_ratio, winrate_percent


@dataclass(slots=True)
class MatchupRow:
    hero_id: int
    hero: str
    hero_image: str
    matches: int
    wins: int
    losses: int
    winrate: float
    avg_kills: float
    avg_deaths: float
    avg_assists: float
    kda: float


def _finalize_rows(
    buckets: dict[int, dict[str, float]],
    resolve_hero_name,
    resolve_hero_image,
) -> list[MatchupRow]:
    rows: list[MatchupRow] = []
    for hero_id, bucket in buckets.items():
        matches = int(bucket["matches"])
        wins = int(bucket["wins"])
        losses = matches - wins
        avg_k = bucket["kills"] / matches if matches else 0.0
        avg_d = bucket["deaths"] / matches if matches else 0.0
        avg_a = bucket["assists"] / matches if matches else 0.0
        rows.append(
            MatchupRow(
                hero_id=hero_id,
                hero=resolve_hero_name(hero_id),
                hero_image=resolve_hero_image(hero_id),
                matches=matches,
                wins=wins,
                losses=losses,
                winrate=winrate_percent(wins, matches),
                avg_kills=avg_k,
                avg_deaths=avg_d,
                avg_assists=avg_a,
                kda=calculate_kda_ratio(avg_k, avg_d, avg_a),
            )
        )
    rows.sort(key=lambda row: (-row.matches, -row.winrate, row.hero))
    return rows


def build_matchup_rows(
    matches: list[MatchSummary],
    detail_lookup,
    extract_player,
    player_id: int,
    resolve_hero_name,
    resolve_hero_image,
) -> dict[str, list[MatchupRow]]:
    with_buckets: dict[int, dict[str, float]] = defaultdict(lambda: {"matches": 0.0, "wins": 0.0, "kills": 0.0, "deaths": 0.0, "assists": 0.0})
    against_buckets: dict[int, dict[str, float]] = defaultdict(lambda: {"matches": 0.0, "wins": 0.0, "kills": 0.0, "deaths": 0.0, "assists": 0.0})

    for match in matches:
        details = detail_lookup(match.match_id)
        players = details.get("players") if isinstance(details, dict) else None
        if not isinstance(players, list):
            continue

        player_row = extract_player(details, player_id=player_id, player_slot=match.player_slot)
        if not isinstance(player_row, dict):
            continue

        player_slot = int(player_row.get("player_slot") or match.player_slot)
        is_radiant = player_slot < 128

        for row in players:
            if not isinstance(row, dict):
                continue
            hero_id = int(row.get("hero_id") or 0)
            other_slot = int(row.get("player_slot") or -1)
            if hero_id <= 0 or other_slot < 0 or other_slot == player_slot:
                continue

            target = with_buckets if (other_slot < 128) == is_radiant else against_buckets
            bucket = target[hero_id]
            bucket["matches"] += 1
            if match.did_win:
                bucket["wins"] += 1
            bucket["kills"] += float(match.kills)
            bucket["deaths"] += float(match.deaths)
            bucket["assists"] += float(match.assists)

    return {
        "with": _finalize_rows(with_buckets, resolve_hero_name, resolve_hero_image),
        "against": _finalize_rows(against_buckets, resolve_hero_name, resolve_hero_image),
    }


def build_matchup_dataframe(rows: list[MatchupRow], min_matches: int) -> pd.DataFrame:
    filtered_rows = [row for row in rows if int(row.matches) >= min_matches]
    return pd.DataFrame(
        [
            {
                "Icon": row.hero_image,
                "Hero": row.hero,
                "Matches": row.matches,
                "Won": row.wins,
                "Lost": row.losses,
                "WR Value": float(row.winrate),
                "WR": f"{round(row.winrate)}%",
            }
            for row in filtered_rows
        ]
    )


def sort_matchup_dataframe(df: pd.DataFrame, *, best_first: bool) -> pd.DataFrame:
    if df.empty:
        return df

    sorted_df = df.sort_values(
        by=["WR Value", "Matches", "Hero"],
        ascending=[not best_first, False, True],
    ).head(8)
    return sorted_df.drop(columns=["WR Value"])


def build_matchup_summary_dataframe(
    df: pd.DataFrame,
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Icon", "Hero", "WR", "Won", "Lost", "Matches"])

    summary = df.copy()
    column_order = ["Icon", "Hero", "WR", "Won", "Lost", "Matches", "WR Value"]
    return summary[column_order]


def sort_matchup_summary_dataframe(summary_df: pd.DataFrame, *, best_first: bool) -> pd.DataFrame:
    if summary_df.empty:
        return summary_df

    sorted_df = summary_df.sort_values(
        by=["WR Value", "Matches", "Hero"],
        ascending=[not best_first, False, True],
    )
    return sorted_df.drop(columns=["WR Value"])


def build_matchup_styler(df: pd.DataFrame):
    styler = df.style
    if df.empty:
        return styler

    winrate_columns = [column for column in df.columns if column == "WR" or str(column).endswith("Win Rate")]
    if not winrate_columns:
        return styler

    return styler.map(
        _style_matchup_winrate_cell,
        subset=winrate_columns,
    )


def _style_matchup_winrate_cell(value: object) -> str:
    text = str(value).strip().replace("%", "")
    try:
        numeric_value = float(text)
    except ValueError:
        return ""
    if numeric_value > 50.0:
        color = "#23a55a"
    elif numeric_value < 50.0:
        color = "#d9534f"
    else:
        color = "#d4a017"
    return f"color: {color}; font-weight: 700;"
