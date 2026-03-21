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


def test_overview_looks_stale_for_reported_150_day_zero_rows() -> None:
    overview = [
        {"hero": "Phantom Assassin", "matches": 117, "avg_net_worth": 31679.0, "avg_damage": 29005.0, "max_hero_damage": 69486},
        {"hero": "Chaos Knight", "matches": 70, "avg_net_worth": 29870.0, "avg_damage": 26285.0, "max_hero_damage": 67891},
        {"hero": "Spectre", "matches": 65, "avg_net_worth": 45227.0, "avg_damage": 48810.0, "max_hero_damage": 53348},
        {"hero": "Wraith King", "matches": 46, "avg_net_worth": 36623.0, "avg_damage": 30819.0, "max_hero_damage": 62461},
        {"hero": "Ursa", "matches": 31, "avg_net_worth": 33103.0, "avg_damage": 24326.0, "max_hero_damage": 39391},
        {"hero": "Muerta", "matches": 10, "avg_net_worth": 32692.0, "avg_damage": 29043.0, "max_hero_damage": 85168},
        {"hero": "Viper", "matches": 6, "avg_net_worth": 0.0, "avg_damage": 0.0, "max_hero_damage": 0},
        {"hero": "Juggernaut", "matches": 3, "avg_net_worth": 0.0, "avg_damage": 0.0, "max_hero_damage": 0},
        {"hero": "Phantom Lancer", "matches": 3, "avg_net_worth": 0.0, "avg_damage": 0.0, "max_hero_damage": 0},
    ]

    assert overview_looks_stale(overview) is True
