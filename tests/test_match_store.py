from __future__ import annotations

from datetime import datetime, timedelta, timezone

from clients.stratz_client import StratzRateLimitError
from models.dtos import QueryFilters
from services.analytics_service import DotaAnalyticsService
from utils.exceptions import OpenDotaRateLimitError
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


def test_match_parse_request_persists_source_and_reason() -> None:
    store = SQLiteMatchStore(":memory:")
    store.upsert_match_parse_request(
        77,
        123,
        status="pending",
        parse_job_id=9001,
        request_source="opendota",
        request_reason="stale_pending_retry",
        requested_at="2026-04-11T16:00:00+00:00",
    )

    row = store.get_match_parse_request(77)

    assert row is not None
    assert row["parse_job_id"] == 9001
    assert row["request_source"] == "opendota"
    assert row["request_reason"] == "stale_pending_retry"


def test_background_sync_run_persists_request_targets_and_data_sources() -> None:
    store = SQLiteMatchStore(":memory:")
    store.insert_background_sync_run(
        account_id=123,
        scope_key="gm:23",
        window_days=365,
        started_at="2026-04-11T20:00:00+00:00",
        finished_at="2026-04-11T20:00:05+00:00",
        status="completed",
        run_source="auto",
        summary_new_matches=1,
        total_matches_in_window=100,
        detail_requested=2,
        detail_completed=1,
        parse_requested=3,
        pending_parse_count=10,
        rate_limited=False,
        next_retry_at=None,
        request_targets="OpenDota, STRATZ",
        data_sources="STRATZ",
        note="Recovered timings.",
    )

    runs = store.list_background_sync_runs(123, "gm:23", 365, limit=1)

    assert runs[0]["request_targets"] == "OpenDota, STRATZ"
    assert runs[0]["data_sources"] == "STRATZ"


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


def test_sync_recent_matches_into_cache_reports_rate_limit_and_keeps_cached_snapshot_usable() -> None:
    class _RateLimitedSummaryClient(_FakeClient):
        def get_player_matches(self, **kwargs):
            raise OpenDotaRateLimitError("OpenDota API rate limit reached")

    client = _RateLimitedSummaryClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)

    store.upsert_player_matches(
        123,
        [
            {
                "match_id": 991,
                "start_time": 1771552800,
                "player_slot": 0,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 11,
                "deaths": 2,
                "assists": 15,
                "duration": 1500,
                "hero_id": 1,
                "hero_damage": 34567,
                "net_worth": 27890,
            }
        ],
    )
    store.upsert_sync_state(
        123,
        "gm:23",
        last_incremental_sync_at="2026-04-11T15:00:00+00:00",
        known_match_count=1,
    )

    filters = QueryFilters(player_id=123, game_mode=23, game_mode_name="Turbo", days=67)
    sync_result = service.sync_recent_matches_into_cache(filters, force=True)
    snapshot = service.get_turbo_overview_snapshot(player_id=123, days=67, force_sync=False, hydrate_details=False)

    assert sync_result.rate_limited is True
    assert sync_result.inserted_match_ids == []
    assert snapshot.overview
    assert snapshot.overview[0]["matches"] == 1
    assert snapshot.overview[0]["avg_net_worth"] == 27890.0
    assert snapshot.overview[0]["avg_damage"] == 34567.0


