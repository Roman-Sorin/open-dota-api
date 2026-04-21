from datetime import date, datetime, time, timedelta, timezone

from models.dtos import MatchSummary, QueryFilters
from services.analytics_service import DotaAnalyticsService


class _FakeClient:
    def get_constants_heroes(self) -> dict:
        return {
            "1": {"id": 1, "localized_name": "Axe", "img": "/apps/dota2/images/heroes/axe.png"},
            "138": {"id": 138, "localized_name": "Muerta", "img": "/apps/dota2/images/heroes/muerta.png"},
        }

    def get_constants_items(self) -> dict:
        return {
            "blink": {"id": 1, "dname": "Blink Dagger", "img": "/apps/dota2/images/items/blink.png"},
            "power_treads": {"id": 63, "dname": "Power Treads", "img": "/apps/dota2/images/items/power_treads.png"},
            "armlet": {"id": 114, "dname": "Armlet of Mordiggian", "img": "/apps/dota2/images/items/armlet.png"},
            "skadi": {"id": 160, "dname": "Eye of Skadi", "img": "/apps/dota2/images/items/skadi.png"},
            "orchid": {"id": 151, "dname": "Orchid Malevolence", "img": "/apps/dota2/images/items/orchid.png"},
            "heart": {"id": 250, "dname": "Heart of Tarrasque", "img": "/apps/dota2/images/items/heart.png"},
            "ultimate_scepter": {"id": 108, "dname": "Aghanim's Scepter", "img": "/apps/dota2/images/items/ultimate_scepter.png"},
            "aghanims_shard": {"id": 609, "dname": "Aghanim's Shard", "img": "/apps/dota2/images/items/aghanims_shard.png"},
            "moon_shard": {"id": 247, "dname": "Moon Shard", "img": "/apps/dota2/images/items/moon_shard.png"},
        }

    def get_constants_patch(self) -> list[dict]:
        return [{"name": "7.40", "date": "2025-01-01T00:00:00Z"}]


class _FakeCache:
    def __init__(self) -> None:
        self._store: dict[str, object] = {}

    def get(self, key: str, max_age=None):
        return self._store.get(key)

    def set(self, key: str, value: object) -> None:
        self._store[key] = value


def test_enrich_hero_damage_from_match_details() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        MatchSummary(
            match_id=101,
            start_time=0,
            player_slot=0,
            radiant_win=True,
            kills=1,
            deaths=1,
            assists=1,
            duration=1200,
            hero_id=1,
            hero_damage=0,
        )
    ]

    service._get_match_details_cached = lambda _: {  # type: ignore[method-assign]
        "players": [{"account_id": 123, "player_slot": 0, "hero_damage": 32123, "net_worth": 25444}]
    }

    service.enrich_hero_damage(player_id=123, matches=matches, max_fallback_detail_calls=3)

    assert matches[0].hero_damage == 32123
    assert matches[0].net_worth == 25444


def test_enrich_hero_damage_cached_details_do_not_consume_budget() -> None:
    cache = _FakeCache()
    cache.set(
        "match_details_101",
        {"players": [{"account_id": 123, "player_slot": 0, "hero_damage": 11111}]},
    )
    service = DotaAnalyticsService(client=_FakeClient(), cache=cache)
    matches = [
        MatchSummary(
            match_id=101,
            start_time=0,
            player_slot=0,
            radiant_win=True,
            kills=1,
            deaths=1,
            assists=1,
            duration=1200,
            hero_id=1,
            hero_damage=0,
        ),
        MatchSummary(
            match_id=202,
            start_time=0,
            player_slot=0,
            radiant_win=True,
            kills=1,
            deaths=1,
            assists=1,
            duration=1200,
            hero_id=1,
            hero_damage=0,
        ),
    ]

    def _fake_get_match_details(match_id: int) -> dict:
        return {"players": [{"account_id": 123, "player_slot": 0, "hero_damage": 22222 if match_id == 202 else 0}]}

    service.client.get_match_details = _fake_get_match_details  # type: ignore[method-assign]

    service.enrich_hero_damage(player_id=123, matches=matches, max_fallback_detail_calls=1)

    assert matches[0].hero_damage == 11111
    assert matches[1].hero_damage == 22222


