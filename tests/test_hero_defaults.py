from webapp.hero_defaults import default_hero_id


def test_default_hero_id_prefers_spectre() -> None:
    hero_names = {
        1: "Axe",
        67: "Spectre",
        42: "Wraith King",
    }

    assert default_hero_id([1, 67, 42], hero_names.__getitem__) == 67


def test_default_hero_id_falls_back_to_first_option_when_spectre_missing() -> None:
    hero_names = {
        1: "Axe",
        42: "Wraith King",
    }

    assert default_hero_id([42, 1], hero_names.__getitem__) == 42