def test_repair_recent_match_item_timings_requests_parse_and_rebuilds_recent_rows() -> None:
    class _ParseRepairClient(_FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.parse_requested: set[int] = set()

        def get_match_details(self, match_id: int) -> dict:
            if match_id in self.parse_requested:
                return {
                    "match_id": match_id,
                    "version": 22,
                    "players": [
                        {
                            "account_id": 123,
                            "player_slot": 0,
                            "level": 25,
                            "item_0": 2001,
                            "item_1": 2002,
                            "item_2": 2003,
                            "item_3": 2004,
                            "item_4": 2005,
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
            return {
                "match_id": match_id,
                "version": None,
                "players": [
                    {
                        "account_id": 123,
                        "player_slot": 0,
                        "level": 25,
                        "item_0": 2001,
                        "item_1": 2002,
                        "item_2": 2003,
                        "item_3": 2004,
                        "item_4": 2005,
                    }
                ],
            }

        def request_match_parse(self, match_id: int) -> int | None:
            self.parse_requested.add(match_id)
            return 1

    client = _ParseRepairClient()
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
    matches = [
        service._parse_match_summary_row(  # noqa: SLF001
            {
                "match_id": 8757792129,
                "start_time": 1775326012,
                "player_slot": 0,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 3,
                "deaths": 1,
                "assists": 14,
                "duration": 1276,
                "hero_id": 67,
                "item_0": 2001,
                "item_1": 2002,
                "item_2": 2003,
                "item_3": 2004,
                "item_4": 2005,
                "item_5": 0,
            }
        )
    ]

    status = service.repair_recent_match_item_timings(
        player_id=123,
        matches=matches,
        limit=1,
        poll_timeout_seconds=1,
        poll_interval_seconds=1,
    )
    recent = service.build_recent_hero_matches(123, matches, limit=1, allow_detail_fetch=False)

    assert status.requested == 1
    assert status.submitted == 1
    assert status.completed == 1
    assert status.pending == 0
    assert [item.purchase_time_min for item in recent[0].items] == [8, 12, 15, 17, 20]


def test_load_match_snapshot_auto_backfills_missing_item_timings_for_unparsed_details() -> None:
    class _AutoParseTimingClient(_FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.parse_requested: set[int] = set()

        def get_match_details(self, match_id: int) -> dict:
            if match_id in self.parse_requested:
                return {
                    "match_id": match_id,
                    "version": 22,
                    "players": [
                        {
                            "account_id": 123,
                            "player_slot": 0,
                            "item_0": 2001,
                            "item_1": 2002,
                            "item_2": 0,
                            "item_3": 0,
                            "item_4": 0,
                            "item_5": 0,
                            "purchase_log": [
                                {"key": "phylactery", "time": 480},
                                {"key": "orchid", "time": 720},
                            ],
                        }
                    ],
                }
            return {
                "match_id": match_id,
                "version": None,
                "players": [
                    {
                        "account_id": 123,
                        "player_slot": 0,
                        "item_0": 2001,
                        "item_1": 2002,
                        "item_2": 0,
                        "item_3": 0,
                        "item_4": 0,
                        "item_5": 0,
                    }
                ],
            }

        def request_match_parse(self, match_id: int) -> int | None:
            self.parse_requested.add(match_id)
            return 1

    client = _AutoParseTimingClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)
    service.references.item_ids_by_key.update(
        {
            "phylactery": 2001,
            "orchid": 2002,
        }
    )
    service.references.item_names_by_id.update(
        {
            2001: "Phylactery",
            2002: "Orchid Malevolence",
        }
    )

    store.upsert_player_matches(
        123,
        [
            {
                "match_id": 800001,
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
                "item_2": 0,
                "item_3": 0,
                "item_4": 0,
                "item_5": 0,
            }
        ],
    )
    store.upsert_match_detail(
        800001,
        {
            "match_id": 800001,
            "version": None,
            "players": [
                {
                    "account_id": 123,
                    "player_slot": 0,
                    "item_0": 2001,
                    "item_1": 2002,
                    "item_2": 0,
                    "item_3": 0,
                    "item_4": 0,
                    "item_5": 0,
                }
            ],
        },
    )

    filters = QueryFilters(player_id=123, game_mode=23, game_mode_name="Turbo")
    matches, status = service.load_match_snapshot(filters, force_sync=False, hydrate_details=True)
    recent = service.build_recent_hero_matches(123, matches, limit=1, allow_detail_fetch=False)

    assert status.requested == 1
    assert 800001 in client.parse_requested
    assert [item.purchase_time_min for item in recent[0].items] == [8, 12]


def test_background_sync_coverage_reports_detail_and_timing_gaps() -> None:
    client = _FakeClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)
    service.references.item_ids_by_key.update({"blink": 1})
    service.references.item_names_by_id.update({1: "Blink Dagger"})

    store.upsert_player_matches(
        123,
        [
            {
                "match_id": 31,
                "start_time": 1771552800,
                "player_slot": 0,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 8,
                "deaths": 3,
                "assists": 11,
                "duration": 1400,
                "hero_id": 1,
                "item_0": 1,
            },
            {
                "match_id": 30,
                "start_time": 1771466400,
                "player_slot": 0,
                "radiant_win": False,
                "game_mode": 23,
                "kills": 4,
                "deaths": 6,
                "assists": 7,
                "duration": 1300,
                "hero_id": 1,
                "item_0": 1,
            },
            {
                "match_id": 29,
                "start_time": 1771380000,
                "player_slot": 0,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 9,
                "deaths": 2,
                "assists": 10,
                "duration": 1500,
                "hero_id": 1,
                "item_0": 1,
            },
        ],
    )
    store.upsert_match_detail(
        31,
        {
            "match_id": 31,
            "version": 22,
            "players": [
                {
                    "account_id": 123,
                    "player_slot": 0,
                    "item_0": 1,
                    "purchase_log": [{"key": "blink", "time": 600}],
                }
            ],
        },
    )
    store.upsert_match_detail(
        30,
        {
            "match_id": 30,
            "version": None,
            "players": [
                {
                    "account_id": 123,
                    "player_slot": 0,
                    "item_0": 1,
                }
            ],
        },
    )
    store.upsert_match_parse_request(30, 123, status="pending", requested_at="2026-04-07T10:00:00+00:00")

    coverage = service.get_background_sync_coverage(player_id=123, window_days=365)

    assert coverage.total_matches == 3
    assert coverage.detail_cached_count == 2
    assert coverage.timing_ready_count == 1
    assert coverage.missing_detail_count == 1
    assert coverage.missing_timing_count == 1
    assert coverage.pending_parse_count == 1
    assert coverage.newest_fully_cached_start_time == 1771552800
    assert coverage.oldest_fully_cached_start_time == 1771552800


def test_background_sync_cycle_updates_state_history_and_parse_queue() -> None:
    class _BackgroundClient(_FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.detail_calls = 0
            self.parse_requested: set[int] = set()

        def get_player_matches(self, **kwargs):
            self.calls += 1
            return [
                {
                    "match_id": 41,
                    "start_time": 1771552800,
                    "player_slot": 0,
                    "radiant_win": True,
                    "game_mode": 23,
                    "kills": 8,
                    "deaths": 3,
                    "assists": 11,
                    "duration": 1400,
                    "hero_id": 1,
                    "item_0": 1,
                },
                {
                    "match_id": 40,
                    "start_time": 1771466400,
                    "player_slot": 0,
                    "radiant_win": False,
                    "game_mode": 23,
                    "kills": 4,
                    "deaths": 6,
                    "assists": 7,
                    "duration": 1300,
                    "hero_id": 1,
                    "item_0": 1,
                },
            ]

        def get_match_details(self, match_id: int) -> dict:
            self.detail_calls += 1
            if match_id in self.parse_requested:
                return {
                    "match_id": match_id,
                    "version": 22,
                    "players": [
                        {
                            "account_id": 123,
                            "player_slot": 0,
                            "item_0": 1,
                            "purchase_log": [{"key": "blink", "time": 600}],
                        }
                    ],
                }
            if match_id == 41:
                return {
                    "match_id": 41,
                    "version": 22,
                    "players": [
                        {
                            "account_id": 123,
                            "player_slot": 0,
                            "item_0": 1,
                            "purchase_log": [{"key": "blink", "time": 600}],
                        }
                    ],
                }
            return {
                "match_id": 40,
                "version": None,
                "players": [
                    {
                        "account_id": 123,
                        "player_slot": 0,
                        "item_0": 1,
                    }
                ],
            }

        def request_match_parse(self, match_id: int) -> int | None:
            self.parse_requested.add(match_id)
            return 1

    client = _BackgroundClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)
    service.references.item_ids_by_key.update({"blink": 1})
    service.references.item_names_by_id.update({1: "Blink Dagger"})

    result = service.run_background_sync_cycle(
        player_id=123,
        window_days=365,
        max_detail_fetches=5,
        max_parse_requests=2,
        force=True,
    )

    state = service.get_background_sync_state(123, window_days=365)
    runs = service.list_background_sync_runs(123, window_days=365, limit=5)
    parse_request = store.get_match_parse_request(40)

    assert result.status == "completed"
    assert result.summary_new_matches == 2
    assert result.detail_completed == 2
    assert result.parse_requested == 1
    assert result.coverage.total_matches == 2
    assert state is not None
    assert state["target_match_count"] == 2
    assert state["detail_cached_count"] == 2
    assert state["pending_parse_count"] == 1
    assert int(state["total_runs"]) == 1
    assert len(runs) == 1
    assert runs[0]["parse_requested"] == 1
    assert runs[0]["run_source"] == "manual"
    assert parse_request is not None
    assert parse_request["status"] == "pending"


def test_background_sync_cycle_skips_summary_head_sync_when_recent_summary_snapshot_exists() -> None:
    class _SummaryRateLimitedClient(_FakeClient):
        def get_player_matches(self, **kwargs):
            raise OpenDotaRateLimitError("OpenDota API rate limit reached")

    client = _SummaryRateLimitedClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)

    store.upsert_player_matches(
        123,
        [
            {
                "match_id": 810001,
                "start_time": 1771552800,
                "player_slot": 0,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 8,
                "deaths": 3,
                "assists": 11,
                "duration": 1400,
                "hero_id": 1,
                "item_0": 1,
            }
        ],
    )
    store.upsert_sync_state(
        123,
        "gm:23",
        last_incremental_sync_at=datetime.now(tz=timezone.utc).isoformat(),
        known_match_count=1,
    )
    store.upsert_background_sync_state(
        123,
        "gm:23",
        365,
        last_summary_sync_at=datetime.now(tz=timezone.utc).isoformat(),
    )

    result = service.run_background_sync_cycle(
        player_id=123,
        window_days=365,
        max_detail_fetches=0,
        max_parse_requests=0,
        force=False,
    )

    assert result.status == "completed"
    assert result.rate_limited is False
    assert result.summary_new_matches == 0
    assert "Using cached summary snapshot; next OpenDota head sync is not due yet." in result.note


def test_background_sync_cycle_applies_stratz_retry_window_after_stratz_rate_limit() -> None:
    class _StratzRateLimitedClient(_FakeClient):
        def get_player_matches(self, **kwargs):
            raise AssertionError("summary sync should have been skipped while recent cache exists")

    class _RateLimitedStratzClient:
        def __init__(self) -> None:
            self.calls = 0

        def get_match_item_purchases(self, match_id: int):
            self.calls += 1
            raise StratzRateLimitError("STRATZ API rate limit reached")

    client = _StratzRateLimitedClient()
    stratz_client = _RateLimitedStratzClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store, stratz_client=stratz_client)

    store.upsert_player_matches(
        123,
        [
            {
                "match_id": 810101,
                "start_time": 1771552800,
                "player_slot": 0,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 8,
                "deaths": 3,
                "assists": 11,
                "duration": 1400,
                "hero_id": 1,
                "item_0": 1,
            }
        ],
    )
    store.upsert_match_detail(
        810101,
        {
            "match_id": 810101,
            "version": None,
            "players": [
                {
                    "account_id": 123,
                    "player_slot": 0,
                    "item_0": 1,
                }
            ],
        },
    )
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    store.upsert_sync_state(
        123,
        "gm:23",
        last_incremental_sync_at=now_iso,
        known_match_count=1,
    )
    store.upsert_background_sync_state(
        123,
        "gm:23",
        365,
        last_summary_sync_at=now_iso,
        next_pending_parse_check_at=(datetime.now(tz=timezone.utc) + timedelta(minutes=10)).isoformat(),
    )

    first = service.run_background_sync_cycle(
        player_id=123,
        window_days=365,
        max_detail_fetches=0,
        max_parse_requests=0,
        rate_limit_cooldown_seconds=50,
        force=False,
    )
    second = service.run_background_sync_cycle(
        player_id=123,
        window_days=365,
        max_detail_fetches=0,
        max_parse_requests=0,
        rate_limit_cooldown_seconds=50,
        force=False,
    )
    state = service.get_background_sync_state(123, window_days=365)

    assert "STRATZ rate limit was hit during timing recovery." in first.note
    assert "Waiting for the next STRATZ retry window." in second.note
    assert state is not None
    assert state["next_stratz_retry_at"] is not None
    assert stratz_client.calls == 1


def test_background_sync_cycle_skips_stratz_when_open_dota_rate_limits_same_cycle() -> None:
    class _OpenDotaRateLimitedClient(_FakeClient):
        def get_player_matches(self, **kwargs):
            raise OpenDotaRateLimitError("OpenDota API rate limit reached")

    class _TrackingStratzClient:
        def __init__(self) -> None:
            self.calls = 0

        def get_match_item_purchases(self, match_id: int):
            self.calls += 1
            return []

    client = _OpenDotaRateLimitedClient()
    stratz_client = _TrackingStratzClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store, stratz_client=stratz_client)

    result = service.run_background_sync_cycle(
        player_id=123,
        window_days=365,
        max_detail_fetches=0,
        max_parse_requests=0,
        force=True,
    )
    runs = service.list_background_sync_runs(123, window_days=365, limit=1)

    assert result.status == "rate_limited"
    assert result.rate_limited is True
    assert "OpenDota rate limit was hit during summary sync." in result.note
    assert "Skipping STRATZ timing recovery this cycle" not in result.note
    assert stratz_client.calls == 0
    assert runs[0]["request_targets"] == "OpenDota"


