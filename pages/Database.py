from __future__ import annotations

from datetime import datetime, timezone
import html
from pathlib import Path
import sys
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Turbo Buff - Database", layout="wide")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.exceptions import OpenDotaError, OpenDotaRateLimitError, ValidationError
from utils.config import is_persistent_match_store_configured
from utils.helpers import format_duration, parse_player_id, unix_to_dt
from webapp.app_runtime import build_service, get_app_version, get_store_warning

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")
DATABASE_UI_VERSION = "v3"
SYNC_PRESETS: dict[str, dict[str, int]] = {
    "Safe": {"detail_batch": 4, "parse_batch": 1, "interval_seconds": 30},
    "Balanced": {"detail_batch": 5, "parse_batch": 5, "interval_seconds": 15},
    "Fast": {"detail_batch": 10, "parse_batch": 10, "interval_seconds": 15},
}


def _ui_key(name: str) -> str:
    return f"{name}_{DATABASE_UI_VERSION}"


def _next_auto_phase(current_phase: str) -> str:
    return "run" if current_phase != "run" else "display"


def _format_datetime(value: str | None) -> str:
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return str(value)
    return dt.astimezone(ISRAEL_TZ).strftime("%Y-%m-%d %H:%M Israel")


def _format_match_time(start_time: int | None) -> str:
    if not start_time:
        return "-"
    return unix_to_dt(int(start_time)).astimezone(ISRAEL_TZ).strftime("%Y-%m-%d %H:%M Israel")


def _status_chip(label: str, *, color: str, background: str) -> str:
    return (
        f'<span style="display:inline-block;padding:0.18rem 0.48rem;border-radius:999px;'
        f'background:{background};color:{color};font-weight:700;font-size:0.74rem;white-space:nowrap;">'
        f"{html.escape(label)}</span>"
    )


def _detail_chip(row: Any) -> str:
    if row.detail_status == "cached":
        return _status_chip("Cached", color="#166534", background="rgba(34,197,94,0.14)")
    return _status_chip("Missing", color="#991b1b", background="rgba(239,68,68,0.16)")


def _timing_chip(row: Any) -> str:
    if row.timing_status == "ready":
        return _status_chip("Ready", color="#166534", background="rgba(34,197,94,0.14)")
    if row.timing_status == "not_needed":
        return _status_chip("N/A", color="#854d0e", background="rgba(234,179,8,0.18)")
    if row.timing_status == "pending_parse":
        return _status_chip("Parse Pending", color="#1d4ed8", background="rgba(59,130,246,0.14)")
    return _status_chip("Missing", color="#991b1b", background="rgba(239,68,68,0.16)")


def _cycle_status_chip(status: str) -> str:
    normalized = (status or "unknown").lower()
    if normalized == "completed":
        return _status_chip("Completed", color="#166534", background="rgba(34,197,94,0.14)")
    if normalized == "cooldown":
        return _status_chip("Cooldown", color="#1d4ed8", background="rgba(59,130,246,0.14)")
    if normalized == "rate_limited":
        return _status_chip("Rate Limited", color="#991b1b", background="rgba(239,68,68,0.16)")
    if normalized == "error":
        return _status_chip("Error", color="#991b1b", background="rgba(239,68,68,0.16)")
    return _status_chip(status.title(), color="#854d0e", background="rgba(234,179,8,0.18)")


def _preset_help_text(preset_name: str) -> str:
    preset = SYNC_PRESETS[preset_name]
    return (
        f"{preset_name}: up to {preset['detail_batch']} match details and "
        f"{preset['parse_batch']} parse request(s) per cycle, auto-refresh every "
        f"{preset['interval_seconds']} sec."
    )


def _metric_card(label: str, value: str) -> str:
    return (
        '<div style="flex:1 1 170px;border:1px solid rgba(49,51,63,0.18);border-radius:0.55rem;'
        'padding:0.7rem;background:rgba(255,255,255,0.02);">'
        f'<div style="font-size:0.78rem;opacity:0.8;">{html.escape(label)}</div>'
        f'<div style="font-size:1.05rem;font-weight:700;margin-top:0.2rem;">{value}</div>'
        "</div>"
    )


