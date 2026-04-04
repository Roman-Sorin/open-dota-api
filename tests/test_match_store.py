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
    assert store.get_latest_player_match_update(123, game_mode=23) is not None


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

    def get_match_details(self, match_id: int) -> dict:
        return {"match_id": match_id, "players": []}


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


def test_service_can_build_cached_turbo_hero_overview_without_api_calls() -> None:
    client = _FakeClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)

    store.upsert_player_matches(
        123,
        [
                {
                    "match_id": 10,
                    "start_time": 1771552800,
                    "player_slot": 0,
                    "radiant_win": True,
                    "game_mode": 23,
                "kills": 9,
                "deaths": 3,
                "assists": 12,
                "duration": 1500,
                "hero_id": 1,
                "hero_damage": 24000,
                "net_worth": 21000,
            }
        ],
    )
    store.upsert_sync_state(123, "gm:23", last_incremental_sync_at="2026-03-15T10:00:00", known_match_count=1)

    rows = service.get_cached_turbo_hero_overview(player_id=123, days=60)

    assert len(rows) == 1
    assert rows[0]["hero"] == "Axe"
    assert rows[0]["radiant_wr"] == 100.0
    assert rows[0]["dire_wr"] == 0.0
    assert client.calls == 0


def test_cached_turbo_hero_overview_enriches_missing_viper_economy_and_damage_from_cached_details() -> None:
    client = _FakeClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)

    store.upsert_player_matches(
        123,
        [
            {
                "match_id": 100,
                "start_time": 1771552800,
                "player_slot": 0,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 8,
                "deaths": 6,
                "assists": 8,
                "duration": 1380,
                "hero_id": 47,
                "hero_damage": 0,
                "net_worth": 0,
            },
            {
                "match_id": 101,
                "start_time": 1771466400,
                "player_slot": 0,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 7,
                "deaths": 5,
                "assists": 9,
                "duration": 1380,
                "hero_id": 47,
                "hero_damage": 0,
                "net_worth": 0,
            },
            {
                "match_id": 102,
                "start_time": 1771380000,
                "player_slot": 0,
                "radiant_win": False,
                "game_mode": 23,
                "kills": 10,
                "deaths": 7,
                "assists": 6,
                "duration": 1380,
                "hero_id": 47,
                "hero_damage": 0,
                "net_worth": 0,
            },
            {
                "match_id": 103,
                "start_time": 1771293600,
                "player_slot": 128,
                "radiant_win": False,
                "game_mode": 23,
                "kills": 9,
                "deaths": 8,
                "assists": 7,
                "duration": 1380,
                "hero_id": 47,
                "hero_damage": 0,
                "net_worth": 0,
            },
            {
                "match_id": 104,
                "start_time": 1771207200,
                "player_slot": 128,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 6,
                "deaths": 5,
                "assists": 10,
                "duration": 1380,
                "hero_id": 47,
                "hero_damage": 0,
                "net_worth": 0,
            },
            {
                "match_id": 105,
                "start_time": 1771120800,
                "player_slot": 128,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 8,
                "deaths": 7,
                "assists": 7,
                "duration": 1380,
                "hero_id": 47,
                "hero_damage": 0,
                "net_worth": 0,
            },
        ],
    )

    for match_id, net_worth, hero_damage in (
        (100, 25000, 24000),
        (101, 26000, 26000),
        (102, 25500, 22000),
        (103, 27000, 18000),
        (104, 28000, 14000),
        (105, 26616, 0),
    ):
        store.upsert_match_detail(
            match_id,
            {
                "match_id": match_id,
                "players": [
                    {
                        "account_id": 123,
                        "player_slot": 0 if match_id <= 102 else 128,
                        "net_worth": net_worth,
                        "hero_damage": hero_damage,
                    }
                ],
            },
        )

    rows = service.get_cached_turbo_hero_overview(player_id=123, days=60)

    assert len(rows) == 1
    assert rows[0]["matches"] == 6
    assert rows[0]["wins"] == 3
    assert rows[0]["losses"] == 3
    assert rows[0]["winrate"] == 50.0
    assert rows[0]["avg_net_worth"] == 26352.666666666668
    assert rows[0]["avg_damage"] == 20800.0
    assert rows[0]["max_hero_damage"] == 26000
    assert client.calls == 0