def test_background_sync_cycle_refreshes_oldest_pending_parse_requests_first() -> None:
    class _PendingRefreshClient(_FakeClient):
        def get_player_matches(self, **kwargs):
            self.calls += 1
            return [
                {
                    "match_id": 52,
                    "start_time": 1771552800,
                    "player_slot": 0,
                    "radiant_win": True,
                    "game_mode": 23,
                    "kills": 8,
                    "deaths": 3,
                    "assists": 11,
                    "duration": 1400,
                    "hero_id": 1,
                    "item_0": 1,
                },
                {
                    "match_id": 51,
                    "start_time": 1771466400,
                    "player_slot": 0,
                    "radiant_win": True,
                    "game_mode": 23,
                    "kills": 8,
                    "deaths": 3,
                    "assists": 11,
                    "duration": 1400,
                    "hero_id": 1,
                    "item_0": 1,
                },
            ]

        def get_match_details(self, match_id: int) -> dict:
            return {
                "match_id": match_id,
                "version": 22,
                "players": [
                    {
                        "account_id": 123,
                        "player_slot": 0,
                        "item_0": 1,
                        "purchase_log": [{"key": "blink", "time": 600}],
                    }
                ],
            }

        def get_parse_job_status(self, job_id: int) -> dict | None:
            return {"jobId": job_id, "status": "completed"}

    client = _PendingRefreshClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)
    service.references.item_ids_by_key["blink"] = 1
    service.references.item_names_by_id[1] = "Blink Dagger"

    store.upsert_player_matches(
        123,
        [
            {
                "match_id": 52,
                "start_time": 1771552800,
                "player_slot": 0,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 8,
                "deaths": 3,
                "assists": 11,
                "duration": 1400,
                "hero_id": 1,
                "item_0": 1,
            },
            {
                "match_id": 51,
                "start_time": 1771466400,
                "player_slot": 0,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 8,
                "deaths": 3,
                "assists": 11,
                "duration": 1400,
                "hero_id": 1,
                "item_0": 1,
            },
        ],
    )
    store.upsert_match_detail(
        52,
        {"match_id": 52, "version": None, "players": [{"account_id": 123, "player_slot": 0, "item_0": 1}]},
    )
    store.upsert_match_detail(
        51,
        {"match_id": 51, "version": None, "players": [{"account_id": 123, "player_slot": 0, "item_0": 1}]},
    )
    store.upsert_match_parse_request(51, 123, status="pending", parse_job_id=1001, requested_at="2026-04-07T10:00:00+00:00")
    store.upsert_match_parse_request(52, 123, status="pending", parse_job_id=1002, requested_at="2026-04-07T11:00:00+00:00")

    result = service.run_background_sync_cycle(
        player_id=123,
        window_days=365,
        max_detail_fetches=0,
        max_parse_requests=1,
        pending_parse_poll_after_seconds=0,
        force=True,
    )

    first = store.get_match_parse_request(51)
    second = store.get_match_parse_request(52)

    assert result.coverage.pending_parse_count == 0
    assert first is not None and first["status"] == "completed"
    assert second is not None and second["status"] == "completed"


