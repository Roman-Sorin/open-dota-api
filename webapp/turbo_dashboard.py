from pathlib import Path
from bisect import bisect_right
from datetime import date, datetime, timedelta
import inspect
import os
import re
import subprocess
import sys
import time

import pandas as pd
import streamlit as st

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
from webapp.hero_overview import (
    HERO_DETAIL_METRIC_ORDER,
    HERO_LOSSES_COLUMN,
    HERO_OVERVIEW_COLUMN_ORDER,
    HERO_WINS_COLUMN,
    build_hero_detail_cards,
    build_hero_overview_row,
)
from webapp.hero_trends import build_daily_trend_points
from webapp.matchups import build_matchup_rows


st.set_page_config(page_title="Turbo Buff", layout="wide")
OVERVIEW_SCHEMA_VERSION = 11

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
        gap: 0.35rem;
        min-width: 236px;
    }
    .recent-items-inline.empty {
        opacity: 0.65;
    }
    .recent-item-inline {
        position: relative;
        width: 34px;
        flex: 0 0 34px;
    }
    .recent-item-inline img {
        width: 34px;
        height: 34px;
        border-radius: 5px;
        display: block;
        margin: 0 auto 0.15rem auto;
    }
    .recent-item-inline-time {
        font-size: 0.63rem;
        line-height: 1.1;
        font-weight: 700;
        white-space: nowrap;
        position: absolute;
        left: 2px;
        bottom: 2px;
        padding: 1px 3px;
        border-radius: 4px;
        color: #fff;
        background: rgba(17, 24, 39, 0.92);
    }
    .recent-item-inline-time.na {
        opacity: 0.58;
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
    start_date = date(2026, 1, 21)
    today = datetime.now().date()
    days = max((today - start_date).days, 7)
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


def _overview_looks_stale(overview: object) -> bool:
    if not isinstance(overview, list) or not overview:
        return False

    has_avg_damage_key = any(isinstance(row, dict) and "avg_damage" in row for row in overview)
    has_avg_net_worth_key = any(isinstance(row, dict) and "avg_net_worth" in row for row in overview)
    if not has_avg_damage_key or not has_avg_net_worth_key:
        return True

    positive_damage_rows = 0
    multi_match_rows = 0
    for row in overview:
        if not isinstance(row, dict):
            continue
        matches = int(row.get("matches") or 0)
        avg_damage = float(row.get("avg_damage") or 0.0)
        if matches > 1:
            multi_match_rows += 1
        if avg_damage > 0:
            positive_damage_rows += 1

    return multi_match_rows > 0 and positive_damage_rows == 0


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
        str(sync_state.get("latest_match_update_at") or ""),
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
        )

    _cache_set("hero_matches_by_key", current_hero_request_key, matches)
    _cache_set("hero_loaded_at_by_key", current_hero_request_key, _utcnow_iso())
    return matches

with st.sidebar:
    st.header("Filters")
    st.caption(f"Version: `{app_version}`")
    player_raw = st.text_input(
        "Player ID or OpenDota URL",
        value=st.session_state.get("player_raw", "1233793238"),
    )
    time_mode_options = ["Days", "Patches", "Start Date"]
    default_mode = st.session_state.get("time_filter_mode", "Days")
    time_filter_mode = st.radio(
        "Time filter mode",
        options=time_mode_options,
        index=time_mode_options.index(default_mode) if default_mode in time_mode_options else 0,
    )

    days = st.session_state.get("days", get_default_days_period())
    start_date_value = st.session_state.get("start_date", date(2026, 1, 21))
    selected_patches = st.session_state.get("selected_patches", [])
    if time_filter_mode == "Days":
        days = st.slider("Period (days)", min_value=7, max_value=365, value=days, step=1)
    elif time_filter_mode == "Patches":
        if not patch_options:
            st.warning("Patch list is temporarily unavailable (OpenDota constants).")
            selected_patches = []
        else:
            if "patches_widget_selection" not in st.session_state:
                st.session_state["patches_widget_selection"] = selected_patches or patch_options[:1]
            # Keep widget value valid when options list changes.
            st.session_state["patches_widget_selection"] = [
                p for p in st.session_state["patches_widget_selection"] if p in patch_options
            ] or patch_options[:1]
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
        value=st.session_state.get("min_hero_matches", 3),
        step=1,
    )
    min_item_matches = st.slider(
        "Min matches per item",
        min_value=1,
        max_value=30,
        value=st.session_state.get("min_item_matches", 3),
        step=1,
    )
    load = st.button("Refresh Turbo Dashboard", type="primary")

if "overview" in st.session_state and st.session_state.get("overview_schema_version") != OVERVIEW_SCHEMA_VERSION:
    st.session_state.pop("overview", None)
    st.session_state.pop("patch_filtered_matches", None)
    _clear_detail_sections()

