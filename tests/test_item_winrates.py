from models.dtos import MatchSummary
from services.analytics_service import DotaAnalyticsService


class _FakeClient:
    def get_constants_heroes(self) -> dict:
        return {"1": {"id": 1, "localized_name": "Axe", "img": "/apps/dota2/images/heroes/axe.png"}}

    def get_constants_items(self) -> dict:
        return {
            "manta": {"id": 1, "dname": "Manta Style", "img": "/apps/dota2/images/items/manta.png"},
            "nullifier": {"id": 2, "dname": "Nullifier", "img": "/apps/dota2/images/items/nullifier.png"},
            "bkb": {"id": 3, "dname": "Black King Bar", "img": "/apps/dota2/images/items/black_king_bar.png"},
            "abyssal_blade": {"id": 4, "dname": "Abyssal Blade", "img": "/apps/dota2/images/items/abyssal_blade.png"},
            "basher": {"id": 5, "dname": "Skull Basher", "img": "/apps/dota2/images/items/basher.png"},
        }

    def get_constants_patch(self) -> list[dict]:
        return [{"name": "7.40", "date": "2025-01-01T00:00:00Z"}]

    def get_match_details(self, match_id: int) -> dict:
        return {"players": []}


class _FakeCache:
    def __init__(self) -> None:
        self._store: dict[str, object] = {}

    def get(self, key: str, max_age=None):
        return self._store.get(key)

    def set(self, key: str, value: object) -> None:
        self._store[key] = value


def _match(match_id: int, won: bool, item_ids: list[int]) -> MatchSummary:
    # player_slot=0 means Radiant side; with radiant_win=won this sets did_win == won.
    return MatchSummary(
        match_id=match_id,
        start_time=0,
        player_slot=0,
        radiant_win=won,
        kills=10,
        deaths=5,
        assists=10,
        duration=1800,
        hero_id=1,
        item_0=item_ids[0] if len(item_ids) > 0 else 0,
        item_1=item_ids[1] if len(item_ids) > 1 else 0,
        item_2=item_ids[2] if len(item_ids) > 2 else 0,
        item_3=item_ids[3] if len(item_ids) > 3 else 0,
        item_4=item_ids[4] if len(item_ids) > 4 else 0,
        item_5=item_ids[5] if len(item_ids) > 5 else 0,
    )


def test_item_winrates_sorted_by_winrate_then_matches() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        _match(1, True, [1]),    # manta win
        _match(2, True, [1]),    # manta win -> 2/2 = 100%
        _match(3, False, [2]),   # nullifier loss -> 0/1 = 0%
        _match(4, True, [3]),    # bkb win
        _match(5, False, [3]),   # bkb loss
        _match(6, True, [3]),    # bkb win -> 2/3 ~= 66.7%
    ]

    rows = service.get_item_winrates(player_id=123, matches=matches, top_n=20)

    assert [row["item"] for row in rows] == ["Manta Style", "Black King Bar", "Nullifier"]
    assert rows[0]["item_winrate"] == 100.0
    assert rows[0]["matches_with_item"] == 2
    assert rows[0]["wins_with_item"] == 2
    assert "avg_kills_with_item" not in rows[0]
    assert "avg_deaths_with_item" not in rows[0]
    assert "avg_assists_with_item" not in rows[0]
    assert "kda_with_item" not in rows[0]


def test_item_winrates_cache_only_does_not_fetch_missing_match_details() -> None:
    class _NoDetailClient(_FakeClient):
        def get_match_details(self, match_id: int) -> dict:
            raise AssertionError("Item winrates should not fetch uncached match details when cache-only mode is used")

    service = DotaAnalyticsService(client=_NoDetailClient(), cache=_FakeCache())
    matches = [_match(1, True, [0, 0, 0, 0, 0, 0])]

    rows = service.get_item_winrates(player_id=123, matches=matches, top_n=20, allow_detail_fetch=False)

    assert rows == []


def test_item_winrate_snapshot_uses_cached_purchase_logs_not_just_final_slots() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        _match(match_id, True, [0, 0, 0, 0, 0, 0])
        for match_id in range(1, 65)
    ]
    detailed_ids = list(range(1, 13))
    for match_id in detailed_ids:
        service._match_details_memory_cache[match_id] = {
            "players": [
                {
                    "account_id": 123,
                    "player_slot": 0,
                    "item_0": 4 if match_id <= 5 else 1,
                    "item_1": 1,
                    "item_2": 0,
                    "item_3": 0,
                    "item_4": 0,
                    "item_5": 0,
                    "purchase_log": [
                        {"key": "abyssal_blade", "time": 1200},
                        {"key": "manta", "time": 800},
                    ],
                }
            ]
        }

    snapshot = service.get_item_winrate_snapshot(player_id=123, matches=matches, top_n=20, allow_detail_fetch=False)

    abyssal = next(row for row in snapshot.rows if row["item"] == "Abyssal Blade")
    manta = next(row for row in snapshot.rows if row["item"] == "Manta Style")
    assert snapshot.total_matches == 64
    assert snapshot.detail_backed_matches == 12
    assert snapshot.missing_matches == 52
    assert snapshot.is_complete is False
    assert abyssal["matches_with_item"] == 12
    assert manta["matches_with_item"] == 12


def test_item_winrate_snapshot_marks_summary_only_matches_as_partial() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        _match(1, True, [1]),
        _match(2, False, [0, 0, 0, 0, 0, 0]),
    ]

    snapshot = service.get_item_winrate_snapshot(player_id=123, matches=matches, top_n=20, allow_detail_fetch=False)

    assert snapshot.summary_only_matches == 1
    assert snapshot.missing_matches == 1
    assert snapshot.is_complete is False
    assert "incomplete for 1 match(es)" in snapshot.note
