from pathlib import Path
import inspect
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clients.opendota_client import OpenDotaClient
from models.dtos import QueryFilters
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


@st.cache_resource
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


st.title("Turbo Buff")
st.caption("Turbo-only Dota 2 personal analytics based on OpenDota")

service = build_service()
service_overview_sig = inspect.signature(service.get_turbo_hero_overview)
supports_patch_overview = "patch_names" in service_overview_sig.parameters
supports_patch_options = hasattr(service, "get_patch_options")
supports_patch_filters = "patch_names" in getattr(QueryFilters, "__dataclass_fields__", {})
supports_patch_mode = supports_patch_overview and supports_patch_options and supports_patch_filters

with st.sidebar:
    st.header("Filters")
    player_raw = st.text_input(
        "Player ID or OpenDota URL",
        value=st.session_state.get("player_raw", "1233793238"),
    )
    time_mode_options = ["Days", "Patches"] if supports_patch_mode else ["Days"]
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
        patch_options = service.get_patch_options()
        default_patches = selected_patches or (patch_options[:1] if patch_options else [])
        selected_patches = st.multiselect(
            "Patches (multi-select)",
            options=patch_options,
            default=[p for p in default_patches if p in patch_options],
        )

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
        service.ensure_player_exists(player_id)
        overview_kwargs: dict[str, object] = {
            "player_id": player_id,
            "days": active_days,
        }
        if supports_patch_mode and active_patches:
            overview_kwargs["patch_names"] = active_patches
        overview = service.get_turbo_hero_overview(**overview_kwargs)

        st.session_state["player_raw"] = player_raw
        st.session_state["player_id"] = player_id
        st.session_state["time_filter_mode"] = time_filter_mode
        st.session_state["days"] = days
        st.session_state["active_days"] = active_days
        st.session_state["selected_patches"] = selected_patches
        st.session_state["active_patches"] = active_patches
        st.session_state["overview"] = overview
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
st.subheader(f"Player {player_id} · Turbo · {selected_filter_text}")

if not overview:
    st.warning("No Turbo matches found for selected period.")
    st.stop()

total_matches = sum(int(row["matches"]) for row in overview)
total_wins = sum(int(row["wins"]) for row in overview)
overall_wr = (total_wins / total_matches * 100.0) if total_matches else 0.0

col1, col2, col3 = st.columns(3)
col1.metric("Turbo Matches", f"{total_matches}")
col2.metric("Turbo Wins", f"{total_wins}")
col3.metric("Turbo Winrate", f"{round(overall_wr)}%")

st.markdown("### Hero Overview")
filtered_overview = [row for row in overview if int(row["matches"]) >= min_hero_matches]

if not filtered_overview:
    st.warning(f"No heroes with at least {min_hero_matches} matches for selected period.")
    st.stop()

hero_table = [
    {
        "hero_image": row.get("hero_image", ""),
        "hero": row["hero"],
        "kda": round(float(row["kda"]), 1),
        "matches": int(row["matches"]),
        "wins": int(row["wins"]),
        "losses": int(row["losses"]),
        "winrate": f"{round(float(row['winrate']))}%",
        "avg_kills": round(float(row["avg_kills"])),
        "avg_deaths": round(float(row["avg_deaths"])),
        "avg_assists": round(float(row["avg_assists"])),
    }
    for row in filtered_overview
]
st.dataframe(
    hero_table,
    use_container_width=True,
    hide_index=True,
    column_config={
        "hero_image": st.column_config.ImageColumn("Hero", help="Hero icon", width="small"),
    },
)

hero_options = {
    f"{row['hero']}  |  {row['matches']} matches  |  {round(float(row['winrate']))}% WR": int(row["hero_id"])
    for row in filtered_overview
}
selected_label = st.selectbox("Select Hero", options=list(hero_options.keys()))
selected_hero_id = hero_options[selected_label]
selected_hero_name = service.resolve_hero_name(selected_hero_id)

filters_kwargs: dict[str, object] = {
    "player_id": player_id,
    "hero_id": selected_hero_id,
    "hero_name": selected_hero_name,
    "game_mode": 23,
    "game_mode_name": "Turbo",
    "days": days,
}
if supports_patch_mode and active_patches:
    filters_kwargs["patch_names"] = active_patches
filters = QueryFilters(**filters_kwargs)

try:
    matches = service.fetch_matches(filters)
except Exception as exc:  # noqa: BLE001
    show_error(exc)
    st.stop()

if not matches:
    st.warning("No matches for selected hero with current Turbo filter.")
    st.stop()

stats = service.build_stats(matches)
item_wr_rows = service.get_item_winrates(player_id, matches, top_n=50)
item_wr_rows = [row for row in item_wr_rows if int(row["matches_with_item"]) >= min_item_matches]

st.markdown(f"### {selected_hero_name} · Detailed Turbo Stats")
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
            "item_image": row.get("item_image", ""),
            "item": row["item"],
            "item_winrate_%": f"{round(float(row['item_winrate']))}%",
            "matches_with_item": int(row["matches_with_item"]),
            "item_pick_rate_%": f"{round(float(row['item_pick_rate']))}%",
            "wins_with_item": int(row["wins_with_item"]),
        }
        for row in item_wr_rows
    ]
    st.dataframe(
        item_winrate_table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "item_image": st.column_config.ImageColumn("Item", help="Item icon", width="small"),
        },
    )
else:
    st.info("No items satisfy current minimum matches threshold.")