def _render_metrics(coverage: Any, state: dict[str, object] | None) -> None:
    state = state or {}
    cards = [
        _metric_card("Turbo Matches In Window", str(coverage.total_matches)),
        _metric_card("Detail Cached", f"{coverage.detail_cached_count}/{coverage.total_matches}"),
        _metric_card("Timings Ready", f"{coverage.timing_ready_count}/{coverage.total_matches}"),
        _metric_card("Missing Detail", str(coverage.missing_detail_count)),
        _metric_card("Missing Timings", str(coverage.missing_timing_count)),
        _metric_card("Pending Parse", str(coverage.pending_parse_count)),
        _metric_card("Window Range", f"{_format_match_time(coverage.oldest_match_start_time)} to {_format_match_time(coverage.newest_match_start_time)}"),
        _metric_card("Fully Cached Through", _format_match_time(coverage.oldest_fully_cached_start_time)),
        _metric_card("Last Status", _cycle_status_chip(str(state.get("last_status") or state.get("status") or "idle"))),
        _metric_card("Next Retry", _format_datetime(str(state.get('next_retry_at')) if state.get('next_retry_at') else None)),
    ]
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;gap:0.55rem;margin:0.4rem 0 1rem 0;">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


class _PageCoverage:
    def __init__(self, state: dict[str, object] | None, rows: list[Any]) -> None:
        state = state or {}
        self.total_matches = int(state.get("target_match_count") or len(rows))
        self.detail_cached_count = int(state.get("detail_cached_count") or 0)
        self.timing_ready_count = int(state.get("timing_ready_count") or 0)
        self.missing_detail_count = int(state.get("missing_detail_count") or 0)
        self.missing_timing_count = int(state.get("missing_timing_count") or 0)
        self.pending_parse_count = int(state.get("pending_parse_count") or 0)
        self.newest_match_start_time = state.get("newest_match_start_time")
        self.oldest_match_start_time = state.get("oldest_match_start_time")
        self.oldest_fully_cached_start_time = state.get("oldest_fully_cached_start_time")
        self.rows = rows


