from __future__ import annotations

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
                }
            ],
        }


class _TrackingStratzClient:
    def __init__(self) -> None:
        self.calls = 0

    def get_match_item_purchases(self, match_id: int):
        self.calls += 1
        return [
            {
                "steamAccountId": 1233793238,
                "playerSlot": 0,
                "stats": {"itemPurchases": [{"itemId": 63, "time": 240}]},
            }
        ]


def test_get_or_fetch_match_details_does_not_use_stratz_timing_fallback() -> None:
    stratz_client = _TrackingStratzClient()
    service = DotaAnalyticsService(
        client=_FakeClient(),
        cache=_FakeCache(),
        match_store=SQLiteMatchStore(":memory:"),
        stratz_client=stratz_client,
    )

    details = service.get_or_fetch_match_details(8622417925, force_refresh=True)
    player_row = service._extract_player_from_match_details(details, player_id=1233793238, player_slot=0)  # noqa: SLF001

    assert player_row is not None
    assert player_row.get("purchase_log") is None
    assert player_row.get("first_purchase_time") is None
    assert stratz_client.calls == 0