def test_background_sync_cycle_retries_stale_pending_parse_backlog_with_reported_150_count() -> None:
    class _StalePendingClient(_FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.parse_requested: list[int] = []

        def get_player_matches(self, **kwargs):
            self.calls += 1
            base_start = 1771552800
            rows = [
                {
                    "match_id": 700000 + offset,
                    "start_time": base_start - (offset * 3600),
                    "player_slot": 0,
                    "radiant_win": True,
                    "game_mode": 23,
                    "kills": 8,
                    "deaths": 3,
                    "assists": 11,
                    "duration": 1400,
                    "hero_id": 1,
                    "item_0": 1,
                }
                for offset in range(150)
            ]
            offset = int(kwargs.get("offset") or 0)
            limit = int(kwargs.get("limit") or 100)
            return rows[offset : offset + limit]

        def get_match_details(self, match_id: int) -> dict:
            return {
                "match_id": match_id,
                "version": None,
                "players": [
                    {
                        "account_id": 123,
                        "player_slot": 0,
                        "item_0": 1,
                    }
                ],
            }

        def request_match_parse(self, match_id: int) -> int | None:
            self.parse_requested.append(match_id)
            return 1

    client = _StalePendingClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)

    now = datetime.now(tz=timezone.utc)
    matches = client.get_player_matches(limit=150, offset=0)
    store.upsert_player_matches(123, matches)
    for offset, match in enumerate(matches):
        match_id = int(match["match_id"])
        stale_requested_at = (now - timedelta(hours=3 + offset)).isoformat()
        stale_polled_at = (now - timedelta(hours=2 + offset)).isoformat()
        store.upsert_match_detail(
            match_id,
            {
                "match_id": match_id,
                "version": None,
                "players": [
                    {
                        "account_id": 123,
                        "player_slot": 0,
                        "item_0": 1,
                    }
                ],
            },
        )
        store.upsert_match_parse_request(
            match_id,
            123,
            status="pending",
            requested_at=stale_requested_at,
            last_polled_at=stale_polled_at,
        )

    result = service.run_background_sync_cycle(
        player_id=123,
        window_days=365,
        max_detail_fetches=0,
        max_parse_requests=5,
        pending_parse_retry_after_seconds=3600,
        force=True,
    )

    first_request = store.get_match_parse_request(700149)
    sixth_request = store.get_match_parse_request(700144)

    assert result.status == "completed"
    assert result.parse_requested == 5
    assert result.coverage.pending_parse_count == 150
    assert "Retried 5 stale replay parse job(s); 150 pending parse job(s) still remain." in result.note
    assert client.parse_requested == [700149, 700148, 700147, 700146, 700145]
    assert first_request is not None
    assert int(first_request["attempts"]) == 2
    assert first_request["last_polled_at"] is not None
    assert sixth_request is not None
    assert int(sixth_request["attempts"]) == 1


