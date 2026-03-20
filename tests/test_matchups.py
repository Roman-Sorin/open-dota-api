from models.dtos import MatchSummary
from services.analytics_service import DotaAnalyticsService
from tests.test_hero_damage_enrichment import _FakeCache
from webapp.matchups import build_matchup_rows


class _MatchupClient:
    def get_constants_heroes(self) -> dict:
        return {
            "1": {"id": 1, "localized_name": "Axe", "img": "/apps/dota2/images/heroes/axe.png"},
            "2": {"id": 2, "localized_name": "Bane", "img": "/apps/dota2/images/heroes/bane.png"},
            "3": {"id": 3, "localized_name": "Crystal Maiden", "img": "/apps/dota2/images/heroes/crystal_maiden.png"},
            "4": {"id": 4, "localized_name": "Drow Ranger", "img": "/apps/dota2/images/heroes/drow_ranger.png"},
        }

    def get_constants_items(self) -> dict:
        return {}

    def get_constants_patch(self) -> list[dict]:
        return [{"name": "7.40", "date": "2025-01-01T00:00:00Z"}]


def test_build_matchup_rows_tracks_with_and_against() -> None:
    service = DotaAnalyticsService(client=_MatchupClient(), cache=_FakeCache())
    matches = [
        MatchSummary(match_id=1, start_time=1, player_slot=0, radiant_win=True, kills=10, deaths=2, assists=8, duration=1800, hero_id=1),
        MatchSummary(match_id=2, start_time=2, player_slot=0, radiant_win=False, kills=4, deaths=5, assists=7, duration=1800, hero_id=1),
    ]
    details = {
        1: {
            "players": [
                {"account_id": 123, "player_slot": 0, "hero_id": 1},
                {"player_slot": 1, "hero_id": 2},
                {"player_slot": 128, "hero_id": 3},
            ]
        },
        2: {
            "players": [
                {"account_id": 123, "player_slot": 0, "hero_id": 1},
                {"player_slot": 1, "hero_id": 2},
                {"player_slot": 128, "hero_id": 4},
            ]
        },
    }

    rows = build_matchup_rows(
        matches=matches,
        detail_lookup=lambda match_id: details[match_id],
        extract_player=service._extract_player_from_match_details,
        player_id=123,
        resolve_hero_name=service.resolve_hero_name,
        resolve_hero_image=service.resolve_hero_image,
    )

    assert rows["with"][0].hero == "Bane"
    assert rows["with"][0].matches == 2
    assert rows["with"][0].winrate == 50.0
    assert [row.hero for row in rows["against"]] == ["Crystal Maiden", "Drow Ranger"]
