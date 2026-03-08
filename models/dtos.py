from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class Intent(str, Enum):
    STATS = "stats"
    ITEMS = "items"
    MATCHES = "matches"


@dataclass(slots=True)
class QueryFilters:
    player_id: int
    hero_id: int | None = None
    hero_name: str | None = None
    game_mode: int | None = None
    game_mode_name: str | None = None
    days: int | None = None
    limit: int = 20


@dataclass(slots=True)
class ParsedAskQuery:
    intent: Intent
    filters: QueryFilters


@dataclass(slots=True)
class MatchSummary:
    match_id: int
    start_time: int
    player_slot: int
    radiant_win: bool
    kills: int
    deaths: int
    assists: int
    duration: int
    hero_id: int | None
    item_0: int = 0
    item_1: int = 0
    item_2: int = 0
    item_3: int = 0
    item_4: int = 0
    item_5: int = 0

    @property
    def did_win(self) -> bool:
        is_radiant = self.player_slot < 128
        return (is_radiant and self.radiant_win) or (not is_radiant and not self.radiant_win)

    @property
    def side(self) -> str:
        return "Radiant" if self.player_slot < 128 else "Dire"


@dataclass(slots=True)
class StatsResult:
    matches: int
    wins: int
    losses: int
    winrate: float
    avg_kills: float
    avg_deaths: float
    avg_assists: float
    kda_ratio: float
    radiant_wr: float
    dire_wr: float


@dataclass(slots=True)
class ItemStat:
    item_id: int
    item_name: str
    count: int
    match_pct: float


@dataclass(slots=True)
class ItemsResult:
    total_matches: int
    final_inventory_items: list[ItemStat]
    purchased_items: list[ItemStat]
    purchased_based_on_logs: bool
    note: str


@dataclass(slots=True)
class MatchRow:
    match_id: int
    started_at: datetime
    result: str
    kda: str
    duration: str
    items: list[str]


JSONDict = dict[str, Any]