def test_cached_sync_state_exposes_latest_match_update_timestamp() -> None:
    client = _FakeClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)

    store.upsert_player_matches(
        123,
        [
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
        ],
    )

    state = service.get_cached_sync_state(123, game_mode=23)

    assert state is not None
    assert state["known_match_count"] == 1
    assert state["latest_match_update_at"]


def test_force_sync_checks_only_new_matches_even_when_incremental_interval_has_not_elapsed() -> None:
    class _IncrementalClient(_FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.pages = [
                [
                    {
                        "match_id": 2,
                        "start_time": 1738541800,
                        "player_slot": 0,
                        "radiant_win": True,
                        "game_mode": 23,
                        "kills": 6,
                        "deaths": 2,
                        "assists": 10,
                        "duration": 1800,
                        "hero_id": 1,
                    },
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
                    },
                ],
                [
                    {
                        "match_id": 3,
                        "start_time": 1738542800,
                        "player_slot": 0,
                        "radiant_win": False,
                        "game_mode": 23,
                        "kills": 4,
                        "deaths": 5,
                        "assists": 11,
                        "duration": 1800,
                        "hero_id": 1,
                    },
                    {
                        "match_id": 2,
                        "start_time": 1738541800,
                        "player_slot": 0,
                        "radiant_win": True,
                        "game_mode": 23,
                        "kills": 6,
                        "deaths": 2,
                        "assists": 10,
                        "duration": 1800,
                        "hero_id": 1,
                    },
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
                    },
                ],
            ]

        def get_player_matches(self, **kwargs):
            self.calls += 1
            return self.pages.pop(0) if self.pages else []

    client = _IncrementalClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)
    filters = QueryFilters(player_id=123, game_mode=23, game_mode_name="Turbo")

    first = service.fetch_matches(filters, force_sync=True)
    second = service.fetch_matches(filters)
    third = service.fetch_matches(filters, force_sync=True)

    assert [match.match_id for match in first] == [2, 1]
    assert [match.match_id for match in second] == [2, 1]
    assert [match.match_id for match in third] == [3, 2, 1]
    assert client.calls == 2
    assert store.count_player_matches(123, game_mode=23) == 3


def test_refresh_cached_matches_hydrates_details_once_and_reuses_them() -> None:
    class _DetailHydrationClient(_FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.detail_calls = 0

        def get_player_matches(self, **kwargs):
            self.calls += 1
            return [
                {
                    "match_id": 10,
                    "start_time": 1771552800,
                    "player_slot": 0,
                    "radiant_win": True,
                    "game_mode": 23,
                    "kills": 8,
                    "deaths": 6,
                    "assists": 8,
                    "duration": 1380,
                    "hero_id": 47,
                    "hero_damage": 0,
                    "net_worth": 0,
                    "item_0": 0,
                    "item_1": 0,
                    "item_2": 0,
                    "item_3": 0,
                    "item_4": 0,
                    "item_5": 0,
                }
            ]

        def get_match_details(self, match_id: int) -> dict:
            self.detail_calls += 1
            return {
                "match_id": match_id,
                "players": [
                    {
                        "account_id": 123,
                        "player_slot": 0,
                        "net_worth": 25555,
                        "hero_damage": 22222,
                        "item_0": 1,
                        "purchase_log": [{"key": "blink", "time": 600}],
                    }
                ],
            }

    client = _DetailHydrationClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)
    service.references.item_ids_by_key["blink"] = 1
    service.references.item_names_by_id[1] = "Blink Dagger"

    filters = QueryFilters(player_id=123, game_mode=23, game_mode_name="Turbo")
    first = service.refresh_cached_matches(filters, hydrate_details=True)
    second = service.refresh_cached_matches(filters, hydrate_details=True)

    service.enrich_hero_damage(123, second, allow_detail_fetch=False)
    recent = service.build_recent_hero_matches(123, second, limit=5, allow_detail_fetch=False)
    item_rows = service.get_item_winrates(123, second, top_n=10, allow_detail_fetch=False)

    assert [match.match_id for match in first] == [10]
    assert [match.match_id for match in second] == [10]
    assert client.calls == 2
    assert client.detail_calls == 1
    assert second[0].net_worth_known is True
    assert second[0].hero_damage_known is True
    assert second[0].net_worth == 25555
    assert second[0].hero_damage == 22222
    assert recent[0].net_worth == 25555
    assert recent[0].hero_damage == 22222
    assert item_rows[0]["item"] == "Blink Dagger"


