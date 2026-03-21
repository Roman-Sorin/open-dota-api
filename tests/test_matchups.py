from models.dtos import MatchSummary
from services.analytics_service import DotaAnalyticsService
from tests.test_hero_damage_enrichment import _FakeCache
from webapp.matchups import MatchupRow, build_matchup_dataframe, build_matchup_rows, build_matchup_styler, sort_matchup_dataframe


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


def test_sort_matchup_dataframe_uses_numeric_winrate_not_percent_string() -> None:
    matchup_rows = [
        MatchupRow(hero_id=1, hero="Nature's Prophet", hero_image="np.png", matches=3, wins=3, losses=0, winrate=100.0, avg_kills=9.0, avg_deaths=0.0, avg_assists=8.0, kda=50.0),
        MatchupRow(hero_id=2, hero="Sniper", hero_image="sniper.png", matches=3, wins=3, losses=0, winrate=100.0, avg_kills=13.0, avg_deaths=4.0, avg_assists=13.0, kda=6.4),
        MatchupRow(hero_id=3, hero="Lion", hero_image="lion.png", matches=3, wins=1, losses=2, winrate=33.0, avg_kills=10.0, avg_deaths=6.0, avg_assists=8.0, kda=2.8),
        MatchupRow(hero_id=4, hero="Nyx Assassin", hero_image="nyx.png", matches=3, wins=1, losses=2, winrate=33.0, avg_kills=11.0, avg_deaths=7.0, avg_assists=10.0, kda=2.8),
    ]

    df = build_matchup_dataframe(matchup_rows, min_matches=3)
    worst = sort_matchup_dataframe(df, best_first=False)
    best = sort_matchup_dataframe(df, best_first=True)

    assert "Avg K/D/A" not in df.columns
    assert "KDA" not in df.columns
    assert list(worst["Hero"])[:2] == ["Lion", "Nyx Assassin"]
    assert list(best["Hero"])[:2] == ["Nature's Prophet", "Sniper"]


def test_build_matchup_styler_colors_win_loss_and_winrate() -> None:
    df = build_matchup_dataframe(
        [
            MatchupRow(hero_id=1, hero="Axe", hero_image="axe.png", matches=4, wins=3, losses=1, winrate=75.0, avg_kills=0.0, avg_deaths=0.0, avg_assists=0.0, kda=0.0),
            MatchupRow(hero_id=2, hero="Bane", hero_image="bane.png", matches=4, wins=2, losses=2, winrate=50.0, avg_kills=0.0, avg_deaths=0.0, avg_assists=0.0, kda=0.0),
            MatchupRow(hero_id=3, hero="Lion", hero_image="lion.png", matches=4, wins=1, losses=3, winrate=25.0, avg_kills=0.0, avg_deaths=0.0, avg_assists=0.0, kda=0.0),
        ],
        min_matches=1,
    )

    html = build_matchup_styler(df).to_html()

    assert "#23a55a" in html
    assert "#d9534f" in html
    assert "#d4a017" in html
