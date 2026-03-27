from models.dtos import QueryFilters
from services.analytics_service import DotaAnalyticsService
from utils.match_filters import is_excluded_match_id
from utils.match_store import SQLiteMatchStore


class _FakeClient:
    def __init__(self, matches: list[dict] | None = None) -> None:
        self.matches = matches or []
        self.calls = 0

    def get_constants_heroes(self) -> dict:
        return {"67": {"id": 67, "localized_name": "Spectre", "img": "/apps/dota2/images/heroes/spectre.png"}}

    def get_constants_items(self) -> dict:
        return {}

    def get_constants_patch(self) -> list[dict]:
        return [{"name": "7.41", "date": "2026-03-24T00:00:00Z"}]

    def get_player_matches(self, **kwargs):
        self.calls += 1
        return list(self.matches)

    def get_match_details(self, match_id: int) -> dict:
        return {"match_id": match_id, "players": []}


class _FakeCache:
    def __init__(self) -> None:
        self._store: dict[str, object] = {}

    def get(self, key: str, max_age=None):
        return self._store.get(key)

    def set(self, key: str, value: object) -> None:
        self._store[key] = value


def test_is_excluded_match_id_tracks_reported_match() -> None:
    assert is_excluded_match_id(8743652071) is True
    assert is_excluded_match_id(8745970611) is True


def test_fetch_matches_excludes_reported_match_from_direct_client_results() -> None:
    client = _FakeClient(
        matches=[
            {
                "match_id": 8743652071,
                "start_time": 1774396800,
                "player_slot": 0,
                "radiant_win": False,
                "game_mode": 23,
                "kills": 7,
                "deaths": 18,
                "assists": 2,
                "duration": 790,
                "hero_id": 67,
                "hero_damage": 17300,
                "net_worth": 32700,
            },
            {
                "match_id": 8745970611,
                "start_time": 1774596800,
                "player_slot": 0,
                "radiant_win": False,
                "game_mode": 23,
                "kills": 4,
                "deaths": 12,
                "assists": 6,
                "duration": 1105,
                "hero_id": 67,
                "hero_damage": 14500,
                "net_worth": 21900,
            },
            {
                "match_id": 8743652999,
                "start_time": 1774397800,
                "player_slot": 0,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 12,
                "deaths": 3,
                "assists": 8,
                "duration": 1200,
                "hero_id": 67,
                "hero_damage": 22000,
                "net_worth": 28000,
            },
        ]
    )
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=None)

    matches = service.fetch_matches(QueryFilters(player_id=123, hero_id=67, game_mode=23, game_mode_name="Turbo"))
    stats = service.build_stats(matches)

    assert [match.match_id for match in matches] == [8743652999]
    assert stats.matches == 1
    assert stats.wins == 1
    assert stats.losses == 0


def test_get_cached_matches_excludes_reported_match_from_sqlite_store() -> None:
    client = _FakeClient()
    store = SQLiteMatchStore(":memory:")
    service = DotaAnalyticsService(client=client, cache=_FakeCache(), match_store=store)
    store.upsert_player_matches(
        123,
        [
            {
                "match_id": 8743652071,
                "start_time": 1774396800,
                "player_slot": 0,
                "radiant_win": False,
                "game_mode": 23,
                "kills": 7,
                "deaths": 18,
                "assists": 2,
                "duration": 790,
                "hero_id": 67,
                "hero_damage": 17300,
                "net_worth": 32700,
            },
            {
                "match_id": 8745970611,
                "start_time": 1774596800,
                "player_slot": 0,
                "radiant_win": False,
                "game_mode": 23,
                "kills": 4,
                "deaths": 12,
                "assists": 6,
                "duration": 1105,
                "hero_id": 67,
                "hero_damage": 14500,
                "net_worth": 21900,
            },
            {
                "match_id": 8743652999,
                "start_time": 1774397800,
                "player_slot": 0,
                "radiant_win": True,
                "game_mode": 23,
                "kills": 12,
                "deaths": 3,
                "assists": 8,
                "duration": 1200,
                "hero_id": 67,
                "hero_damage": 22000,
                "net_worth": 28000,
            },
        ],
    )

    matches = service.get_cached_matches(QueryFilters(player_id=123, hero_id=67, game_mode=23, game_mode_name="Turbo"))
    stats = service.build_stats(matches)

    assert [match.match_id for match in matches] == [8743652999]
    assert stats.matches == 1
    assert stats.wins == 1
    assert stats.losses == 0