def test_turbo_hero_overview_uses_confirmed_damage_samples_only() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        MatchSummary(
            match_id=101,
            start_time=0,
            player_slot=0,
            radiant_win=True,
            kills=1,
            deaths=1,
            assists=1,
            duration=1200,
            hero_id=1,
            hero_damage=30000,
            hero_damage_known=True,
        ),
        MatchSummary(
            match_id=102,
            start_time=0,
            player_slot=0,
            radiant_win=True,
            kills=1,
            deaths=1,
            assists=1,
            duration=1200,
            hero_id=1,
            hero_damage=0,
            hero_damage_known=False,
        ),
    ]

    service.fetch_matches = lambda filters: matches  # type: ignore[method-assign]
    service.enrich_hero_damage = lambda player_id, matches, max_fallback_detail_calls=45: None  # type: ignore[method-assign]

    rows = service.get_turbo_hero_overview(player_id=123, days=60)

    assert len(rows) == 1
    assert rows[0]["avg_damage"] == 30000
    assert rows[0]["avg_damage_samples"] == 1


def test_build_stats_tracks_avg_net_worth_and_damage() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        MatchSummary(
            match_id=1,
            start_time=0,
            player_slot=0,
            radiant_win=True,
            kills=10,
            deaths=2,
            assists=8,
            duration=1200,
            hero_id=1,
            lane_efficiency_pct=60.0,
            lane_efficiency_known=True,
            net_worth=18000,
            net_worth_known=True,
            hero_damage=15000,
            hero_damage_known=True,
        ),
        MatchSummary(
            match_id=2,
            start_time=0,
            player_slot=0,
            radiant_win=False,
            kills=4,
            deaths=6,
            assists=10,
            duration=1200,
            hero_id=1,
            lane_efficiency_pct=40.0,
            lane_efficiency_known=True,
            net_worth=24000,
            net_worth_known=True,
            hero_damage=21000,
            hero_damage_known=True,
        ),
    ]

    stats = service.build_stats(matches)

    assert stats.avg_net_worth == 21000
    assert stats.avg_damage == 18000
    assert stats.avg_duration_seconds == 1200
    assert stats.lane_winrate == 50.0
    assert stats.lane_sample_count == 2
    assert stats.max_kills == 10
    assert stats.max_hero_damage == 21000


def test_turbo_hero_overview_matches_reported_phantom_lancer_example() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        MatchSummary(
            match_id=1,
            start_time=0,
            player_slot=0,
            radiant_win=False,
            kills=2,
            deaths=11,
            assists=8,
            duration=2226,
            hero_id=1,
            hero_damage=12700,
            hero_damage_known=True,
        ),
        MatchSummary(
            match_id=2,
            start_time=0,
            player_slot=128,
            radiant_win=False,
            kills=4,
            deaths=7,
            assists=11,
            duration=1635,
            hero_id=1,
            hero_damage=14700,
            hero_damage_known=True,
        ),
        MatchSummary(
            match_id=3,
            start_time=0,
            player_slot=128,
            radiant_win=False,
            kills=2,
            deaths=5,
            assists=9,
            duration=1325,
            hero_id=1,
            hero_damage=9700,
            hero_damage_known=True,
        ),
    ]

    service.fetch_matches = lambda filters: matches  # type: ignore[method-assign]
    service.enrich_hero_damage = lambda player_id, matches, max_fallback_detail_calls=45: None  # type: ignore[method-assign]

    rows = service.get_turbo_hero_overview(player_id=123, days=180)

    assert len(rows) == 1
    assert rows[0]["matches"] == 3
    assert rows[0]["avg_damage"] == 12366.666666666666
    assert rows[0]["avg_damage_samples"] == 3


def test_turbo_hero_overview_includes_avg_net_worth() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        MatchSummary(
            match_id=1,
            start_time=0,
            player_slot=0,
            radiant_win=True,
            kills=2,
            deaths=1,
            assists=10,
            duration=1200,
            hero_id=1,
            net_worth=22000,
            net_worth_known=True,
            hero_damage=10000,
            hero_damage_known=True,
        ),
        MatchSummary(
            match_id=2,
            start_time=0,
            player_slot=0,
            radiant_win=True,
            kills=3,
            deaths=2,
            assists=12,
            duration=1200,
            hero_id=1,
            net_worth=26000,
            net_worth_known=True,
            hero_damage=14000,
            hero_damage_known=True,
        ),
    ]

    service.fetch_matches = lambda filters: matches  # type: ignore[method-assign]
    service.enrich_hero_damage = lambda player_id, matches, max_fallback_detail_calls=45: None  # type: ignore[method-assign]

    rows = service.get_turbo_hero_overview(player_id=123, days=60)

    assert rows[0]["avg_net_worth"] == 24000
    assert rows[0]["avg_net_worth_samples"] == 2