if "overview" in st.session_state and _overview_looks_stale(st.session_state.get("overview")):
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
                all_cached_matches = service.get_cached_matches(base_filters)
                selected_set = set(active_patches)
                patch_filtered_matches = [
                    m for m in all_cached_matches if _resolve_patch_name(m.start_time, patch_timeline) in selected_set
                ]
                service.enrich_hero_damage(
                    player_id,
                    patch_filtered_matches,
                    max_fallback_detail_calls=max(120, len(patch_filtered_matches)),
                )
                overview = _build_overview_from_matches(patch_filtered_matches, service)
            else:
                patch_filtered_matches = None
                overview = service.get_cached_turbo_hero_overview(
                    player_id=player_id,
                    days=active_days,
                    start_date=active_start_date,
                    patch_names=active_patches,
                )
            if overview:
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
                lambda: service.fetch_matches(base_filters),
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
            )
            overview = _build_overview_from_matches(patch_filtered_matches, service)
        else:
            overview_kwargs: dict[str, object] = {
                "player_id": player_id,
                "days": active_days,
                "start_date": active_start_date,
            }
            if active_patches:
                overview_kwargs["patch_names"] = active_patches
            overview = run_with_rate_limit_retry(
                lambda: service.get_turbo_hero_overview(**overview_kwargs),
                operation_label="hero overview",
            )

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
    ("Turbo Wins", f"{total_wins}"),
    ("Turbo Losses", f"{total_losses}"),
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
    hero_table_styler = hero_table_styler.applymap(
        lambda _: "color: #23a55a; font-weight: 700;",
        subset=[HERO_WINS_COLUMN],
    ).applymap(
        lambda _: "color: #d9534f; font-weight: 700;",
        subset=[HERO_LOSSES_COLUMN],
    ).applymap(
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


default_hero_id = next(
    (hero_id for hero_id in hero_ids if service.resolve_hero_name(hero_id) == "Wraith King"),
    hero_ids[0],
)
selected_hero_id = st.selectbox(
    "Select Hero",
    options=hero_ids,
    index=hero_ids.index(default_hero_id),
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
current_item_request_key = (*current_hero_snapshot_key, int(min_item_matches))
hero_matches = _cache_get("hero_matches_by_key", current_hero_snapshot_key)
hero_matches_loaded = isinstance(hero_matches, list)
hero_loaded_at = _cache_get("hero_loaded_at_by_key", current_hero_snapshot_key)
hero_section_stale = _is_section_stale(
    str(hero_loaded_at) if hero_loaded_at is not None else None,
    str(dashboard_loaded_at) if dashboard_loaded_at is not None else None,
)

action_col_1, action_col_2, action_col_3 = st.columns(3)
with action_col_1:
    load_hero_matches = st.button("Refresh Hero Details")
with action_col_2:
    load_item_winrates = st.button("Refresh Item Winrates")
with action_col_3:
    load_recent_matches = st.button("Refresh Recent Matches")

if load_hero_matches:
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
            st.caption("Hero details were loaded before the latest dashboard refresh. Click `Refresh Hero Details` to rebuild this section from the current dashboard snapshot.")
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
    st.info("Hero details load automatically from cache when available. Click `Refresh Hero Details` to build this section from the current dashboard snapshot.")

st.markdown("### Matchups")
matchup_request_key = _matchup_cache_key(
    player_id=player_id,
    days=days,
    active_patches=active_patches,
    active_start_date=active_start_date,
    dashboard_loaded_at=str(dashboard_loaded_at) if dashboard_loaded_at is not None else None,
    selected_hero_id=selected_hero_id,
)
load_matchups = st.button("Refresh Matchups")
if load_matchups:
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
            "selected": build_matchup_rows(
                matches=selected_matchup_matches,
                detail_lookup=service._get_match_details_cached,  # noqa: SLF001
                extract_player=service._extract_player_from_match_details,  # noqa: SLF001
                player_id=player_id,
                resolve_hero_name=service.resolve_hero_name,
                resolve_hero_image=service.resolve_hero_image,
            ),
            "global": build_matchup_rows(
                matches=all_matchup_matches,
                detail_lookup=service._get_match_details_cached,  # noqa: SLF001
                extract_player=service._extract_player_from_match_details,  # noqa: SLF001
                player_id=player_id,
                resolve_hero_name=service.resolve_hero_name,
                resolve_hero_image=service.resolve_hero_image,
            ),
        }
        _cache_set("matchup_rows_by_key", matchup_request_key, matchup_rows)
        _cache_set("matchup_loaded_at_by_key", matchup_request_key, _utcnow_iso())
    except Exception as exc:  # noqa: BLE001
        show_error(exc)

matchup_rows = _cache_get("matchup_rows_by_key", matchup_request_key)
if isinstance(matchup_rows, dict):
    min_matchup_matches = st.slider("Min matchup matches", min_value=1, max_value=20, value=3, step=1)
    selected_tab, global_tab = st.tabs([f"{selected_hero_name}", "All Heroes"])

    def _matchup_df(rows: list) -> pd.DataFrame:
        filtered_rows = [row for row in rows if int(row.matches) >= min_matchup_matches]
        return pd.DataFrame(
            [
                {
                    "Icon": row.hero_image,
                    "Hero": row.hero,
                    "Matches": row.matches,
                    "Won": row.wins,
                    "Lost": row.losses,
                    "WR": f"{round(row.winrate)}%",
                    "Avg K/D/A": f"{round(row.avg_kills)}/{round(row.avg_deaths)}/{round(row.avg_assists)}",
                    "KDA": round(row.kda, 1),
                }
                for row in filtered_rows
            ]
        )

    with selected_tab:
        best_with, worst_against = st.columns(2)
        with best_with:
            st.caption("Best/Worst With")
            selected_with = _matchup_df(matchup_rows["selected"]["with"])
            if not selected_with.empty:
                st.caption("Best With")
                best = selected_with.sort_values(by=["WR", "Matches", "Hero"], ascending=[False, False, True]).head(8)
                worst = selected_with.sort_values(by=["WR", "Matches", "Hero"], ascending=[True, False, True]).head(8)
                st.dataframe(best, use_container_width=True, hide_index=True, column_config={"Icon": st.column_config.ImageColumn("Hero", width="small")})
                st.caption("Worst With")
                st.dataframe(worst, use_container_width=True, hide_index=True, column_config={"Icon": st.column_config.ImageColumn("Hero", width="small")})
            else:
                st.info("No selected-hero team matchup rows for current filter.")
        with worst_against:
            st.caption("Best/Worst Against")
            selected_against = _matchup_df(matchup_rows["selected"]["against"])
            if not selected_against.empty:
                st.caption("Best Against")
                best = selected_against.sort_values(by=["WR", "Matches", "Hero"], ascending=[False, False, True]).head(8)
                worst = selected_against.sort_values(by=["WR", "Matches", "Hero"], ascending=[True, False, True]).head(8)
                st.dataframe(best, use_container_width=True, hide_index=True, column_config={"Icon": st.column_config.ImageColumn("Hero", width="small")})
                st.caption("Worst Against")
                st.dataframe(worst, use_container_width=True, hide_index=True, column_config={"Icon": st.column_config.ImageColumn("Hero", width="small")})
            else:
                st.info("No selected-hero opponent matchup rows for current filter.")

    with global_tab:
        global_with_col, global_against_col = st.columns(2)
        with global_with_col:
            st.caption("Global Best/Worst With")
            global_with = _matchup_df(matchup_rows["global"]["with"])
            if not global_with.empty:
                st.caption("Global Best With")
                best = global_with.sort_values(by=["WR", "Matches", "Hero"], ascending=[False, False, True]).head(8)
                worst = global_with.sort_values(by=["WR", "Matches", "Hero"], ascending=[True, False, True]).head(8)
                st.dataframe(best, use_container_width=True, hide_index=True, column_config={"Icon": st.column_config.ImageColumn("Hero", width="small")})
                st.caption("Global Worst With")
                st.dataframe(worst, use_container_width=True, hide_index=True, column_config={"Icon": st.column_config.ImageColumn("Hero", width="small")})
            else:
                st.info("No global team matchup rows for current filter.")
        with global_against_col:
            st.caption("Global Best/Worst Against")
            global_against = _matchup_df(matchup_rows["global"]["against"])
            if not global_against.empty:
                st.caption("Global Best Against")
                best = global_against.sort_values(by=["WR", "Matches", "Hero"], ascending=[False, False, True]).head(8)
                worst = global_against.sort_values(by=["WR", "Matches", "Hero"], ascending=[True, False, True]).head(8)
                st.dataframe(best, use_container_width=True, hide_index=True, column_config={"Icon": st.column_config.ImageColumn("Hero", width="small")})
                st.caption("Global Worst Against")
                st.dataframe(worst, use_container_width=True, hide_index=True, column_config={"Icon": st.column_config.ImageColumn("Hero", width="small")})
            else:
                st.info("No global opponent matchup rows for current filter.")
else:
    st.info("Matchups need player match details. Click `Refresh Matchups` to build selected-hero and global With/Against tables from current cached matches.")

if load_item_winrates:
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
        item_wr_rows = service.get_item_winrates(player_id, matches, top_n=50)
        item_wr_rows = [row for row in item_wr_rows if int(row["matches_with_item"]) >= min_item_matches]
        item_wr_rows.sort(
            key=lambda row: (
                -round(float(row.get("item_winrate", 0.0))),
                -int(row.get("matches_with_item", 0)),
                -int(row.get("wins_with_item", 0)),
                str(row.get("item", "")),
            )
        )
        _cache_set("item_rows_by_key", current_item_request_key, item_wr_rows)
        _cache_set("item_loaded_at_by_key", current_item_request_key, _utcnow_iso())
    except Exception as exc:  # noqa: BLE001
        show_error(exc)

st.markdown("### Item Winrates (when item appears in final slots)")
item_wr_rows = _cache_get("item_rows_by_key", current_item_request_key)
item_loaded_at = _cache_get("item_loaded_at_by_key", current_item_request_key)
item_section_stale = _is_section_stale(
    str(item_loaded_at) if item_loaded_at is not None else None,
    str(dashboard_loaded_at) if dashboard_loaded_at is not None else None,
)
if isinstance(item_wr_rows, list):
    if item_section_stale:
        st.caption("Item stats were loaded before the latest dashboard refresh. Click `Refresh Item Winrates` to rebuild this section from the current dashboard snapshot.")
    if item_wr_rows:
        item_winrate_table = pd.DataFrame(
            [
                {
                    "Icon": row.get("item_image", ""),
                    "Item": row["item"],
                    "Item Winrate": round(float(row["item_winrate"])),
                    "Matches": int(row.get("matches_with_item", 0)),
                }
                for row in item_wr_rows
            ]
        )
        item_winrate_styler = item_winrate_table.style.applymap(
            _style_winrate_cell,
            subset=["Item Winrate"],
        )
        st.dataframe(
            item_winrate_styler,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Icon": st.column_config.ImageColumn("Item", help="Item icon", width="small"),
                "Item Winrate": st.column_config.NumberColumn("Item Winrate", format="%.0f%%"),
            },
        )
    else:
        st.info("No items satisfy current minimum matches threshold.")