def test_background_sync_cycle_prioritizes_recently_retried_pending_jobs_for_completion() -> None:
    class _PendingCompletionClient(_FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.retried_match_ids: set[int] = set()

        def get_player_matches(self, **kwargs):
            self.calls += 1
            return [
                {
                    "match_id": 901 + offset,
                    "start_time": 1771552800 - (offset * 3600),
                    "player_slot": 0,
                    "radiant_win": True,
                    "game_mode": 23,
                    "kills": 8,
                    "deaths": 3,
                    "assists": 11,
                    "duration": 1400,
                    "hero_id": 1,
                    "item_0": 1,
                }
                for offset in range(12)
            ]

        def get_match_details(self, match_id: int) -> dict:
            player = {
                "account_id": 123,
                "player_slot": 0,
                "item_0": 1,
            }
            if match_id in self.retried_match_ids:
                player["purchase_log"] = [{"key": "blink", "time": 600}]
            return {
                "match_id": match_id,
                "version": 22 if match_id in self.retried_match_ids else None,
                "players": [player],
            }

        def request_match_parse(self, match_id: int) -> int | None:
            self.retried_match_ids.add(match_id)
            return 500000 + match_id

        def get_parse_job_status(self, job_id: int) -> dict | None:
            match_id = int(job_id) - 500000
            if match_id in self.retried_match_ids:
                return {"jobId": job_id, "status": "completed"}
            return None

    client = _PendingCompletionClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)
    service.references.item_ids_by_key["blink"] = 1
    service.references.item_names_by_id[1] = "Blink Dagger"

    now = datetime.now(tz=timezone.utc)
    matches = client.get_player_matches()
    store.upsert_player_matches(123, matches)
    for offset, match in enumerate(matches):
        match_id = int(match["match_id"])
        activity_at = (now - timedelta(hours=4 + offset)).isoformat()
        store.upsert_match_detail(
            match_id,
            {"match_id": match_id, "version": None, "players": [{"account_id": 123, "player_slot": 0, "item_0": 1}]},
        )
        store.upsert_match_parse_request(
            match_id,
            123,
            status="pending",
            requested_at=activity_at,
            last_polled_at=activity_at,
        )

    first_cycle = service.run_background_sync_cycle(
        player_id=123,
        window_days=365,
        max_detail_fetches=0,
        max_parse_requests=5,
        pending_parse_retry_after_seconds=3600,
        pending_parse_poll_after_seconds=0,
        force=True,
    )
    second_cycle = service.run_background_sync_cycle(
        player_id=123,
        window_days=365,
        max_detail_fetches=0,
        max_parse_requests=5,
        pending_parse_retry_after_seconds=3600,
        pending_parse_poll_after_seconds=0,
        force=True,
    )

    assert first_cycle.parse_requested == 5
    assert first_cycle.coverage.pending_parse_count == 12
    assert second_cycle.parse_requested == 5
    assert second_cycle.coverage.pending_parse_count == 7
    assert "Resolved 5 pending replay parse job(s)." in second_cycle.note


def test_background_sync_cycle_does_not_poll_fresh_pending_parse_jobs_before_poll_delay() -> None:
    class _FreshPendingClient(_FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.detail_calls = 0

        def get_player_matches(self, **kwargs):
            self.calls += 1
            return [
                {
                    "match_id": 9901,
                    "start_time": 1771552800,
                    "player_slot": 0,
                    "radiant_win": True,
                    "game_mode": 23,
                    "kills": 8,
                    "deaths": 3,
                    "assists": 11,
                    "duration": 1400,
                    "hero_id": 1,
                    "item_0": 1,
                }
            ]

        def get_match_details(self, match_id: int) -> dict:
            self.detail_calls += 1
            return {
                "match_id": match_id,
                "version": None,
                "players": [{"account_id": 123, "player_slot": 0, "item_0": 1}],
            }

    client = _FreshPendingClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)
    store.upsert_player_matches(123, client.get_player_matches())
    store.upsert_match_detail(9901, {"match_id": 9901, "version": None, "players": [{"account_id": 123, "player_slot": 0, "item_0": 1}]})
    fresh_activity_at = datetime.now(tz=timezone.utc).isoformat()
    store.upsert_match_parse_request(
        9901,
        123,
        status="pending",
        requested_at=fresh_activity_at,
        last_polled_at=fresh_activity_at,
    )

    result = service.run_background_sync_cycle(
        player_id=123,
        window_days=365,
        max_detail_fetches=0,
        max_parse_requests=1,
        pending_parse_retry_after_seconds=3600,
        pending_parse_poll_after_seconds=300,
        force=True,
    )

    pending_request = store.get_match_parse_request(9901)

    assert result.status == "completed"
    assert result.coverage.pending_parse_count == 1
    assert client.detail_calls == 0
    assert pending_request is not None
    assert pending_request["status"] == "pending"