def test_turbo_hero_overview_tracks_duration_and_maxima() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        MatchSummary(
            match_id=1,
            start_time=0,
            player_slot=0,
            radiant_win=True,
            kills=9,
            deaths=2,
            assists=10,
            duration=1500,
            hero_id=1,
            lane_efficiency_pct=55.0,
            lane_efficiency_known=True,
            hero_damage=12000,
            hero_damage_known=True,
        ),
        MatchSummary(
            match_id=2,
            start_time=0,
            player_slot=0,
            radiant_win=False,
            kills=14,
            deaths=5,
            assists=7,
            duration=2100,
            hero_id=1,
            lane_efficiency_pct=45.0,
            lane_efficiency_known=True,
            hero_damage=28000,
            hero_damage_known=True,
        ),
    ]

    service.fetch_matches = lambda filters: matches  # type: ignore[method-assign]
    service.enrich_hero_damage = lambda player_id, matches, max_fallback_detail_calls=45: None  # type: ignore[method-assign]

    rows = service.get_turbo_hero_overview(player_id=123, days=60)

    assert rows[0]["avg_duration_seconds"] == 1800
    assert rows[0]["lane_winrate"] == 50.0
    assert rows[0]["max_kills"] == 14
    assert rows[0]["max_hero_damage"] == 28000


def test_turbo_hero_overview_tracks_side_winrates() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        MatchSummary(
            match_id=1,
            start_time=0,
            player_slot=0,
            radiant_win=True,
            kills=1,
            deaths=1,
            assists=1,
            duration=1200,
            hero_id=1,
        ),
        MatchSummary(
            match_id=2,
            start_time=0,
            player_slot=0,
            radiant_win=False,
            kills=1,
            deaths=1,
            assists=1,
            duration=1200,
            hero_id=1,
        ),
        MatchSummary(
            match_id=3,
            start_time=0,
            player_slot=128,
            radiant_win=False,
            kills=1,
            deaths=1,
            assists=1,
            duration=1200,
            hero_id=1,
        ),
    ]

    service.fetch_matches = lambda filters: matches  # type: ignore[method-assign]
    service.enrich_hero_damage = lambda player_id, matches, max_fallback_detail_calls=45: None  # type: ignore[method-assign]

    rows = service.get_turbo_hero_overview(player_id=123, days=60)

    assert rows[0]["radiant_wr"] == 50.0
    assert rows[0]["dire_wr"] == 100.0


def test_build_turbo_hero_overview_rows_uses_same_side_winrates_as_detail_stats() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        MatchSummary(
            match_id=1,
            start_time=0,
            player_slot=0,
            radiant_win=True,
            kills=10,
            deaths=2,
            assists=8,
            duration=1200,
            hero_id=1,
        ),
        MatchSummary(
            match_id=2,
            start_time=0,
            player_slot=0,
            radiant_win=False,
            kills=5,
            deaths=6,
            assists=7,
            duration=1500,
            hero_id=1,
        ),
        MatchSummary(
            match_id=3,
            start_time=0,
            player_slot=128,
            radiant_win=False,
            kills=14,
            deaths=4,
            assists=9,
            duration=1800,
            hero_id=1,
        ),
    ]

    overview_row = service.build_turbo_hero_overview_rows(matches)[0]
    detail_stats = service.build_stats(matches)

    assert overview_row["radiant_wr"] == detail_stats.radiant_wr == 50.0
    assert overview_row["dire_wr"] == detail_stats.dire_wr == 100.0


def test_fetch_matches_supports_lettered_patch_names() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    service._patch_starts = [1735689600, 1738368000]
    service._patch_names = ["7.40", "7.40c"]

    service.client.get_player_matches = lambda **kwargs: [  # type: ignore[method-assign]
        {
            "match_id": 1,
            "start_time": 1739000000,
            "player_slot": 0,
            "radiant_win": True,
            "kills": 1,
            "deaths": 1,
            "assists": 1,
            "duration": 1200,
            "hero_id": 1,
            "hero_damage": 10000,
        }
    ]

    rows = service.fetch_matches(
        QueryFilters(
            player_id=123,
            game_mode=23,
            game_mode_name="Turbo",
            patch_names=["7.40c"],
        )
    )

    assert len(rows) == 1
    assert rows[0].match_id == 1


