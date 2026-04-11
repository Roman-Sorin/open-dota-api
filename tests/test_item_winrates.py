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
            "tango": {"id": 6, "dname": "Tango", "img": "/apps/dota2/images/items/tango.png"},
            "magic_stick": {"id": 7, "dname": "Magic Stick", "img": "/apps/dota2/images/items/magic_stick.png"},
            "branches": {"id": 8, "dname": "Iron Branch", "img": "/apps/dota2/images/items/branches.png"},
            "quelling_blade": {"id": 9, "dname": "Quelling Blade", "img": "/apps/dota2/images/items/quelling_blade.png"},
            "tpscroll": {"id": 10, "dname": "Town Portal Scroll", "img": "/apps/dota2/images/items/tpscroll.png"},
            "ultimate_scepter": {"id": 108, "dname": "Aghanim's Scepter", "img": "/apps/dota2/images/items/ultimate_scepter.png"},
            "moon_shard": {"id": 247, "dname": "Moon Shard", "img": "/apps/dota2/images/items/moon_shard.png"},
            "aghanims_shard": {"id": 609, "dname": "Aghanim's Shard", "img": "/apps/dota2/images/items/aghanims_shard.png"},
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


def test_item_winrate_snapshot_ignores_purchase_log_only_items_and_counts_final_inventory_and_backpack() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        _match(match_id, True, [0, 0, 0, 0, 0, 0])
        for match_id in range(1, 9)
    ]
    detailed_ids = list(range(1, 7))
    for match_id in detailed_ids:
        service._match_details_memory_cache[match_id] = {
            "players": [
                {
                    "account_id": 123,
                    "player_slot": 0,
                    "item_0": 1,
                    "item_1": 0,
                    "item_2": 0,
                    "item_3": 0,
                    "item_4": 0,
                    "item_5": 0,
                    "backpack_0": 4 if match_id <= 4 else 0,
                    "backpack_1": 0,
                    "backpack_2": 0,
                    "purchase_log": [
                        {"key": "tango", "time": 0},
                        {"key": "magic_stick", "time": 0},
                        {"key": "branches", "time": 0},
                        {"key": "quelling_blade", "time": 0},
                        {"key": "tpscroll", "time": 0},
                        {"key": "manta", "time": 800},
                        {"key": "abyssal_blade", "time": 1200},
                    ],
                }
            ]
        }

    snapshot = service.get_item_winrate_snapshot(player_id=123, matches=matches, top_n=20, allow_detail_fetch=False)

    abyssal = next(row for row in snapshot.rows if row["item"] == "Abyssal Blade")
    manta = next(row for row in snapshot.rows if row["item"] == "Manta Style")
    assert snapshot.total_matches == 8
    assert snapshot.detail_backed_matches == 6
    assert snapshot.missing_matches == 2
    assert snapshot.is_complete is False
    assert abyssal["matches_with_item"] == 4
    assert manta["matches_with_item"] == 6
    assert all(
        row["item"] not in {"Tango", "Magic Stick", "Iron Branch", "Quelling Blade", "Town Portal Scroll"}
        for row in snapshot.rows
    )
    assert "final-inventory/backpack coverage for 6 match(es)" in snapshot.note


def test_item_winrates_mix_summary_slots_with_cached_detail_backpack_without_counting_purchase_log_noise() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        _match(1, True, [1]),
        _match(2, False, [0, 0, 0, 0, 0, 0]),
        _match(3, True, [0, 0, 0, 0, 0, 0]),
    ]
    service._match_details_memory_cache[2] = {
        "players": [
            {
                "account_id": 123,
                "player_slot": 0,
                "item_0": 0,
                "item_1": 0,
                "item_2": 0,
                "item_3": 0,
                "item_4": 0,
                "item_5": 0,
                "backpack_0": 4,
                "backpack_1": 0,
                "backpack_2": 0,
                "purchase_log": [
                    {"key": "tango", "time": 0},
                    {"key": "magic_stick", "time": 0},
                ],
            }
        ]
    }
    service._match_details_memory_cache[3] = {
        "players": [
            {
                "account_id": 123,
                "player_slot": 0,
                "item_0": 0,
                "item_1": 0,
                "item_2": 0,
                "item_3": 0,
                "item_4": 0,
                "item_5": 0,
                "backpack_0": 0,
                "backpack_1": 0,
                "backpack_2": 0,
                "purchase_log": [
                    {"key": "tango", "time": 0},
                    {"key": "magic_stick", "time": 0},
                ],
            }
        ]
    }

    rows = service.get_item_winrates(player_id=123, matches=matches, top_n=20, allow_detail_fetch=False)

    assert [row["item"] for row in rows] == ["Manta Style", "Abyssal Blade"]
    assert next(row for row in rows if row["item"] == "Manta Style")["matches_with_item"] == 1
    assert next(row for row in rows if row["item"] == "Abyssal Blade")["matches_with_item"] == 1


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


def test_item_winrate_snapshot_includes_consumed_buffs_from_cached_details() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        _match(1, True, [1]),
        _match(2, False, [1]),
    ]
    service._match_details_memory_cache[1] = {
        "players": [
            {
                "account_id": 123,
                "player_slot": 0,
                "item_0": 1,
                "item_1": 0,
                "item_2": 0,
                "item_3": 0,
                "item_4": 0,
                "item_5": 0,
                "aghanims_scepter": 1,
                "permanent_buffs": [{"permanent_buff": 2, "grant_time": 900}],
            }
        ]
    }
    service._match_details_memory_cache[2] = {
        "players": [
            {
                "account_id": 123,
                "player_slot": 0,
                "item_0": 1,
                "item_1": 0,
                "item_2": 0,
                "item_3": 0,
                "item_4": 0,
                "item_5": 0,
                "aghanims_scepter": 1,
                "permanent_buffs": [{"permanent_buff": 2, "grant_time": 960}],
            }
        ]
    }

    snapshot = service.get_item_winrate_snapshot(player_id=123, matches=matches, top_n=20, allow_detail_fetch=False)

    scepter = next(row for row in snapshot.rows if row["item"] == "Aghanim's Scepter")
    assert scepter["matches_with_item"] == 2
    assert scepter["wins_with_item"] == 1
    assert scepter["is_buff"] is True


def test_item_winrate_snapshot_does_not_mark_inventory_moon_shard_as_buff() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        _match(1, True, [247]),
        _match(2, False, [247]),
    ]
    service._match_details_memory_cache[1] = {
        "players": [
            {
                "account_id": 123,
                "player_slot": 0,
                "item_0": 247,
                "item_1": 0,
                "item_2": 0,
                "item_3": 0,
                "item_4": 0,
                "item_5": 0,
                "first_purchase_time": {"moon_shard": 600},
            }
        ]
    }
    service._match_details_memory_cache[2] = {
        "players": [
            {
                "account_id": 123,
                "player_slot": 0,
                "item_0": 247,
                "item_1": 0,
                "item_2": 0,
                "item_3": 0,
                "item_4": 0,
                "item_5": 0,
                "first_purchase_time": {"moon_shard": 660},
            }
        ]
    }

    snapshot = service.get_item_winrate_snapshot(player_id=123, matches=matches, top_n=20, allow_detail_fetch=False)

    moon_shard = next(row for row in snapshot.rows if row["item"] == "Moon Shard")
    assert moon_shard["matches_with_item"] == 2
    assert moon_shard["is_buff"] is False
