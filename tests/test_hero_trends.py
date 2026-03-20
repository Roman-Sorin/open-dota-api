from models.dtos import MatchSummary
from services.analytics_service import DotaAnalyticsService
from tests.test_hero_damage_enrichment import _FakeCache, _FakeClient
from webapp.hero_trends import build_rolling_trend_points, build_weekly_trend_points


def _match(match_id: int, start_time: int, won: bool, kills: int, deaths: int, assists: int) -> MatchSummary:
    return MatchSummary(
        match_id=match_id,
        start_time=start_time,
        player_slot=0,
        radiant_win=won,
        kills=kills,
        deaths=deaths,
        assists=assists,
        duration=1800,
        hero_id=1,
        net_worth=20000 + match_id * 1000,
        net_worth_known=True,
        hero_damage=10000 + match_id * 500,
        hero_damage_known=True,
    )


def test_build_weekly_trend_points_groups_matches_by_week() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        _match(1, 1738540800, True, 10, 2, 8),   # 2025-02-03
        _match(2, 1738713600, False, 5, 5, 7),   # 2025-02-05
        _match(3, 1739145600, True, 8, 3, 9),    # 2025-02-10
    ]

    points = build_weekly_trend_points(matches, service.build_stats)

    assert [point.label for point in points] == ["2025-02-03", "2025-02-10"]
    assert points[0].matches == 2
    assert points[0].wins == 1
    assert points[0].losses == 1
    assert points[1].matches == 1
    assert points[1].winrate == 100.0


def test_build_rolling_trend_points_uses_requested_window() -> None:
    service = DotaAnalyticsService(client=_FakeClient(), cache=_FakeCache())
    matches = [
        _match(1, 1738540800, True, 10, 2, 8),
        _match(2, 1738627200, False, 5, 5, 7),
        _match(3, 1738713600, True, 8, 3, 9),
        _match(4, 1738800000, True, 12, 4, 10),
    ]

    points = build_rolling_trend_points(matches, service.build_stats, window_size=3)

    assert len(points) == 2
    assert points[0].label == "2025-02-05"
    assert points[0].matches == 3
    assert round(points[0].winrate, 2) == 66.67
    assert points[1].label == "2025-02-06"
    assert points[1].wins == 2
    assert points[1].losses == 1
