from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any

from clients.opendota_client import OpenDotaClient
from models.dtos import ItemStat, ItemsResult, MatchRow, MatchSummary, QueryFilters, StatsResult
from parsers.input_parser import HeroParser
from utils.cache import JsonFileCache
from utils.exceptions import OpenDotaNotFoundError, OpenDotaRateLimitError
from utils.helpers import calculate_kda_ratio, format_duration, unix_to_dt, winrate_percent
from utils.match_store import SQLiteMatchStore


@dataclass(slots=True)
class ReferenceData:
    hero_parser: HeroParser
    hero_names_by_id: dict[int, str]
    hero_images_by_id: dict[int, str]
    item_names_by_id: dict[int, str]
    item_images_by_id: dict[int, str]
    item_ids_by_key: dict[str, int]


@dataclass(slots=True)
class RecentMatchItem:
    item_id: int
    item_name: str
    item_image: str
    purchase_time_min: int | None


@dataclass(slots=True)
class RecentHeroMatch:
    match_id: int
    hero_name: str
    hero_image: str
    hero_level: int | None
    hero_variant: int | None
    result: str
    started_at: datetime
    duration: str
    duration_seconds: int
    kills: int
    deaths: int
    assists: int
    kda_ratio: float
    net_worth: int | None
    hero_damage: int | None
    items: list[RecentMatchItem]


@dataclass(slots=True)
class CachePolicy:
    key: str
    ttl: timedelta


