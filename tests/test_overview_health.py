from webapp.overview_health import overview_looks_stale


def test_overview_looks_stale_for_per_hero_zero_economy_and_damage_row() -> None:
    overview = [
        {
            "hero": "Ursa",
            "matches": 18,
            "avg_net_worth": 28958.0,
            "avg_damage": 22313.0,
            "max_hero_damage": 39391,
        },
        {
            "hero": "Muerta",
            "matches": 10,
            "avg_net_worth": 32692.0,
            "avg_damage": 29043.0,
            "max_hero_damage": 85168,
        },
        {
            "hero": "Viper",
            "matches": 6,
            "avg_net_worth": 0.0,
            "avg_damage": 0.0,
            "max_hero_damage": 0,
        },
    ]

    assert overview_looks_stale(overview) is True


def test_overview_looks_stale_returns_false_for_valid_multi_hero_overview() -> None:
    overview = [
        {
            "hero": "Ursa",
            "matches": 18,
            "avg_net_worth": 28958.0,
            "avg_damage": 22313.0,
            "max_hero_damage": 39391,
        },
        {
            "hero": "Muerta",
            "matches": 10,
            "avg_net_worth": 32692.0,
            "avg_damage": 29043.0,
            "max_hero_damage": 85168,
        },
    ]

    assert overview_looks_stale(overview) is False
