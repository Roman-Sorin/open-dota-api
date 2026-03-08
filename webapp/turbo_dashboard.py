from pathlib import Path
from bisect import bisect_right
from datetime import datetime
import inspect
import re
import sys
import time

import streamlit as st
import streamlit.components.v1 as components

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
    return DotaAnalyticsService(client=client, cache=cache)


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


def _build_patch_ranges(patch_timeline: list[tuple[int, str]]) -> dict[str, tuple[int, int | None]]:
    ranges: dict[str, tuple[int, int | None]] = {}
    for i, (start_ts, name) in enumerate(patch_timeline):
        end_ts: int | None = None
        if i + 1 < len(patch_timeline):
            end_ts = patch_timeline[i + 1][0] - 1
        ranges[name] = (start_ts, end_ts)
    return ranges


def _patch_option_label(name: str, patch_ranges: dict[str, tuple[int, int | None]]) -> str:
    if name not in patch_ranges:
        return name
    start_ts, end_ts = patch_ranges[name]
    start_str = datetime.utcfromtimestamp(start_ts).strftime("%Y-%m-%d")
    end_str = "now" if end_ts is None else datetime.utcfromtimestamp(end_ts).strftime("%Y-%m-%d")
    return f"{name} ({start_str} - {end_str})"


def _hide_patch_dates_in_selected_tags() -> None:
    # Streamlit applies format_func labels to both dropdown options and selected tags.
    # Keep long labels in dropdown, but shorten selected tags back to patch name.
    components.html(
        """
        <script>
          (function() {
            const clean = () => {
              const tags = parent.document.querySelectorAll(
                'div[data-testid="stMultiSelect"] div[data-baseweb="tag"] span'
              );
              tags.forEach((el) => {
                const txt = (el.textContent || '');
                el.textContent = txt.replace(/\\s*\\(\\d{4}-\\d{2}-\\d{2}\\s*-\\s*(?:\\d{4}-\\d{2}-\\d{2}|now)\\)\\s*$/, '');
              });
            };
            clean();
            setTimeout(clean, 200);
            setTimeout(clean, 800);
          })();
        </script>
        """,
        height=0,
    )


def _build_overview_from_matches(matches: list[MatchSummary], service: DotaAnalyticsService) -> list[dict]:
    grouped: dict[int, dict[str, float]] = {}
    for match in matches:
        hero_id = int(match.hero_id or 0)
        if hero_id <= 0:
            continue
        bucket = grouped.setdefault(
            hero_id,
            {"matches": 0, "wins": 0, "kills": 0.0, "deaths": 0.0, "assists": 0.0},
        )
        bucket["matches"] += 1
        bucket["wins"] += 1 if match.did_win else 0
        bucket["kills"] += float(match.kills)
        bucket["deaths"] += float(match.deaths)
        bucket["assists"] += float(match.assists)

    rows: list[dict] = []
    for hero_id, agg in grouped.items():
        games = int(agg["matches"])
        wins = int(agg["wins"])
        losses = games - wins
        avg_k = agg["kills"] / games
        avg_d = agg["deaths"] / games
        avg_a = agg["assists"] / games
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
                "kda": kda,
            }
        )
    rows.sort(key=lambda x: (-x["matches"], -x["winrate"]))
    return rows


st.title("Turbo Buff")
st.caption("Turbo-only Dota 2 personal analytics based on OpenDota")

service = build_service()
try:
    service_overview_sig = inspect.signature(service.get_turbo_hero_overview)
    supports_patch_overview = "patch_names" in service_overview_sig.parameters
except Exception:  # noqa: BLE001
    supports_patch_overview = False
query_filters_supports_patch = "patch_names" in getattr(QueryFilters, "__dataclass_fields__", {})
patch_timeline = _load_patch_timeline(service)
patch_options = _build_patch_options(patch_timeline)
patch_ranges = _build_patch_ranges(patch_timeline)

