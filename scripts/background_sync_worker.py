from __future__ import annotations

import argparse
from datetime import datetime, timezone
import time
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.exceptions import OpenDotaError
from webapp.app_runtime import build_service


def _seconds_until(iso_value: str | None) -> int:
    if not iso_value:
        return 0
    try:
        target = datetime.fromisoformat(iso_value)
    except ValueError:
        return 0
    return max(int((target - datetime.now(tz=timezone.utc)).total_seconds()), 0)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an autonomous Turbo cache sync worker outside the Streamlit UI."
    )
    parser.add_argument("--player", type=int, required=True, help="OpenDota account id")
    parser.add_argument("--window-days", type=int, default=365, help="How far back the worker should fill the cache")
    parser.add_argument("--detail-batch", type=int, default=6, help="Max missing match details fetched per cycle")
    parser.add_argument("--parse-batch", type=int, default=2, help="Max replay parse requests submitted per cycle")
    parser.add_argument("--interval-seconds", type=int, default=60, help="Normal pause between successful cycles")
    parser.add_argument("--pause-after-429-seconds", type=int, default=600, help="Pause after OpenDota HTTP 429")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    args = parser.parse_args()

    service = build_service()

    while True:
        started_at = datetime.now(tz=timezone.utc).isoformat()
        try:
            result = service.run_background_sync_cycle(
                player_id=args.player,
                game_mode=23,
                window_days=max(args.window_days, 30),
                max_detail_fetches=max(args.detail_batch, 1),
                max_parse_requests=max(args.parse_batch, 0),
                rate_limit_cooldown_seconds=max(args.pause_after_429_seconds, 10),
                force=False,
            )
        except OpenDotaError as exc:
            print(f"[{started_at}] worker_error={exc}")
            if args.once:
                return 1
            time.sleep(max(args.pause_after_429_seconds, 10))
            continue

        print(
            "[{started}] status={status} total={total} new={new} details={details} parses={parses} pending={pending} note={note}".format(
                started=started_at,
                status=result.status,
                total=result.total_matches_in_window,
                new=result.summary_new_matches,
                details=result.detail_completed,
                parses=result.parse_requested,
                pending=result.pending_parse_count,
                note=result.note,
            )
        )

        if args.once:
            return 0

        if result.status == "rate_limited":
            sleep_seconds = _seconds_until(result.next_retry_at)
            time.sleep(max(sleep_seconds, max(args.pause_after_429_seconds, 10)))
        elif result.status == "cooldown":
            sleep_seconds = _seconds_until(result.next_retry_at)
            time.sleep(max(sleep_seconds, 10))
        else:
            time.sleep(max(args.interval_seconds, 10))


if __name__ == "__main__":
    raise SystemExit(main())
