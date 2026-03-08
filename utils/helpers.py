from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re


PLAYER_URL_RE = re.compile(r"opendota\.com/players/(\d+)", re.IGNORECASE)
INTEGER_RE = re.compile(r"\b(\d{6,12})\b")

# Russian keywords encoded explicitly to avoid shell/codepage corruption.
RU_TURBO = "\u0442\u0443\u0440\u0431\u043e"
RU_MONTH = "\u043c\u0435\u0441\u044f\u0446"
RU_MONTHS_1 = "\u043c\u0435\u0441\u044f\u0446\u0430"
RU_MONTHS_2 = "\u043c\u0435\u0441\u044f\u0446\u0435\u0432"
RU_DAY = "\u0434\u0435\u043d\u044c"
RU_DAYS_1 = "\u0434\u043d\u044f"
RU_DAYS_2 = "\u0434\u043d\u0435\u0439"
RU_FOR_MONTH = "\u0437\u0430 \u043c\u0435\u0441\u044f\u0446"
RU_FOR_2_MONTHS = "\u0437\u0430 2 \u043c\u0435\u0441\u044f\u0446\u0430"


def parse_player_id(value: str) -> int:
    text = value.strip()
    match = PLAYER_URL_RE.search(text)
    if match:
        return int(match.group(1))

    if text.isdigit():
        return int(text)

    fallback = INTEGER_RE.search(text)
    if fallback:
        return int(fallback.group(1))

    raise ValueError("Could not parse player id from input")


def calculate_kda_ratio(kills: float, deaths: float, assists: float) -> float:
    if deaths <= 0:
        return float(kills + assists)
    return (kills + assists) / deaths


def winrate_percent(wins: int, total: int) -> float:
    if total == 0:
        return 0.0
    return (wins / total) * 100.0


def parse_days_from_period(text: str) -> int | None:
    lowered = text.lower()

    month_match = re.search(
        rf"(\d+)\s*({RU_MONTH}|{RU_MONTHS_1}|{RU_MONTHS_2}|month|months)",
        lowered,
    )
    if month_match:
        return int(month_match.group(1)) * 30

    day_match = re.search(rf"(\d+)\s*({RU_DAYS_2}|{RU_DAYS_1}|{RU_DAY}|day|days)", lowered)
    if day_match:
        return int(day_match.group(1))

    if RU_FOR_MONTH in lowered or "last month" in lowered:
        return 30

    if RU_FOR_2_MONTHS in lowered:
        return 60

    return None


def format_duration(seconds: int) -> str:
    minutes = seconds // 60
    sec = seconds % 60
    return f"{minutes:02d}:{sec:02d}"


def unix_to_dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def since_days(days: int) -> datetime:
    return datetime.now(tz=timezone.utc) - timedelta(days=days)
