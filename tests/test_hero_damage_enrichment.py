from datetime import date

from models.dtos import MatchSummary, QueryFilters
from services.analytics_service import DotaAnalyticsService


class _FakeClient:
    def get_constants_heroes(self) -> dict:
        return {"1": {"id": 1, "localized_name": "Axe", "img": "/apps/dota2/images/heroes/axe.png"}}

    def get_constants_items(self) -> dict:
        return {
            "blink": {"id": 1, "dname": "Blink Dagger", "img": "/apps/dota2/images/items/blink.png"},
            "power_treads": {"id": 63, "dname": "Power Treads", "img": "/apps/dota2/images/items/power_treads.png"},
            "armlet": {"id": 114, "dname": "Armlet of Mordiggian", "img": "/apps/dota2/images/items/armlet.png"},
            "skadi": {"id": 160, "dname": "Eye of Skadi", "img": "/apps/dota2/images/items/skadi.png"},
            "orchid": {"id": 151, "dname": "Orchid Malevolence", "img": "/apps/dota2/images/items/orchid.png"},
            "heart": {"id": 108, "dname": "Heart of Tarrasque", "img": "/apps/dota2/images/items/heart.png"},
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
            item_4=108,
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
                "item_4": 108,
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
    assert [item.item_id for item in rows[0].items] == [63, 114, 160, 151, 108, 1]
    assert [item.purchase_time_min for item in rows[0].items] == [3, 5, 23, 9, 17, 12]