def test_background_sync_cycle_skips_pending_checks_during_quiet_period_after_recent_work() -> None:
    class _QuietPeriodClient(_FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.parse_requested: set[int] = set()
            self.parse_status_calls = 0

        def get_player_matches(self, **kwargs):
            self.calls += 1
            return [
                {
                    "match_id": 4101,
                    "start_time": 1771552800,
                    "player_slot": 0,
                    "radiant_win": True,
                    "game_mode": 23,
                    "kills": 8,
                    "deaths": 3,
                    "assists": 11,
                    "duration": 1400,
                    "hero_id": 1,
                    "item_0": 1,
                },
                {
                    "match_id": 4100,
                    "start_time": 1771466400,
                    "player_slot": 0,
                    "radiant_win": False,
                    "game_mode": 23,
                    "kills": 4,
                    "deaths": 6,
                    "assists": 7,
                    "duration": 1300,
                    "hero_id": 1,
                    "item_0": 1,
                },
            ]

        def get_match_details(self, match_id: int) -> dict:
            if match_id == 4101:
                return {
                    "match_id": 4101,
                    "version": 22,
                    "players": [
                        {
                            "account_id": 123,
                            "player_slot": 0,
                            "item_0": 1,
                            "purchase_log": [{"key": "blink", "time": 600}],
                        }
                    ],
                }
            return {
                "match_id": 4100,
                "version": None,
                "players": [
                    {
                        "account_id": 123,
                        "player_slot": 0,
                        "item_0": 1,
                    }
                ],
            }

        def request_match_parse(self, match_id: int) -> int | None:
            self.parse_requested.add(match_id)
            return 700000 + match_id

        def get_parse_job_status(self, job_id: int) -> dict | None:
            self.parse_status_calls += 1
            raise AssertionError("quiet-period cycle should not poll parse job status")

    client = _QuietPeriodClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)
    service.references.item_ids_by_key["blink"] = 1
    service.references.item_names_by_id[1] = "Blink Dagger"

    first_cycle = service.run_background_sync_cycle(
        player_id=123,
        window_days=365,
        max_detail_fetches=5,
        max_parse_requests=1,
        pending_parse_quiet_period_seconds=300,
        force=True,
    )
    second_cycle = service.run_background_sync_cycle(
        player_id=123,
        window_days=365,
        max_detail_fetches=0,
        max_parse_requests=1,
        pending_parse_quiet_period_seconds=300,
        run_source="auto",
    )

    assert first_cycle.parse_requested == 1
    assert second_cycle.status == "completed"
    assert "Waiting before the next pending replay-parse check after recent OpenDota activity." in second_cycle.note
    assert client.parse_status_calls == 0


def test_background_sync_cycle_waiting_does_not_reset_pending_retry_timer() -> None:
    class _PendingTimerClient(_FakeClient):
        def get_player_matches(self, **kwargs):
            self.calls += 1
            return [
                {
                    "match_id": 5100,
                    "start_time": 1771466400,
                    "player_slot": 0,
                    "radiant_win": False,
                    "game_mode": 23,
                    "kills": 4,
                    "deaths": 6,
                    "assists": 7,
                    "duration": 1300,
                    "hero_id": 1,
                    "item_0": 1,
                }
            ]

        def get_match_details(self, match_id: int) -> dict:
            return {
                "match_id": 5100,
                "version": None,
                "players": [
                    {
                        "account_id": 123,
                        "player_slot": 0,
                        "item_0": 1,
                    }
                ],
            }

    client = _PendingTimerClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)
    store.upsert_player_matches(123, client.get_player_matches())
    store.upsert_match_detail(5100, {"match_id": 5100, "version": None, "players": [{"account_id": 123, "player_slot": 0, "item_0": 1}]})
    activity_at = (datetime.now(tz=timezone.utc) - timedelta(minutes=2)).isoformat()
    store.upsert_match_parse_request(
        5100,
        123,
        status="pending",
        parse_job_id=900100,
        requested_at=activity_at,
        last_polled_at=activity_at,
    )

    result = service.run_background_sync_cycle(
        player_id=123,
        window_days=365,
        max_detail_fetches=0,
        max_parse_requests=1,
        pending_parse_retry_after_seconds=3600,
        pending_parse_poll_after_seconds=300,
        force=True,
    )

    pending_request = store.get_match_parse_request(5100)

    assert result.status == "completed"
    assert result.parse_requested == 0
    assert pending_request is not None
    assert pending_request["last_polled_at"] == activity_at


