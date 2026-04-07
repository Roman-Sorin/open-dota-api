from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clients.opendota_client import OpenDotaClient
from models.dtos import QueryFilters
from services.analytics_service import DotaAnalyticsService
from utils.cache import JsonFileCache
from utils.config import get_cache_dir, get_match_store_path, get_settings
from utils.match_store import SQLiteMatchStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill missing parsed item timings for cached Turbo matches.")
    parser.add_argument("--player", type=int, required=True, help="OpenDota account id")
    parser.add_argument("--patch", dest="patches", action="append", default=[], help="Patch name to include; repeatable")
    parser.add_argument("--batch-size", type=int, default=20, help="Maximum cached matches to process in this run")
    parser.add_argument("--poll-timeout", type=int, default=75, help="Seconds to wait for parse completion")
    parser.add_argument("--poll-interval", type=int, default=5, help="Seconds between parse polls")
    args = parser.parse_args()

    settings = get_settings()
    cache = JsonFileCache(get_cache_dir(), ttl_hours=settings.cache_ttl_hours)
    store = SQLiteMatchStore(get_match_store_path())
    client = OpenDotaClient(settings.base_url, timeout_seconds=settings.timeout_seconds, api_key=settings.api_key)
    service = DotaAnalyticsService(client=client, cache=cache, match_store=store)

    filters = QueryFilters(
        player_id=args.player,
        game_mode=23,
        game_mode_name="Turbo",
        patch_names=args.patches or None,
    )
    matches = service.get_cached_matches(filters)
    status = service.backfill_item_timing_details(
        player_id=args.player,
        matches=matches,
        batch_size=max(args.batch_size, 1),
        poll_timeout_seconds=max(args.poll_timeout, 0),
        poll_interval_seconds=max(args.poll_interval, 1),
    )
    print(
        "requested={requested} submitted={submitted} completed={completed} pending={pending} already_available={already_available}".format(
            requested=status.requested,
            submitted=status.submitted,
            completed=status.completed,
            pending=status.pending,
            already_available=status.already_available,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