def _render_match_table(rows: list[Any], service) -> None:
    table_rows: list[str] = []
    for row in rows:
        hero_name = html.escape(service.resolve_hero_name(row.hero_id))
        result = "Win" if ((row.player_slot < 128 and row.radiant_win) or (row.player_slot >= 128 and not row.radiant_win)) else "Loss"
        result_html = (
            f'<span style="font-weight:700;color:{"#23a55a" if result == "Win" else "#d9534f"};">{result}</span>'
        )
        table_rows.append(
            "<tr>"
            f"<td>{row.match_id}</td>"
            f"<td>{html.escape(_format_match_time(row.start_time))}</td>"
            f"<td>{hero_name}</td>"
            f"<td>{result_html}</td>"
            f"<td>{row.kills}/{row.deaths}/{row.assists}</td>"
            f"<td>{html.escape(format_duration(row.duration))}</td>"
            f"<td>{_detail_chip(row)}</td>"
            f"<td>{_timing_chip(row)}</td>"
            f"<td>{html.escape(_format_datetime(row.summary_updated_at))}</td>"
            f"<td>{html.escape(_format_datetime(row.detail_updated_at))}</td>"
            "</tr>"
        )

    st.markdown(
        """
        <style>
        .db-table-wrap { overflow-x: auto; }
        .db-table { width: 100%; min-width: 980px; border-collapse: collapse; font-size: 0.84rem; }
        .db-table th {
            text-align: left;
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            opacity: 0.72;
            padding: 0.48rem 0.55rem;
            border-bottom: 1px solid rgba(49, 51, 63, 0.18);
            white-space: nowrap;
        }
        .db-table td {
            padding: 0.55rem;
            border-bottom: 1px solid rgba(49, 51, 63, 0.1);
            vertical-align: middle;
            white-space: nowrap;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        (
            '<div class="db-table-wrap"><table class="db-table"><thead><tr>'
            "<th>Match ID</th><th>Played</th><th>Hero</th><th>Result</th><th>K/D/A</th><th>Duration</th>"
            "<th>Detail</th><th>Timings</th><th>Summary Cached</th><th>Detail Cached</th>"
            "</tr></thead><tbody>"
            + "".join(table_rows)
            + "</tbody></table></div>"
        ),
        unsafe_allow_html=True,
    )


service = build_service()
app_version = get_app_version()

st.title("Database")
st.caption(f"Build: `{app_version}`")
st.caption(
    "This page monitors the Turbo cache backlog for one player. It can auto-run one sync cycle per refresh while the page stays open. "
    "A true always-on background worker still requires an external runner; Streamlit pages do not keep running after the session is closed."
)
store_warning = get_store_warning()
if store_warning:
    st.error(store_warning)
if not is_persistent_match_store_configured():
    st.warning(
        "Persistent external match storage is not configured for this deployment yet. "
        "App reboot or redeploy can reset the local cache until Google Drive snapshot storage "
        "or DATABASE_URL is connected."
    )
with st.expander("How to use this page", expanded=True):
    st.markdown(
        """
        1. Open this page and check `Turbo Matches In Window`, `Detail Cached`, and `Timings Ready`.
        2. Press `Run Sync Cycle` once if you want one manual cache-fill pass.
        3. Enable `Auto-fill while this page stays open` if you want the page to keep working in the background while this browser tab stays open.
        4. Use `Sync Speed` to control how aggressive each cycle is. `Balanced` is the recommended default.

        Terms:
        - `Detail Cached`: full OpenDota match payload is already stored locally.
        - `Timings Ready`: item timings are already usable for that match.
        - `Pending Parse`: OpenDota replay parse was requested, but timing data is not ready yet.
        - `Fully Cached Through`: newest continuous part of the window that is already complete without gaps.
        """
    )
    st.caption(
        "Times on this page are shown in Israel time. During implementation I tested real OpenDota requests and observed "
        "rate-limit headers such as `X-Rate-Limit-Remaining-Minute` and `X-Rate-Limit-Remaining-Day`. "
        "Based on that, the default auto mode is now `Balanced` at 15 seconds."
    )

player_default = st.session_state.get(_ui_key("database_player_raw"), st.session_state.get("player_raw", "1233793238"))
window_default = int(st.session_state.get(_ui_key("database_window_days"), 365) or 365)
detail_default = int(st.session_state.get(_ui_key("database_detail_batch"), 5) or 5)
parse_default = int(st.session_state.get(_ui_key("database_parse_batch"), 5) or 5)
cooldown_default = int(st.session_state.get(_ui_key("database_cooldown_seconds"), 50) or 50)
auto_default = bool(st.session_state.get(_ui_key("database_auto_run"), True))
interval_default = int(st.session_state.get(_ui_key("database_auto_run_seconds"), 15) or 15)
page_size_default = int(st.session_state.get(_ui_key("database_page_size"), 100) or 100)
preset_default = st.session_state.get(_ui_key("database_sync_preset"), "Balanced")
auto_phase_key = _ui_key("database_auto_cycle_phase")
if preset_default not in SYNC_PRESETS:
    preset_default = "Balanced"

controls = st.columns([1.2, 0.8, 1.0])
player_raw = controls[0].text_input("Player ID or OpenDota URL", value=player_default, key=_ui_key("database_player_raw"))
window_days = controls[1].number_input(
    "Window (days)",
    min_value=30,
    value=window_default,
    step=1,
    key=_ui_key("database_window_days"),
    help="How far back the background cache should cover. Default is 365 days, but you can set a larger window.",
)
sync_preset = controls[2].selectbox(
    "Sync Speed",
    options=list(SYNC_PRESETS.keys()),
    index=list(SYNC_PRESETS.keys()).index(preset_default),
    key=_ui_key("database_sync_preset"),
    help="Safe = slower but gentler on quota, Balanced = recommended, Fast = more aggressive.",
)
st.caption(_preset_help_text(sync_preset))

secondary = st.columns([1.4, 1.0, 1.0])
cooldown_seconds = secondary[0].number_input(
    "Pause after rate-limit error (sec)",
    min_value=10,
    max_value=3600,
    value=cooldown_default,
    step=10,
    key=_ui_key("database_cooldown_seconds"),
    help="If OpenDota returns HTTP 429, auto-fill pauses for this many seconds before trying again.",
)
page_size = secondary[1].number_input(
    "Matches per page",
    min_value=10,
    max_value=500,
    value=page_size_default,
    step=10,
    key=_ui_key("database_page_size"),
    help="How many cached matches to display on one page. This does not limit the database job itself.",
)
auto_run = secondary[2].checkbox("Auto-fill while this page stays open", value=auto_default, key=_ui_key("database_auto_run"))
st.caption(
    f"If OpenDota returns HTTP 429, auto-fill pauses for {int(cooldown_seconds)} second(s) and then tries again."
)

active_detail_batch = SYNC_PRESETS[sync_preset]["detail_batch"]
active_parse_batch = SYNC_PRESETS[sync_preset]["parse_batch"]
active_interval_seconds = SYNC_PRESETS[sync_preset]["interval_seconds"]

with st.expander("Advanced settings"):
    detail_batch = st.number_input(
        "Match details per cycle",
        min_value=1,
        max_value=50,
        value=detail_default,
        step=1,
        key=_ui_key("database_detail_batch"),
        help="How many missing full match payloads the job may fetch in one cycle.",
    )
    parse_batch = st.number_input(
        "Replay parses per cycle",
        min_value=0,
        max_value=20,
        value=parse_default,
        step=1,
        key=_ui_key("database_parse_batch"),
        help="How many OpenDota replay-parse requests may be submitted in one cycle for missing item timings.",
    )
    auto_run_seconds = st.slider(
        "Auto-fill interval (sec)",
        min_value=15,
        max_value=300,
        value=interval_default,
        step=15,
        key=_ui_key("database_auto_run_seconds"),
        help="How often the page runs another cycle while this tab stays open.",
    )
    use_advanced_batches = st.checkbox(
        "Use advanced batch values instead of Sync Speed preset",
        value=False,
        key=_ui_key("database_use_advanced_batches"),
    )

if st.session_state.get(_ui_key("database_use_advanced_batches")):
    active_detail_batch = int(detail_batch)
    active_parse_batch = int(parse_batch)
    active_interval_seconds = int(auto_run_seconds)

run_cycle_request_key = _ui_key("database_run_cycle_requested")
force_cycle_request_key = _ui_key("database_force_cycle_requested")
run_cycle = bool(st.session_state.pop(run_cycle_request_key, False))
force_cycle = bool(st.session_state.pop(force_cycle_request_key, False))

try:
    player_id = parse_player_id(player_raw)
except ValidationError as exc:
    st.error(str(exc))
    st.stop()

st.session_state["player_raw"] = player_raw

auto_phase = str(st.session_state.get(auto_phase_key, "display") or "display")
if not auto_run:
    st.session_state[auto_phase_key] = "display"

run_result = None
should_run_auto_cycle = auto_run and auto_phase == "run"
if run_cycle or force_cycle or should_run_auto_cycle:
    try:
        run_result = service.run_background_sync_cycle(
            player_id=player_id,
            game_mode=23,
            window_days=int(window_days),
            max_detail_fetches=int(active_detail_batch),
            max_parse_requests=int(active_parse_batch),
            rate_limit_cooldown_seconds=int(cooldown_seconds),
            force=bool(force_cycle),
        )
        st.session_state[auto_phase_key] = "display"
    except (OpenDotaError, OpenDotaRateLimitError) as exc:
        st.error(str(exc))
        st.session_state[auto_phase_key] = "display"
    except Exception as exc:  # noqa: BLE001
        st.error(f"Background sync cycle failed: {exc}")
        st.session_state[auto_phase_key] = "display"

state = service.get_background_sync_state(player_id, game_mode=23, window_days=int(window_days))
runs = service.list_background_sync_runs(player_id, game_mode=23, window_days=int(window_days), limit=20)

total_rows = int((state or {}).get("target_match_count") or 0)
current_page_size = max(int(page_size), 1)
total_pages = max((max(total_rows, 1) + current_page_size - 1) // current_page_size, 1)
current_page = int(st.session_state.get(_ui_key("database_page_number"), 1) or 1)
current_page = max(1, min(current_page, total_pages))
start_idx = (current_page - 1) * current_page_size
page_rows = service.list_background_match_status_rows(
    player_id=player_id,
    game_mode=23,
    window_days=int(window_days),
    limit=current_page_size,
    offset=start_idx,
)
coverage = _PageCoverage(state, page_rows)

if run_result is not None:
    if run_result.status == "completed":
        st.success(run_result.note)
    elif run_result.status == "cooldown":
        st.info(run_result.note)
    elif run_result.status == "rate_limited":
        st.warning(run_result.note)

_render_metrics(coverage, state)
st.caption(
    f"Current cycle settings: up to {active_detail_batch} detail fetch(es) and {active_parse_batch} parse request(s) per cycle. "
    f"Auto-fill interval: {active_interval_seconds} sec. Pause after 429: {int(cooldown_seconds)} sec."
)

button_cols = st.columns([0.9, 0.9, 2.2])
if button_cols[0].button("Run One Sync Cycle", type="primary"):
    st.session_state[run_cycle_request_key] = True
    st.rerun()
if button_cols[1].button("Run Now Ignoring Cooldown"):
    st.session_state[force_cycle_request_key] = True
    st.rerun()

recent_runs_df = pd.DataFrame(
    [
        {
            "Started": _format_datetime(str(row.get("started_at")) if row.get("started_at") else None),
            "Status": str(row.get("status") or ""),
            "New summaries": int(row.get("summary_new_matches") or 0),
            "Detail fetched": int(row.get("detail_completed") or 0),
            "Parse requested": int(row.get("parse_requested") or 0),
            "Pending parse": int(row.get("pending_parse_count") or 0),
            "Rate limited": "Yes" if int(row.get("rate_limited") or 0) else "No",
            "Next retry": _format_datetime(str(row.get("next_retry_at")) if row.get("next_retry_at") else None),
            "Note": str(row.get("note") or ""),
        }
        for row in runs
    ]
)

st.subheader("Sync History")
if recent_runs_df.empty:
    st.info("No sync cycles recorded yet.")
else:
    st.dataframe(recent_runs_df, use_container_width=True, hide_index=True)
    rate_limited_runs = sum(1 for row in runs if int(row.get("rate_limited") or 0))
    detail_total = sum(int(row.get("detail_completed") or 0) for row in runs)
    parse_total = sum(int(row.get("parse_requested") or 0) for row in runs)
    st.caption(
        f"Observed over last {len(runs)} cycle(s): {detail_total} detail payload(s) fetched, "
        f"{parse_total} parse request(s) submitted, {rate_limited_runs} rate-limited cycle(s). "
        f"Current pause-after-429 on this page is {int(cooldown_seconds)} second(s)."
    )

st.subheader("Cached Matches")
if not coverage.rows:
    st.info("No cached Turbo matches for the selected window yet.")
else:
    nav_cols = st.columns([1.1, 0.9, 0.8, 0.8, 0.8, 0.8, 1.8])
    page_input = nav_cols[0].number_input(
        "Page",
        min_value=1,
        max_value=total_pages,
        value=current_page,
        step=1,
        key=_ui_key("database_page_number_input"),
    )
    if nav_cols[1].button("First", key=_ui_key("database_page_first")):
        current_page = 1
    elif nav_cols[2].button("Prev", key=_ui_key("database_page_prev")):
        current_page = max(1, current_page - 1)
    elif nav_cols[3].button("Next", key=_ui_key("database_page_next")):
        current_page = min(total_pages, current_page + 1)
    elif nav_cols[4].button("Last", key=_ui_key("database_page_last")):
        current_page = total_pages
    else:
        current_page = int(page_input)

    current_page = max(1, min(current_page, total_pages))
    st.session_state[_ui_key("database_page_number")] = current_page
    start_idx = (current_page - 1) * current_page_size
    end_idx = min(start_idx + current_page_size, total_rows)

    st.caption(
        f"Showing matches {start_idx + 1}-{end_idx} of {total_rows} cached match(es). "
        f"Page {current_page} of {total_pages}. This table is newest-first."
    )
    _render_match_table(coverage.rows, service)

if auto_run:
    st.caption(
        f"Auto-fill is active. Current browser phase: `{auto_phase}`. This page will rerun automatically while the tab stays open."
    )
    st.session_state[auto_phase_key] = _next_auto_phase(auto_phase)
    components.html(
        f"""
        <script>
        const delayMs = {int(active_interval_seconds) * 1000};
        setTimeout(() => {{
          try {{
            window.parent.location.reload();
          }} catch (err) {{
            window.location.reload();
          }}
        }}, delayMs);
        </script>
        """,
        height=0,
    )