def test_fetch_matches_respects_start_date_filter() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    service.client.get_player_matches = lambda **kwargs: [  # type: ignore[method-assign]
        {
            "match_id": 1,
            "start_time": 1736899200,
            "player_slot": 0,
            "radiant_win": True,
            "kills": 1,
            "deaths": 1,
            "assists": 1,
            "duration": 1200,
            "hero_id": 1,
            "hero_damage": 10000,
        },
        {
            "match_id": 2,
            "start_time": 1738540800,
            "player_slot": 0,
            "radiant_win": True,
            "kills": 1,
            "deaths": 1,
            "assists": 1,
            "duration": 1200,
            "hero_id": 1,
            "hero_damage": 10000,
        },
    ]

    rows = service.fetch_matches(
        QueryFilters(
            player_id=123,
            game_mode=23,
            game_mode_name="Turbo",
            start_date=date(2025, 2, 1),
        )
    )

    assert len(rows) == 1
    assert rows[0].match_id == 2


def test_min_start_time_uses_calendar_day_boundary_for_days_filter() -> None:
    now = datetime.now(tz=timezone.utc)
    boundary_date = now.date() - timedelta(days=60)
    boundary_start = int(datetime.combine(boundary_date, time(hour=2), tzinfo=timezone.utc).timestamp())

    min_start = DotaAnalyticsService._min_start_time(
        QueryFilters(player_id=123, game_mode=23, game_mode_name="Turbo", days=60)
    )

    assert min_start == int(datetime.combine(boundary_date, time.min, tzinfo=timezone.utc).timestamp())
    assert boundary_start >= min_start


def test_fetch_matches_uses_cache_for_historical_query() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    calls: list[int] = []

    def _fake_get_player_matches(**kwargs):
        calls.append(1)
        return [
            {
                "match_id": 1,
                "start_time": 1738540800,
                "player_slot": 0,
                "radiant_win": True,
                "kills": 1,
                "deaths": 1,
                "assists": 1,
                "duration": 1200,
                "hero_id": 1,
                "net_worth": 20500,
                "hero_damage": 10000,
            }
        ]

    service.client.get_player_matches = _fake_get_player_matches  # type: ignore[method-assign]
    filters = QueryFilters(
        player_id=123,
        game_mode=23,
        game_mode_name="Turbo",
        start_date=date(2025, 2, 1),
    )

    first = service.fetch_matches(filters)
    second = service.fetch_matches(filters)

    assert len(calls) == 1
    assert first[0].net_worth == 20500
    assert second[0].net_worth == 20500


def test_recent_hero_matches_use_final_slots_with_matching_final_item_timings() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        MatchSummary(
            match_id=101,
            start_time=0,
            player_slot=0,
            radiant_win=True,
            kills=10,
            deaths=2,
            assists=8,
            duration=1500,
            hero_id=1,
            item_0=63,
            item_1=114,
            item_2=160,
            item_3=151,
            item_4=250,
            item_5=1,
        )
    ]

    service._get_match_details_cached = lambda _: {  # type: ignore[method-assign]
        "players": [
            {
                "account_id": 123,
                "player_slot": 0,
                "level": 27,
                "hero_variant": 2,
                "net_worth": 26173,
                "hero_damage": 15592,
                "item_0": 63,
                "item_1": 114,
                "item_2": 160,
                "item_3": 151,
                "item_4": 250,
                "item_5": 1,
                "purchase_log": [
                    {"key": "boots", "time": 15},
                    {"key": "power_treads", "time": 180},
                    {"key": "armlet", "time": 344},
                    {"key": "orchid", "time": 543},
                    {"key": "blink", "time": 774},
                    {"key": "heart", "time": 1046},
                    {"key": "skadi", "time": 1390},
                ],
            }
        ]
    }

    rows = service.build_recent_hero_matches(player_id=123, matches=matches, limit=10)

    assert len(rows) == 1
    assert rows[0].hero_level == 27
    assert rows[0].hero_variant == 2
    assert rows[0].net_worth == 26173
    assert rows[0].hero_damage == 15592
    assert rows[0].kda_ratio == 9.0
    assert [item.item_id for item in rows[0].items] == [63, 114, 151, 1, 250, 160]
    assert [item.purchase_time_min for item in rows[0].items] == [3, 5, 9, 12, 17, 23]