def test_turbo_overview_snapshot_reports_incomplete_detail_coverage_for_zero_rows() -> None:
    client = _FakeClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)

    store.upsert_player_matches(
        123,
        [
            {
                "match_id": 200,
                "start_time": 1771552800,
                "player_slot": 0,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 8,
                "deaths": 6,
                "assists": 8,
                "duration": 1380,
                "hero_id": 47,
                "hero_damage": 0,
                "net_worth": 0,
            },
            {
                "match_id": 201,
                "start_time": 1771466400,
                "player_slot": 0,
                "radiant_win": False,
                "game_mode": 23,
                "kills": 7,
                "deaths": 5,
                "assists": 9,
                "duration": 1380,
                "hero_id": 47,
                "hero_damage": 0,
                "net_worth": 0,
            },
            {
                "match_id": 202,
                "start_time": 1771380000,
                "player_slot": 128,
                "radiant_win": False,
                "game_mode": 23,
                "kills": 10,
                "deaths": 7,
                "assists": 6,
                "duration": 1380,
                "hero_id": 47,
                "hero_damage": 0,
                "net_worth": 0,
            },
        ],
    )
    store.upsert_sync_state(123, "gm:23", last_incremental_sync_at="2026-03-15T10:00:00", known_match_count=3)

    snapshot = service.get_turbo_overview_snapshot(player_id=123, days=150, force_sync=False, hydrate_details=False)

    assert snapshot.detail_status.requested == 3
    assert snapshot.detail_status.remaining == 3
    assert snapshot.is_valid is False
    assert snapshot.overview[0]["hero"] == "Hero #47"
    assert snapshot.overview[0]["avg_net_worth"] == 0.0
    assert snapshot.overview[0]["avg_damage"] == 0.0
    assert snapshot.overview[0]["max_hero_damage"] == 0