else:
    st.info("Item stats stay cached per hero/filter during the session. Click `Refresh Item Winrates` to build this section from the current dashboard snapshot.")

recent_matches_key = recent_matches_state_key(selected_hero_id, days, active_patches, active_start_date)
if recent_matches_key not in st.session_state:
    st.session_state[recent_matches_key] = 10

if load_recent_matches:
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
        recent_rows = service.build_recent_hero_matches(
            player_id=player_id,
            matches=matches,
            limit=min(visible_recent_matches, len(matches)),
        )
        _cache_set("recent_rows_by_key", current_hero_snapshot_key, recent_rows)
        _cache_set("recent_loaded_at_by_key", current_hero_snapshot_key, _utcnow_iso())
        _cache_set("recent_limit_loaded_by_key", current_hero_snapshot_key, visible_recent_matches)
    except Exception as exc:  # noqa: BLE001
        show_error(exc)

st.markdown("### Hero Matches - Recent Matches for Hero")
recent_match_rows = _cache_get("recent_rows_by_key", current_hero_snapshot_key)
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
        )
        _cache_set("recent_rows_by_key", current_hero_snapshot_key, recent_match_rows)
        _cache_set("recent_limit_loaded_by_key", current_hero_snapshot_key, visible_recent_matches)
    except Exception as exc:  # noqa: BLE001
        show_error(exc)
        recent_matches_loaded = False

