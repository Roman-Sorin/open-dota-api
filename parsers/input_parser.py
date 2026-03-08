from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from models.dtos import Intent, ParsedAskQuery, QueryFilters
from utils.exceptions import ValidationError
from utils.helpers import RU_TURBO, parse_days_from_period, parse_player_id


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


@dataclass(slots=True)
class HeroHit:
    hero_id: int
    hero_name: str


class HeroParser:
    def __init__(self, heroes: dict[int, str], aliases: dict[str, int]) -> None:
        self.heroes = heroes
        self.aliases = aliases

    @classmethod
    def from_constants(cls, heroes_constants: dict[str, dict]) -> "HeroParser":
        by_id: dict[int, str] = {}
        alias_map: dict[str, int] = {}
        name_to_id: dict[str, int] = {}

        for hero in heroes_constants.values():
            hero_id = int(hero["id"])
            localized = str(hero.get("localized_name", "")).strip()
            machine = str(hero.get("name", "")).replace("npc_dota_hero_", "").replace("_", " ").strip()

            preferred = localized or machine
            by_id[hero_id] = preferred
            name_to_id[_normalize(preferred)] = hero_id

            candidates = {preferred, machine}
            for name in list(candidates):
                tokens = [p for p in name.split() if p]
                if len(tokens) >= 2:
                    candidates.add("".join(t[0] for t in tokens))

            for candidate in candidates:
                normalized = _normalize(candidate)
                if normalized:
                    alias_map[normalized] = hero_id

        # Centralized extra aliases for common RU nicknames/short forms.
        extra_alias_to_hero_name = {
            "\u0444\u0430\u043d\u0442\u043e\u043c\u043a\u0430": "Phantom Assassin",
            "\u043f\u0430": "Phantom Assassin",
            "\u0446\u043a": "Chaos Knight",
            "\u0430\u043c": "Anti-Mage",
            "\u0432\u043a": "Wraith King",
        }
        for alias, hero_name in extra_alias_to_hero_name.items():
            hero_id = name_to_id.get(_normalize(hero_name))
            if hero_id is not None:
                alias_map[_normalize(alias)] = hero_id

        return cls(heroes=by_id, aliases=alias_map)

    def parse_hero(self, text: str) -> HeroHit | None:
        normalized = _normalize(text)
        if not normalized:
            return None

        if normalized in self.aliases:
            hero_id = self.aliases[normalized]
            return HeroHit(hero_id=hero_id, hero_name=self.heroes[hero_id])

        for alias, hero_id in sorted(self.aliases.items(), key=lambda kv: len(kv[0]), reverse=True):
            if len(alias) < 2:
                continue
            if re.search(rf"\b{re.escape(alias)}\b", normalized):
                return HeroHit(hero_id=hero_id, hero_name=self.heroes[hero_id])

        return None

    def suggest(self, text: str, limit: int = 5) -> list[str]:
        normalized = _normalize(text)
        scored: list[tuple[int, str]] = []
        for hero_name in self.heroes.values():
            low = hero_name.lower()
            score = 0
            if normalized in low:
                score = 3
            elif any(part in low for part in normalized.split()):
                score = 1
            if score > 0:
                scored.append((score, hero_name))

        scored.sort(key=lambda x: (-x[0], x[1]))
        return [name for _, name in scored[:limit]]


RU_ITEM = "\u043f\u0440\u0435\u0434\u043c\u0435\u0442"
RU_SLOT = "\u0441\u043b\u043e\u0442"
RU_LAST = "\u043f\u043e\u0441\u043b\u0435\u0434\u043d"
RU_MATCH = "\u043c\u0430\u0442\u0447"
RU_GAME = "\u0438\u0433\u0440"
RU_STATS = "\u0441\u0442\u0430\u0442"
RU_WINRATE = "\u0432\u0438\u043d\u0440\u0435\u0439\u0442"
RU_BUY = "\u043f\u043e\u043a\u0443\u043f"


def parse_mode(text: str) -> tuple[int, str] | None:
    lowered = text.lower()
    if "turbo" in lowered or RU_TURBO in lowered:
        return 23, "Turbo"
    return None


def detect_intent(text: str) -> Intent:
    lowered = text.lower()
    if any(word in lowered for word in ("item", RU_ITEM, RU_SLOT, RU_BUY, "bkb", "purchase")):
        return Intent.ITEMS
    if any(word in lowered for word in (RU_STATS, "stat", "kda", "winrate", RU_WINRATE)):
        return Intent.STATS
    if any(word in lowered for word in ("match", RU_MATCH, RU_GAME, "games")):
        return Intent.MATCHES
    return Intent.STATS


def parse_limit(text: str, default_limit: int = 20) -> int:
    lowered = text.lower()
    match = re.search(
        rf"(?:{RU_LAST}\w*|last)\s+(\d+)\s*(?:{RU_MATCH}\w*|{RU_GAME}\w*|match(?:es)?|games?)",
        lowered,
    )
    if match:
        return max(1, min(int(match.group(1)), 100))
    return default_limit


def parse_ask_query(text: str, hero_parser: HeroParser) -> ParsedAskQuery:
    try:
        player_id = parse_player_id(text)
    except ValueError as exc:
        raise ValidationError(
            "Player id was not found in query. Provide OpenDota profile URL or numeric id."
        ) from exc

    hero_hit = hero_parser.parse_hero(text)
    mode = parse_mode(text)
    days = parse_days_from_period(text)
    intent = detect_intent(text)
    limit = parse_limit(text)

    return ParsedAskQuery(
        intent=intent,
        filters=QueryFilters(
            player_id=player_id,
            hero_id=hero_hit.hero_id if hero_hit else None,
            hero_name=hero_hit.hero_name if hero_hit else None,
            game_mode=mode[0] if mode else None,
            game_mode_name=mode[1] if mode else None,
            days=days,
            limit=limit,
        ),
    )


def parse_player_input(raw: str) -> int:
    try:
        return parse_player_id(raw)
    except ValueError as exc:
        raise ValidationError("Unable to parse player id. Use numeric id or OpenDota URL") from exc


def find_hero_by_name(name: str, hero_parser: HeroParser) -> HeroHit:
    hit = hero_parser.parse_hero(name)
    if hit:
        return hit

    suggestions = hero_parser.suggest(name)
    suggestion_text = ", ".join(suggestions) if suggestions else "No close matches"
    raise ValidationError(f"Hero '{name}' was not found. Suggestions: {suggestion_text}")


def ensure_required_filters(player_id: int, hero_id: int | None, mode: int | None, days: int | None) -> None:
    _ = (player_id, hero_id, mode, days)


def parse_days(days: int | None, fallback: int = 60) -> int:
    return fallback if days is None else max(1, days)


def list_hero_names(hero_parser: HeroParser) -> Iterable[str]:
    return hero_parser.heroes.values()
