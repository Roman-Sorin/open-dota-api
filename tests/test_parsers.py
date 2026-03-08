from models.dtos import Intent
from parsers.input_parser import HeroParser, parse_ask_query, parse_mode
from utils.helpers import parse_days_from_period, parse_player_id


HEROES_FIXTURE = {
    "1": {"id": 1, "name": "npc_dota_hero_antimage", "localized_name": "Anti-Mage"},
    "44": {"id": 44, "name": "npc_dota_hero_phantom_assassin", "localized_name": "Phantom Assassin"},
    "81": {"id": 81, "name": "npc_dota_hero_chaos_knight", "localized_name": "Chaos Knight"},
}


def test_parse_player_id_from_url() -> None:
    url = "https://www.opendota.com/players/1233793238"
    assert parse_player_id(url) == 1233793238


def test_parse_hero_alias_ck() -> None:
    parser = HeroParser.from_constants(HEROES_FIXTURE)
    hit = parser.parse_hero("ck")
    assert hit is not None
    assert hit.hero_id == 81


def test_parse_hero_alias_fantomka_ru() -> None:
    parser = HeroParser.from_constants(HEROES_FIXTURE)
    hit = parser.parse_hero("\u0444\u0430\u043d\u0442\u043e\u043c\u043a\u0430")
    assert hit is not None
    assert hit.hero_id == 44


def test_parse_mode_turbo_ru() -> None:
    parsed = parse_mode("\u0442\u0443\u0440\u0431\u043e")
    assert parsed is not None
    assert parsed[0] == 23


def test_parse_period_two_months_ru() -> None:
    text = "\u0437\u0430 \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 2 \u043c\u0435\u0441\u044f\u0446\u0430"
    assert parse_days_from_period(text) == 60


def test_ask_period_not_treated_as_match_limit() -> None:
    parser = HeroParser.from_constants(HEROES_FIXTURE)
    query = "\u0434\u0430\u0439 \u043c\u043d\u0435 \u0441\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0443 \u043f\u043e \u0438\u0433\u0440\u043e\u043a\u0443 1233793238 \u043d\u0430 Chaos Knight \u0432 \u0442\u0443\u0440\u0431\u043e \u0437\u0430 \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 2 \u043c\u0435\u0441\u044f\u0446\u0430"
    parsed = parse_ask_query(query, parser)
    assert parsed.intent == Intent.STATS
    assert parsed.filters.limit == 20
    assert parsed.filters.days == 60


def test_ask_items_has_priority_over_stats_keyword() -> None:
    parser = HeroParser.from_constants(HEROES_FIXTURE)
    query = "\u0434\u0430\u0439 \u0441\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0443 \u043f\u043e \u043f\u043e\u043a\u0443\u043f\u043a\u0435 \u043f\u0440\u0435\u0434\u043c\u0435\u0442\u043e\u0432 \u043d\u0430 \u0444\u0430\u043d\u0442\u043e\u043c\u043a\u0435 1233793238"
    parsed = parse_ask_query(query, parser)
    assert parsed.intent == Intent.ITEMS