def test_recent_hero_matches_use_aegis_objective_time_when_purchase_log_lacks_aegis() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        MatchSummary(
            match_id=102,
            start_time=0,
            player_slot=128,
            radiant_win=False,
            kills=3,
            deaths=1,
            assists=14,
            duration=1276,
            hero_id=1,
            item_0=117,
            item_1=160,
            item_2=151,
            item_3=250,
            item_4=1,
            item_5=0,
        )
    ]

    service.references.item_names_by_id[117] = "Aegis of the Immortal"
    service.references.item_images_by_id[117] = "aegis.png"

    service._get_match_details_cached = lambda _: {  # type: ignore[method-assign]
        "players": [
            {
                "account_id": 123,
                "player_slot": 128,
                "level": 25,
                "hero_variant": 0,
                "item_0": 117,
                "item_1": 160,
                "item_2": 151,
                "item_3": 250,
                "item_4": 1,
                "item_5": 0,
                "purchase_log": [
                    {"key": "orchid", "time": 720},
                    {"key": "blink", "time": 900},
                    {"key": "skadi", "time": 1200},
                    {"key": "heart", "time": 1320},
                ],
            }
        ],
        "objectives": [
            {"time": 1020, "type": "CHAT_MESSAGE_AEGIS", "player_slot": 128},
        ],
    }

    rows = service.build_recent_hero_matches(player_id=123, matches=matches, limit=10)

    assert [item.item_id for item in rows[0].items] == [151, 1, 117, 160, 250]
    assert [item.purchase_time_min for item in rows[0].items] == [12, 15, 17, 20, 22]


def test_recent_hero_matches_include_consumed_buff_items() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        MatchSummary(
            match_id=103,
            start_time=0,
            player_slot=0,
            radiant_win=True,
            kills=13,
            deaths=6,
            assists=17,
            duration=1645,
            hero_id=1,
            item_0=160,
            item_1=151,
            item_2=1,
            item_3=63,
            item_4=114,
            item_5=250,
        )
    ]

    service._get_match_details_cached = lambda _: {  # type: ignore[method-assign]
        "players": [
            {
                "account_id": 123,
                "player_slot": 0,
                "level": 30,
                "hero_variant": 0,
                "item_0": 160,
                "item_1": 151,
                "item_2": 1,
                "item_3": 63,
                "item_4": 114,
                "item_5": 250,
                "aghanims_scepter": 1,
                "permanent_buffs": [{"permanent_buff": 2, "grant_time": 910}],
                "purchase_log": [
                    {"key": "power_treads", "time": 180},
                    {"key": "armlet", "time": 344},
                    {"key": "orchid", "time": 543},
                    {"key": "blink", "time": 774},
                    {"key": "skadi", "time": 1190},
                    {"key": "ultimate_scepter", "time": 910},
                ],
            }
        ]
    }

    rows = service.build_recent_hero_matches(player_id=123, matches=matches, limit=10)

    assert rows[0].items[0].item_name == "Aghanim's Scepter"
    assert rows[0].items[0].purchase_time_min == 15
    assert rows[0].items[0].is_buff is True


def test_recent_hero_matches_do_not_mark_unconsumed_moon_shard_as_buff() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        MatchSummary(
            match_id=104,
            start_time=0,
            player_slot=0,
            radiant_win=True,
            kills=7,
            deaths=8,
            assists=10,
            duration=1771,
            hero_id=1,
            item_0=145,
            item_1=247,
            item_2=116,
            item_3=263,
            item_4=208,
            item_5=139,
        )
    ]

    service.references.item_names_by_id.update(
        {
            145: "Battle Fury",
            247: "Moon Shard",
            116: "Black King Bar",
            263: "Eye of Skadi",
            208: "Abyssal Blade",
            139: "Butterfly",
        }
    )

    service._get_match_details_cached = lambda _: {  # type: ignore[method-assign]
        "players": [
            {
                "account_id": 123,
                "player_slot": 0,
                "level": 27,
                "hero_variant": 0,
                "item_0": 145,
                "item_1": 247,
                "item_2": 116,
                "item_3": 263,
                "item_4": 208,
                "item_5": 139,
                "aghanims_shard": 1,
                "first_purchase_time": {
                    "bfury": 300,
                    "moon_shard": 600,
                    "black_king_bar": 780,
                    "skadi": 1320,
                    "abyssal_blade": 1440,
                    "butterfly": 1620,
                },
            }
        ]
    }

    rows = service.build_recent_hero_matches(player_id=123, matches=matches, limit=10)

    moon_shards = [item for item in rows[0].items if item.item_id == 247]
    assert len(moon_shards) == 1
    assert moon_shards[0].is_buff is False
    assert moon_shards[0].purchase_time_min == 10


