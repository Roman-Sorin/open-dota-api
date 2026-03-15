from __future__ import annotations

from models.dtos import QueryFilters
from services.analytics_service import DotaAnalyticsService
from utils.match_store import SQLiteMatchStore


def test_match_store_persists_summary_and_details() -> None:
    store = SQLiteMatchStore(":memory:")
    store.upsert_player_matches(
        123,
        [
            {
                "match_id": 1,
                "start_time": 100,
                "player_slot": 0,
                "radiant_win": True,
                "kills": 5,
                "deaths": 2,
                "assists": 9,
                "duration": 1800,
                "hero_id": 1,
                "game_mode": 23,
                "hero_damage": 12345,
                "net_worth": 22222,
                "item_0": 1,
                "item_1": 2,
                "item_2": 3,
                "item_3": 4,
                "item_4": 5,
                "item_5": 6,
            }
        ],
    )

    rows = store.query_player_matches(123, hero_id=1, game_mode=23)

    assert len(rows) == 1
    assert rows[0]["match_id"] == 1
    assert rows[0]["hero_damage"] == 12345

    assert store.get_match_ids_without_details(123, game_mode=23) == [1]

    store.upsert_match_detail(1, {"match_id": 1, "players": [{"account_id": 123, "last_hits": 250}]})
    assert store.get_match_ids_without_details(123, game_mode=23) == []
    assert store.get_match_detail(1) == {"match_id": 1, "players": [{"account_id": 123, "last_hits": 250}]}


class _FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    def get_constants_heroes(self) -> dict:
        return {"1": {"id": 1, "localized_name": "Axe", "img": "/apps/dota2/images/heroes/axe.png"}}

    def get_constants_items(self) -> dict:
        return {}

    def get_constants_patch(self) -> list[dict]:
        return [{"name": "7.40", "date": "2025-01-01T00:00:00Z"}]

    def get_player_profile(self, account_id: int) -> dict:
        return {"profile": {"account_id": account_id}}

    def get_player_matches(self, **kwargs):
        self.calls += 1
        return [
            {
                "match_id": 1,
                "start_time": 1738540800,
                "player_slot": 0,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 5,
                "deaths": 2,
                "assists": 9,
                "duration": 1800,
                "hero_id": 1,
            }
        ]


class _FakeCache:
    def __init__(self) -> None:
        self._store: dict[str, object] = {}

    def get(self, key: str, max_age=None):
        return self._store.get(key)

    def set(self, key: str, value: object) -> None:
        self._store[key] = value


def test_service_fetch_matches_uses_sqlite_store_between_calls() -> None:
    client = _FakeClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)

    filters = QueryFilters(player_id=123, game_mode=23, game_mode_name="Turbo")
    first = service.fetch_matches(filters)
    second = service.fetch_matches(filters)

    assert len(first) == 1
    assert len(second) == 1
    assert client.calls == 1
