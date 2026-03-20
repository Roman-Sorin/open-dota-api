from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from models.dtos import MatchSummary, StatsResult


@dataclass(slots=True)
class HeroTrendPoint:
    label: str
    matches: int
    wins: int
    losses: int
    winrate: float
    kda: float
    avg_net_worth: float
    avg_damage: float
    avg_duration_minutes: float
    radiant_wr: float
    dire_wr: float


def _to_point(label: str, stats: StatsResult) -> HeroTrendPoint:
    return HeroTrendPoint(
        label=label,
        matches=stats.matches,
        wins=stats.wins,
        losses=stats.losses,
        winrate=stats.winrate,
        kda=stats.kda_ratio,
        avg_net_worth=stats.avg_net_worth,
        avg_damage=stats.avg_damage,
        avg_duration_minutes=stats.avg_duration_seconds / 60.0,
        radiant_wr=stats.radiant_wr,
        dire_wr=stats.dire_wr,
    )


def build_daily_trend_points(
    matches: list[MatchSummary],
    stats_builder: Callable[[list[MatchSummary]], StatsResult],
) -> list[HeroTrendPoint]:
    ordered_matches = sorted(matches, key=lambda match: match.start_time)
    grouped: OrderedDict[str, list[MatchSummary]] = OrderedDict()

    for match in ordered_matches:
        label = datetime.fromtimestamp(match.start_time, tz=UTC).date().isoformat()
        grouped.setdefault(label, []).append(match)

    return [_to_point(label, stats_builder(bucket)) for label, bucket in grouped.items()]
