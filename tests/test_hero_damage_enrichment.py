from datetime import date

from models.dtos import MatchSummary, QueryFilters
from services.analytics_service import DotaAnalyticsService


class _FakeClient:
    def get_constants_heroes(self) -> dict:
        return {"1": {"id": 1, "localized_name": "Axe", "img": "/apps/dota2/images/heroes/axe.png"}}

    def get_constants_items(self) -> dict:
        return {"blink": {"id": 1, "dname": "Blink Dagger", "img": "/apps/dota2/images/items/blink.png"}}

    def get_constants_patch(self) -> list[dict]:
        return [{"name": "7.40", "date": "2025-01-01T00:00:00Z"}]


class _FakeCache:
    def __init__(self) -> None:
        self._store: dict[str, object] = {}

    def get(self, key: str):
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
        "players": [{"account_id": 123, "player_slot": 0, "hero_damage": 32123}]
    }

    service.enrich_hero_damage(player_id=123, matches=matches, max_fallback_detail_calls=3)

    assert matches[0].hero_damage == 32123


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