if recent_matches_loaded:
    recent_match_rows = recent_match_rows or []
    if recent_section_stale:
        st.caption("Recent matches were loaded before the latest dashboard refresh. Click `Refresh Recent Matches` to rebuild this section from the current dashboard snapshot.")
    st.caption(f"Showing {min(visible_recent_matches, len(matches))} of {len(matches)} matches")

    table_rows_html = ""
    for row in recent_match_rows:
        result_class = "win" if row.result == "Win" else "loss"
        duration_percent = duration_bar_percent(row.duration_seconds)
        kills_pct, deaths_pct, assists_pct = kda_bar_segments(row.kills, row.deaths, row.assists)
        item_html = "".join(
            (
                '<div class="recent-item-inline">'
                f'<img src="{item.item_image}" alt="{item.item_name}" title="{item.item_name}"/>'
                f'<div class="recent-item-inline-time{" na" if item.purchase_time_min is None else ""}">'
                f'{f"{item.purchase_time_min}m" if item.purchase_time_min is not None else "-"}'
                "</div>"
                "</div>"
            )
            for item in row.items
        ) or '<div class="recent-items-inline empty">No item data</div>'
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
    st.info("Recent matches stay cached per hero/filter during the session. Click `Refresh Recent Matches` to build this section from the current dashboard snapshot.")

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
        st.info("Hero trends use the selected hero match dataset. Click `Refresh Hero Details` first.")
