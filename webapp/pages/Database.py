from __future__ import annotations

from datetime import datetime, timezone
import html
from pathlib import Path
import sys

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.analytics_service import BackgroundMatchStatusRow, BackgroundSyncCoverage
from utils.exceptions import OpenDotaError, OpenDotaRateLimitError, ValidationError
from utils.helpers import format_duration, parse_player_id, unix_to_dt
from webapp.app_runtime import build_service, get_app_version


st.set_page_config(page_title="Turbo Buff Database", layout="wide")


def _format_datetime(value: str | None) -> str:
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return str(value)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _format_match_time(start_time: int | None) -> str:
    if not start_time:
        return "-"
    return unix_to_dt(int(start_time)).strftime("%Y-%m-%d %H:%M UTC")


def _status_chip(label: str, *, color: str, background: str) -> str:
    return (
        f'<span style="display:inline-block;padding:0.18rem 0.48rem;border-radius:999px;'
        f'background:{background};color:{color};font-weight:700;font-size:0.74rem;white-space:nowrap;">'
        f"{html.escape(label)}</span>"
    )


def _detail_chip(row: BackgroundMatchStatusRow) -> str:
    if row.detail_status == "cached":
        return _status_chip("Cached", color="#166534", background="rgba(34,197,94,0.14)")
    return _status_chip("Missing", color="#991b1b", background="rgba(239,68,68,0.16)")


def _timing_chip(row: BackgroundMatchStatusRow) -> str:
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


def _metric_card(label: str, value: str) -> str:
    return (
        '<div style="flex:1 1 170px;border:1px solid rgba(49,51,63,0.18);border-radius:0.55rem;'
        'padding:0.7rem;background:rgba(255,255,255,0.02);">'
        f'<div style="font-size:0.78rem;opacity:0.8;">{html.escape(label)}</div>'
        f'<div style="font-size:1.05rem;font-weight:700;margin-top:0.2rem;">{value}</div>'
        "</div>"
    )


def _render_metrics(coverage: BackgroundSyncCoverage, state: dict[str, object] | None) -> None:
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


def _render_match_table(rows: list[BackgroundMatchStatusRow], service) -> None:
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


def _schedule_autorefresh(seconds: int) -> None:
    components.html(
        f"""
        <script>
        const target = window.parent;
        setTimeout(() => target.location.reload(), {max(seconds, 15) * 1000});
        </script>
        """,
        height=0,
    )


service = build_service()
app_version = get_app_version()

st.title("Database")
st.caption(f"Build: `{app_version}`")
st.caption(
    "This page monitors the Turbo cache backlog for one player. It can auto-run one sync cycle per refresh while the page stays open. "
    "A true always-on background worker still requires an external runner; Streamlit pages do not keep running after the session is closed."
)

player_default = st.session_state.get("database_player_raw", st.session_state.get("player_raw", "1233793238"))
window_default = int(st.session_state.get("database_window_days", 365) or 365)
detail_default = int(st.session_state.get("database_detail_batch", 8) or 8)
parse_default = int(st.session_state.get("database_parse_batch", 3) or 3)
cooldown_default = int(st.session_state.get("database_cooldown_minutes", 60) or 60)
auto_default = bool(st.session_state.get("database_auto_run", False))
interval_default = int(st.session_state.get("database_auto_run_seconds", 120) or 120)

controls = st.columns([1.2, 0.8, 0.8, 0.8])
player_raw = controls[0].text_input("Player ID or OpenDota URL", value=player_default, key="database_player_raw")
window_days = controls[1].number_input("Window (days)", min_value=30, max_value=365, value=window_default, step=1, key="database_window_days")
detail_batch = controls[2].number_input("Detail batch", min_value=1, max_value=50, value=detail_default, step=1, key="database_detail_batch")
parse_batch = controls[3].number_input("Parse batch", min_value=0, max_value=20, value=parse_default, step=1, key="database_parse_batch")

secondary = st.columns([0.8, 0.8, 1.2, 1.2])
cooldown_minutes = secondary[0].number_input(
    "Cooldown (min)",
    min_value=5,
    max_value=240,
    value=cooldown_default,
    step=5,
    key="database_cooldown_minutes",
)
table_limit = secondary[1].number_input("Rows", min_value=10, max_value=200, value=50, step=10)
auto_run = secondary[2].checkbox("Auto-run while this page stays open", value=auto_default, key="database_auto_run")
auto_run_seconds = secondary[3].slider("Auto-run interval (sec)", min_value=15, max_value=300, value=interval_default, step=15, key="database_auto_run_seconds")

button_cols = st.columns([0.9, 0.9, 2.2])
run_cycle = button_cols[0].button("Run Sync Cycle", type="primary")
force_cycle = button_cols[1].button("Force Sync Cycle")

try:
    player_id = parse_player_id(player_raw)
except ValidationError as exc:
    st.error(str(exc))
    st.stop()

st.session_state["player_raw"] = player_raw

run_result = None
if run_cycle or force_cycle or auto_run:
    try:
        run_result = service.run_background_sync_cycle(
            player_id=player_id,
            game_mode=23,
            window_days=int(window_days),
            max_detail_fetches=int(detail_batch),
            max_parse_requests=int(parse_batch),
            rate_limit_cooldown_minutes=int(cooldown_minutes),
            force=bool(force_cycle),
        )
    except (OpenDotaError, OpenDotaRateLimitError) as exc:
        st.error(str(exc))

state = service.get_background_sync_state(player_id, game_mode=23, window_days=int(window_days))
coverage = service.get_background_sync_coverage(
    player_id=player_id,
    game_mode=23,
    window_days=int(window_days),
    limit=None,
)
runs = service.list_background_sync_runs(player_id, game_mode=23, window_days=int(window_days), limit=20)

if run_result is not None:
    if run_result.status == "completed":
        st.success(run_result.note)
    elif run_result.status == "cooldown":
        st.info(run_result.note)
    elif run_result.status == "rate_limited":
        st.warning(run_result.note)

_render_metrics(coverage, state)

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
        f"Cooldown policy on this page is {int(cooldown_minutes)} minute(s) after a 429."
    )

st.subheader("Cached Matches")
if not coverage.rows:
    st.info("No cached Turbo matches for the selected window yet.")
else:
    _render_match_table(coverage.rows[: int(table_limit)], service)

if auto_run:
    st.caption(
        "Auto-run is enabled for this browser session. The page will refresh and run another cycle while it remains open."
    )
    _schedule_autorefresh(int(auto_run_seconds))
