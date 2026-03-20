from webapp.hero_overview import (
    HERO_LOSSES_COLUMN,
    HERO_MATCHES_COLUMN,
    HERO_OVERVIEW_COLUMN_ORDER,
    HERO_WINS_COLUMN,
    build_hero_overview_row,
)


def test_hero_overview_row_uses_short_english_columns_and_formats_kda() -> None:
    row = build_hero_overview_row(
        {
            "hero": "Chaos Knight",
            "hero_image": "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/chaos_knight.png",
            "matches": 63,
            "wins": 38,
            "losses": 25,
            "winrate": 60.0,
            "avg_kills": 9.0,
            "avg_deaths": 5.0,
            "avg_assists": 9.0,
            "kda": 3.3,
            "avg_duration_seconds": 1507.0,
            "avg_net_worth": 29069.0,
            "avg_damage": 25002.0,
            "max_kills": 22,
            "max_hero_damage": 83436,
            "radiant_wr": 61.0,
            "dire_wr": 60.0,
        }
    )

    assert list(row.keys()) == HERO_OVERVIEW_COLUMN_ORDER
    assert row[HERO_MATCHES_COLUMN] == 63
    assert row[HERO_WINS_COLUMN] == 38
    assert row[HERO_LOSSES_COLUMN] == 25
    assert row["KDA"] == "3.3"
    assert row["WR"] == "60%"
    assert row["Dur"] == "25:07"