def test_background_sync_cycle_parse_only_retry_does_not_start_pending_quiet_period() -> None:
    class _ParseOnlyRetryClient(_FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.parse_requested: set[int] = set()
            self.parse_status_calls = 0

        def get_player_matches(self, **kwargs):
            self.calls += 1
            return [
                {
                    "match_id": 8801,
                    "start_time": 1771466400,
                    "player_slot": 0,
                    "radiant_win": False,
                    "game_mode": 23,
                    "kills": 4,
                    "deaths": 6,
                    "assists": 7,
                    "duration": 1300,
                    "hero_id": 1,
                    "item_0": 1,
                }
            ]

        def get_match_details(self, match_id: int) -> dict:
            player = {"account_id": 123, "player_slot": 0, "item_0": 1}
            if match_id in self.parse_requested:
                player["purchase_log"] = [{"key": "blink", "time": 600}]
            return {"match_id": match_id, "version": 22 if match_id in self.parse_requested else None, "players": [player]}

        def request_match_parse(self, match_id: int) -> int | None:
            self.parse_requested.add(match_id)
            return 900000 + match_id

        def get_parse_job_status(self, job_id: int) -> dict | None:
            self.parse_status_calls += 1
            return {"jobId": job_id, "status": "completed"}

    client = _ParseOnlyRetryClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)
    service.references.item_ids_by_key["blink"] = 1
    service.references.item_names_by_id[1] = "Blink Dagger"

    store.upsert_player_matches(
        123,
        [
            {
                "match_id": 8801,
                "start_time": 1771466400,
                "player_slot": 0,
                "radiant_win": False,
                "game_mode": 23,
                "kills": 4,
                "deaths": 6,
                "assists": 7,
                "duration": 1300,
                "hero_id": 1,
                "item_0": 1,
            }
        ],
    )
    store.upsert_match_detail(
        8801,
        {"match_id": 8801, "version": None, "players": [{"account_id": 123, "player_slot": 0, "item_0": 1}]},
    )
    stale_at = (datetime.now(tz=timezone.utc) - timedelta(hours=4)).isoformat()
    store.upsert_match_parse_request(
        8801,
        123,
        status="pending",
        requested_at=stale_at,
        last_polled_at=stale_at,
    )
    store.upsert_background_sync_state(
        123,
        "gm:23",
        365,
        last_summary_sync_at=datetime.now(tz=timezone.utc).isoformat(),
    )

    first_cycle = service.run_background_sync_cycle(
        player_id=123,
        window_days=365,
        max_detail_fetches=0,
        max_parse_requests=1,
        pending_parse_retry_after_seconds=3600,
        pending_parse_poll_after_seconds=0,
        pending_parse_quiet_period_seconds=300,
        force=False,
    )
    second_cycle = service.run_background_sync_cycle(
        player_id=123,
        window_days=365,
        max_detail_fetches=0,
        max_parse_requests=1,
        pending_parse_retry_after_seconds=3600,
        pending_parse_poll_after_seconds=0,
        pending_parse_quiet_period_seconds=300,
        force=False,
    )

    assert first_cycle.parse_requested == 1
    assert "Waiting before the next pending replay-parse check after recent OpenDota activity." not in second_cycle.note
    assert second_cycle.coverage.pending_parse_count == 0
    assert client.parse_status_calls >= 1


def test_background_sync_cycle_retries_stale_pending_even_if_recently_polled() -> None:
    class _RetryStalePolledClient(_FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.requested_match_ids: list[int] = []

        def get_player_matches(self, **kwargs):
            self.calls += 1
            return [
                {
                    "match_id": 6100,
                    "start_time": 1771466400,
                    "player_slot": 0,
                    "radiant_win": False,
                    "game_mode": 23,
                    "kills": 4,
                    "deaths": 6,
                    "assists": 7,
                    "duration": 1300,
                    "hero_id": 1,
                    "item_0": 1,
                }
            ]

        def get_match_details(self, match_id: int) -> dict:
            return {
                "match_id": 6100,
                "version": None,
                "players": [
                    {
                        "account_id": 123,
                        "player_slot": 0,
                        "item_0": 1,
                    }
                ],
            }

        def request_match_parse(self, match_id: int) -> int | None:
            self.requested_match_ids.append(match_id)
            return 901001

    client = _RetryStalePolledClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)
    store.upsert_player_matches(123, client.get_player_matches())
    store.upsert_match_detail(6100, {"match_id": 6100, "version": None, "players": [{"account_id": 123, "player_slot": 0, "item_0": 1}]})
    requested_at = (datetime.now(tz=timezone.utc) - timedelta(hours=2)).isoformat()
    recently_polled_at = (datetime.now(tz=timezone.utc) - timedelta(minutes=2)).isoformat()
    store.upsert_match_parse_request(
        6100,
        123,
        status="pending",
        parse_job_id=900100,
        requested_at=requested_at,
        last_polled_at=recently_polled_at,
    )

    result = service.run_background_sync_cycle(
        player_id=123,
        window_days=365,
        max_detail_fetches=0,
        max_parse_requests=1,
        pending_parse_retry_after_seconds=3600,
        pending_parse_poll_after_seconds=300,
        force=True,
    )

    pending_request = store.get_match_parse_request(6100)

    assert result.status == "completed"
    assert result.parse_requested == 1
    assert client.requested_match_ids == [6100]
    assert pending_request is not None
    assert pending_request["parse_job_id"] == 901001


