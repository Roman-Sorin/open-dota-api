from __future__ import annotations

from models.dtos import QueryFilters
from services.analytics_service import DotaAnalyticsService
from utils.match_store import SQLiteMatchStore


class _FakeCache:
    def __init__(self) -> None:
        self._store: dict[str, object] = {}

    def get(self, key: str, max_age=None):
        return self._store.get(key)

    def set(self, key: str, value: object) -> None:
        self._store[key] = value


class _FakeClient:
    def get_constants_heroes(self) -> dict:
        return {"44": {"id": 44, "localized_name": "Phantom Assassin", "img": "/apps/dota2/images/heroes/phantom_assassin.png"}}

    def get_constants_items(self) -> dict:
        return {
            "power_treads": {"id": 63, "dname": "Power Treads", "img": "/apps/dota2/images/items/power_treads.png"},
            "monkey_king_bar": {"id": 135, "dname": "Monkey King Bar", "img": "/apps/dota2/images/items/monkey_king_bar.png"},
            "black_king_bar": {"id": 116, "dname": "Black King Bar", "img": "/apps/dota2/images/items/black_king_bar.png"},
            "abyssal_blade": {"id": 149, "dname": "Abyssal Blade", "img": "/apps/dota2/images/items/abyssal_blade.png"},
            "desolator": {"id": 168, "dname": "Desolator", "img": "/apps/dota2/images/items/desolator.png"},
        }

    def get_constants_patch(self) -> list[dict]:
        return [{"name": "7.41", "date": "2026-01-01T00:00:00Z"}]

    def get_match_details(self, match_id: int) -> dict:
        return {
            "match_id": match_id,
            "version": None,
            "players": [
                {
                    "account_id": 1233793238,
                    "player_slot": 0,
                    "item_0": 63,
                    "item_1": 135,
                    "item_2": 116,
                    "item_3": 149,
                    "item_4": 168,
                    "item_5": 0,
                }
            ],
        }


class _FakeStratzClient:
    def __init__(self) -> None:
        self.requested_match_ids: list[int] = []

    def get_match_item_purchases(self, match_id: int) -> list[dict]:
        self.requested_match_ids.append(match_id)
        return [
            {
                "steamAccountId": 1233793238,
                "playerSlot": 0,
                "stats": {
                    "itemPurchases": [
                        {"itemId": 63, "time": 240},
                        {"itemId": 135, "time": 600},
                        {"itemId": 116, "time": 780},
                        {"itemId": 149, "time": 1140},
                        {"itemId": 168, "time": 1140},
                    ]
                },
            }
        ]


def test_reported_match_8622417925_recovers_timings_from_stratz_after_open_dota_missing_them() -> None:
    service = DotaAnalyticsService(
        client=_FakeClient(),
        cache=_FakeCache(),
        match_store=SQLiteMatchStore(":memory:"),
        stratz_client=_FakeStratzClient(),
    )

    details = service.get_or_fetch_match_details(8622417925, force_refresh=True)
    player_row = service._extract_player_from_match_details(details, player_id=1233793238, player_slot=0)  # noqa: SLF001

    assert player_row is not None
    assert service._player_row_has_timing_data(player_row)  # noqa: SLF001
    assert player_row["first_purchase_time"]["monkey_king_bar"] == 600
    assert player_row["purchase_log"][1] == {"key": "monkey_king_bar", "time": 600}


def test_background_sync_coverage_counts_reported_match_as_ready_after_stratz_backfill() -> None:
    store = SQLiteMatchStore(":memory:")
    store.upsert_player_matches(
        1233793238,
        [
            {
                "match_id": 8622417925,
                "start_time": 1765000000,
                "player_slot": 0,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 5,
                "deaths": 1,
                "assists": 11,
                "duration": 1221,
                "hero_id": 44,
                "item_0": 63,
                "item_1": 135,
                "item_2": 116,
                "item_3": 149,
                "item_4": 168,
                "item_5": 0,
            }
        ],
    )
    store.upsert_match_detail(
        8622417925,
        {
            "match_id": 8622417925,
            "version": None,
            "players": [
                {
                    "account_id": 1233793238,
                    "player_slot": 0,
                    "item_0": 63,
                    "item_1": 135,
                    "item_2": 116,
                    "item_3": 149,
                    "item_4": 168,
                    "item_5": 0,
                }
            ],
        },
    )

    service = DotaAnalyticsService(
        client=_FakeClient(),
        cache=_FakeCache(),
        match_store=store,
        stratz_client=_FakeStratzClient(),
    )

    matches = service.get_cached_matches(
        QueryFilters(player_id=1233793238, game_mode=23, game_mode_name="Turbo")
    )
    completed = service.backfill_item_timing_details_from_stratz(
        player_id=1233793238,
        matches=matches,
        batch_size=1,
    )
    coverage = service.get_background_sync_coverage(player_id=1233793238, game_mode=23, window_days=365)

    assert completed == 1
    assert coverage.timing_ready_count == 1
    assert coverage.missing_timing_count == 0