def test_refresh_cached_matches_rehydrates_legacy_details_without_purchase_log_for_recent_item_timings() -> None:
    class _LegacyDetailRefreshClient(_FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.detail_calls = 0

        def get_player_matches(self, **kwargs):
            self.calls += 1
            return [
                {
                    "match_id": 725001,
                    "start_time": 1771552800,
                    "player_slot": 0,
                    "radiant_win": True,
                    "game_mode": 23,
                    "kills": 3,
                    "deaths": 1,
                    "assists": 14,
                    "duration": 1276,
                    "hero_id": 1,
                    "item_0": 2001,
                    "item_1": 2002,
                    "item_2": 2003,
                    "item_3": 2004,
                    "item_4": 2005,
                    "item_5": 0,
                }
            ]

        def get_match_details(self, match_id: int) -> dict:
            self.detail_calls += 1
            return {
                "match_id": match_id,
                "players": [
                    {
                        "account_id": 123,
                        "player_slot": 0,
                        "level": 25,
                        "hero_variant": 0,
                        "net_worth": 25500,
                        "hero_damage": 17200,
                        "item_0": 2001,
                        "item_1": 2002,
                        "item_2": 2003,
                        "item_3": 2004,
                        "item_4": 2005,
                        "item_5": 0,
                        "purchase_log": [
                            {"key": "phylactery", "time": 480},
                            {"key": "orchid", "time": 720},
                            {"key": "manta", "time": 900},
                            {"key": "aegis", "time": 1020},
                            {"key": "skadi", "time": 1200},
                        ],
                    }
                ],
            }

    client = _LegacyDetailRefreshClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)
    service.references.item_ids_by_key.update(
        {
            "phylactery": 2001,
            "orchid": 2002,
            "manta": 2003,
            "aegis": 2004,
            "skadi": 2005,
        }
    )
    service.references.item_names_by_id.update(
        {
            2001: "Phylactery",
            2002: "Orchid Malevolence",
            2003: "Manta Style",
            2004: "Aegis of the Immortal",
            2005: "Eye of Skadi",
        }
    )

    store.upsert_match_detail(
        725001,
        {
            "match_id": 725001,
            "players": [
                {
                    "account_id": 123,
                    "player_slot": 0,
                    "level": 25,
                    "hero_variant": 0,
                    "net_worth": 25500,
                    "hero_damage": 17200,
                    "item_0": 2001,
                    "item_1": 2002,
                    "item_2": 2003,
                    "item_3": 2004,
                    "item_4": 2005,
                    "item_5": 0,
                }
            ],
        },
    )

    filters = QueryFilters(player_id=123, game_mode=23, game_mode_name="Turbo")
    matches = service.refresh_cached_matches(filters, hydrate_details=True)
    recent = service.build_recent_hero_matches(123, matches, limit=5, allow_detail_fetch=False)

    assert client.detail_calls == 1
    assert [item.item_name for item in recent[0].items] == [
        "Phylactery",
        "Orchid Malevolence",
        "Manta Style",
        "Aegis of the Immortal",
        "Eye of Skadi",
    ]
    assert [item.purchase_time_min for item in recent[0].items] == [8, 12, 15, 17, 20]


def test_load_match_snapshot_rehydrates_cached_details_missing_purchase_log() -> None:
    class _SnapshotHydrationClient(_FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.detail_calls = 0

        def get_match_details(self, match_id: int) -> dict:
            self.detail_calls += 1
            return {
                "match_id": match_id,
                "players": [
                    {
                        "account_id": 123,
                        "player_slot": 0,
                        "item_0": 1,
                        "purchase_log": [{"key": "blink", "time": 600}],
                    }
                ],
            }

    client = _SnapshotHydrationClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)
    service.references.item_ids_by_key["blink"] = 1
    service.references.item_names_by_id[1] = "Blink Dagger"

    store.upsert_player_matches(
        123,
        [
            {
                "match_id": 99,
                "start_time": 1771552800,
                "player_slot": 0,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 8,
                "deaths": 6,
                "assists": 8,
                "duration": 1380,
                "hero_id": 1,
                "item_0": 1,
                "item_1": 0,
                "item_2": 0,
                "item_3": 0,
                "item_4": 0,
                "item_5": 0,
            }
        ],
    )
    store.upsert_match_detail(
        99,
        {
            "match_id": 99,
            "players": [
                {
                    "account_id": 123,
                    "player_slot": 0,
                    "item_0": 1,
                }
            ],
        },
    )

    filters = QueryFilters(player_id=123, game_mode=23, game_mode_name="Turbo")
    matches, status = service.load_match_snapshot(filters, force_sync=False, hydrate_details=True)
    recent = service.build_recent_hero_matches(123, matches, limit=5, allow_detail_fetch=False)

    assert status.requested == 1
    assert status.completed == 1
    assert status.remaining == 0
    assert client.detail_calls == 1
    assert [item.purchase_time_min for item in recent[0].items] == [10]