def test_background_sync_cycle_fetches_four_new_matches_during_long_window_cooldown() -> None:
    recent_sync_at = "2026-04-08T10:00:00+00:00"

    class _RecentCooldownClient(_FakeClient):
        def get_player_matches(self, **kwargs):
            self.calls += 1
            return [
                {
                    "match_id": 9004,
                    "start_time": 1775642400,
                    "player_slot": 0,
                    "radiant_win": False,
                    "game_mode": 23,
                    "kills": 19,
                    "deaths": 9,
                    "assists": 34,
                    "duration": 2312,
                    "hero_id": 67,
                },
                {
                    "match_id": 9003,
                    "start_time": 1775639400,
                    "player_slot": 128,
                    "radiant_win": False,
                    "game_mode": 23,
                    "kills": 11,
                    "deaths": 4,
                    "assists": 10,
                    "duration": 1563,
                    "hero_id": 44,
                },
                {
                    "match_id": 9002,
                    "start_time": 1775636100,
                    "player_slot": 0,
                    "radiant_win": True,
                    "game_mode": 23,
                    "kills": 2,
                    "deaths": 5,
                    "assists": 10,
                    "duration": 1332,
                    "hero_id": 93,
                },
                {
                    "match_id": 9001,
                    "start_time": 1775634900,
                    "player_slot": 128,
                    "radiant_win": True,
                    "game_mode": 23,
                    "kills": 5,
                    "deaths": 5,
                    "assists": 6,
                    "duration": 1280,
                    "hero_id": 44,
                },
                {
                    "match_id": 8760879094,
                    "start_time": 1775482740,
                    "player_slot": 0,
                    "radiant_win": True,
                    "game_mode": 23,
                    "kills": 13,
                    "deaths": 6,
                    "assists": 17,
                    "duration": 1645,
                    "hero_id": 67,
                },
                {
                    "match_id": 8760856204,
                    "start_time": 1775481600,
                    "player_slot": 128,
                    "radiant_win": True,
                    "game_mode": 23,
                    "kills": 0,
                    "deaths": 4,
                    "assists": 1,
                    "duration": 905,
                    "hero_id": 93,
                },
                {
                    "match_id": 8760828457,
                    "start_time": 1775480340,
                    "player_slot": 128,
                    "radiant_win": True,
                    "game_mode": 23,
                    "kills": 1,
                    "deaths": 5,
                    "assists": 0,
                    "duration": 1038,
                    "hero_id": 93,
                },
            ]

    client = _RecentCooldownClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)

    store.upsert_player_matches(
        1233793238,
        [
            {
                "match_id": 8760879094,
                "start_time": 1775482740,
                "player_slot": 0,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 13,
                "deaths": 6,
                "assists": 17,
                "duration": 1645,
                "hero_id": 67,
            },
            {
                "match_id": 8760856204,
                "start_time": 1775481600,
                "player_slot": 128,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 0,
                "deaths": 4,
                "assists": 1,
                "duration": 905,
                "hero_id": 93,
            },
            {
                "match_id": 8760828457,
                "start_time": 1775480340,
                "player_slot": 128,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 1,
                "deaths": 5,
                "assists": 0,
                "duration": 1038,
                "hero_id": 93,
            },
        ],
    )
    store.upsert_sync_state(
        1233793238,
        "gm:23",
        last_incremental_sync_at=recent_sync_at,
        known_match_count=3,
    )

    result = service.run_background_sync_cycle(
        player_id=1233793238,
        window_days=365,
        max_detail_fetches=0,
        max_parse_requests=0,
        force=False,
    )

    cached_matches = service.get_cached_matches(
        QueryFilters(player_id=1233793238, game_mode=23, game_mode_name="Turbo", days=365)
    )
    background_rows = service.list_background_match_status_rows(
        player_id=1233793238,
        game_mode=23,
        window_days=365,
        limit=10,
    )
    state = service.match_store.get_sync_state(1233793238, "gm:23")

    assert result.summary_new_matches == 4
    assert result.coverage.total_matches == 7
    assert client.calls == 1
    assert [match.match_id for match in cached_matches[:4]] == [9004, 9003, 9002, 9001]
    assert [row.match_id for row in background_rows[:4]] == [9004, 9003, 9002, 9001]
    assert state is not None
    assert state["last_incremental_sync_at"] == recent_sync_at


def test_background_sync_cycle_persists_manual_and_auto_run_source() -> None:
    class _RunSourceClient(_FakeClient):
        def get_player_matches(self, **kwargs):
            self.calls += 1
            return [
                {
                    "match_id": 77,
                    "start_time": 1771552800,
                    "player_slot": 0,
                    "radiant_win": True,
                    "game_mode": 23,
                    "kills": 8,
                    "deaths": 3,
                    "assists": 11,
                    "duration": 1400,
                    "hero_id": 1,
                }
            ]

        def get_match_details(self, match_id: int) -> dict:
            return {"match_id": match_id, "version": 22, "players": [{"account_id": 123, "player_slot": 0}]}

    client = _RunSourceClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)

    service.run_background_sync_cycle(player_id=123, window_days=365, max_detail_fetches=0, max_parse_requests=0, force=False, run_source="manual")
    service.run_background_sync_cycle(player_id=123, window_days=365, max_detail_fetches=0, max_parse_requests=0, force=True, run_source="auto")

    runs = service.list_background_sync_runs(123, window_days=365, limit=5)

    assert [run["run_source"] for run in runs[:2]] == ["auto", "manual"]


def test_background_sync_cycle_treats_summary_sync_rate_limit_as_cooldown() -> None:
    class _SummaryRateLimitClient(_FakeClient):
        def get_player_matches(self, **kwargs):
            raise OpenDotaRateLimitError("OpenDota API rate limit reached")

    client = _SummaryRateLimitClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)

    result = service.run_background_sync_cycle(
        player_id=123,
        window_days=365,
        max_detail_fetches=0,
        max_parse_requests=0,
        rate_limit_cooldown_seconds=50,
        force=True,
        run_source="auto",
    )

    runs = service.list_background_sync_runs(123, window_days=365, limit=1)

    assert result.status == "rate_limited"
    assert result.rate_limited is True
    assert result.next_retry_at is not None
    assert "summary sync" in result.note
    assert runs[0]["status"] == "rate_limited"
    assert runs[0]["rate_limited"] == 1
