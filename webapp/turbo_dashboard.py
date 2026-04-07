from pathlib import Path
from bisect import bisect_right
from datetime import date, datetime, timedelta
import html
import inspect
import os
import re
import subprocess
import sys
import time
from types import SimpleNamespace

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clients.opendota_client import OpenDotaClient
from models.dtos import MatchSummary, QueryFilters
from services.analytics_service import DotaAnalyticsService
from utils.cache import JsonFileCache
from utils.config import get_cache_dir, get_match_store_path, get_settings
from utils.exceptions import OpenDotaError, OpenDotaNotFoundError, OpenDotaRateLimitError, ValidationError
from utils.helpers import format_duration, parse_player_id
from utils.match_store import SQLiteMatchStore
from webapp.dashboard_state import build_hero_snapshot_request_key
from webapp.filter_defaults import default_patch_selection
from webapp.hero_defaults import default_hero_id
from webapp.hero_overview import (
    HERO_DETAIL_METRIC_ORDER,
    HERO_LOSSES_COLUMN,
    HERO_OVERVIEW_COLUMN_ORDER,
    HERO_WINS_COLUMN,
    build_hero_detail_cards,
    build_hero_overview_row,
)
from webapp.hero_trends import build_daily_trend_points
from webapp import matchups as matchup_utils
from webapp.overview_health import overview_looks_stale
from webapp.styling import apply_cell_style


st.set_page_config(page_title="Turbo Buff", layout="wide")
OVERVIEW_SCHEMA_VERSION = 15
ITEM_WINRATES_SCHEMA_VERSION = 3
CONSUMABLE_BUFF_ITEM_KEYS: dict[str, int] = {
    "moon_shard": 247,
    "ultimate_scepter": 108,
    "aghanims_shard": 609,
}
PERMANENT_BUFF_ITEM_KEYS: dict[int, str] = {
    1: "moon_shard",
    2: "ultimate_scepter",
    12: "aghanims_shard",
}
DEFAULT_FILTER_BASELINE_DATE = date(2026, 3, 24)

