from __future__ import annotations

from services.analytics_service import DotaAnalyticsService
from utils.cache import JsonFileCache
from utils.match_store import SQLiteMatchStore


class _FakeClient:
    def __init__(self) -> None:
        self.timeout_seconds = 20

    def get_constants_heroes(self):
        return {
            "npc_dota_hero_phantom_assassin": {
                "id": 44,
                "localized_name": "Phantom Assassin",
                "img": "/apps/dota2/images/dota_react/heroes/phantom_assassin.png",
            }
        }

    def get_constants_items(self):
        return {
            "quelling_blade": {"id": 11, "dname": "Quelling Blade", "img": "/apps/dota2/images/dota_react/items/quelling_blade.png"},
            "phase_boots": {"id": 50, "dname": "Phase Boots", "img": "/apps/dota2/images/dota_react/items/phase_boots.png"},
            "poor_mans_shield": {"id": 73, "dname": "Poor Man's Shield", "img": "/apps/dota2/images/dota_react/items/poor_mans_shield.png"},
            "magic_stick": {"id": 34, "dname": "Magic Stick", "img": "/apps/dota2/images/dota_react/items/magic_stick.png"},
            "magic_wand": {"id": 36, "dname": "Magic Wand", "img": "/apps/dota2/images/dota_react/items/magic_wand.png"},
        }

    def get_constants_patch(self):
        return []


class _FakeStratzClient:
    def get_match_item_purchases(self, match_id: int):
        return [
            {
                "steamAccountId": 1233793238,
                "playerSlot": 2,
                "stats": {
                    "itemPurchases": [
                        {"itemId": 11, "time": -89},
                        {"itemId": 73, "time": 88},
                        {"itemId": 36, "time": 110},
                    ]
                },
            }
        ]


def test_stratz_enrichment_completes_pending_parse_request(tmp_path) -> None:
    store = SQLiteMatchStore(tmp_path / "matches.sqlite3")
    try:
        service = DotaAnalyticsService(
            client=_FakeClient(),
            cache=JsonFileCache(tmp_path / "json-cache"),
            match_store=store,
            stratz_client=_FakeStratzClient(),
        )
        details = {
            "players": [
                {
                    "account_id": 1233793238,
                    "player_slot": 2,
                }
            ]
        }
        store.upsert_match_detail(8622417925, details)
        store.upsert_match_parse_request(
            8622417925,
            1233793238,
            status="pending",
            requested_at="2026-04-08T00:00:00+00:00",
        )

        changed = service._enrich_match_details_with_stratz_timings(8622417925, details)
        parse_request = store.get_match_parse_request(8622417925)
        enriched = store.get_match_detail(8622417925)
        player = (enriched or {}).get("players", [{}])[0]

        assert changed is True
        assert parse_request is not None
        assert parse_request["status"] == "completed"
        assert parse_request["completed_at"] is not None
        assert len(player.get("purchase_log") or []) == 3
        assert isinstance(player.get("first_purchase_time"), dict)
        assert enriched["timing_source"] == "stratz_fallback"
    finally:
        store.close()