def test_turbo_hero_overview_matches_reported_muerta_example() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        MatchSummary(
            match_id=1001,
            start_time=1,
            player_slot=0,
            radiant_win=True,
            kills=9,
            deaths=5,
            assists=12,
            duration=1571,
            hero_id=138,
            net_worth=38000,
            net_worth_known=True,
            hero_damage=85168,
            hero_damage_known=True,
        ),
        MatchSummary(
            match_id=1002,
            start_time=2,
            player_slot=0,
            radiant_win=False,
            kills=3,
            deaths=8,
            assists=10,
            duration=1082,
            hero_id=138,
            net_worth=29000,
            net_worth_known=True,
            hero_damage=23000,
            hero_damage_known=True,
        ),
        MatchSummary(
            match_id=1003,
            start_time=3,
            player_slot=0,
            radiant_win=True,
            kills=6,
            deaths=7,
            assists=18,
            duration=1631,
            hero_id=138,
            net_worth=37200,
            net_worth_known=True,
            hero_damage=32000,
            hero_damage_known=True,
        ),
        MatchSummary(
            match_id=1004,
            start_time=4,
            player_slot=128,
            radiant_win=False,
            kills=18,
            deaths=6,
            assists=8,
            duration=2876,
            hero_id=138,
            net_worth=43000,
            net_worth_known=True,
            hero_damage=26000,
            hero_damage_known=True,
        ),
        MatchSummary(
            match_id=1005,
            start_time=5,
            player_slot=128,
            radiant_win=True,
            kills=5,
            deaths=9,
            assists=12,
            duration=1930,
            hero_id=138,
            net_worth=36370,
            net_worth_known=True,
            hero_damage=23227,
            hero_damage_known=True,
        ),
    ]

    rows = service.build_turbo_hero_overview_rows(matches)

    assert len(rows) == 1
    assert rows[0]["hero"] == "Muerta"
    assert rows[0]["matches"] == 5
    assert rows[0]["winrate"] == 60.0
    assert rows[0]["avg_kills"] == 8.2
    assert rows[0]["avg_deaths"] == 7.0
    assert rows[0]["avg_assists"] == 12.0
    assert round(float(rows[0]["kda"]), 1) == 2.9
    assert rows[0]["avg_duration_seconds"] == 1818.0
    assert rows[0]["avg_net_worth"] == 36714.0
    assert rows[0]["avg_damage"] == 37879.0
    assert rows[0]["max_kills"] == 18
    assert rows[0]["max_hero_damage"] == 85168
    assert round(float(rows[0]["radiant_wr"]), 2) == round((2 / 3) * 100, 2)
    assert rows[0]["dire_wr"] == 50.0


def test_recent_hero_matches_cache_only_skips_uncached_details() -> None:
    class _NoDetailClient(_FakeClient):
        def get_match_details(self, match_id: int) -> dict:
            raise AssertionError("Recent matches should not fetch uncached match details in cache-only mode")

    service = DotaAnalyticsService(client=_NoDetailClient(), cache=_FakeCache())
    matches = [
        MatchSummary(
            match_id=9001,
            start_time=1,
            player_slot=0,
            radiant_win=True,
            kills=8,
            deaths=2,
            assists=7,
            duration=1400,
            hero_id=1,
            item_0=1,
            item_1=0,
            item_2=0,
            item_3=0,
            item_4=0,
            item_5=0,
        )
    ]

    rows = service.build_recent_hero_matches(player_id=123, matches=matches, limit=10, allow_detail_fetch=False)

    assert len(rows) == 1
    assert rows[0].hero_name == "Axe"
    assert rows[0].net_worth is None
    assert rows[0].hero_damage is None
    assert [item.item_id for item in rows[0].items] == [1]