st.markdown(
    """
    <style>
    .metrics-wrap {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        margin: 0.5rem 0 1rem 0;
    }
    .metric-card {
        flex: 1 1 150px;
        border: 1px solid rgba(49, 51, 63, 0.2);
        border-radius: 0.5rem;
        padding: 0.6rem 0.7rem;
        background: rgba(255, 255, 255, 0.02);
    }
    .metric-label {
        font-size: 0.78rem;
        opacity: 0.85;
    }
    .metric-value {
        font-size: 1.05rem;
        font-weight: 700;
        line-height: 1.2;
        margin-top: 0.2rem;
    }
    .hero-select-preview {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        margin: 0.35rem 0 0.75rem 0;
        padding: 0.45rem 0.55rem;
        border: 1px solid rgba(49, 51, 63, 0.2);
        border-radius: 0.45rem;
        background: rgba(255, 255, 255, 0.02);
    }
    .hero-select-preview img {
        width: 34px;
        height: 34px;
        border-radius: 4px;
        object-fit: cover;
    }
    .hero-select-name {
        font-size: 0.92rem;
        font-weight: 700;
        line-height: 1.1;
    }
    .hero-select-meta {
        font-size: 0.78rem;
        opacity: 0.85;
        margin-top: 0.1rem;
    }
    .recent-matches-wrap {
        overflow-x: auto;
        margin-top: 0.5rem;
    }
    .recent-matches-table {
        width: 100%;
        min-width: 760px;
        border-collapse: collapse;
        font-size: 0.84rem;
    }
    .recent-matches-table th {
        text-align: left;
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        opacity: 0.72;
        padding: 0.45rem 0.55rem;
        border-bottom: 1px solid rgba(49, 51, 63, 0.18);
        white-space: nowrap;
    }
    .recent-matches-table td {
        padding: 0.55rem;
        border-bottom: 1px solid rgba(49, 51, 63, 0.1);
        vertical-align: middle;
    }
    .recent-hero-cell {
        min-width: 150px;
    }
    .recent-hero-wrap {
        display: flex;
        align-items: center;
        gap: 0.55rem;
    }
    .recent-hero-icon-wrap {
        position: relative;
        width: 38px;
        height: 38px;
        flex: 0 0 38px;
    }
    .recent-hero-icon-wrap img {
        width: 38px;
        height: 38px;
        border-radius: 6px;
        display: block;
    }
    .recent-hero-level,
    .recent-hero-variant {
        position: absolute;
        min-width: 16px;
        height: 16px;
        padding: 0 4px;
        border-radius: 999px;
        font-size: 0.6rem;
        font-weight: 700;
        line-height: 16px;
        text-align: center;
        color: #fff;
        background: rgba(17, 24, 39, 0.92);
        border: 1px solid rgba(255, 255, 255, 0.16);
    }
    .recent-hero-level {
        top: -5px;
        left: -5px;
    }
    .recent-hero-variant {
        right: -5px;
        bottom: -5px;
    }
    .recent-hero-name {
        font-weight: 700;
        line-height: 1.1;
    }
    .recent-result {
        font-weight: 700;
        white-space: nowrap;
    }
    .recent-result.win {
        color: #23a55a;
    }
    .recent-result.loss {
        color: #d9534f;
    }
    .recent-when {
        white-space: nowrap;
        opacity: 0.78;
        font-size: 0.72rem;
        margin-top: 0.12rem;
    }
    .recent-duration-value,
    .recent-kda-value {
        white-space: nowrap;
        font-weight: 700;
    }
    .recent-bar {
        width: 100%;
        height: 6px;
        border-radius: 999px;
        overflow: hidden;
        background: rgba(255, 255, 255, 0.08);
        margin-top: 0.32rem;
    }
    .recent-bar-fill {
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, #d97706 0%, #f59e0b 100%);
    }
    .recent-kda-bar {
        display: flex;
        width: 100%;
        height: 6px;
        border-radius: 999px;
        overflow: hidden;
        background: rgba(255, 255, 255, 0.08);
        margin-top: 0.32rem;
    }
    .recent-kda-kills {
        background: #c2410c;
    }
    .recent-kda-deaths {
        background: #6b7280;
    }
    .recent-kda-assists {
        background: #15803d;
    }
    .recent-stat-value {
        white-space: nowrap;
        font-weight: 700;
    }
    .recent-items-inline {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 0.35rem;
        min-width: 236px;
    }
    .recent-items-main {
        display: flex;
        align-items: flex-start;
        gap: 0.35rem;
        min-width: 0;
    }
    .recent-items-buffs {
        display: flex;
        align-items: flex-start;
        justify-content: flex-end;
        gap: 0.35rem;
        margin-left: auto;
        min-width: 0;
    }
    .recent-items-inline.empty {
        opacity: 0.65;
    }
    .recent-item-inline {
        position: relative;
        width: 34px;
        flex: 0 0 34px;
        display: inline-flex;
        align-items: flex-start;
        justify-content: center;
        padding-bottom: 0.15rem;
    }
    .recent-item-inline img {
        width: 34px;
        height: auto;
        border-radius: 5px;
        display: block;
        margin: 0 auto;
    }
    .recent-item-chip {
        position: absolute;
        min-width: 16px;
        height: 16px;
        padding: 0 4px;
        border-radius: 999px;
        font-size: 0.6rem;
        font-weight: 700;
        line-height: 16px;
        text-align: center;
        white-space: nowrap;
        color: #fff;
        background: rgba(17, 24, 39, 0.92);
        border: 1px solid rgba(255, 255, 255, 0.16);
    }
    .recent-item-chip-time {
        left: -5px;
        bottom: -5px;
    }
    .recent-item-chip-buff {
        top: -5px;
        right: -5px;
        color: #111827;
        background: rgba(245, 158, 11, 0.96);
        border-color: rgba(17, 24, 39, 0.2);
    }
    .recent-item-chip.na {
        opacity: 0.58;
    }
    .item-winrates-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.84rem;
        margin-top: 0.45rem;
    }
    .item-winrates-table th {
        text-align: left;
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        opacity: 0.72;
        padding: 0.45rem 0.55rem;
        border-bottom: 1px solid rgba(49, 51, 63, 0.18);
        white-space: nowrap;
    }
    .item-winrates-table td {
        padding: 0.5rem 0.55rem;
        border-bottom: 1px solid rgba(49, 51, 63, 0.08);
        vertical-align: middle;
    }
    .item-winrate-item-cell {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        min-width: 220px;
    }
    .item-winrate-item-name {
        font-weight: 600;
        line-height: 1.2;
    }
    .item-winrate-num {
        white-space: nowrap;
        font-weight: 700;
    }
    .item-winrate-win {
        color: #23a55a;
        font-weight: 700;
    }
    .item-winrate-loss {
        color: #d9534f;
        font-weight: 700;
    }
    @media (max-width: 768px) {
        .block-container {
            padding-top: 1rem;
            padding-left: 0.8rem;
            padding-right: 0.8rem;
            max-width: 100%;
        }
        div[data-testid="stMetric"] {
            padding: 0.4rem;
        }
        div[data-testid="stDataFrameResizable"] {
            overflow-x: auto;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def build_service() -> DotaAnalyticsService:
    settings = get_settings()
    client = OpenDotaClient(
        base_url=settings.base_url,
        timeout_seconds=settings.timeout_seconds,
        api_key=settings.api_key,
    )
    cache = JsonFileCache(cache_dir=get_cache_dir(), ttl_hours=settings.cache_ttl_hours)
    match_store = SQLiteMatchStore(get_match_store_path())
    return DotaAnalyticsService(client=client, cache=cache, match_store=match_store)


def get_app_version() -> str:
    env_candidates = (
        os.getenv("APP_VERSION"),
        os.getenv("GIT_COMMIT"),
        os.getenv("COMMIT_SHA"),
        os.getenv("VERCEL_GIT_COMMIT_SHA"),
        os.getenv("GITHUB_SHA"),
    )
    for candidate in env_candidates:
        if candidate:
            return candidate[:7]

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        version = result.stdout.strip()
        if version:
            return version
    except Exception:  # noqa: BLE001
        pass

    return "unknown"


def get_default_days_period() -> int:
    start_date = DEFAULT_FILTER_BASELINE_DATE
    today = datetime.now().date()
    days = max((today - start_date).days + 1, 1)
    return min(days, 365)


def get_effective_start_date(days: int | None, start_date_value: date | None) -> date | None:
    candidates: list[date] = []
    if days is not None:
        candidates.append(datetime.now().date() - timedelta(days=days))
    if start_date_value is not None:
        candidates.append(start_date_value)
    return max(candidates) if candidates else None


def format_time_ago(dt: datetime) -> str:
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    delta = now - dt
    total_seconds = max(int(delta.total_seconds()), 0)
    minutes = total_seconds // 60
    hours = total_seconds // 3600
    days = total_seconds // 86400
    if days >= 365:
        years = days // 365
        return f"{years} year{'s' if years != 1 else ''} ago"
    if days >= 30:
        months = days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    if days >= 1:
        return f"{days} day{'s' if days != 1 else ''} ago"
    if hours >= 1:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    if minutes >= 1:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    return "just now"


def recent_matches_state_key(
    hero_id: int,
    days: int | None,
    active_patches: list[str],
    active_start_date: date | None,
) -> str:
    patch_key = ",".join(active_patches) if active_patches else "no-patches"
    start_key = active_start_date.isoformat() if active_start_date else "no-start"
    days_key = str(days) if days is not None else "no-days"
    return f"recent_matches_limit_{hero_id}_{days_key}_{patch_key}_{start_key}"


def duration_bar_percent(duration_seconds: int, full_scale_seconds: int = 45 * 60) -> float:
    return max(0.0, min(duration_seconds / full_scale_seconds * 100.0, 100.0))


def kda_bar_segments(kills: int, deaths: int, assists: int) -> tuple[float, float, float]:
    total = max(kills + deaths + assists, 1)
    return (
        kills / total * 100.0,
        deaths / total * 100.0,
        assists / total * 100.0,
    )


def winrate_color(value: float) -> str:
    if value > 50.0:
        return "#23a55a"
    if value < 50.0:
        return "#d9534f"
    return "#d4a017"


def colored_winrate_html(value: float) -> str:
    rounded = round(float(value))
    return f'<span style="color: {winrate_color(float(value))}; font-weight: 700;">{rounded}%</span>'


def colored_metric_html(value: object, color: str) -> str:
    return f'<span style="color: {color}; font-weight: 700;">{value}</span>'


def _style_winrate_cell(value: object) -> str:
    text = str(value).strip().replace("%", "")
    try:
        numeric_value = float(text)
    except ValueError:
        return ""
    return f"color: {winrate_color(numeric_value)}; font-weight: 700;"


WINRATE_CARD_LABELS = {"Winrate", "Radiant WR", "Dire WR"}


def show_error(exc: Exception) -> None:
    if isinstance(exc, OpenDotaNotFoundError):
        st.error("Player was not found in OpenDota.")
    elif isinstance(exc, OpenDotaRateLimitError):
        st.error("OpenDota rate limit reached. Retry later or configure OPENDOTA_API_KEY.")
    elif isinstance(exc, ValidationError):
        st.error(str(exc))
    elif isinstance(exc, OpenDotaError):
        st.error(str(exc))
    else:
        st.error(f"Unexpected error: {exc}")


def run_with_rate_limit_retry(
    operation: callable,
    operation_label: str,
    retries: int = 2,
    cooldown_seconds: int = 5,
):
    attempt = 0
    while True:
        try:
            return operation()
        except OpenDotaRateLimitError:
            if attempt >= retries:
                raise
            attempt += 1
            status = st.empty()
            progress = st.progress(0)
            with st.spinner("OpenDota rate limit reached. Waiting to retry..."):
                for elapsed in range(cooldown_seconds):
                    seconds_left = cooldown_seconds - elapsed
                    status.warning(
                        f"Rate limit reached. Retrying {operation_label} in {seconds_left}s "
                        f"(attempt {attempt + 1} of {retries + 1})"
                    )
                    progress.progress(int((elapsed + 1) * 100 / cooldown_seconds))
                    time.sleep(1)
            status.empty()
            progress.empty()


def _load_patch_timeline(service: DotaAnalyticsService) -> list[tuple[int, str]]:
    cached = service.cache.get("patch_timeline_v2")
    if isinstance(cached, list) and cached:
        try:
            return [(int(row[0]), str(row[1])) for row in cached if isinstance(row, list | tuple) and len(row) == 2]
        except Exception:  # noqa: BLE001
            pass

    timeline: list[tuple[int, str]] = []

    # Primary source: Valve patchnotes feed (contains lettered patches like 7.40b/7.40c).
    try:
        response = service.client.session.get(
            "https://www.dota2.com/datafeed/patchnoteslist",
            params={"language": "english"},
            timeout=service.client.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        patches = payload.get("patches") if isinstance(payload, dict) else []
        if isinstance(patches, list):
            for row in patches:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("patch_name") or row.get("patch_number") or "").strip()
                ts = int(row.get("patch_timestamp") or 0)
                if name and ts > 0:
                    timeline.append((ts, name))
    except Exception:  # noqa: BLE001
        timeline = []

    # Fallback source: OpenDota constants/patch (numeric-only names).
    if not timeline:
        raw: list[dict] = []
        if hasattr(service.client, "get_constants_patch"):
            raw = service.client.get_constants_patch()
        elif hasattr(service.client, "_request"):
            result = service.client._request("GET", "constants/patch")
            raw = result if isinstance(result, list) else []

        for row in raw:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            date_raw = str(row.get("date") or "").strip()
            if not name or not date_raw:
                continue
            try:
                ts = int(datetime.fromisoformat(date_raw.replace("Z", "+00:00")).timestamp())
            except ValueError:
                continue
            timeline.append((ts, name))

    timeline.sort(key=lambda x: x[0])
    if timeline:
        service.cache.set("patch_timeline_v2", [[ts, name] for ts, name in timeline])
    return timeline


def _resolve_patch_name(start_time: int, patch_timeline: list[tuple[int, str]]) -> str | None:
    if not patch_timeline:
        return None
    starts = [row[0] for row in patch_timeline]
    idx = bisect_right(starts, start_time) - 1
    if idx < 0:
        return None
    return patch_timeline[idx][1]


def _patch_base(name: str) -> str:
    match = re.match(r"^(\d+\.\d+)", name)
    return match.group(1) if match else name


def _is_lettered_patch(name: str) -> bool:
    return any(ch.isalpha() for ch in name)


def _build_patch_options(patch_timeline: list[tuple[int, str]]) -> list[str]:
    if not patch_timeline:
        return []

    latest_patch_name = patch_timeline[-1][1]
    latest_base = _patch_base(latest_patch_name)

    seen: set[str] = set()
    options: list[str] = []
    for _, name in reversed(patch_timeline):
        if name in seen:
            continue
        seen.add(name)

        # Keep lettered subpatches only for the latest base patch (e.g. 7.40b/7.40c).
        if _is_lettered_patch(name) and _patch_base(name) != latest_base:
            continue
        options.append(name)
    return options


def _build_overview_from_matches(matches: list[MatchSummary], service: DotaAnalyticsService) -> list[dict]:
    return service.build_turbo_hero_overview_rows(matches)


st.title("Turbo Buff")
st.caption("Turbo-only Dota 2 personal analytics based on OpenDota")
app_version = get_app_version()
st.caption(f"Build: `{app_version}`")

service = build_service()
try:
    service_overview_sig = inspect.signature(service.get_turbo_hero_overview)
    supports_patch_overview = "patch_names" in service_overview_sig.parameters
except Exception:  # noqa: BLE001
    supports_patch_overview = False
query_filters_supports_patch = "patch_names" in getattr(QueryFilters, "__dataclass_fields__", {})
patch_timeline = _load_patch_timeline(service)
patch_options = _build_patch_options(patch_timeline)


def _clear_detail_sections() -> None:
    for key in (
        "hero_matches_by_key",
        "hero_loaded_at_by_key",
        "item_rows_by_key",
        "item_loaded_at_by_key",
        "recent_rows_by_key",
        "recent_loaded_at_by_key",
        "recent_limit_loaded_by_key",
    ):
        st.session_state.pop(key, None)


def _session_dict(key: str) -> dict[object, object]:
    value = st.session_state.get(key)
    if not isinstance(value, dict):
        value = {}
        st.session_state[key] = value
    return value


def _cache_get(bucket_key: str, request_key: object) -> object | None:
    return _session_dict(bucket_key).get(request_key)


def _cache_set(bucket_key: str, request_key: object, value: object) -> None:
    bucket = _session_dict(bucket_key)
    bucket[request_key] = value


def _set_active_matchup_snapshot(request_key: object, rows: object) -> None:
    st.session_state["active_matchup_request_key"] = request_key
    st.session_state["active_matchup_rows"] = rows
    st.session_state["current_matchup_request_key"] = request_key
    st.session_state["current_matchup_rows"] = rows


def _get_active_matchup_snapshot(request_key: object) -> object | None:
    if st.session_state.get("active_matchup_request_key") == request_key:
        return st.session_state.get("active_matchup_rows")
    return None


def _get_current_matchup_snapshot(request_key: object) -> object | None:
    if st.session_state.get("current_matchup_request_key") == request_key:
        return st.session_state.get("current_matchup_rows")
    return None


def _set_current_section_snapshot(section_name: str, request_key: object, rows: object) -> None:
    st.session_state[f"current_{section_name}_request_key"] = request_key
    st.session_state[f"current_{section_name}_rows"] = rows


def _get_current_section_snapshot(section_name: str, request_key: object) -> object | None:
    if st.session_state.get(f"current_{section_name}_request_key") == request_key:
        return st.session_state.get(f"current_{section_name}_rows")
    return None


def _store_recent_section_snapshot(
    request_key: object,
    rows: object,
    *,
    visible_recent_matches: int,
    loaded_at_value: str | None = None,
) -> None:
    _cache_set("recent_rows_by_key", request_key, rows)
    _cache_set("recent_loaded_at_by_key", request_key, loaded_at_value or _utcnow_iso())
    _cache_set("recent_limit_loaded_by_key", request_key, visible_recent_matches)
    _set_current_section_snapshot("recent", request_key, rows)


def _mark_section_visible(section_name: str, request_key: object) -> None:
    st.session_state[f"current_{section_name}_visible_request_key"] = request_key


def _is_section_visible(section_name: str, request_key: object) -> bool:
    return st.session_state.get(f"current_{section_name}_visible_request_key") == request_key


def _ensure_section_visible(section_name: str, request_key: object) -> None:
    if st.session_state.get(f"current_{section_name}_visible_request_key") != request_key:
        _mark_section_visible(section_name, request_key)


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat()


def _is_section_stale(section_loaded_at: str | None, dashboard_loaded_at: str | None) -> bool:
    if not section_loaded_at or not dashboard_loaded_at:
        return False
    return section_loaded_at < dashboard_loaded_at


def _coalesce_dashboard_cache_timestamp(sync_state: dict[str, object] | None) -> str | None:
    if not isinstance(sync_state, dict):
        return None
    timestamps = [
        str(sync_state.get("last_incremental_sync_at") or ""),
        str(sync_state.get("last_full_sync_at") or ""),
    ]
    normalized = [value for value in timestamps if value]
    return max(normalized) if normalized else None


TREND_METRIC_LABELS: dict[str, str] = {
    "winrate": "WR",
    "kda": "KDA",
    "avg_net_worth": "NW",
    "avg_damage": "Dmg",
    "matches": "Matches",
    "wins": "Won",
    "losses": "Lost",
    "avg_duration_minutes": "Dur",
    "radiant_wr": "Rad WR",
    "dire_wr": "Dire WR",
}


def _matchup_cache_key(
    player_id: int,
    days: int | None,
    active_patches: list[str],
    active_start_date: date | None,
    dashboard_loaded_at: str | None,
    selected_hero_id: int,
) -> tuple[object, ...]:
    return (
        int(player_id),
        days,
        tuple(active_patches),
        active_start_date.isoformat() if active_start_date else None,
        dashboard_loaded_at,
        int(selected_hero_id),
    )


def _store_dashboard_state(
    *,
    player_raw_value: str,
    player_id: int,
    time_filter_mode_value: str,
    days_value: int | None,
    active_days_value: int | None,
    start_date_value: date | None,
    active_start_date_value: date | None,
    selected_patches_value: list[str],
    active_patches_value: list[str],
    overview_value: list[dict],
    patch_filtered_matches_value: list[MatchSummary] | None,
    min_hero_matches_value: int,
    min_item_matches_value: int,
    loaded_at_value: str,
    cache_only: bool,
) -> None:
    st.session_state["player_raw"] = player_raw_value
    st.session_state["player_id"] = player_id
    st.session_state["time_filter_mode"] = time_filter_mode_value
    st.session_state["days"] = days_value
    st.session_state["active_days"] = active_days_value
    st.session_state["start_date"] = start_date_value
    st.session_state["active_start_date"] = active_start_date_value
    st.session_state["selected_patches"] = selected_patches_value
    st.session_state["active_patches"] = active_patches_value
    st.session_state["overview"] = overview_value
    st.session_state["overview_schema_version"] = OVERVIEW_SCHEMA_VERSION
    st.session_state["dashboard_loaded_at"] = loaded_at_value
    st.session_state["patch_filtered_matches"] = patch_filtered_matches_value
    st.session_state["min_hero_matches"] = min_hero_matches_value
    st.session_state["min_item_matches"] = min_item_matches_value
    st.session_state["overview_cache_only"] = cache_only
    st.session_state["overview_requires_refresh"] = False


def _load_selected_hero_matches(
    service: DotaAnalyticsService,
    player_id: int,
    selected_hero_id: int,
    selected_hero_name: str,
    days: int | None,
    active_patches: list[str],
    active_start_date: date | None,
    current_hero_request_key: tuple[object, ...],
    *,
    force_refresh: bool = False,
) -> list[MatchSummary]:
    if not force_refresh:
        cached_matches = _cache_get("hero_matches_by_key", current_hero_request_key)
        if isinstance(cached_matches, list):
            return cached_matches

    if active_patches and not supports_patch_overview:
        patch_filtered_matches = st.session_state.get("patch_filtered_matches") or []
        matches = [m for m in patch_filtered_matches if int(m.hero_id or 0) == selected_hero_id]
    else:
        filters_kwargs: dict[str, object] = {
            "player_id": player_id,
            "hero_id": selected_hero_id,
            "hero_name": selected_hero_name,
            "game_mode": 23,
            "game_mode_name": "Turbo",
            "days": days,
            "start_date": active_start_date,
        }
        if active_patches and query_filters_supports_patch:
            filters_kwargs["patch_names"] = active_patches
        matches = service.get_cached_matches(QueryFilters(**filters_kwargs))
        service.enrich_hero_damage(
            player_id,
            matches,
            max_fallback_detail_calls=max(60, len(matches)),
            allow_detail_fetch=False,
        )

    _cache_set("hero_matches_by_key", current_hero_request_key, matches)
    _cache_set("hero_loaded_at_by_key", current_hero_request_key, _utcnow_iso())
    return matches


def _get_turbo_overview_snapshot_safe(
    service: DotaAnalyticsService,
    *,
    player_id: int,
    days: int | None,
    start_date: date | None,
    patch_names: list[str] | None = None,
    force_sync: bool,
    hydrate_details: bool,
):
    normalized_patch_names = patch_names or []
    if hasattr(service, "get_turbo_overview_snapshot"):
        return service.get_turbo_overview_snapshot(
            player_id=player_id,
            days=days,
            start_date=start_date,
            patch_names=normalized_patch_names,
            force_sync=force_sync,
            hydrate_details=hydrate_details,
        )

    filters = QueryFilters(
        player_id=player_id,
        game_mode=23,
        game_mode_name="Turbo",
        days=days,
        start_date=start_date,
        patch_names=normalized_patch_names,
    )
    if force_sync:
        if hasattr(service, "refresh_cached_matches"):
            matches = service.refresh_cached_matches(filters, hydrate_details=hydrate_details)
        else:
            matches = service.fetch_matches(filters, force_sync=True)
    else:
        matches = service.get_cached_matches(filters) if hasattr(service, "get_cached_matches") else service.fetch_matches(filters)
    if matches:
        service.enrich_hero_damage(
            player_id,
            matches,
            max_fallback_detail_calls=max(120, len(matches)),
            allow_detail_fetch=False,
        )
    class _FallbackSnapshot:
        def __init__(self, rows):
            self.overview = rows
            self.matches = matches
            self.is_valid = not overview_looks_stale(rows)
    return _FallbackSnapshot(service.build_turbo_hero_overview_rows(matches) if matches else [])


def _build_item_purchase_times_by_item(
    service: DotaAnalyticsService,
    *,
    player_row: dict | None,
    details: dict | None,
    player_slot: int | None,
    tracked_item_ids: set[int],
) -> dict[int, list[int]]:
    purchase_times_by_item: dict[int, list[int]] = {}
    if not isinstance(player_row, dict):
        return purchase_times_by_item

    purchase_log = player_row.get("purchase_log")
    if isinstance(purchase_log, list):
        for event in purchase_log:
            if not isinstance(event, dict):
                continue
            item_id = service.references.item_ids_by_key.get(str(event.get("key") or ""))
            if not item_id or item_id not in tracked_item_ids:
                continue
            purchase_times_by_item.setdefault(item_id, []).append(max(int(event.get("time") or 0) // 60, 0))

    first_purchase_time = player_row.get("first_purchase_time")
    if isinstance(first_purchase_time, dict):
        for key, value in first_purchase_time.items():
            item_id = service.references.item_ids_by_key.get(str(key))
            if not item_id or item_id not in tracked_item_ids or item_id in purchase_times_by_item:
                continue
            try:
                purchase_times_by_item[item_id] = [max(int(value) // 60, 0)]
            except (TypeError, ValueError):
                continue

    if 117 in tracked_item_ids and 117 not in purchase_times_by_item and isinstance(details, dict):
        objectives = details.get("objectives")
        if isinstance(objectives, list):
            for event in objectives:
                if not isinstance(event, dict):
                    continue
                if str(event.get("type") or "") != "CHAT_MESSAGE_AEGIS":
                    continue
                if player_slot is not None and int(event.get("player_slot") or -1) != int(player_slot):
                    continue
                try:
                    purchase_times_by_item[117] = [max(int(event.get("time") or 0) // 60, 0)]
                except (TypeError, ValueError):
                    pass
                break

    return purchase_times_by_item


def _player_row_buff_items_local(service: DotaAnalyticsService, player_row: dict | None) -> list[tuple[int, int | None]]:
    if not isinstance(player_row, dict):
        return []

    by_item_id: dict[int, int | None] = {}
    permanent_buffs = player_row.get("permanent_buffs")
    if isinstance(permanent_buffs, list):
        for buff in permanent_buffs:
            if not isinstance(buff, dict):
                continue
            item_key = PERMANENT_BUFF_ITEM_KEYS.get(int(buff.get("permanent_buff") or 0))
            if not item_key:
                continue
            item_id = CONSUMABLE_BUFF_ITEM_KEYS[item_key]
            grant_time = buff.get("grant_time")
            try:
                by_item_id[item_id] = max(int(grant_time) // 60, 0)
            except (TypeError, ValueError):
                by_item_id[item_id] = None

    first_purchase_time = player_row.get("first_purchase_time")
    if isinstance(first_purchase_time, dict):
        for item_key, item_id in CONSUMABLE_BUFF_ITEM_KEYS.items():
            if item_id in by_item_id and by_item_id[item_id] is not None:
                continue
            if item_key not in first_purchase_time:
                continue
            try:
                by_item_id[item_id] = max(int(first_purchase_time[item_key]) // 60, 0)
            except (TypeError, ValueError):
                by_item_id[item_id] = None

    for field_name, item_key in (
        ("moonshard", "moon_shard"),
        ("aghanims_scepter", "ultimate_scepter"),
        ("aghanims_shard", "aghanims_shard"),
    ):
        if int(player_row.get(field_name) or 0) <= 0:
            continue
        item_id = CONSUMABLE_BUFF_ITEM_KEYS[item_key]
        by_item_id.setdefault(item_id, None)

    return [(item_id, by_item_id[item_id]) for item_id in by_item_id]


def _augment_recent_rows_with_cached_buffs(
    service: DotaAnalyticsService,
    *,
    player_id: int,
    matches: list[MatchSummary],
    recent_rows: list[object],
) -> list[object]:
    match_by_id = {int(match.match_id): match for match in matches}
    for row in recent_rows:
        match_id = int(getattr(row, "match_id", 0) or 0)
        match = match_by_id.get(match_id)
        if match is None:
            continue
        details = service.get_match_details_if_cached(match_id)
        if not isinstance(details, dict):
            continue
        player_row = service._extract_player_from_match_details(  # noqa: SLF001
            details,
            player_id=player_id,
            player_slot=match.player_slot,
        )
        buff_items = _player_row_buff_items_local(service, player_row)
        if not buff_items:
            continue
        existing_ids = {int(getattr(item, "item_id", 0) or 0) for item in getattr(row, "items", [])}
        augmented_items = list(getattr(row, "items", []))
        for item_id, grant_time_min in buff_items:
            if item_id in existing_ids:
                continue
            augmented_items.append(
                SimpleNamespace(
                    item_id=item_id,
                    item_name=service.references.item_names_by_id.get(item_id, f"Item #{item_id}"),
                    item_image=service.references.item_images_by_id.get(item_id, ""),
                    purchase_time_min=grant_time_min,
                    is_buff=True,
                    buff_label="Buff",
                )
            )
        augmented_items.sort(
            key=lambda item: (
                not bool(getattr(item, "is_buff", False)),
                getattr(item, "purchase_time_min", None) is None,
                getattr(item, "purchase_time_min", None) if getattr(item, "purchase_time_min", None) is not None else 10_000,
                getattr(item, "item_name", ""),
            )
        )
        row.items = augmented_items
    return recent_rows


def _build_item_winrate_snapshot_from_cached_inventory(
    service: DotaAnalyticsService,
    *,
    player_id: int,
    matches: list[MatchSummary],
    top_n: int,
) -> dict[str, object]:
    total = len(matches)
    if total == 0:
        return {
            "rows": [],
            "note": "No matches available for item stats.",
            "missing_matches": 0,
            "summary_only_matches": 0,
            "detail_backed_matches": 0,
            "is_complete": True,
            "total_matches": 0,
        }

    appear_counter: dict[int, int] = {}
    win_counter: dict[int, int] = {}
    timing_sum_by_item: dict[int, int] = {}
    timing_count_by_item: dict[int, int] = {}
    detail_backed_matches = 0
    summary_only_matches = 0
    missing_matches = 0
    timed_item_matches = 0

    for match in matches:
        summary_items = {
            int(item_id)
            for item_id in (match.item_0, match.item_1, match.item_2, match.item_3, match.item_4, match.item_5)
            if int(item_id or 0) > 0
        }
        unique_items = set(summary_items)
        detail_backed_this_match = False
        purchase_times_by_item: dict[int, list[int]] = {}

        details = service.get_match_details_if_cached(match.match_id)
        if isinstance(details, dict):
            player_row = service._extract_player_from_match_details(  # noqa: SLF001
                details,
                player_id=player_id,
                player_slot=match.player_slot,
            )
            if isinstance(player_row, dict):
                detail_items = {
                    int(player_row.get(field_name) or 0)
                    for field_name in (
                        "item_0",
                        "item_1",
                        "item_2",
                        "item_3",
                        "item_4",
                        "item_5",
                        "backpack_0",
                        "backpack_1",
                        "backpack_2",
                    )
                    if int(player_row.get(field_name) or 0) > 0
                }
                if detail_items:
                    buff_items = _player_row_buff_items_local(service, player_row)
                    detail_items.update(item_id for item_id, _ in buff_items)
                    unique_items.update(detail_items)
                    detail_backed_this_match = True
                    purchase_times_by_item = _build_item_purchase_times_by_item(
                        service,
                        player_row=player_row,
                        details=details,
                        player_slot=match.player_slot,
                        tracked_item_ids=detail_items,
                    )
                    for buff_item_id, grant_time_min in buff_items:
                        if grant_time_min is None:
                            purchase_times_by_item.setdefault(buff_item_id, [])
                            continue
                        purchase_times_by_item.setdefault(buff_item_id, []).append(grant_time_min)

        if not unique_items:
            missing_matches += 1
            continue

        if detail_backed_this_match:
            detail_backed_matches += 1
        elif summary_items:
            summary_only_matches += 1

        for item_id in unique_items:
            appear_counter[item_id] = appear_counter.get(item_id, 0) + 1
            if match.did_win:
                win_counter[item_id] = win_counter.get(item_id, 0) + 1
            item_times = purchase_times_by_item.get(item_id)
            if item_times:
                timing_sum_by_item[item_id] = timing_sum_by_item.get(item_id, 0) + min(item_times)
                timing_count_by_item[item_id] = timing_count_by_item.get(item_id, 0) + 1
                timed_item_matches += 1

    rows: list[dict[str, object]] = []
    for item_id, appearances in appear_counter.items():
        wins = win_counter.get(item_id, 0)
        avg_time_count = timing_count_by_item.get(item_id, 0)
        rows.append(
            {
                "item_id": item_id,
                "item": service.references.item_names_by_id.get(item_id, f"Item #{item_id}"),
                "item_image": service.resolve_item_image(item_id),
                "matches_with_item": appearances,
                "item_pick_rate": round((appearances / total) * 100, 2) if total > 0 else 0.0,
                "wins_with_item": wins,
                "item_winrate": round((wins / appearances) * 100, 2) if appearances > 0 else 0.0,
                "avg_item_timing_min": (
                    round(timing_sum_by_item[item_id] / avg_time_count, 1)
                    if avg_time_count > 0
                    else None
                ),
                "timed_matches_with_item": avg_time_count,
                "is_buff": item_id in CONSUMABLE_BUFF_ITEM_KEYS.values(),
            }
        )

    rows.sort(
        key=lambda row: (
            -float(row["item_winrate"]),
            -int(row["matches_with_item"]),
            -int(row["wins_with_item"]),
            str(row["item"]),
        )
    )

    notes: list[str] = []
    if detail_backed_matches > 0:
        notes.append(
            f"Cached match details contributed final-inventory/backpack coverage for {detail_backed_matches} match(es)."
        )
    if summary_only_matches > 0:
        notes.append(
            f"{summary_only_matches} match(es) rely on summary final slots only, so sold/replaced items may be missed there."
        )
    if missing_matches > 0:
        notes.append(
            f"Item stats are incomplete for {missing_matches} match(es) because neither cached details nor summary item slots are available. Run `Refresh Turbo Dashboard` to hydrate missing match details."
        )
    if timed_item_matches > 0:
        notes.append("Average item timings use cached timing data when available.")

    return {
        "rows": rows[:top_n],
        "note": " ".join(notes).strip(),
        "missing_matches": missing_matches,
        "summary_only_matches": summary_only_matches,
        "detail_backed_matches": detail_backed_matches,
        "is_complete": missing_matches == 0,
        "total_matches": total,
    }


def _item_snapshot_uses_legacy_purchase_logic(snapshot_payload: dict[str, object]) -> bool:
    return "purchase/final-item coverage" in str(snapshot_payload.get("note") or "")


def _get_item_winrate_snapshot_safe(
    service: DotaAnalyticsService,
    *,
    player_id: int,
    matches: list[MatchSummary],
    top_n: int,
    allow_detail_fetch: bool,
) -> dict[str, object]:
    return _build_item_winrate_snapshot_from_cached_inventory(
        service,
        player_id=player_id,
        matches=matches,
        top_n=top_n,
    )


def _format_item_timing_label(timing_min: float | None) -> str:
    if timing_min is None:
        return "-"
    return f"{int(round(float(timing_min)))}m"


def _render_item_icon_html(*, image_url: str, item_name: str, timing_min: float | int | None, is_buff: bool) -> str:
    badge_html = '<div class="recent-item-chip recent-item-chip-buff">buff</div>' if is_buff else ""
    time_class_suffix = " na" if timing_min is None else ""
    return (
        '<div class="recent-item-inline">'
        f'<img src="{image_url}" alt="{item_name}" title="{item_name}"/>'
        f"{badge_html}"
        f'<div class="recent-item-chip recent-item-chip-time{time_class_suffix}">{_format_item_timing_label(None if timing_min is None else float(timing_min))}</div>'
        "</div>"
    )


def _render_sortable_item_winrates_table(item_wr_rows: list[dict[str, object]]) -> tuple[str, int]:
    rows_html = ""
    for row in item_wr_rows:
        item_name = str(row["item"])
        item_wr = float(row["item_winrate"])
        matches = int(row.get("matches_with_item", 0))
        won = int(row.get("wins_with_item", 0))
        lost = matches - won
        avg_timing = float(row["avg_item_timing_min"]) if row.get("avg_item_timing_min") is not None else None
        timing_sort_value = "" if avg_timing is None else f"{avg_timing:.3f}"
        icon_html = _render_item_icon_html(
            image_url=str(row.get("item_image", "")),
            item_name=item_name,
            timing_min=avg_timing,
            is_buff=bool(row.get("is_buff")),
        )
        rows_html += (
            f'<tr data-item="{html.escape(item_name.lower())}" data-timing="{timing_sort_value}" data-wr="{item_wr}" data-matches="{matches}" data-won="{won}" data-lost="{lost}">'
            "<td>"
            '<div class="item-winrate-item-cell">'
            f"{icon_html}"
            f'<div class="item-winrate-item-name">{html.escape(item_name)}</div>'
            "</div>"
            "</td>"
            f'<td><span class="item-winrate-num" style="color:{winrate_color(item_wr)};">{round(item_wr)}%</span></td>'
            f'<td><span class="item-winrate-num">{matches}</span></td>'
            f'<td><span class="item-winrate-win">{won}</span></td>'
            f'<td><span class="item-winrate-loss">{lost}</span></td>'
            "</tr>"
        )

    table_height = min(max(180, 88 + (len(item_wr_rows) * 42)), 980)
    return f"""
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        html, body {{
          margin: 0;
          padding: 0;
          background: transparent;
          color: rgba(250, 250, 250, 0.92);
          font-family: sans-serif;
        }}
        .recent-matches-wrap{{overflow-x:auto;margin-top:0.5rem;}}
        .recent-matches-table{{width:100%;min-width:640px;border-collapse:collapse;font-size:0.84rem;}}
        .recent-matches-table th{{text-align:left;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.04em;opacity:0.72;padding:0.45rem 0.55rem;border-bottom:1px solid rgba(49,51,63,0.18);white-space:nowrap;cursor:pointer;user-select:none;}}
        .recent-matches-table td{{padding:0.55rem;border-bottom:1px solid rgba(49,51,63,0.1);vertical-align:middle;}}
        .item-winrate-item-cell{{display:flex;align-items:center;gap:0.6rem;min-width:220px;}}
        .item-winrate-item-name{{font-weight:700;line-height:1.1;}}
        .item-winrate-num{{white-space:nowrap;font-weight:700;}}
        .item-winrate-win{{color:#23a55a;font-weight:700;}}
        .item-winrate-loss{{color:#d9534f;font-weight:700;}}
        .recent-item-inline{{position:relative;width:34px;flex:0 0 34px;display:inline-flex;align-items:flex-start;justify-content:center;padding-bottom:0.15rem;}}
        .recent-item-inline img{{width:34px;height:auto;border-radius:5px;display:block;margin:0 auto;}}
        .recent-item-chip{{position:absolute;min-width:16px;height:16px;padding:0 4px;border-radius:999px;font-size:0.6rem;font-weight:700;line-height:16px;text-align:center;white-space:nowrap;color:#fff;background:rgba(17,24,39,0.92);border:1px solid rgba(255,255,255,0.16);}}
        .recent-item-chip-time{{left:-5px;bottom:-5px;}}
        .recent-item-chip-buff{{top:-5px;right:-5px;color:#111827;background:rgba(245,158,11,0.96);border-color:rgba(17,24,39,0.2);}}
        .recent-item-chip.na{{opacity:0.58;}}
        .sort-indicator{{display:inline-block;min-width:1ch;margin-left:0.2rem;opacity:0.7;}}
      </style>
    </head>
    <body>
      <div class="recent-matches-wrap">
        <table class="recent-matches-table" id="item-winrates-table">
          <thead>
            <tr>
              <th data-sort-key="timing" data-default-dir="asc">Item<span class="sort-indicator"></span></th>
              <th data-sort-key="wr" data-default-dir="desc">WR<span class="sort-indicator">v</span></th>
              <th data-sort-key="matches" data-default-dir="desc">Matches<span class="sort-indicator"></span></th>
              <th data-sort-key="won" data-default-dir="desc">Won<span class="sort-indicator"></span></th>
              <th data-sort-key="lost" data-default-dir="desc">Lost<span class="sort-indicator"></span></th>
            </tr>
          </thead>
          <tbody>
            {rows_html}
          </tbody>
        </table>
      </div>
      <script>
        (() => {{
          const table = document.getElementById('item-winrates-table');
          const tbody = table.querySelector('tbody');
          const headers = [...table.querySelectorAll('th[data-sort-key]')];
          let activeKey = 'wr';
          let activeDir = 'desc';

          const applyIndicators = () => {{
            headers.forEach((header) => {{
              const indicator = header.querySelector('.sort-indicator');
              if (!indicator) return;
              indicator.textContent = header.dataset.sortKey === activeKey ? (activeDir === 'asc' ? '^' : 'v') : '';
            }});
          }};

          const sortRows = (key, dir) => {{
            const rows = [...tbody.querySelectorAll('tr')];
            rows.sort((a, b) => {{
              const av = a.dataset[key] ?? '';
              const bv = b.dataset[key] ?? '';
              if (key === 'timing') {{
                const aMissing = av === '';
                const bMissing = bv === '';
                if (aMissing || bMissing) {{
                  if (aMissing && bMissing) return (a.dataset.item ?? '').localeCompare(b.dataset.item ?? '');
                  return aMissing ? 1 : -1;
                }}
                const an = Number(av);
                const bn = Number(bv);
                if (an !== bn) return dir === 'asc' ? an - bn : bn - an;
                return (a.dataset.item ?? '').localeCompare(b.dataset.item ?? '');
              }}
              if (key === 'item') {{
                return dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
              }}
              const an = Number(av);
              const bn = Number(bv);
              if (an !== bn) return dir === 'asc' ? an - bn : bn - an;
              return (a.dataset.item ?? '').localeCompare(b.dataset.item ?? '');
            }});
            rows.forEach((row) => tbody.appendChild(row));
            activeKey = key;
            activeDir = dir;
            applyIndicators();
          }};

          headers.forEach((header) => {{
            header.addEventListener('click', () => {{
              const key = header.dataset.sortKey;
              const defaultDir = header.dataset.defaultDir || 'desc';
              const nextDir = activeKey === key ? (activeDir === 'desc' ? 'asc' : 'desc') : defaultDir;
              sortRows(key, nextDir);
            }});
          }});

          sortRows(activeKey, activeDir);
        }})();
      </script>
    </body>
    </html>
    """, table_height

with st.sidebar:
    st.header("Filters")
    st.caption(f"Version: `{app_version}`")
    player_raw = st.text_input(
        "Player ID or OpenDota URL",
        value=st.session_state.get("player_raw", "1233793238"),
    )
    time_mode_options = ["Days", "Patches", "Start Date"]
    default_mode = st.session_state.get("time_filter_mode", "Patches")
    time_filter_mode = st.radio(
        "Time filter mode",
        options=time_mode_options,
        index=time_mode_options.index(default_mode) if default_mode in time_mode_options else 0,
    )

    days = st.session_state.get("days", get_default_days_period())
    start_date_value = st.session_state.get("start_date", DEFAULT_FILTER_BASELINE_DATE)
    selected_patches = st.session_state.get("selected_patches", default_patch_selection(patch_options))
    if time_filter_mode == "Days":
        days = st.slider("Period (days)", min_value=1, max_value=365, value=days, step=1)
    elif time_filter_mode == "Patches":
        if not patch_options:
            st.warning("Patch list is temporarily unavailable (OpenDota constants).")
            selected_patches = []
        else:
            if "patches_widget_selection" not in st.session_state:
                st.session_state["patches_widget_selection"] = selected_patches or default_patch_selection(patch_options)
            # Keep widget value valid when options list changes.
            st.session_state["patches_widget_selection"] = [
                p for p in st.session_state["patches_widget_selection"] if p in patch_options
            ] or default_patch_selection(patch_options)
            selected_patches = st.multiselect(
                "Patches (multi-select)",
                options=patch_options,
                key="patches_widget_selection",
            )
    else:
        start_date_value = st.date_input(
            "Start date",
            value=start_date_value,
            min_value=date(2020, 1, 1),
            max_value=datetime.now().date(),
        )

    min_hero_matches = st.slider(
        "Min matches per hero",
        min_value=1,
        max_value=50,
        value=st.session_state.get("min_hero_matches", 2),
        step=1,
    )
    min_item_matches = st.slider(
        "Min matches per item",
        min_value=1,
        max_value=30,
        value=st.session_state.get("min_item_matches", 2),
        step=1,
    )
    load = st.button("Refresh Turbo Dashboard", type="primary")

if "overview" in st.session_state and st.session_state.get("overview_schema_version") != OVERVIEW_SCHEMA_VERSION:
    st.session_state.pop("overview", None)
    st.session_state.pop("patch_filtered_matches", None)
    _clear_detail_sections()

if "overview" in st.session_state and overview_looks_stale(st.session_state.get("overview")):
    st.session_state.pop("overview", None)
    st.session_state.pop("patch_filtered_matches", None)
    _clear_detail_sections()

if "overview" in st.session_state:
    try:
        cached_player_id = parse_player_id(st.session_state.get("player_raw", player_raw))
        cached_overview_state = service.get_cached_sync_state(cached_player_id, game_mode=23)
        latest_cache_timestamp = _coalesce_dashboard_cache_timestamp(cached_overview_state)
        dashboard_loaded_at = st.session_state.get("dashboard_loaded_at")
        if latest_cache_timestamp and dashboard_loaded_at and str(dashboard_loaded_at) < latest_cache_timestamp:
            st.session_state.pop("overview", None)
            st.session_state.pop("patch_filtered_matches", None)
            _clear_detail_sections()
    except Exception:  # noqa: BLE001
        pass

if "overview" not in st.session_state:
    try:
        active_days = days if time_filter_mode == "Days" else None
        active_patches = selected_patches if time_filter_mode == "Patches" else []
        active_start_date = start_date_value if time_filter_mode == "Start Date" else None
        player_id = parse_player_id(player_raw)
        cached_sync_state = service.get_cached_sync_state(player_id, game_mode=23)
        if cached_sync_state and int(cached_sync_state.get("known_match_count") or 0) > 0:
            if active_patches and not supports_patch_overview:
                base_filters = QueryFilters(
                    player_id=player_id,
                    game_mode=23,
                    game_mode_name="Turbo",
                    days=None,
                    start_date=active_start_date,
                )
                all_cached_matches, _ = service.load_match_snapshot(base_filters, force_sync=False, hydrate_details=False)
                selected_set = set(active_patches)
                patch_filtered_matches = [
                    m for m in all_cached_matches if _resolve_patch_name(m.start_time, patch_timeline) in selected_set
                ]
                service.enrich_hero_damage(
                    player_id,
                    patch_filtered_matches,
                    max_fallback_detail_calls=max(120, len(patch_filtered_matches)),
                    allow_detail_fetch=False,
                )
                overview = _build_overview_from_matches(patch_filtered_matches, service)
            else:
                patch_filtered_matches = None
                overview_snapshot = _get_turbo_overview_snapshot_safe(
                    service,
                    player_id=player_id,
                    days=active_days,
                    start_date=active_start_date,
                    patch_names=active_patches,
                    force_sync=False,
                    hydrate_details=False,
                )
                overview = overview_snapshot.overview
            if overview and overview_looks_stale(overview):
                st.session_state["overview_requires_refresh"] = True
            elif overview:
                _store_dashboard_state(
                    player_raw_value=player_raw,
                    player_id=player_id,
                    time_filter_mode_value=time_filter_mode,
                    days_value=days,
                    active_days_value=active_days,
                    start_date_value=start_date_value,
                    active_start_date_value=active_start_date,
                    selected_patches_value=selected_patches,
                    active_patches_value=active_patches,
                    overview_value=overview,
                    patch_filtered_matches_value=patch_filtered_matches,
                    min_hero_matches_value=min_hero_matches,
                    min_item_matches_value=min_item_matches,
                    loaded_at_value=str(_coalesce_dashboard_cache_timestamp(cached_sync_state) or _utcnow_iso()),
                    cache_only=True,
                )
    except ValidationError:
        pass

if load:
    try:
        if time_filter_mode == "Patches" and not selected_patches:
            st.warning("Select at least one patch.")
            st.stop()

        active_days = days if time_filter_mode == "Days" else None
        active_patches = selected_patches if time_filter_mode == "Patches" else []
        active_start_date = start_date_value if time_filter_mode == "Start Date" else None

        player_id = parse_player_id(player_raw)
        run_with_rate_limit_retry(
            lambda: service.ensure_player_exists(player_id),
            operation_label="player profile",
        )
        patch_filtered_matches: list[MatchSummary] | None = None
        if active_patches and not supports_patch_overview:
            base_filters = QueryFilters(
                player_id=player_id,
                game_mode=23,
                game_mode_name="Turbo",
                days=None,
                start_date=active_start_date,
            )
            all_turbo_matches = run_with_rate_limit_retry(
                lambda: service.load_match_snapshot(base_filters, force_sync=True, hydrate_details=True)[0],
                operation_label="patch-filtered matches",
            )
            selected_set = set(active_patches)
            patch_filtered_matches = [
                m for m in all_turbo_matches if _resolve_patch_name(m.start_time, patch_timeline) in selected_set
            ]
            service.enrich_hero_damage(
                player_id,
                patch_filtered_matches,
                max_fallback_detail_calls=max(120, len(patch_filtered_matches)),
                allow_detail_fetch=False,
            )
            overview = _build_overview_from_matches(patch_filtered_matches, service)
        else:
            overview_kwargs: dict[str, object] = {
                "player_id": player_id,
                "days": active_days,
                "start_date": active_start_date,
                "force_sync": True,
                "hydrate_details": True,
            }
            if active_patches:
                overview_kwargs["patch_names"] = active_patches
            overview_snapshot = run_with_rate_limit_retry(
                lambda: _get_turbo_overview_snapshot_safe(service, **overview_kwargs),
                operation_label="hero overview",
            )
            overview = overview_snapshot.overview

        if overview and overview_looks_stale(overview):
            st.session_state["overview_requires_refresh"] = True
            st.warning(
                "The current overview snapshot is still incomplete for some heroes "
                "(for example zero NW/Dmg/Max Dmg rows). The invalid snapshot was not rendered."
            )
        else:
            _store_dashboard_state(
                player_raw_value=player_raw,
                player_id=player_id,
                time_filter_mode_value=time_filter_mode,
                days_value=days,
                active_days_value=active_days,
                start_date_value=start_date_value,
                active_start_date_value=active_start_date,
                selected_patches_value=selected_patches,
                active_patches_value=active_patches,
                overview_value=overview,
                patch_filtered_matches_value=patch_filtered_matches,
                min_hero_matches_value=min_hero_matches,
                min_item_matches_value=min_item_matches,
                loaded_at_value=_utcnow_iso(),
                cache_only=False,
            )
    except Exception as exc:  # noqa: BLE001
        show_error(exc)

if "overview" not in st.session_state:
    if st.session_state.get("overview_requires_refresh"):
        st.warning(
            "Cached overview data for the current filter is incomplete "
            "(for example heroes with zero NW/Dmg/Max Dmg rows). "
            "Click `Refresh Turbo Dashboard` to rebuild a valid snapshot."
        )
    else:
        st.info("Enter player to auto-load cached dashboard data, or click `Refresh Turbo Dashboard` to fetch it.")
    st.stop()

player_id = st.session_state["player_id"]
days = st.session_state.get("active_days")
active_start_date = st.session_state.get("active_start_date")
active_patches = st.session_state.get("active_patches", [])
overview = st.session_state["overview"]
overview_cache_only = bool(st.session_state.get("overview_cache_only"))
min_hero_matches = st.session_state.get("min_hero_matches", min_hero_matches)
min_item_matches = st.session_state.get("min_item_matches", min_item_matches)
effective_start_date = get_effective_start_date(days, active_start_date)

if active_patches:
    selected_filter_text = f"Patches: {', '.join(active_patches)}"
    if effective_start_date:
        selected_filter_text += f" | Since {effective_start_date.isoformat()}"
elif effective_start_date:
    selected_filter_text = f"Since {effective_start_date.isoformat()}"
else:
    selected_filter_text = f"Last {days} days"
st.subheader(f"Player {player_id} - Turbo - {selected_filter_text}")
if overview_cache_only:
    st.caption("Loaded from local cache. Click `Refresh Turbo Dashboard` to sync new matches from OpenDota.")

if not overview:
    st.warning("No Turbo matches found for selected period.")
    st.stop()

total_matches = sum(int(row["matches"]) for row in overview)
total_wins = sum(int(row["wins"]) for row in overview)
total_losses = total_matches - total_wins
overall_wr = (total_wins / total_matches * 100.0) if total_matches else 0.0

top_cards = [
    ("Turbo Matches", f"{total_matches}"),
    ("Turbo Wins", colored_metric_html(total_wins, "#23a55a")),
    ("Turbo Losses", colored_metric_html(total_losses, "#d9534f")),
    ("Turbo Winrate", colored_winrate_html(overall_wr)),
]
top_html = "".join(
    f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div>'
    for label, value in top_cards
)
st.markdown(f'<div class="metrics-wrap">{top_html}</div>', unsafe_allow_html=True)

st.markdown("### Hero Overview")
filtered_overview = [row for row in overview if int(row["matches"]) >= min_hero_matches]

if not filtered_overview:
    st.warning(f"No heroes with at least {min_hero_matches} matches for selected period.")
    st.stop()

hero_table = [build_hero_overview_row(row) for row in filtered_overview]
hero_rows_by_id = {int(row["hero_id"]): row for row in filtered_overview}
hero_ids = list(hero_rows_by_id.keys())

hero_table_df = pd.DataFrame(hero_table, columns=HERO_OVERVIEW_COLUMN_ORDER)
hero_table_styler = hero_table_df.style
if not hero_table_df.empty:
    hero_table_styler = apply_cell_style(
        hero_table_styler,
        lambda _: "color: #23a55a; font-weight: 700;",
        subset=[HERO_WINS_COLUMN],
    )
    hero_table_styler = apply_cell_style(
        hero_table_styler,
        lambda _: "color: #d9534f; font-weight: 700;",
        subset=[HERO_LOSSES_COLUMN],
    )
    hero_table_styler = apply_cell_style(
        hero_table_styler,
        _style_winrate_cell,
        subset=["WR", "Rad WR", "Dire WR"],
    )

st.dataframe(
    hero_table_styler,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Icon": st.column_config.ImageColumn("Hero", help="Hero icon", width="small"),
    },
)


def _hero_option_label(hero_id: int) -> str:
    row = hero_rows_by_id[hero_id]
    return (
        f"{row['hero']}  |  {int(row['matches'])} matches  |  "
        f"{round(float(row['winrate']))}% WR  |  KDA {round(float(row['kda']), 1)}"
    )


default_selected_hero_id = default_hero_id(hero_ids, service.resolve_hero_name)
selected_hero_id = st.selectbox(
    "Select Hero",
    options=hero_ids,
    index=hero_ids.index(default_selected_hero_id),
    format_func=_hero_option_label,
)
selected_hero_row = hero_rows_by_id[selected_hero_id]
selected_hero_name = service.resolve_hero_name(selected_hero_id)

st.markdown(
    (
        '<div class="hero-select-preview">'
        f'<img src="{selected_hero_row.get("hero_image", "")}" alt="{selected_hero_name}"/>'
        "<div>"
        f'<div class="hero-select-name">{selected_hero_name}</div>'
        f'<div class="hero-select-meta">{int(selected_hero_row["matches"])} matches - '
        f'{colored_winrate_html(float(selected_hero_row["winrate"]))} WR - KDA {round(float(selected_hero_row["kda"]), 1)}</div>'
        "</div>"
        "</div>"
    ),
    unsafe_allow_html=True,
)

dashboard_loaded_at = st.session_state.get("dashboard_loaded_at")
current_hero_snapshot_key = build_hero_snapshot_request_key(
    player_id=player_id,
    hero_id=selected_hero_id,
    days=days,
    active_patches=active_patches,
    active_start_date=active_start_date,
    dashboard_loaded_at=str(dashboard_loaded_at) if dashboard_loaded_at is not None else None,
)
matchup_request_key = _matchup_cache_key(
    player_id=player_id,
    days=days,
    active_patches=active_patches,
    active_start_date=active_start_date,
    dashboard_loaded_at=str(dashboard_loaded_at) if dashboard_loaded_at is not None else None,
    selected_hero_id=selected_hero_id,
)
current_item_request_key = (*current_hero_snapshot_key, int(min_item_matches), ITEM_WINRATES_SCHEMA_VERSION)
_ensure_section_visible("matchup", matchup_request_key)
_ensure_section_visible("item", current_item_request_key)
_ensure_section_visible("recent", current_hero_snapshot_key)
hero_matches = _cache_get("hero_matches_by_key", current_hero_snapshot_key)
hero_matches_loaded = isinstance(hero_matches, list)
hero_loaded_at = _cache_get("hero_loaded_at_by_key", current_hero_snapshot_key)
hero_section_stale = _is_section_stale(
    str(hero_loaded_at) if hero_loaded_at is not None else None,
    str(dashboard_loaded_at) if dashboard_loaded_at is not None else None,
)

if not hero_matches_loaded:
    try:
        hero_matches = _load_selected_hero_matches(
            service,
            player_id,
            selected_hero_id,
            selected_hero_name,
            days,
            active_patches,
            active_start_date,
            current_hero_snapshot_key,
        )
        hero_matches_loaded = isinstance(hero_matches, list)
        hero_loaded_at = _cache_get("hero_loaded_at_by_key", current_hero_snapshot_key)
        hero_section_stale = _is_section_stale(
            str(hero_loaded_at) if hero_loaded_at is not None else None,
            str(dashboard_loaded_at) if dashboard_loaded_at is not None else None,
        )
    except Exception:  # noqa: BLE001
        hero_matches_loaded = False

st.caption("Selected hero actions")
action_col_0, action_col_1, action_col_2, action_col_3, action_col_4 = st.columns(5)
with action_col_0:
    load_all_sections = st.button("Refresh All Hero Sections")
with action_col_1:
    load_hero_matches = st.button("Refresh Hero Details")
with action_col_2:
    load_matchups = st.button("Refresh Matchups")
with action_col_3:
    load_item_winrates = st.button("Refresh Item Winrates")
with action_col_4:
    load_recent_matches = st.button("Refresh Recent Matches")
st.caption("Use `Refresh All Hero Sections` to rebuild all four selected-hero sections in one Streamlit rerun.")

if load_all_sections or load_hero_matches:
    try:
        hero_matches = _load_selected_hero_matches(
            service,
            player_id,
            selected_hero_id,
            selected_hero_name,
            days,
            active_patches,
            active_start_date,
            current_hero_snapshot_key,
            force_refresh=True,
        )
        hero_matches_loaded = True
        hero_section_stale = False
    except Exception as exc:  # noqa: BLE001
        show_error(exc)

st.markdown(f"### {selected_hero_name} - Detailed Turbo Stats")
matches = hero_matches if hero_matches_loaded else None
if hero_matches_loaded:
    matches = matches or []
    if matches:
        if hero_section_stale:
            st.caption("Hero details were loaded before the latest dashboard refresh. Use the hero action bar above to rebuild this section from the current dashboard snapshot.")
        stats = service.build_stats(matches)
        stats_cards = build_hero_detail_cards(
            {
                "matches": stats.matches,
                "wins": stats.wins,
                "losses": stats.losses,
                "winrate": stats.winrate,
                "avg_kills": stats.avg_kills,
                "avg_deaths": stats.avg_deaths,
                "avg_assists": stats.avg_assists,
                "kda": stats.kda_ratio,
                "avg_duration_seconds": stats.avg_duration_seconds,
                "avg_net_worth": stats.avg_net_worth,
                "avg_damage": stats.avg_damage,
                "max_kills": stats.max_kills,
                "max_hero_damage": stats.max_hero_damage,
                "radiant_wr": stats.radiant_wr,
                "dire_wr": stats.dire_wr,
            }
        )
        stats_html = "".join(
            (
                f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">'
                f"{colored_winrate_html(float(value.strip('%')) if isinstance(value, str) else float(value)) if label in WINRATE_CARD_LABELS else colored_metric_html(value, '#23a55a') if label == 'Won Matches' else colored_metric_html(value, '#d9534f') if label == 'Lost Matches' else value}"
                "</div></div>"
            )
            for label, value in stats_cards
        )
        st.markdown(f'<div class="metrics-wrap">{stats_html}</div>', unsafe_allow_html=True)
    else:
        st.warning("No matches for selected hero with current Turbo filter.")
else:
    st.info("Hero details load automatically from cache when available. Use the hero action bar above to build this section from the current dashboard snapshot.")

st.markdown("### Matchups")
if load_all_sections or load_matchups:
    try:
        _mark_section_visible("matchup", matchup_request_key)
        if active_patches and not supports_patch_overview:
            all_matchup_matches = st.session_state.get("patch_filtered_matches") or []
        else:
            all_matchup_matches = service.get_cached_matches(
                QueryFilters(
                    player_id=player_id,
                    game_mode=23,
                    game_mode_name="Turbo",
                    days=days,
                    start_date=active_start_date,
                    patch_names=active_patches,
                )
            )
        selected_matchup_matches = [m for m in all_matchup_matches if int(m.hero_id or 0) == selected_hero_id]
        matchup_rows = {
            "selected": matchup_utils.build_matchup_rows(
                matches=selected_matchup_matches,
                detail_lookup=service.get_match_details_if_cached,
                extract_player=service._extract_player_from_match_details,  # noqa: SLF001
                player_id=player_id,
                resolve_hero_name=service.resolve_hero_name,
                resolve_hero_image=service.resolve_hero_image,
            ),
            "global": matchup_utils.build_matchup_rows(
                matches=all_matchup_matches,
                detail_lookup=service.get_match_details_if_cached,
                extract_player=service._extract_player_from_match_details,  # noqa: SLF001
                player_id=player_id,
                resolve_hero_name=service.resolve_hero_name,
                resolve_hero_image=service.resolve_hero_image,
            ),
        }
        _cache_set("matchup_rows_by_key", matchup_request_key, matchup_rows)
        _cache_set("matchup_loaded_at_by_key", matchup_request_key, _utcnow_iso())
        _set_active_matchup_snapshot(matchup_request_key, matchup_rows)
    except Exception as exc:  # noqa: BLE001
        show_error(exc)

matchup_rows = _cache_get("matchup_rows_by_key", matchup_request_key)
if matchup_rows is None:
    matchup_rows = _get_active_matchup_snapshot(matchup_request_key)
    if matchup_rows is not None:
        _cache_set("matchup_rows_by_key", matchup_request_key, matchup_rows)
if matchup_rows is None:
    matchup_rows = _get_current_matchup_snapshot(matchup_request_key)
    if matchup_rows is not None:
        _cache_set("matchup_rows_by_key", matchup_request_key, matchup_rows)
if matchup_rows is None and _is_section_visible("matchup", matchup_request_key):
    try:
        if active_patches and not supports_patch_overview:
            all_matchup_matches = st.session_state.get("patch_filtered_matches") or []
        else:
            all_matchup_matches = service.get_cached_matches(
                QueryFilters(
                    player_id=player_id,
                    game_mode=23,
                    game_mode_name="Turbo",
                    days=days,
                    start_date=active_start_date,
                    patch_names=active_patches,
                )
            )
        selected_matchup_matches = [m for m in all_matchup_matches if int(m.hero_id or 0) == selected_hero_id]
        matchup_rows = {
            "selected": matchup_utils.build_matchup_rows(
                matches=selected_matchup_matches,
                detail_lookup=service.get_match_details_if_cached,
                extract_player=service._extract_player_from_match_details,  # noqa: SLF001
                player_id=player_id,
                resolve_hero_name=service.resolve_hero_name,
                resolve_hero_image=service.resolve_hero_image,
            ),
            "global": matchup_utils.build_matchup_rows(
                matches=all_matchup_matches,
                detail_lookup=service.get_match_details_if_cached,
                extract_player=service._extract_player_from_match_details,  # noqa: SLF001
                player_id=player_id,
                resolve_hero_name=service.resolve_hero_name,
                resolve_hero_image=service.resolve_hero_image,
            ),
        }
        _cache_set("matchup_rows_by_key", matchup_request_key, matchup_rows)
        _set_active_matchup_snapshot(matchup_request_key, matchup_rows)
    except Exception:
        matchup_rows = None
if isinstance(matchup_rows, dict):
    min_matchup_matches = st.slider(
        "Min matchup matches",
        min_value=1,
        max_value=20,
        value=st.session_state.get("min_matchup_matches", 3),
        step=1,
        key="min_matchup_matches",
    )
    selected_tab, global_tab = st.tabs([f"{selected_hero_name}", "All Heroes"])
    matchup_column_config = {
        "Icon": st.column_config.ImageColumn("Hero", width="small"),
        "WR": st.column_config.NumberColumn("WR", format="%.2f%%"),
        "Won": st.column_config.NumberColumn("Won", format="%d"),
        "Lost": st.column_config.NumberColumn("Lost", format="%d"),
        "Matches": st.column_config.NumberColumn("Matches", format="%d"),
    }

    with selected_tab:
        selected_with = matchup_utils.build_matchup_summary_dataframe(
            matchup_utils.build_matchup_dataframe(matchup_rows["selected"]["with"], min_matchup_matches),
        )
        selected_against = matchup_utils.build_matchup_summary_dataframe(
            matchup_utils.build_matchup_dataframe(matchup_rows["selected"]["against"], min_matchup_matches),
        )
        selected_with_col, selected_against_col = st.columns(2)
        with selected_with_col:
            if not selected_with.empty:
                st.caption("Hero Teammates")
                st.dataframe(
                    matchup_utils.build_matchup_styler(
                        matchup_utils.sort_matchup_summary_dataframe(selected_with, best_first=True)
                    ),
                    use_container_width=True,
                    hide_index=True,
                    column_config=matchup_column_config,
                )
            else:
                st.info("No selected-hero teammate rows for current filter.")
        with selected_against_col:
            if not selected_against.empty:
                st.caption("Hero Opponents")
                st.dataframe(
                    matchup_utils.build_matchup_styler(
                        matchup_utils.sort_matchup_summary_dataframe(selected_against, best_first=False)
                    ),
                    use_container_width=True,
                    hide_index=True,
                    column_config=matchup_column_config,
                )
            else:
                st.info("No selected-hero opponent matchup rows for current filter.")

    with global_tab:
        global_with_summary = matchup_utils.build_matchup_summary_dataframe(
            matchup_utils.build_matchup_dataframe(matchup_rows["global"]["with"], min_matchup_matches),
        )
        global_matchup_summary = matchup_utils.build_matchup_summary_dataframe(
            matchup_utils.build_matchup_dataframe(matchup_rows["global"]["against"], min_matchup_matches),
        )
        global_with_col, global_against_col = st.columns(2)
        with global_with_col:
            if not global_with_summary.empty:
                st.caption("Player Teammates")
                st.dataframe(
                    matchup_utils.build_matchup_styler(
                        matchup_utils.sort_matchup_summary_dataframe(global_with_summary, best_first=True)
                    ),
                    use_container_width=True,
                    hide_index=True,
                    column_config=matchup_column_config,
                )
            else:
                st.info("No global teammate rows for current filter.")
        with global_against_col:
            if not global_matchup_summary.empty:
                st.caption("Player Opponents")
                st.dataframe(
                    matchup_utils.build_matchup_styler(
                        matchup_utils.sort_matchup_summary_dataframe(global_matchup_summary, best_first=False)
                    ),
                    use_container_width=True,
                    hide_index=True,
                    column_config=matchup_column_config,
                )
            else:
                st.info("No global opponent matchup rows for current filter.")
    if (
        selected_with.empty
        and selected_against.empty
        and global_with_summary.empty
        and global_matchup_summary.empty
    ):
        st.caption(
            "No cached match-detail player compositions are available for the current snapshot yet. "
            "Run `Refresh Turbo Dashboard` to hydrate them, then `Refresh Matchups` will rebuild from cache."
        )
else:
    st.info("Matchups use cached match details only. Use the hero action bar above to build selected-hero and global With/Against tables from already cached matches.")

if load_all_sections or load_item_winrates:
    try:
        _mark_section_visible("item", current_item_request_key)
        matches = _load_selected_hero_matches(
            service,
            player_id,
            selected_hero_id,
            selected_hero_name,
            days,
            active_patches,
            active_start_date,
            current_hero_snapshot_key,
        )
        item_snapshot_payload = _get_item_winrate_snapshot_safe(
            service,
            player_id=player_id,
            matches=matches,
            top_n=50,
            allow_detail_fetch=False,
        )
        item_wr_rows = [row for row in item_snapshot_payload["rows"] if int(row["matches_with_item"]) >= min_item_matches]
        item_wr_rows.sort(
            key=lambda row: (
                -round(float(row.get("item_winrate", 0.0))),
                -int(row.get("matches_with_item", 0)),
                -int(row.get("wins_with_item", 0)),
                str(row.get("item", "")),
            )
        )
        item_snapshot_payload["rows"] = item_wr_rows
        _cache_set("item_rows_by_key", current_item_request_key, item_snapshot_payload)
        _cache_set("item_loaded_at_by_key", current_item_request_key, _utcnow_iso())
        _set_current_section_snapshot("item", current_item_request_key, item_snapshot_payload)
    except Exception as exc:  # noqa: BLE001
        show_error(exc)

st.markdown("### Item Winrates")
st.caption("Counts use final inventory only. Cached match details can add backpack items; summary-only matches fall back to final slots.")
item_snapshot_payload = _cache_get("item_rows_by_key", current_item_request_key)
if isinstance(item_snapshot_payload, dict) and _item_snapshot_uses_legacy_purchase_logic(item_snapshot_payload):
    item_snapshot_payload = None
if item_snapshot_payload is None:
    item_snapshot_payload = _get_current_section_snapshot("item", current_item_request_key)
    if isinstance(item_snapshot_payload, dict) and _item_snapshot_uses_legacy_purchase_logic(item_snapshot_payload):
        item_snapshot_payload = None
    if item_snapshot_payload is not None:
        _cache_set("item_rows_by_key", current_item_request_key, item_snapshot_payload)
if item_snapshot_payload is None and _is_section_visible("item", current_item_request_key):
    try:
        matches = _load_selected_hero_matches(
            service,
            player_id,
            selected_hero_id,
            selected_hero_name,
            days,
            active_patches,
            active_start_date,
            current_hero_snapshot_key,
        )
        item_snapshot_payload = _get_item_winrate_snapshot_safe(
            service,
            player_id=player_id,
            matches=matches,
            top_n=50,
            allow_detail_fetch=False,
        )
        item_wr_rows = [row for row in item_snapshot_payload["rows"] if int(row["matches_with_item"]) >= min_item_matches]
        item_wr_rows.sort(
            key=lambda row: (
                -round(float(row.get("item_winrate", 0.0))),
                -int(row.get("matches_with_item", 0)),
                -int(row.get("wins_with_item", 0)),
                str(row.get("item", "")),
            )
        )
        item_snapshot_payload["rows"] = item_wr_rows
        _cache_set("item_rows_by_key", current_item_request_key, item_snapshot_payload)
        _set_current_section_snapshot("item", current_item_request_key, item_snapshot_payload)
    except Exception:
        item_snapshot_payload = None
item_loaded_at = _cache_get("item_loaded_at_by_key", current_item_request_key)
item_section_stale = _is_section_stale(
    str(item_loaded_at) if item_loaded_at is not None else None,
    str(dashboard_loaded_at) if dashboard_loaded_at is not None else None,
)
if isinstance(item_snapshot_payload, dict):
    item_wr_rows = item_snapshot_payload.get("rows") if isinstance(item_snapshot_payload.get("rows"), list) else []
    item_note = str(item_snapshot_payload.get("note") or "")
    item_is_complete = bool(item_snapshot_payload.get("is_complete"))
    if item_section_stale:
        st.caption("Item stats were loaded before the latest dashboard refresh. Use the hero action bar above to rebuild this section from the current dashboard snapshot.")
    if item_note:
        if item_is_complete:
            st.caption(item_note)
        else:
            st.warning(item_note)
    if item_wr_rows:
        item_table_html, item_table_height = _render_sortable_item_winrates_table(item_wr_rows)
        components.html(
            item_table_html,
            height=item_table_height,
            scrolling=False,
        )
    else:
        st.info("No items satisfy current minimum matches threshold.")
else:
    st.info("Item stats stay cached per hero/filter during the session. Use the hero action bar above to build this section from the current dashboard snapshot.")

recent_matches_key = recent_matches_state_key(selected_hero_id, days, active_patches, active_start_date)
if recent_matches_key not in st.session_state:
    st.session_state[recent_matches_key] = 10

if load_all_sections or load_recent_matches:
    try:
        _mark_section_visible("recent", current_hero_snapshot_key)
        matches = _load_selected_hero_matches(
            service,
            player_id,
            selected_hero_id,
            selected_hero_name,
            days,
            active_patches,
            active_start_date,
            current_hero_snapshot_key,
        )
        visible_recent_matches = int(st.session_state[recent_matches_key])
        recent_rows = service.build_recent_hero_matches(
            player_id=player_id,
            matches=matches,
            limit=min(visible_recent_matches, len(matches)),
            allow_detail_fetch=False,
        )
        recent_rows = _augment_recent_rows_with_cached_buffs(
            service,
            player_id=player_id,
            matches=matches,
            recent_rows=recent_rows,
        )
        _store_recent_section_snapshot(
            current_hero_snapshot_key,
            recent_rows,
            visible_recent_matches=visible_recent_matches,
        )
    except Exception as exc:  # noqa: BLE001
        show_error(exc)

st.markdown("### Hero Matches - Recent Matches for Hero")
repair_recent_item_timings = st.button("Repair Missing Item Timings via OpenDota Parse")
if repair_recent_item_timings:
    try:
        matches = _load_selected_hero_matches(
            service,
            player_id,
            selected_hero_id,
            selected_hero_name,
            days,
            active_patches,
            active_start_date,
            current_hero_snapshot_key,
        )
        visible_recent_matches = int(st.session_state[recent_matches_key])
        repair_status = service.repair_recent_match_item_timings(
            player_id=player_id,
            matches=matches,
            limit=min(visible_recent_matches, len(matches)),
        )
        recent_match_rows = service.build_recent_hero_matches(
            player_id=player_id,
            matches=matches,
            limit=min(visible_recent_matches, len(matches)),
            allow_detail_fetch=False,
        )
        recent_match_rows = _augment_recent_rows_with_cached_buffs(
            service,
            player_id=player_id,
            matches=matches,
            recent_rows=recent_match_rows,
        )
        _mark_section_visible("recent", current_hero_snapshot_key)
        _store_recent_section_snapshot(
            current_hero_snapshot_key,
            recent_match_rows,
            visible_recent_matches=visible_recent_matches,
        )
        if repair_status.completed > 0:
            st.success(
                f"Repaired item timings for {repair_status.completed} recent match(es)."
            )
        elif repair_status.pending > 0:
            st.warning(
                f"Submitted {repair_status.submitted} OpenDota parse request(s); {repair_status.pending} match(es) are still pending parse."
            )
        else:
            st.info("Visible recent matches already had all item timings available, or OpenDota has no parseable replay timing data yet.")
    except Exception as exc:  # noqa: BLE001
        show_error(exc)
recent_match_rows = _cache_get("recent_rows_by_key", current_hero_snapshot_key)
if recent_match_rows is None:
    recent_match_rows = _get_current_section_snapshot("recent", current_hero_snapshot_key)
    if recent_match_rows is not None:
        _cache_set("recent_rows_by_key", current_hero_snapshot_key, recent_match_rows)
if (recent_match_rows is None or (load and _is_section_visible("recent", current_hero_snapshot_key))) and _is_section_visible("recent", current_hero_snapshot_key):
    try:
        matches = _load_selected_hero_matches(
            service,
            player_id,
            selected_hero_id,
            selected_hero_name,
            days,
            active_patches,
            active_start_date,
            current_hero_snapshot_key,
        )
        visible_recent_matches = int(st.session_state[recent_matches_key])
        recent_match_rows = service.build_recent_hero_matches(
            player_id=player_id,
            matches=matches,
            limit=min(visible_recent_matches, len(matches)),
            allow_detail_fetch=False,
        )
        recent_match_rows = _augment_recent_rows_with_cached_buffs(
            service,
            player_id=player_id,
            matches=matches,
            recent_rows=recent_match_rows,
        )
        _store_recent_section_snapshot(
            current_hero_snapshot_key,
            recent_match_rows,
            visible_recent_matches=visible_recent_matches,
        )
    except Exception:
        recent_match_rows = None
recent_loaded_at = _cache_get("recent_loaded_at_by_key", current_hero_snapshot_key)
recent_matches_loaded = isinstance(recent_match_rows, list)
visible_recent_matches = int(st.session_state[recent_matches_key])
loaded_recent_matches = int(_cache_get("recent_limit_loaded_by_key", current_hero_snapshot_key) or 0)
recent_section_stale = _is_section_stale(
    str(recent_loaded_at) if recent_loaded_at is not None else None,
    str(dashboard_loaded_at) if dashboard_loaded_at is not None else None,
)

if recent_matches_loaded and loaded_recent_matches != visible_recent_matches:
    try:
        matches = hero_matches or []
        recent_match_rows = service.build_recent_hero_matches(
            player_id=player_id,
            matches=matches,
            limit=min(visible_recent_matches, len(matches)),
            allow_detail_fetch=False,
        )
        recent_match_rows = _augment_recent_rows_with_cached_buffs(
            service,
            player_id=player_id,
            matches=matches,
            recent_rows=recent_match_rows,
        )
        _store_recent_section_snapshot(
            current_hero_snapshot_key,
            recent_match_rows,
            visible_recent_matches=visible_recent_matches,
        )
    except Exception as exc:  # noqa: BLE001
        show_error(exc)
        recent_matches_loaded = False

if recent_matches_loaded:
    recent_match_rows = recent_match_rows or []
    if recent_section_stale:
        st.caption("Recent matches were loaded before the latest dashboard refresh. Use the hero action bar above to rebuild this section from the current dashboard snapshot.")
    st.caption(f"Showing {min(visible_recent_matches, len(matches))} of {len(matches)} matches")

    table_rows_html = ""
    for row in recent_match_rows:
        result_class = "win" if row.result == "Win" else "loss"
        duration_percent = duration_bar_percent(row.duration_seconds)
        kills_pct, deaths_pct, assists_pct = kda_bar_segments(row.kills, row.deaths, row.assists)
        regular_item_html = "".join(
            _render_item_icon_html(
                image_url=item.item_image,
                item_name=item.item_name,
                timing_min=item.purchase_time_min,
                is_buff=bool(getattr(item, "is_buff", False)),
            )
            for item in row.items
            if not bool(getattr(item, "is_buff", False))
        )
        buff_item_html = "".join(
            _render_item_icon_html(
                image_url=item.item_image,
                item_name=item.item_name,
                timing_min=item.purchase_time_min,
                is_buff=True,
            )
            for item in row.items
            if bool(getattr(item, "is_buff", False))
        )
        item_html = (
            f'<div class="recent-items-main">{regular_item_html}</div>'
            f'<div class="recent-items-buffs">{buff_item_html}</div>'
        ) if (regular_item_html or buff_item_html) else '<div class="recent-items-inline empty">No item data</div>'
        table_rows_html += (
            "<tr>"
            '<td class="recent-hero-cell">'
            '<div class="recent-hero-wrap">'
            '<div class="recent-hero-icon-wrap">'
            f'<img src="{row.hero_image}" alt="{row.hero_name}"/>'
            f'<div class="recent-hero-level">{row.hero_level or "?"}</div>'
            f'<div class="recent-hero-variant">{row.hero_variant or "-"}</div>'
            "</div>"
            f'<div class="recent-hero-name">{row.hero_name}</div>'
            "</div>"
            "</td>"
            f'<td><div class="recent-result {result_class}">{row.result} Match</div>'
            f'<div class="recent-when">{format_time_ago(row.started_at)}</div></td>'
            '<td>'
            f'<div class="recent-duration-value">{row.duration}</div>'
            f'<div class="recent-bar"><div class="recent-bar-fill" style="width:{duration_percent:.1f}%"></div></div>'
            "</td>"
            '<td>'
            f'<div class="recent-kda-value">{row.kills}/{row.deaths}/{row.assists}</div>'
            '<div class="recent-kda-bar">'
            f'<div class="recent-kda-kills" style="width:{kills_pct:.1f}%"></div>'
            f'<div class="recent-kda-deaths" style="width:{deaths_pct:.1f}%"></div>'
            f'<div class="recent-kda-assists" style="width:{assists_pct:.1f}%"></div>'
            "</div>"
            "</td>"
            f'<td><div class="recent-stat-value">{row.kda_ratio:.1f}</div></td>'
            f'<td><div class="recent-stat-value">{f"{round((row.net_worth or 0) / 1000, 1)}k" if row.net_worth else "-"}</div></td>'
            f'<td><div class="recent-stat-value">{f"{round((row.hero_damage or 0) / 1000, 1)}k" if row.hero_damage else "-"}</div></td>'
            f'<td><div class="recent-items-inline">{item_html}</div></td>'
            "</tr>"
        )

    st.markdown(
        (
            '<div class="recent-matches-wrap">'
            '<table class="recent-matches-table">'
            "<thead><tr>"
            "<th>Hero</th>"
            "<th>Result</th>"
            "<th>Duration</th>"
            "<th>K/D/A</th>"
            "<th>KDA</th>"
            "<th>Net Worth</th>"
            "<th>Damage</th>"
            "<th>Items</th>"
            "</tr></thead>"
            f"<tbody>{table_rows_html}</tbody>"
            "</table>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    if visible_recent_matches < len(matches):
        if st.button("Load 10 more matches", key=f"{recent_matches_key}_load_more"):
            st.session_state[recent_matches_key] = min(visible_recent_matches + 10, len(matches))
            st.rerun()
else:
    st.info("Recent matches stay cached per hero/filter during the session. Use the hero action bar above to build this section from the current dashboard snapshot.")

with st.expander("Experimental: Hero Trends", expanded=False):
    st.caption("Daily trend view for the selected hero. Kept at the bottom because this section is still experimental.")
    trend_metrics_key = f"hero_trends_metrics_{current_hero_snapshot_key}"
    trend_metric_defaults = ["winrate", "kda", "avg_net_worth", "avg_damage", "matches"]
    selected_trend_metrics = st.multiselect(
        "Daily Trend Metrics",
        options=list(TREND_METRIC_LABELS.keys()),
        default=trend_metric_defaults,
        format_func=lambda metric: TREND_METRIC_LABELS[metric],
        key=trend_metrics_key,
    )

    if hero_matches_loaded:
        matches = hero_matches or []
        if matches:
            trend_points = build_daily_trend_points(matches, service.build_stats)
            if not selected_trend_metrics:
                st.info("Select at least one trend metric.")
            else:
                trend_df = pd.DataFrame(
                    [
                        {
                            "Date": point.label,
                            **{TREND_METRIC_LABELS[key]: getattr(point, key) for key in selected_trend_metrics},
                        }
                        for point in trend_points
                    ]
                ).set_index("Date")
                for column in ("WR", "Rad WR", "Dire WR", "KDA"):
                    if column in trend_df.columns:
                        trend_df[column] = trend_df[column].round(2)
                for column in ("NW", "Dmg"):
                    if column in trend_df.columns:
                        trend_df[column] = trend_df[column].round(0)
                if "Dur" in trend_df.columns:
                    trend_df["Dur"] = trend_df["Dur"].round(1)
                st.line_chart(trend_df, use_container_width=True)
                st.dataframe(trend_df, use_container_width=True)
        else:
            st.info("No matches available for hero trends with current filter.")
    else:
        st.info("Hero trends use the selected hero match dataset. Use the hero action bar above and refresh hero details first.")