class DotaAnalyticsService:
    def __init__(self, client: OpenDotaClient, cache: JsonFileCache, match_store: SQLiteMatchStore | None = None) -> None:
        self.client = client
        self.cache = cache
        self.match_store = match_store
        self.references = self._load_references()
        self._match_details_memory_cache: dict[int, dict[str, Any]] = {}
        self._patch_starts, self._patch_names = self._load_patch_timeline()

    def _load_references(self) -> ReferenceData:
        def to_asset_url(path: str | None) -> str:
            if not path:
                return ""
            if path.startswith("http://") or path.startswith("https://"):
                return path
            return f"https://cdn.cloudflare.steamstatic.com{path}"

        heroes = self.cache.get("constants_heroes")
        if heroes is None:
            heroes = self.client.get_constants_heroes()
            self.cache.set("constants_heroes", heroes)

        items = self.cache.get("constants_items")
        if items is None:
            items = self.client.get_constants_items()
            self.cache.set("constants_items", items)

        hero_parser = HeroParser.from_constants(heroes)
        hero_images_by_id: dict[int, str] = {}
        for hero in heroes.values():
            hero_id = int(hero.get("id") or 0)
            if hero_id <= 0:
                continue
            hero_images_by_id[hero_id] = to_asset_url(str(hero.get("img") or ""))

        item_names_by_id: dict[int, str] = {}
        item_images_by_id: dict[int, str] = {}
        item_ids_by_key: dict[str, int] = {}
        for key, value in items.items():
            item_id = int(value.get("id", 0))
            if item_id <= 0:
                continue
            display_name = str(value.get("dname") or key.replace("_", " ").title())
            item_names_by_id[item_id] = display_name
            item_images_by_id[item_id] = to_asset_url(str(value.get("img") or ""))
            item_ids_by_key[str(key)] = item_id

        return ReferenceData(
            hero_parser=hero_parser,
            hero_names_by_id=hero_parser.heroes,
            hero_images_by_id=hero_images_by_id,
            item_names_by_id=item_names_by_id,
            item_images_by_id=item_images_by_id,
            item_ids_by_key=item_ids_by_key,
        )

    def _load_patch_timeline(self) -> tuple[list[int], list[str]]:
        timeline: list[tuple[int, str]] = []

        cached_timeline = self.cache.get("patch_timeline_v2")
        if isinstance(cached_timeline, list) and cached_timeline:
            try:
                timeline = [
                    (int(row[0]), str(row[1]))
                    for row in cached_timeline
                    if isinstance(row, list | tuple) and len(row) == 2
                ]
            except Exception:
                timeline = []

        if not timeline and hasattr(self.client, "session"):
            try:
                response = self.client.session.get(
                    "https://www.dota2.com/datafeed/patchnoteslist",
                    params={"language": "english"},
                    timeout=self.client.timeout_seconds,
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
            except Exception:
                timeline = []

        if not timeline:
            patches = self.cache.get("constants_patch")
            if patches is None:
                patches = self.client.get_constants_patch()
                self.cache.set("constants_patch", patches)

            if isinstance(patches, list):
                for row in patches:
                    if not isinstance(row, dict):
                        continue
                    name = str(row.get("name") or "").strip()
                    date_raw = str(row.get("date") or "").strip()
                    if not name or not date_raw:
                        continue
                    try:
                        start_dt = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                    timeline.append((int(start_dt.timestamp()), name))

        timeline.sort(key=lambda x: x[0])
        if not timeline:
            return [], []

        self.cache.set("patch_timeline_v2", [[ts, name] for ts, name in timeline])
        starts = [row[0] for row in timeline]
        names = [row[1] for row in timeline]
        return starts, names

    def get_patch_options(self) -> list[str]:
        # Newest-first for UI convenience.
        return list(reversed(self._patch_names))

    def _resolve_patch_name_for_start_time(self, start_time: int) -> str | None:
        if not self._patch_starts:
            return None
        idx = bisect_right(self._patch_starts, start_time) - 1
        if idx < 0:
            return None
        return self._patch_names[idx]

    def ensure_player_exists(self, player_id: int) -> None:
        cache_key = f"player_profile_{player_id}"
        profile = self.cache.get(cache_key, max_age=timedelta(hours=24))
        if not isinstance(profile, dict):
            profile = self.client.get_player_profile(player_id)
            self.cache.set(cache_key, profile)
        if not isinstance(profile, dict) or not profile.get("profile"):
            raise OpenDotaNotFoundError(f"Player {player_id} was not found")

    def _get_matches_cache_ttl(self, filters: QueryFilters, limit: int | None) -> timedelta:
        if limit is not None:
            return timedelta(minutes=20)
        if filters.days is not None:
            if filters.days <= 3:
                return timedelta(minutes=30)
            if filters.days <= 14:
                return timedelta(hours=2)
            if filters.days <= 60:
                return timedelta(hours=12)
            return timedelta(days=3)
        if filters.start_date is not None:
            age_days = max((datetime.now(tz=timezone.utc).date() - filters.start_date).days, 0)
            if age_days <= 3:
                return timedelta(minutes=30)
            if age_days <= 14:
                return timedelta(hours=2)
            if age_days <= 60:
                return timedelta(hours=12)
            return timedelta(days=3)
        return timedelta(hours=6)

    def _build_matches_cache_policy(self, filters: QueryFilters, limit: int | None) -> CachePolicy:
        return CachePolicy(
            key=(
                "player_matches_v2_"
                f"{filters.player_id}_"
                f"{filters.hero_id or 'all'}_"
                f"{filters.game_mode or 'all'}_"
                f"{filters.days or 'all'}_"
                f"{filters.start_date.isoformat() if filters.start_date else 'none'}_"
                f"{','.join(sorted(filters.patch_names or [])) or 'no-patches'}_"
                f"{limit or 'all'}"
            ),
            ttl=self._get_matches_cache_ttl(filters, limit),
        )

    @staticmethod
    def _min_start_time(filters: QueryFilters) -> int | None:
        min_start = None
        if filters.days:
            min_start = int((datetime.now(tz=timezone.utc).timestamp()) - filters.days * 86400)
        if filters.start_date:
            start_date_ts = int(datetime.combine(filters.start_date, time.min, tzinfo=timezone.utc).timestamp())
            min_start = max(min_start, start_date_ts) if min_start is not None else start_date_ts
        return min_start

    @staticmethod
    def _sync_scope_key(game_mode: int | None) -> str:
        return f"gm:{game_mode}" if game_mode is not None else "gm:all"

    def _parse_match_summary_row(
        self,
        row: dict[str, Any],
        *,
        selected_patches: set[str] | None = None,
        min_start: int | None = None,
    ) -> MatchSummary | None:
        start_time = int(row.get("start_time") or 0)
        if min_start is not None and start_time < min_start:
            return None
        if selected_patches:
            patch_name = self._resolve_patch_name_for_start_time(start_time)
            if patch_name not in selected_patches:
                return None

        hero_damage = int(row.get("hero_damage") or 0)
        lane_efficiency_pct = row.get("lane_efficiency_pct")
        net_worth = int(row.get("net_worth") or 0)
        match = MatchSummary(
            match_id=int(row.get("match_id") or 0),
            start_time=start_time,
            player_slot=int(row.get("player_slot") or 0),
            radiant_win=bool(row.get("radiant_win")),
            kills=int(row.get("kills") or 0),
            deaths=int(row.get("deaths") or 0),
            assists=int(row.get("assists") or 0),
            duration=int(row.get("duration") or 0),
            hero_id=int(row.get("hero_id") or 0) if row.get("hero_id") is not None else None,
            lane_efficiency_pct=float(lane_efficiency_pct or 0.0),
            lane_efficiency_known=lane_efficiency_pct is not None,
            net_worth=net_worth,
            net_worth_known=net_worth > 0,
            hero_damage=hero_damage,
            hero_damage_known=hero_damage > 0,
            item_0=int(row.get("item_0") or 0),
            item_1=int(row.get("item_1") or 0),
            item_2=int(row.get("item_2") or 0),
            item_3=int(row.get("item_3") or 0),
            item_4=int(row.get("item_4") or 0),
            item_5=int(row.get("item_5") or 0),
        )
        return match if match.match_id > 0 else None

    def _sync_player_matches(self, filters: QueryFilters, *, force: bool = False) -> None:
        if self.match_store is None:
            return

        significant = 0 if filters.game_mode == 23 else None
        scope_key = self._sync_scope_key(filters.game_mode)
        state = self.match_store.get_sync_state(filters.player_id, scope_key)
        batch_size = 100
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        min_sync_interval = timedelta(minutes=10)
        if filters.days is not None and filters.days > 30:
            min_sync_interval = timedelta(hours=12)
        if filters.start_date is not None:
            age_days = max((datetime.now(tz=timezone.utc).date() - filters.start_date).days, 0)
            if age_days > 30:
                min_sync_interval = timedelta(hours=12)
            elif age_days > 7:
                min_sync_interval = timedelta(hours=2)

        def fetch_page(offset: int) -> list[dict[str, Any]]:
            return self.client.get_player_matches(
                account_id=filters.player_id,
                game_mode=filters.game_mode,
                limit=batch_size,
                offset=offset,
                significant=significant,
            )

        if not force and state and state.get("last_incremental_sync_at"):
            try:
                last_sync = datetime.fromisoformat(str(state["last_incremental_sync_at"]))
                if datetime.now(tz=timezone.utc) - last_sync < min_sync_interval:
                    return
            except ValueError:
                pass

        if state is None:
            offset = 0
            total_rows = 0
            while True:
                chunk = fetch_page(offset)
                if not chunk:
                    break
                self.match_store.upsert_player_matches(filters.player_id, chunk)
                total_rows += len(chunk)
                if len(chunk) < batch_size:
                    break
                offset += batch_size

            self.match_store.upsert_sync_state(
                filters.player_id,
                scope_key,
                last_incremental_sync_at=now_iso,
                last_full_sync_at=now_iso,
                known_match_count=self.match_store.count_player_matches(filters.player_id, filters.game_mode),
            )
            return

        first_page = fetch_page(0)
        if not first_page:
            self.match_store.upsert_sync_state(
                filters.player_id,
                scope_key,
                last_incremental_sync_at=now_iso,
                known_match_count=self.match_store.count_player_matches(filters.player_id, filters.game_mode),
            )
            return

        page_index = 0
        while True:
            current_chunk = first_page if page_index == 0 else fetch_page(page_index * batch_size)
            if not current_chunk:
                break
            existing_ids = self.match_store.get_existing_match_ids(
                filters.player_id,
                [int(row.get("match_id") or 0) for row in current_chunk],
            )
            self.match_store.upsert_player_matches(filters.player_id, current_chunk)
            if existing_ids or len(current_chunk) < batch_size:
                break
            page_index += 1

        self.match_store.upsert_sync_state(
            filters.player_id,
            scope_key,
            last_incremental_sync_at=now_iso,
            known_match_count=self.match_store.count_player_matches(filters.player_id, filters.game_mode),
        )

    @staticmethod
    def _serialize_match_summary(match: MatchSummary) -> dict[str, Any]:
        return {
            "match_id": match.match_id,
            "start_time": match.start_time,
            "player_slot": match.player_slot,
            "radiant_win": match.radiant_win,
            "kills": match.kills,
            "deaths": match.deaths,
            "assists": match.assists,
            "duration": match.duration,
            "hero_id": match.hero_id,
            "lane_efficiency_pct": match.lane_efficiency_pct,
            "lane_efficiency_known": match.lane_efficiency_known,
            "net_worth": match.net_worth,
            "net_worth_known": match.net_worth_known,
            "hero_damage": match.hero_damage,
            "hero_damage_known": match.hero_damage_known,
            "item_0": match.item_0,
            "item_1": match.item_1,
            "item_2": match.item_2,
            "item_3": match.item_3,
            "item_4": match.item_4,
            "item_5": match.item_5,
        }

    @staticmethod
    def _deserialize_match_summaries(payload: Any) -> list[MatchSummary] | None:
        if not isinstance(payload, list):
            return None
        rows: list[MatchSummary] = []
        try:
            for row in payload:
                if not isinstance(row, dict):
                    return None
                rows.append(
                    MatchSummary(
                        match_id=int(row.get("match_id") or 0),
                        start_time=int(row.get("start_time") or 0),
                        player_slot=int(row.get("player_slot") or 0),
                        radiant_win=bool(row.get("radiant_win")),
                        kills=int(row.get("kills") or 0),
                        deaths=int(row.get("deaths") or 0),
                        assists=int(row.get("assists") or 0),
                        duration=int(row.get("duration") or 0),
                        hero_id=int(row["hero_id"]) if row.get("hero_id") is not None else None,
                        lane_efficiency_pct=float(row.get("lane_efficiency_pct") or 0.0),
                        lane_efficiency_known=bool(row.get("lane_efficiency_known")),
                        net_worth=int(row.get("net_worth") or 0),
                        net_worth_known=bool(row.get("net_worth_known")),
                        hero_damage=int(row.get("hero_damage") or 0),
                        hero_damage_known=bool(row.get("hero_damage_known")),
                        item_0=int(row.get("item_0") or 0),
                        item_1=int(row.get("item_1") or 0),
                        item_2=int(row.get("item_2") or 0),
                        item_3=int(row.get("item_3") or 0),
                        item_4=int(row.get("item_4") or 0),
                        item_5=int(row.get("item_5") or 0),
                    )
                )
        except Exception:
            return None
        return rows

    def fetch_matches(self, filters: QueryFilters, limit: int | None = None, *, force_sync: bool = False) -> list[MatchSummary]:
        significant = 0 if filters.game_mode == 23 else None
        selected_patches = set(filters.patch_names or [])
        min_start = self._min_start_time(filters)

        if self.match_store is not None:
            self._sync_player_matches(filters, force=force_sync)
            stored_rows = self.match_store.query_player_matches(
                filters.player_id,
                hero_id=filters.hero_id,
                game_mode=filters.game_mode,
                min_start_time=min_start,
                limit=None,
            )
            parsed_store_rows = [
                match
                for match in (
                    self._parse_match_summary_row(row, selected_patches=selected_patches, min_start=min_start)
                    for row in stored_rows
                )
                if match is not None
            ]
            return parsed_store_rows[:limit] if limit is not None else parsed_store_rows

        cache_policy = self._build_matches_cache_policy(filters, limit)
        cached_matches = self._deserialize_match_summaries(
            self.cache.get(cache_policy.key, max_age=cache_policy.ttl)
        )
        if cached_matches is not None:
            return cached_matches

        def parse_rows(rows: list[dict]) -> list[MatchSummary]:
            parsed: list[MatchSummary] = []
            for row in rows:
                match = self._parse_match_summary_row(row, selected_patches=selected_patches, min_start=min_start)
                if match is not None:
                    parsed.append(match)
            return parsed

        # For explicit "latest N" queries we only need one request.
        if limit is not None:
            data = self.client.get_player_matches(
                account_id=filters.player_id,
                hero_id=filters.hero_id,
                game_mode=filters.game_mode,
                days=filters.days,
                limit=limit,
                significant=significant,
            )
            parsed = parse_rows(data)
            self.cache.set(cache_policy.key, [self._serialize_match_summary(match) for match in parsed])
            return parsed

        # For stats/items aggregate mode, paginate through the full filtered period.
        batch_size = 100
        max_pages = 50
        offset = 0
        all_matches: list[MatchSummary] = []

        for _ in range(max_pages):
            chunk = self.client.get_player_matches(
                account_id=filters.player_id,
                hero_id=filters.hero_id,
                game_mode=filters.game_mode,
                days=filters.days,
                limit=batch_size,
                offset=offset,
                significant=significant,
            )
            if not chunk:
                break

            parsed_chunk = parse_rows(chunk)
            all_matches.extend(parsed_chunk)

            if len(chunk) < batch_size:
                break

            # Matches are returned newest first. If we're already beyond period, stop.
            if min_start is not None:
                oldest_start = int(chunk[-1].get("start_time") or 0)
                if oldest_start and oldest_start < min_start:
                    break

            offset += batch_size

        self.cache.set(cache_policy.key, [self._serialize_match_summary(match) for match in all_matches])
        return all_matches

    def get_cached_matches(self, filters: QueryFilters, limit: int | None = None) -> list[MatchSummary]:
        if self.match_store is None:
            return []
        selected_patches = set(filters.patch_names or [])
        min_start = self._min_start_time(filters)
        stored_rows = self.match_store.query_player_matches(
            filters.player_id,
            hero_id=filters.hero_id,
            game_mode=filters.game_mode,
            min_start_time=min_start,
            limit=None,
        )
        parsed_store_rows = [
            match
            for match in (
                self._parse_match_summary_row(row, selected_patches=selected_patches, min_start=min_start)
                for row in stored_rows
            )
            if match is not None
        ]
        return parsed_store_rows[:limit] if limit is not None else parsed_store_rows

    def get_cached_sync_state(self, player_id: int, game_mode: int | None = None) -> dict[str, Any] | None:
        if self.match_store is None:
            return None
        state = self.match_store.get_sync_state(player_id, self._sync_scope_key(game_mode))
        latest_update = self.match_store.get_latest_player_match_update(player_id, game_mode=game_mode)
        if state is None:
            if latest_update is None:
                return None
            return {
                "account_id": int(player_id),
                "scope_key": self._sync_scope_key(game_mode),
                "last_incremental_sync_at": None,
                "last_full_sync_at": None,
                "known_match_count": self.match_store.count_player_matches(player_id, game_mode),
                "latest_match_update_at": latest_update,
            }
        merged = dict(state)
        merged["latest_match_update_at"] = latest_update
        return merged

    def build_stats(self, matches: list[MatchSummary]) -> StatsResult:
        total = len(matches)
        if total == 0:
            return StatsResult(
                matches=0,
                wins=0,
                losses=0,
                winrate=0.0,
                avg_kills=0.0,
                avg_deaths=0.0,
                avg_assists=0.0,
                kda_ratio=0.0,
                avg_duration_seconds=0.0,
                avg_net_worth=0.0,
                avg_damage=0.0,
                lane_winrate=0.0,
                lane_sample_count=0,
                max_kills=0,
                max_hero_damage=0,
                radiant_wr=0.0,
                dire_wr=0.0,
            )

        wins = sum(1 for m in matches if m.did_win)
        losses = total - wins

        kills = sum(m.kills for m in matches)
        deaths = sum(m.deaths for m in matches)
        assists = sum(m.assists for m in matches)
        duration_total = sum(m.duration for m in matches)
        net_worth_total = sum(float(m.net_worth) for m in matches if m.net_worth_known)
        net_worth_samples = sum(1 for m in matches if m.net_worth_known)
        hero_damage_total = sum(float(m.hero_damage) for m in matches if m.hero_damage_known)
        hero_damage_samples = sum(1 for m in matches if m.hero_damage_known)
        lane_wins = sum(1 for m in matches if m.lane_efficiency_known and m.lane_efficiency_pct >= 50.0)
        lane_samples = sum(1 for m in matches if m.lane_efficiency_known)

        radiant_matches = [m for m in matches if m.side == "Radiant"]
        dire_matches = [m for m in matches if m.side == "Dire"]
        radiant_wins = sum(1 for m in radiant_matches if m.did_win)
        dire_wins = sum(1 for m in dire_matches if m.did_win)

        avg_k = kills / total
        avg_d = deaths / total
        avg_a = assists / total

        return StatsResult(
            matches=total,
            wins=wins,
            losses=losses,
            winrate=winrate_percent(wins, total),
            avg_kills=avg_k,
            avg_deaths=avg_d,
            avg_assists=avg_a,
            kda_ratio=calculate_kda_ratio(avg_k, avg_d, avg_a),
            avg_duration_seconds=duration_total / total,
            avg_net_worth=(net_worth_total / net_worth_samples) if net_worth_samples > 0 else 0.0,
            avg_damage=(hero_damage_total / hero_damage_samples) if hero_damage_samples > 0 else 0.0,
            lane_winrate=winrate_percent(lane_wins, lane_samples),
            lane_sample_count=lane_samples,
            max_kills=max(int(m.kills) for m in matches),
            max_hero_damage=max(int(m.hero_damage) for m in matches if m.hero_damage_known) if hero_damage_samples > 0 else 0,
            radiant_wr=winrate_percent(radiant_wins, len(radiant_matches)),
            dire_wr=winrate_percent(dire_wins, len(dire_matches)),
        )

    def build_turbo_hero_overview_rows(self, matches: list[MatchSummary]) -> list[dict[str, Any]]:
        grouped: dict[int, list[MatchSummary]] = {}
        for match in matches:
            hero_id = int(match.hero_id or 0)
            if hero_id <= 0:
                continue
            grouped.setdefault(hero_id, []).append(match)

        rows: list[dict[str, Any]] = []
        for hero_id, hero_matches in grouped.items():
            stats = self.build_stats(hero_matches)
            rows.append(
                {
                    "hero_id": hero_id,
                    "hero": self.resolve_hero_name(hero_id),
                    "hero_image": self.resolve_hero_image(hero_id),
                    "matches": stats.matches,
                    "wins": stats.wins,
                    "losses": stats.losses,
                    "winrate": stats.winrate,
                    "avg_kills": stats.avg_kills,
                    "avg_deaths": stats.avg_deaths,
                    "avg_assists": stats.avg_assists,
                    "avg_duration_seconds": stats.avg_duration_seconds,
                    "lane_winrate": stats.lane_winrate,
                    "lane_winrate_samples": stats.lane_sample_count,
                    "max_kills": stats.max_kills,
                    "max_hero_damage": stats.max_hero_damage,
                    "radiant_wr": stats.radiant_wr,
                    "dire_wr": stats.dire_wr,
                    "avg_net_worth": stats.avg_net_worth,
                    "avg_net_worth_samples": sum(1 for m in hero_matches if m.net_worth_known),
                    "avg_damage": stats.avg_damage,
                    "avg_damage_samples": sum(1 for m in hero_matches if m.hero_damage_known),
                    "kda": stats.kda_ratio,
                }
            )

        rows.sort(key=lambda x: (-x["matches"], -x["winrate"]))
        return rows

    def get_cached_turbo_hero_overview(
        self,
        player_id: int,
        days: int | None = 60,
        start_date=None,
        patch_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        filters = QueryFilters(
            player_id=player_id,
            game_mode=23,
            game_mode_name="Turbo",
            days=days,
            start_date=start_date,
            patch_names=patch_names,
        )
        matches = self.get_cached_matches(filters)
        if not matches:
            return []
        self.enrich_hero_damage(player_id, matches, max_fallback_detail_calls=max(120, len(matches)))
        return self.build_turbo_hero_overview_rows(matches)

    def _counter_to_item_stats(self, counter: Counter[int], total_matches: int, top_n: int = 12) -> list[ItemStat]:
        rows: list[ItemStat] = []
        for item_id, count in counter.most_common(top_n):
            name = self.references.item_names_by_id.get(item_id, f"Item #{item_id}")
            rows.append(
                ItemStat(
                    item_id=item_id,
                    item_name=name,
                    count=count,
                    match_pct=winrate_percent(count, total_matches),
                )
            )
        return rows

    @staticmethod
    def _summary_item_ids(match: MatchSummary) -> list[int]:
        return [match.item_0, match.item_1, match.item_2, match.item_3, match.item_4, match.item_5]

    def _extract_player_from_match_details(
        self,
        details: dict,
        player_id: int | None = None,
        player_slot: int | None = None,
    ) -> dict | None:
        players = details.get("players") if isinstance(details, dict) else None
        if not isinstance(players, list):
            return None

        if player_id is not None:
            row = next((p for p in players if int(p.get("account_id") or -1) == player_id), None)
            if row:
                return row

        if player_slot is not None:
            row = next((p for p in players if int(p.get("player_slot") or -1) == player_slot), None)
            if row:
                return row

        return None

    @staticmethod
    def _player_row_item_ids(player_row: dict) -> list[int]:
        return [int(player_row.get(f"item_{i}") or 0) for i in range(6)]

    def _has_match_details_cached(self, match_id: int) -> bool:
        if match_id in self._match_details_memory_cache:
            return True

        if self.match_store is not None and isinstance(self.match_store.get_match_detail(match_id), dict):
            return True

        cache_key = f"match_details_{match_id}"
        return isinstance(self.cache.get(cache_key), dict)

    def _get_match_details_cached(self, match_id: int) -> dict[str, Any]:
        if match_id in self._match_details_memory_cache:
            return self._match_details_memory_cache[match_id]

        if self.match_store is not None:
            stored = self.match_store.get_match_detail(match_id)
            if isinstance(stored, dict):
                self._match_details_memory_cache[match_id] = stored
                return stored

        cache_key = f"match_details_{match_id}"
        cached = self.cache.get(cache_key)
        if isinstance(cached, dict):
            self._match_details_memory_cache[match_id] = cached
            if self.match_store is not None:
                self.match_store.upsert_match_detail(match_id, cached)
            return cached

        details = self.client.get_match_details(match_id)
        self._match_details_memory_cache[match_id] = details
        if self.match_store is not None:
            self.match_store.upsert_match_detail(match_id, details)
        self.cache.set(cache_key, details)
        return details

    def enrich_hero_damage(
        self,
        player_id: int,
        matches: list[MatchSummary],
        max_fallback_detail_calls: int = 45,
    ) -> None:
        fallback_detail_calls = 0
        for match in matches:
            if match.hero_damage_known and match.net_worth_known and match.lane_efficiency_known:
                continue
            details_cached = self._has_match_details_cached(match.match_id)
            if not details_cached and fallback_detail_calls >= max_fallback_detail_calls:
                break
            try:
                details = self._get_match_details_cached(match.match_id)
                if not details_cached:
                    fallback_detail_calls += 1
                player_row = self._extract_player_from_match_details(
                    details,
                    player_id=player_id,
                    player_slot=match.player_slot,
                )
                if player_row:
                    hero_damage = int(player_row.get("hero_damage") or 0)
                    net_worth = int(player_row.get("net_worth") or 0)
                    lane_efficiency_pct = player_row.get("lane_efficiency_pct")
                    if hero_damage > 0:
                        match.hero_damage = hero_damage
                        match.hero_damage_known = True
                    if net_worth > 0:
                        match.net_worth = net_worth
                        match.net_worth_known = True
                    if lane_efficiency_pct is not None:
                        match.lane_efficiency_pct = float(lane_efficiency_pct or 0.0)
                        match.lane_efficiency_known = True
                    if self.match_store is not None:
                        self.match_store.update_player_match_enrichment(
                            player_id,
                            match.match_id,
                            hero_damage=hero_damage if hero_damage > 0 else None,
                            net_worth=net_worth if net_worth > 0 else None,
                            lane_efficiency_pct=float(lane_efficiency_pct) if lane_efficiency_pct is not None else None,
                        )
            except OpenDotaRateLimitError:
                break

    def build_items(self, player_id: int, matches: list[MatchSummary], include_purchase_logs: bool = True) -> ItemsResult:
        total = len(matches)
        if total == 0:
            return ItemsResult(0, [], [], False, "No matches available for item stats")

        final_counter: Counter[int] = Counter()
        fallback_item_matches = 0
        fallback_detail_calls = 0
        max_fallback_detail_calls = 35
        rate_limited = False
        for match in matches:
            ids = self._summary_item_ids(match)
            if not any(ids) and fallback_detail_calls < max_fallback_detail_calls:
                # Fallback: get final inventory from match details when players/matches projection is empty.
                try:
                    details = self._get_match_details_cached(match.match_id)
                    fallback_detail_calls += 1
                    player_row = self._extract_player_from_match_details(
                        details,
                        player_id=player_id,
                        player_slot=match.player_slot,
                    )
                    if player_row:
                        ids = self._player_row_item_ids(player_row)
                        if any(ids):
                            fallback_item_matches += 1
                except OpenDotaRateLimitError:
                    rate_limited = True

            for item_id in ids:
                if item_id > 0:
                    final_counter[item_id] += 1

        final_items = self._counter_to_item_stats(final_counter, total)

        purchase_counter: Counter[int] = Counter()
        analyzed_matches = 0

        if include_purchase_logs:
            for match in matches[:25]:
                try:
                    details = self._get_match_details_cached(match.match_id)
                    player_row = self._extract_player_from_match_details(
                        details,
                        player_id=player_id,
                        player_slot=match.player_slot,
                    )
                    if not player_row:
                        continue

                    purchase_log = player_row.get("purchase_log")
                    if not isinstance(purchase_log, list):
                        continue

                    analyzed_matches += 1
                    seen_in_match: set[int] = set()
                    for event in purchase_log:
                        key = str(event.get("key") or "")
                        item_id = self.references.item_ids_by_key.get(key)
                        if item_id and item_id not in seen_in_match:
                            purchase_counter[item_id] += 1
                            seen_in_match.add(item_id)
                except OpenDotaRateLimitError:
                    rate_limited = True
                    break

        # Percent is relative to all filtered matches so partial purchase-log coverage is not misleading.
        purchased_items = self._counter_to_item_stats(purchase_counter, total)
        purchase_based = analyzed_matches > 0

        notes: list[str] = []
        if fallback_item_matches > 0:
            notes.append(
                f"Final inventory used match-details fallback for {fallback_item_matches} match(es) because players/matches had empty item slots."
            )
        if fallback_detail_calls >= max_fallback_detail_calls:
            notes.append("Final item fallback reached API-safe limit; results may be partial for older matches.")

        if purchase_based:
            notes.append(
                f"Purchased items are based on purchase_log for {analyzed_matches} match(es) out of {total}."
            )
        else:
            notes.append("purchase_log is unavailable for filtered matches; purchased-items table is empty.")
        if rate_limited:
            notes.append("OpenDota rate limit was hit during item enrichment; partial fallback data shown.")

        note = " ".join(notes)

        return ItemsResult(
            total_matches=total,
            final_inventory_items=final_items,
            purchased_items=purchased_items,
            purchased_based_on_logs=purchase_based,
            note=note,
        )

    def build_match_rows(self, player_id: int, matches: list[MatchSummary], limit: int = 20) -> list[MatchRow]:
        rows: list[MatchRow] = []

        for match in matches[:limit]:
            item_ids = self._summary_item_ids(match)
            if not any(item_ids):
                try:
                    details = self._get_match_details_cached(match.match_id)
                    player_row = self._extract_player_from_match_details(
                        details,
                        player_id=player_id,
                        player_slot=match.player_slot,
                    )
                    if player_row:
                        item_ids = self._player_row_item_ids(player_row)
                except OpenDotaRateLimitError:
                    item_ids = []
            item_names = [self.references.item_names_by_id.get(item_id, f"#{item_id}") for item_id in item_ids if item_id > 0]

            rows.append(
                MatchRow(
                    match_id=match.match_id,
                    started_at=unix_to_dt(match.start_time),
                    result="Win" if match.did_win else "Loss",
                    kda=f"{match.kills}/{match.deaths}/{match.assists}",
                    duration=format_duration(match.duration),
                    net_worth=match.net_worth if match.net_worth_known else None,
                    items=item_names,
                )
            )

        return rows

    def _build_recent_match_items(self, player_row: dict | None, final_item_ids: list[int]) -> list[RecentMatchItem]:
        purchase_times_by_item: dict[int, list[int]] = {}
        purchase_log = player_row.get("purchase_log") if isinstance(player_row, dict) else None
        if isinstance(purchase_log, list):
            for event in purchase_log:
                if not isinstance(event, dict):
                    continue
                key = str(event.get("key") or "")
                item_id = self.references.item_ids_by_key.get(key)
                if not item_id:
                    continue
                purchase_times_by_item.setdefault(item_id, []).append(max(int(event.get("time") or 0) // 60, 0))

        items: list[RecentMatchItem] = []
        for original_index, item_id in enumerate(final_item_ids):
            if item_id <= 0:
                continue
            purchase_times = purchase_times_by_item.get(item_id, [])
            purchase_time_min = purchase_times.pop(0) if purchase_times else None
            item = RecentMatchItem(
                item_id=item_id,
                item_name=self.references.item_names_by_id.get(item_id, f"Item #{item_id}"),
                item_image=self.references.item_images_by_id.get(item_id, ""),
                purchase_time_min=purchase_time_min,
            )
            items.append((original_index, item))
        items.sort(
            key=lambda pair: (
                pair[1].purchase_time_min is None,
                pair[1].purchase_time_min if pair[1].purchase_time_min is not None else 10_000,
                pair[0],
            )
        )
        return [item for _, item in items[:6]]

    def build_recent_hero_matches(
        self,
        player_id: int,
        matches: list[MatchSummary],
        limit: int = 10,
    ) -> list[RecentHeroMatch]:
        rows: list[RecentHeroMatch] = []

        for match in matches[:limit]:
            item_ids = self._summary_item_ids(match)
            player_row = None
            try:
                details = self._get_match_details_cached(match.match_id)
                player_row = self._extract_player_from_match_details(
                    details,
                    player_id=player_id,
                    player_slot=match.player_slot,
                )
                if player_row:
                    item_ids = self._player_row_item_ids(player_row)
            except OpenDotaRateLimitError:
                player_row = None

            rows.append(
                RecentHeroMatch(
                    match_id=match.match_id,
                    hero_name=self.resolve_hero_name(match.hero_id),
                    hero_image=self.resolve_hero_image(match.hero_id),
                    hero_level=int(player_row.get("level") or 0) if isinstance(player_row, dict) else None,
                    hero_variant=int(player_row.get("hero_variant") or 0) if isinstance(player_row, dict) else None,
                    result="Win" if match.did_win else "Loss",
                    started_at=unix_to_dt(match.start_time),
                    duration=format_duration(match.duration),
                    duration_seconds=int(match.duration),
                    kills=int(match.kills),
                    deaths=int(match.deaths),
                    assists=int(match.assists),
                    kda_ratio=calculate_kda_ratio(float(match.kills), float(match.deaths), float(match.assists)),
                    net_worth=int(player_row.get("net_worth") or 0) if isinstance(player_row, dict) else None,
                    hero_damage=int(player_row.get("hero_damage") or 0) if isinstance(player_row, dict) else None,
                    items=self._build_recent_match_items(player_row, item_ids),
                )
            )

        return rows

    def resolve_hero_name(self, hero_id: int | None) -> str:
        if hero_id is None:
            return "Any"
        return self.references.hero_names_by_id.get(hero_id, f"Hero #{hero_id}")

    def backfill_match_details(
        self,
        player_id: int,
        game_mode: int | None = None,
        max_matches: int | None = None,
    ) -> int:
        if self.match_store is None:
            return 0
        match_ids = self.match_store.get_match_ids_without_details(player_id, game_mode=game_mode, limit=max_matches)
        completed = 0
        for match_id in match_ids:
            try:
                self._get_match_details_cached(match_id)
                completed += 1
            except OpenDotaRateLimitError:
                break
        return completed

    def get_turbo_hero_overview(
        self,
        player_id: int,
        days: int | None = 60,
        start_date=None,
        patch_names: list[str] | None = None,
        force_sync: bool = False,
    ) -> list[dict[str, Any]]:
        filters = QueryFilters(
            player_id=player_id,
            game_mode=23,
            game_mode_name="Turbo",
            days=days,
            start_date=start_date,
            patch_names=patch_names,
        )
        matches = self.fetch_matches(filters, force_sync=force_sync) if force_sync else self.fetch_matches(filters)
        if not matches:
            return []
        self.enrich_hero_damage(player_id, matches, max_fallback_detail_calls=max(120, len(matches)))
        return self.build_turbo_hero_overview_rows(matches)

    def get_item_winrates(self, player_id: int, matches: list[MatchSummary], top_n: int = 20) -> list[dict[str, Any]]:
        total = len(matches)
        if total == 0:
            return []

        appear_counter: Counter[int] = Counter()
        win_counter: Counter[int] = Counter()

        fallback_detail_calls = 0
        max_fallback_detail_calls = 35
        for match in matches:
            item_ids = self._summary_item_ids(match)
            if not any(item_ids) and fallback_detail_calls < max_fallback_detail_calls:
                try:
                    details = self._get_match_details_cached(match.match_id)
                    fallback_detail_calls += 1
                    player_row = self._extract_player_from_match_details(
                        details,
                        player_id=player_id,
                        player_slot=match.player_slot,
                    )
                    if player_row:
                        item_ids = self._player_row_item_ids(player_row)
                except OpenDotaRateLimitError:
                    break

            unique_items = {item_id for item_id in item_ids if item_id > 0}
            for item_id in unique_items:
                appear_counter[item_id] += 1
                if match.did_win:
                    win_counter[item_id] += 1

        rows: list[dict[str, Any]] = []
        for item_id, appearances in appear_counter.items():
            if appearances <= 0:
                continue
            wins = win_counter[item_id]
            rows.append(
                {
                    "item_id": item_id,
                    "item": self.references.item_names_by_id.get(item_id, f"Item #{item_id}"),
                    "item_image": self.resolve_item_image(item_id),
                    "matches_with_item": appearances,
                    "item_pick_rate": winrate_percent(appearances, total),
                    "wins_with_item": wins,
                    "item_winrate": winrate_percent(wins, appearances),
                }
            )

        rows.sort(
            key=lambda x: (
                -x["item_winrate"],
                -x["matches_with_item"],
                -x["wins_with_item"],
                x["item"],
            )
        )
        return rows[:top_n]

    def resolve_hero_image(self, hero_id: int | None) -> str:
        if hero_id is None:
            return ""
        return self.references.hero_images_by_id.get(hero_id, "")

    def resolve_item_image(self, item_id: int | None) -> str:
        if item_id is None:
            return ""
        return self.references.item_images_by_id.get(item_id, "")