with st.sidebar:
    st.header("Filters")
    player_raw = st.text_input(
        "Player ID or OpenDota URL",
        value=st.session_state.get("player_raw", "1233793238"),
    )
    time_mode_options = ["Days", "Patches"]
    default_mode = st.session_state.get("time_filter_mode", "Days")
    time_filter_mode = st.radio(
        "Time filter mode",
        options=time_mode_options,
        index=time_mode_options.index(default_mode) if default_mode in time_mode_options else 0,
    )

    days = st.session_state.get("days", 60)
    selected_patches = st.session_state.get("selected_patches", [])
    if time_filter_mode == "Days":
        days = st.slider("Period (days)", min_value=7, max_value=365, value=days, step=1)
    else:
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
                format_func=lambda p: _patch_option_label(p, patch_ranges),
            )
            _hide_patch_dates_in_selected_tags()

    min_hero_matches = st.slider(
        "Min matches per hero",
        min_value=1,
        max_value=50,
        value=st.session_state.get("min_hero_matches", 3),
        step=1,
    )
    min_item_matches = st.slider("Min matches per item", min_value=1, max_value=30, value=5, step=1)
    load = st.button("Load Turbo Dashboard", type="primary")

# Auto-load once on first page open, manual button remains available for refresh.
if "auto_loaded" not in st.session_state:
    st.session_state["auto_loaded"] = False

if not st.session_state["auto_loaded"] and "overview" not in st.session_state:
    load = True
    st.session_state["auto_loaded"] = True

if load:
    try:
        if time_filter_mode == "Patches" and not selected_patches:
            st.warning("Select at least one patch.")
            st.stop()

        active_days = days if time_filter_mode == "Days" else None
        active_patches = selected_patches if time_filter_mode == "Patches" else []

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
            )
            all_turbo_matches = run_with_rate_limit_retry(
                lambda: service.fetch_matches(base_filters),
                operation_label="patch-filtered matches",
            )
            selected_set = set(active_patches)
            patch_filtered_matches = [
                m for m in all_turbo_matches if _resolve_patch_name(m.start_time, patch_timeline) in selected_set
            ]
            overview = _build_overview_from_matches(patch_filtered_matches, service)
        else:
            overview_kwargs: dict[str, object] = {
                "player_id": player_id,
                "days": active_days,
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
        st.session_state["selected_patches"] = selected_patches
        st.session_state["active_patches"] = active_patches
        st.session_state["overview"] = overview
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
active_patches = st.session_state.get("active_patches", [])
overview = st.session_state["overview"]
min_hero_matches = st.session_state.get("min_hero_matches", min_hero_matches)
min_item_matches = st.session_state.get("min_item_matches", min_item_matches)

if active_patches:
    selected_filter_text = f"Patches: {', '.join(active_patches)}"
else:
    selected_filter_text = f"Last {days} days"
st.subheader(f"Player {player_id} - Turbo - {selected_filter_text}")

if not overview:
    st.warning("No Turbo matches found for selected period.")
    st.stop()

total_matches = sum(int(row["matches"]) for row in overview)
total_wins = sum(int(row["wins"]) for row in overview)
overall_wr = (total_wins / total_matches * 100.0) if total_matches else 0.0

top_cards = [
    ("Turbo Matches", f"{total_matches}"),
    ("Turbo Wins", f"{total_wins}"),
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
    }
    for row in filtered_overview
]
st.dataframe(
    hero_table,
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

st.markdown("### Item Winrates (when item appears in final slots)")
if item_wr_rows:
    item_winrate_table = [
        {
            "Icon": row.get("item_image", ""),
            "Item": row["item"],
            "Item Winrate": f"{round(float(row['item_winrate']))}%",
            "Matches With Item": int(row["matches_with_item"]),
            "Item Pick Rate": f"{round(float(row['item_pick_rate']))}%",
            "Wins With Item": int(row["wins_with_item"]),
        }
        for row in item_wr_rows
    ]
    st.dataframe(
        item_winrate_table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Icon": st.column_config.ImageColumn("Item", help="Item icon", width="small"),
        },
    )
else:
    st.info("No items satisfy current minimum matches threshold.")
