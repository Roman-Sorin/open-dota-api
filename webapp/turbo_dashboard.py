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
from utils.config import get_cache_dir, get_settings
from utils.exceptions import OpenDotaError, OpenDotaNotFoundError, OpenDotaRateLimitError, ValidationError
from utils.helpers import parse_player_id


st.set_page_config(page_title="Turbo Buff", layout="wide")
OVERVIEW_SCHEMA_VERSION = 5

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
    .recent-match-card {
        border: 1px solid rgba(49, 51, 63, 0.16);
        border-radius: 0.8rem;
        padding: 0.8rem;
        margin-bottom: 0.75rem;
        background: rgba(255, 255, 255, 0.03);
    }
    .recent-match-top {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.8rem;
    }
    .recent-match-hero {
        display: flex;
        align-items: center;
        gap: 0.7rem;
    }
    .recent-match-hero img {
        width: 40px;
        height: 40px;
        border-radius: 6px;
        object-fit: cover;
    }
    .recent-match-title {
        font-size: 0.95rem;
        font-weight: 700;
        line-height: 1.1;
    }
    .recent-match-subtitle {
        font-size: 0.78rem;
        opacity: 0.8;
        margin-top: 0.12rem;
    }
    .recent-match-result {
        font-size: 0.88rem;
        font-weight: 700;
        text-align: right;
        white-space: nowrap;
    }
    .recent-match-result.win {
        color: #23a55a;
    }
    .recent-match-result.loss {
        color: #d9534f;
    }
    .recent-match-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.6rem;
        margin-top: 0.75rem;
    }
    .recent-match-cell {
        border: 1px solid rgba(49, 51, 63, 0.12);
        border-radius: 0.65rem;
        padding: 0.55rem 0.65rem;
        background: rgba(255, 255, 255, 0.02);
    }
    .recent-match-label {
        font-size: 0.72rem;
        opacity: 0.72;
        text-transform: uppercase;
        letter-spacing: 0.03em;
    }
    .recent-match-value {
        font-size: 0.92rem;
        font-weight: 700;
        margin-top: 0.12rem;
    }
    .recent-match-items {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(58px, 1fr));
        gap: 0.45rem;
        margin-top: 0.75rem;
    }
    .recent-item {
        text-align: center;
    }
    .recent-item img {
        width: 100%;
        max-width: 58px;
        border-radius: 6px;
        display: block;
        margin: 0 auto 0.2rem auto;
    }
    .recent-item-time {
        font-size: 0.72rem;
        font-weight: 700;
        line-height: 1;
    }
    .recent-item-time.na {
        opacity: 0.6;
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
        .recent-match-grid {
            grid-template-columns: 1fr 1fr;
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
    return DotaAnalyticsService(client=client, cache=cache)


@st.cache_data(show_spinner=False)
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
    start_date = date(2026, 1, 22)
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
    grouped: dict[int, dict[str, float]] = {}
    for match in matches:
        hero_id = int(match.hero_id or 0)
        if hero_id <= 0:
            continue
        bucket = grouped.setdefault(
            hero_id,
            {
                "matches": 0,
                "wins": 0,
                "kills": 0.0,
                "deaths": 0.0,
                "assists": 0.0,
                "hero_damage": 0.0,
                "hero_damage_samples": 0,
            },
        )
        bucket["matches"] += 1
        bucket["wins"] += 1 if match.did_win else 0
        bucket["kills"] += float(match.kills)
        bucket["deaths"] += float(match.deaths)
        bucket["assists"] += float(match.assists)
        if match.hero_damage_known:
            bucket["hero_damage"] += float(match.hero_damage)
            bucket["hero_damage_samples"] += 1

    rows: list[dict] = []
    for hero_id, agg in grouped.items():
        games = int(agg["matches"])
        wins = int(agg["wins"])
        losses = games - wins
        avg_k = agg["kills"] / games
        avg_d = agg["deaths"] / games
        avg_a = agg["assists"] / games
        damage_samples = int(agg["hero_damage_samples"])
        avg_damage = agg["hero_damage"] / damage_samples if damage_samples > 0 else 0.0
        wr = (wins / games * 100.0) if games else 0.0
        kda = (avg_k + avg_a) / avg_d if avg_d > 0 else (avg_k + avg_a)
        rows.append(
            {
                "hero_id": hero_id,
                "hero": service.resolve_hero_name(hero_id),
                "hero_image": service.resolve_hero_image(hero_id),
                "matches": games,
                "wins": wins,
                "losses": losses,
                "winrate": wr,
                "avg_kills": avg_k,
                "avg_deaths": avg_d,
                "avg_assists": avg_a,
                "avg_damage": avg_damage,
                "avg_damage_samples": damage_samples,
                "kda": kda,
            }
        )
    rows.sort(key=lambda x: (-x["matches"], -x["winrate"]))
    return rows


def _ensure_item_rows_have_kda(
    item_rows: list[dict],
    matches: list[MatchSummary],
    service: DotaAnalyticsService,
    player_id: int,
) -> list[dict]:
    if not item_rows:
        return item_rows
    if all("avg_kills_with_item" in row and "kda_with_item" in row for row in item_rows):
        return item_rows

    target_item_ids = {int(row.get("item_id") or 0) for row in item_rows}
    target_item_ids.discard(0)

    per_item: dict[int, dict[str, float]] = {
        item_id: {"appearances": 0, "kills": 0.0, "deaths": 0.0, "assists": 0.0}
        for item_id in target_item_ids
    }

    total_matches = max(len(matches), 1)
    global_kills = sum(int(m.kills) for m in matches)
    global_deaths = sum(int(m.deaths) for m in matches)
    global_assists = sum(int(m.assists) for m in matches)
    global_avg_k = global_kills / total_matches
    global_avg_d = global_deaths / total_matches
    global_avg_a = global_assists / total_matches

    fallback_detail_calls = 0
    max_fallback_detail_calls = 45

    for match in matches:
        item_ids = [
            int(getattr(match, "item_0", 0) or 0),
            int(getattr(match, "item_1", 0) or 0),
            int(getattr(match, "item_2", 0) or 0),
            int(getattr(match, "item_3", 0) or 0),
            int(getattr(match, "item_4", 0) or 0),
            int(getattr(match, "item_5", 0) or 0),
        ]
        if not any(item_ids) and fallback_detail_calls < max_fallback_detail_calls:
            try:
                details = service._get_match_details_cached(match.match_id)  # noqa: SLF001
                fallback_detail_calls += 1
                player_row = service._extract_player_from_match_details(  # noqa: SLF001
                    details,
                    player_id=player_id,
                    player_slot=match.player_slot,
                )
                if player_row:
                    item_ids = service._player_row_item_ids(player_row)  # noqa: SLF001
            except OpenDotaRateLimitError:
                pass

        item_ids = set(item_ids)
        item_ids.discard(0)
        for item_id in item_ids:
            if item_id not in per_item:
                continue
            bucket = per_item[item_id]
            bucket["appearances"] += 1
            bucket["kills"] += float(match.kills)
            bucket["deaths"] += float(match.deaths)
            bucket["assists"] += float(match.assists)

    for row in item_rows:
        item_id = int(row.get("item_id") or 0)
        bucket = per_item.get(item_id)
        if bucket and bucket["appearances"] > 0:
            avg_k = bucket["kills"] / bucket["appearances"]
            avg_d = bucket["deaths"] / bucket["appearances"]
            avg_a = bucket["assists"] / bucket["appearances"]
        else:
            # Last-resort fallback for missing item-slot coverage.
            avg_k = global_avg_k
            avg_d = global_avg_d
            avg_a = global_avg_a

        row["avg_kills_with_item"] = avg_k
        row["avg_deaths_with_item"] = avg_d
        row["avg_assists_with_item"] = avg_a
        row["kda_with_item"] = (avg_k + avg_a) / avg_d if avg_d > 0 else (avg_k + avg_a)

    return item_rows


def _overview_looks_stale(overview: object) -> bool:
    if not isinstance(overview, list) or not overview:
        return False

    has_avg_damage_key = any(isinstance(row, dict) and "avg_damage" in row for row in overview)
    if not has_avg_damage_key:
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
    start_date_value = st.session_state.get("start_date", date(2026, 1, 22))
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
    min_item_matches = st.slider("Min matches per item", min_value=1, max_value=30, value=3, step=1)
    load = st.button("Load Turbo Dashboard", type="primary")

# Auto-load once on first page open, manual button remains available for refresh.
if "auto_loaded" not in st.session_state:
    st.session_state["auto_loaded"] = False

if not st.session_state["auto_loaded"] and "overview" not in st.session_state:
    load = True
    st.session_state["auto_loaded"] = True

# Force one-time refresh when overview structure changes between app versions.
if "overview" in st.session_state and st.session_state.get("overview_schema_version") != OVERVIEW_SCHEMA_VERSION:
    load = True

if "overview" in st.session_state and _overview_looks_stale(st.session_state.get("overview")):
    load = True

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

        st.session_state["player_raw"] = player_raw
        st.session_state["player_id"] = player_id
        st.session_state["time_filter_mode"] = time_filter_mode
        st.session_state["days"] = days
        st.session_state["active_days"] = active_days
        st.session_state["start_date"] = start_date_value
        st.session_state["active_start_date"] = active_start_date
        st.session_state["selected_patches"] = selected_patches
        st.session_state["active_patches"] = active_patches
        st.session_state["overview"] = overview
        st.session_state["overview_schema_version"] = OVERVIEW_SCHEMA_VERSION
        st.session_state["patch_filtered_matches"] = patch_filtered_matches
        st.session_state["min_hero_matches"] = min_hero_matches
        st.session_state["min_item_matches"] = min_item_matches
    except Exception as exc:  # noqa: BLE001
        show_error(exc)

if "overview" not in st.session_state:
    st.info("Enter player and click 'Load Turbo Dashboard'.")
    st.stop()

player_id = st.session_state["player_id"]
days = st.session_state.get("active_days")
active_start_date = st.session_state.get("active_start_date")
active_patches = st.session_state.get("active_patches", [])
overview = st.session_state["overview"]
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
    ("Turbo Winrate", f"{round(overall_wr)}%"),
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

hero_table = [
    {
        "Icon": row.get("hero_image", ""),
        "Hero": row["hero"],
        "Winrate": f"{round(float(row['winrate']))}%",
        "Avg K/D/A": (
            f"{round(float(row['avg_kills']))}/"
            f"{round(float(row['avg_deaths']))}/"
            f"{round(float(row['avg_assists']))}"
        ),
        "KDA": round(float(row["kda"]), 1),
        "Matches": int(row["matches"]),
        "Wins": int(row["wins"]),
        "Losses": int(row["losses"]),
        "Avg Kills": round(float(row["avg_kills"])),
        "Avg Deaths": round(float(row["avg_deaths"])),
        "Avg Assists": round(float(row["avg_assists"])),
        "Avg Damage": round(float(row.get("avg_damage", 0.0))),
    }
    for row in filtered_overview
]
hero_table_df = pd.DataFrame(hero_table)
if not hero_table_df.empty and "Avg Damage" in hero_table_df.columns:
    hero_table_df["Avg Damage"] = hero_table_df["Avg Damage"].astype("int64")

st.dataframe(
    hero_table_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Icon": st.column_config.ImageColumn("Hero", help="Hero icon", width="small"),
    },
)
hero_rows_by_id = {int(row["hero_id"]): row for row in filtered_overview}
hero_ids = list(hero_rows_by_id.keys())


def _hero_option_label(hero_id: int) -> str:
    row = hero_rows_by_id[hero_id]
    return (
        f"{row['hero']}  |  {int(row['matches'])} matches  |  "
        f"{round(float(row['winrate']))}% WR  |  KDA {round(float(row['kda']), 1)}"
    )


selected_hero_id = st.selectbox("Select Hero", options=hero_ids, format_func=_hero_option_label)
selected_hero_row = hero_rows_by_id[selected_hero_id]
selected_hero_name = service.resolve_hero_name(selected_hero_id)

st.markdown(
    (
        '<div class="hero-select-preview">'
        f'<img src="{selected_hero_row.get("hero_image", "")}" alt="{selected_hero_name}"/>'
        "<div>"
        f'<div class="hero-select-name">{selected_hero_name}</div>'
        f'<div class="hero-select-meta">{int(selected_hero_row["matches"])} matches - '
        f'{round(float(selected_hero_row["winrate"]))}% WR - KDA {round(float(selected_hero_row["kda"]), 1)}</div>'
        "</div>"
        "</div>"
    ),
    unsafe_allow_html=True,
)

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
    filters = QueryFilters(**filters_kwargs)

    try:
        matches = run_with_rate_limit_retry(
            lambda: service.fetch_matches(filters),
            operation_label="hero matches",
        )
    except Exception as exc:  # noqa: BLE001
        show_error(exc)
        st.stop()

if not matches:
    st.warning("No matches for selected hero with current Turbo filter.")
    st.stop()

stats = service.build_stats(matches)
item_wr_rows = service.get_item_winrates(player_id, matches, top_n=50)
item_wr_rows = [row for row in item_wr_rows if int(row["matches_with_item"]) >= min_item_matches]
item_wr_rows = _ensure_item_rows_have_kda(item_wr_rows, matches, service, player_id)
item_wr_rows.sort(
    key=lambda row: (
        -round(float(row.get("item_winrate", 0.0))),
        -int(row.get("matches_with_item", 0)),
        -int(row.get("wins_with_item", 0)),
        str(row.get("item", "")),
    )
)

st.markdown(f"### {selected_hero_name} - Detailed Turbo Stats")
stats_cards = [
    ("Matches", f"{round(stats.matches)}"),
    ("Winrate", f"{round(stats.winrate)}%"),
    ("Avg K/D/A", f"{round(stats.avg_kills)}/{round(stats.avg_deaths)}/{round(stats.avg_assists)}"),
    ("KDA", f"{round(stats.kda_ratio, 1)}"),
    ("Radiant WR", f"{round(stats.radiant_wr)}%"),
    ("Dire WR", f"{round(stats.dire_wr)}%"),
]
stats_html = "".join(
    f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div>'
    for label, value in stats_cards
)
st.markdown(f'<div class="metrics-wrap">{stats_html}</div>', unsafe_allow_html=True)

recent_matches_key = recent_matches_state_key(selected_hero_id, days, active_patches, active_start_date)
if recent_matches_key not in st.session_state:
    st.session_state[recent_matches_key] = 10
visible_recent_matches = int(st.session_state[recent_matches_key])
recent_match_rows = service.build_recent_hero_matches(
    player_id=player_id,
    matches=matches,
    limit=min(visible_recent_matches, len(matches)),
)

st.markdown("### Hero Matches - Recent Matches for Hero")
st.caption(f"Showing {min(visible_recent_matches, len(matches))} of {len(matches)} matches")

for row in recent_match_rows:
    result_class = "win" if row.result == "Win" else "loss"
    item_html = "".join(
        (
            '<div class="recent-item">'
            f'<img src="{item.item_image}" alt="{item.item_name}" title="{item.item_name}"/>'
            f'<div class="recent-item-time{" na" if item.purchase_time_min is None else ""}">'
            f'{f"{item.purchase_time_min}m" if item.purchase_time_min is not None else "-"}'
            "</div>"
            "</div>"
        )
        for item in row.items
    ) or '<div class="recent-match-subtitle">No item data</div>'
    st.markdown(
        (
            '<div class="recent-match-card">'
            '<div class="recent-match-top">'
            '<div class="recent-match-hero">'
            f'<img src="{row.hero_image}" alt="{row.hero_name}"/>'
            "<div>"
            f'<div class="recent-match-title">{row.hero_name}</div>'
            f'<div class="recent-match-subtitle">Match #{row.match_id} · {format_time_ago(row.started_at)}</div>'
            "</div>"
            "</div>"
            f'<div class="recent-match-result {result_class}">{row.result} Match</div>'
            "</div>"
            '<div class="recent-match-grid">'
            '<div class="recent-match-cell">'
            '<div class="recent-match-label">Duration</div>'
            f'<div class="recent-match-value">{row.duration}</div>'
            "</div>"
            '<div class="recent-match-cell">'
            '<div class="recent-match-label">KDA</div>'
            f'<div class="recent-match-value">{row.kills}/{row.deaths}/{row.assists}</div>'
            "</div>"
            '<div class="recent-match-cell">'
            '<div class="recent-match-label">Ratio</div>'
            f'<div class="recent-match-value">{round(row.kda_ratio, 1)}</div>'
            "</div>"
            '<div class="recent-match-cell">'
            '<div class="recent-match-label">Result</div>'
            f'<div class="recent-match-value">{row.result}</div>'
            "</div>"
            "</div>"
            f'<div class="recent-match-items">{item_html}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )

if visible_recent_matches < len(matches):
    if st.button("Load 10 more matches", key=f"{recent_matches_key}_load_more"):
        st.session_state[recent_matches_key] = min(visible_recent_matches + 10, len(matches))
        st.rerun()

st.markdown("### Item Winrates (when item appears in final slots)")
if item_wr_rows:
    item_winrate_table = [
        {
            "Icon": row.get("item_image", ""),
            "Item": row["item"],
            "Item Winrate": round(float(row["item_winrate"])),
            "Matches": int(row.get("matches_with_item", 0)),
            "Avg K/D/A": (
                f"{round(float(row.get('avg_kills_with_item', 0.0)))}/"
                f"{round(float(row.get('avg_deaths_with_item', 0.0)))}/"
                f"{round(float(row.get('avg_assists_with_item', 0.0)))}"
            ),
            "KDA": round(float(row.get("kda_with_item", 0.0)), 1),
        }
        for row in item_wr_rows
    ]
    st.dataframe(
        item_winrate_table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Icon": st.column_config.ImageColumn("Item", help="Item icon", width="small"),
            "Item Winrate": st.column_config.NumberColumn("Item Winrate", format="%.0f%%"),
        },
    )
else:
    st.info("No items satisfy current minimum matches threshold.")
