from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import ssl
from typing import Any
from urllib.parse import parse_qs, urlparse

import pg8000.dbapi
try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # noqa: BLE001
    psycopg = None
    dict_row = None


class PostgresMatchStore:
    def __init__(self, database_url: str) -> None:
        self._driver = "pg8000"
        self._conn = self._connect_from_url(database_url)
        self._init_schema()

    def _connect_from_url(self, database_url: str):
        if psycopg is not None:
            try:
                self._driver = "psycopg"
                return psycopg.connect(database_url, autocommit=True, row_factory=dict_row)
            except Exception:  # noqa: BLE001
                self._driver = "pg8000"
        parsed = urlparse(database_url)
        query = parse_qs(parsed.query)
        ssl_context: ssl.SSLContext | bool | None = None
        if (query.get("sslmode", [""])[0] or "").lower() == "require":
            ssl_context = ssl.create_default_context()
        port = parsed.port or 5432
        conn = pg8000.dbapi.connect(
            user=parsed.username or "",
            password=parsed.password or "",
            host=parsed.hostname or "",
            port=int(port),
            database=(parsed.path or "/").lstrip("/"),
            ssl_context=ssl_context,
        )
        try:
            conn.autocommit = True
        except Exception:  # noqa: BLE001
            pass
        return conn

    def _init_schema(self) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS player_matches (
                    account_id BIGINT NOT NULL,
                    match_id BIGINT NOT NULL,
                    start_time BIGINT NOT NULL,
                    player_slot INTEGER NOT NULL,
                    radiant_win BOOLEAN NOT NULL,
                    kills INTEGER NOT NULL,
                    deaths INTEGER NOT NULL,
                    assists INTEGER NOT NULL,
                    duration INTEGER NOT NULL,
                    hero_id INTEGER,
                    game_mode INTEGER,
                    net_worth BIGINT,
                    hero_damage BIGINT,
                    lane_efficiency_pct DOUBLE PRECISION,
                    item_0 INTEGER NOT NULL DEFAULT 0,
                    item_1 INTEGER NOT NULL DEFAULT 0,
                    item_2 INTEGER NOT NULL DEFAULT 0,
                    item_3 INTEGER NOT NULL DEFAULT 0,
                    item_4 INTEGER NOT NULL DEFAULT 0,
                    item_5 INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (account_id, match_id)
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_player_matches_lookup ON player_matches (account_id, game_mode, hero_id, start_time DESC)"
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS match_details (
                    match_id BIGINT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS match_user_tags (
                    account_id BIGINT NOT NULL,
                    match_id BIGINT NOT NULL,
                    tag_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (account_id, match_id, tag_key)
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_match_user_tags_lookup ON match_user_tags (account_id, match_id)"
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_state (
                    account_id BIGINT NOT NULL,
                    scope_key TEXT NOT NULL,
                    last_incremental_sync_at TEXT,
                    last_full_sync_at TEXT,
                    known_match_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (account_id, scope_key)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS background_sync_state (
                    account_id BIGINT NOT NULL,
                    scope_key TEXT NOT NULL,
                    window_days INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'idle',
                    last_started_at TEXT,
                    last_finished_at TEXT,
                    last_status TEXT,
                    last_error TEXT,
                    last_rate_limited_at TEXT,
                    next_retry_at TEXT,
                    next_stratz_retry_at TEXT,
                    next_pending_parse_check_at TEXT,
                    last_summary_sync_at TEXT,
                    target_match_count INTEGER NOT NULL DEFAULT 0,
                    detail_cached_count INTEGER NOT NULL DEFAULT 0,
                    timing_ready_count INTEGER NOT NULL DEFAULT 0,
                    missing_detail_count INTEGER NOT NULL DEFAULT 0,
                    missing_timing_count INTEGER NOT NULL DEFAULT 0,
                    pending_parse_count INTEGER NOT NULL DEFAULT 0,
                    newest_match_start_time BIGINT,
                    oldest_match_start_time BIGINT,
                    newest_fully_cached_start_time BIGINT,
                    oldest_fully_cached_start_time BIGINT,
                    total_runs INTEGER NOT NULL DEFAULT 0,
                    total_detail_fetches INTEGER NOT NULL DEFAULT 0,
                    total_parse_requests INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (account_id, scope_key, window_days)
                )
                """
            )
            cur.execute("ALTER TABLE background_sync_state ADD COLUMN IF NOT EXISTS next_pending_parse_check_at TEXT")
            cur.execute("ALTER TABLE background_sync_state ADD COLUMN IF NOT EXISTS next_stratz_retry_at TEXT")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS background_sync_runs (
                    id BIGSERIAL PRIMARY KEY,
                    account_id BIGINT NOT NULL,
                    scope_key TEXT NOT NULL,
                    window_days INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    run_source TEXT NOT NULL DEFAULT 'manual',
                    summary_new_matches INTEGER NOT NULL DEFAULT 0,
                    total_matches_in_window INTEGER NOT NULL DEFAULT 0,
                    detail_requested INTEGER NOT NULL DEFAULT 0,
                    detail_completed INTEGER NOT NULL DEFAULT 0,
                    parse_requested INTEGER NOT NULL DEFAULT 0,
                    pending_parse_count INTEGER NOT NULL DEFAULT 0,
                    rate_limited INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TEXT,
                    request_targets TEXT,
                    data_sources TEXT,
                    note TEXT
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_background_sync_runs_lookup ON background_sync_runs (account_id, scope_key, window_days, started_at DESC)"
            )
            cur.execute("ALTER TABLE background_sync_runs ADD COLUMN IF NOT EXISTS run_source TEXT NOT NULL DEFAULT 'manual'")
            cur.execute("ALTER TABLE background_sync_runs ADD COLUMN IF NOT EXISTS request_targets TEXT")
            cur.execute("ALTER TABLE background_sync_runs ADD COLUMN IF NOT EXISTS data_sources TEXT")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS match_parse_requests (
                    match_id BIGINT PRIMARY KEY,
                    account_id BIGINT NOT NULL,
                    status TEXT NOT NULL,
                    parse_job_id BIGINT,
                    request_source TEXT,
                    request_reason TEXT,
                    requested_at TEXT NOT NULL,
                    last_polled_at TEXT,
                    completed_at TEXT,
                    attempts INTEGER NOT NULL DEFAULT 1,
                    last_error TEXT
                )
                """
            )
            cur.execute("ALTER TABLE match_parse_requests ADD COLUMN IF NOT EXISTS parse_job_id BIGINT")
            cur.execute("ALTER TABLE match_parse_requests ADD COLUMN IF NOT EXISTS request_source TEXT")
            cur.execute("ALTER TABLE match_parse_requests ADD COLUMN IF NOT EXISTS request_reason TEXT")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_match_parse_requests_lookup ON match_parse_requests (account_id, status, requested_at DESC)"
            )
        self._commit()

    def _commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def flush_persistent_snapshot(self, *, force: bool = False) -> None:
        return None

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(tz=timezone.utc).isoformat()

    @staticmethod
    def _json_loads(payload: str) -> dict[str, Any]:
        value = json.loads(payload)
        return value if isinstance(value, dict) else {}

    @contextmanager
    def _cursor(self):
        cur = self._conn.cursor()
        try:
            yield cur
        finally:
            close = getattr(cur, "close", None)
            if callable(close):
                close()

    def _fetchall_dicts(self, cur) -> list[dict[str, Any]]:
        rows = cur.fetchall()
        if self._driver == "psycopg":
            return [dict(row) for row in rows]
        columns = [item[0] for item in (cur.description or [])]
        return [dict(zip(columns, row, strict=False)) for row in rows]

    def _fetchone_dict(self, cur) -> dict[str, Any] | None:
        row = cur.fetchone()
        if row is None:
            return None
        if self._driver == "psycopg":
            return dict(row)
        columns = [item[0] for item in (cur.description or [])]
        return dict(zip(columns, row, strict=False))

    def get_existing_match_ids(self, account_id: int, match_ids: list[int]) -> set[int]:
        unique_ids = [int(match_id) for match_id in set(match_ids) if int(match_id) > 0]
        if not unique_ids:
            return set()
        placeholders = ",".join("%s" for _ in unique_ids)
        query = f"SELECT match_id FROM player_matches WHERE account_id = %s AND match_id IN ({placeholders})"
        with self._cursor() as cur:
            cur.execute(query, [int(account_id), *unique_ids])
            rows = self._fetchall_dicts(cur)
        return {int(row["match_id"]) for row in rows}

    def upsert_player_matches(self, account_id: int, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        now_iso = self._now_iso()
        prepared: list[tuple[Any, ...]] = []
        for row in rows:
            match_id = int(row.get("match_id") or 0)
            if match_id <= 0:
                continue
            prepared.append(
                (
                    int(account_id),
                    match_id,
                    int(row.get("start_time") or 0),
                    int(row.get("player_slot") or 0),
                    bool(row.get("radiant_win")),
                    int(row.get("kills") or 0),
                    int(row.get("deaths") or 0),
                    int(row.get("assists") or 0),
                    int(row.get("duration") or 0),
                    int(row.get("hero_id") or 0) if row.get("hero_id") is not None else None,
                    int(row.get("game_mode") or 0) if row.get("game_mode") is not None else None,
                    int(row.get("net_worth") or 0),
                    int(row.get("hero_damage") or 0),
                    float(row.get("lane_efficiency_pct") or 0.0) if row.get("lane_efficiency_pct") is not None else None,
                    int(row.get("item_0") or 0),
                    int(row.get("item_1") or 0),
                    int(row.get("item_2") or 0),
                    int(row.get("item_3") or 0),
                    int(row.get("item_4") or 0),
                    int(row.get("item_5") or 0),
                    json.dumps(row, ensure_ascii=False),
                    now_iso,
                )
            )
        if not prepared:
            return
        with self._cursor() as cur:
            cur.executemany(
                """
                INSERT INTO player_matches (
                    account_id, match_id, start_time, player_slot, radiant_win, kills, deaths, assists,
                    duration, hero_id, game_mode, net_worth, hero_damage, lane_efficiency_pct,
                    item_0, item_1, item_2, item_3, item_4, item_5, payload_json, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(account_id, match_id) DO UPDATE SET
                    start_time = excluded.start_time,
                    player_slot = excluded.player_slot,
                    radiant_win = excluded.radiant_win,
                    kills = excluded.kills,
                    deaths = excluded.deaths,
                    assists = excluded.assists,
                    duration = excluded.duration,
                    hero_id = excluded.hero_id,
                    game_mode = COALESCE(excluded.game_mode, player_matches.game_mode),
                    net_worth = CASE WHEN excluded.net_worth > 0 THEN excluded.net_worth ELSE player_matches.net_worth END,
                    hero_damage = CASE WHEN excluded.hero_damage > 0 THEN excluded.hero_damage ELSE player_matches.hero_damage END,
                    lane_efficiency_pct = COALESCE(excluded.lane_efficiency_pct, player_matches.lane_efficiency_pct),
                    item_0 = excluded.item_0,
                    item_1 = excluded.item_1,
                    item_2 = excluded.item_2,
                    item_3 = excluded.item_3,
                    item_4 = excluded.item_4,
                    item_5 = excluded.item_5,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                prepared,
            )
        self._commit()

    def query_player_matches(
        self,
        account_id: int,
        hero_id: int | None = None,
        game_mode: int | None = None,
        min_start_time: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["account_id = %s"]
        params: list[Any] = [int(account_id)]
        if hero_id is not None:
            clauses.append("hero_id = %s")
            params.append(int(hero_id))
        if game_mode is not None:
            clauses.append("(game_mode = %s OR game_mode IS NULL)")
            params.append(int(game_mode))
        if min_start_time is not None:
            clauses.append("start_time >= %s")
            params.append(int(min_start_time))
        query = (
            "SELECT payload_json FROM player_matches "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY start_time DESC"
        )
        if limit is not None:
            query += " LIMIT %s"
            params.append(int(limit))
        with self._cursor() as cur:
            cur.execute(query, params)
            rows = self._fetchall_dicts(cur)
        return [self._json_loads(str(row["payload_json"])) for row in rows]

    def query_player_match_status_rows(
        self,
        account_id: int,
        hero_id: int | None = None,
        game_mode: int | None = None,
        min_start_time: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clauses = ["pm.account_id = %s"]
        params: list[Any] = [int(account_id)]
        if hero_id is not None:
            clauses.append("pm.hero_id = %s")
            params.append(int(hero_id))
        if game_mode is not None:
            clauses.append("(pm.game_mode = %s OR pm.game_mode IS NULL)")
            params.append(int(game_mode))
        if min_start_time is not None:
            clauses.append("pm.start_time >= %s")
            params.append(int(min_start_time))
        query = (
            "SELECT pm.match_id, pm.payload_json, pm.updated_at AS summary_updated_at, "
            "md.updated_at AS detail_updated_at "
            "FROM player_matches pm "
            "LEFT JOIN match_details md ON md.match_id = pm.match_id "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY pm.start_time DESC"
        )
        if limit is not None:
            query += " LIMIT %s"
            params.append(int(limit))
        if offset > 0:
            query += " OFFSET %s"
            params.append(int(offset))
        with self._cursor() as cur:
            cur.execute(query, params)
            rows = self._fetchall_dicts(cur)
        return [
            {
                "match_id": int(row["match_id"]),
                "payload": self._json_loads(str(row["payload_json"])),
                "summary_updated_at": str(row["summary_updated_at"]) if row["summary_updated_at"] is not None else None,
                "detail_updated_at": str(row["detail_updated_at"]) if row["detail_updated_at"] is not None else None,
            }
            for row in rows
        ]

    def update_player_match_enrichment(
        self,
        account_id: int,
        match_id: int,
        *,
        hero_damage: int | None = None,
        net_worth: int | None = None,
        lane_efficiency_pct: float | None = None,
    ) -> None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT payload_json FROM player_matches WHERE account_id = %s AND match_id = %s",
                (int(account_id), int(match_id)),
            )
            existing = self._fetchone_dict(cur)
            if existing is None:
                return
            payload = self._json_loads(str(existing["payload_json"]))
            if hero_damage is not None and hero_damage > 0:
                payload["hero_damage"] = int(hero_damage)
            if net_worth is not None and net_worth > 0:
                payload["net_worth"] = int(net_worth)
            if lane_efficiency_pct is not None:
                payload["lane_efficiency_pct"] = float(lane_efficiency_pct)
            cur.execute(
                """
                UPDATE player_matches
                SET hero_damage = COALESCE(%s, hero_damage),
                    net_worth = COALESCE(%s, net_worth),
                    lane_efficiency_pct = COALESCE(%s, lane_efficiency_pct),
                    payload_json = %s,
                    updated_at = %s
                WHERE account_id = %s AND match_id = %s
                """,
                (
                    int(hero_damage) if hero_damage is not None and hero_damage > 0 else None,
                    int(net_worth) if net_worth is not None and net_worth > 0 else None,
                    float(lane_efficiency_pct) if lane_efficiency_pct is not None else None,
                    json.dumps(payload, ensure_ascii=False),
                    self._now_iso(),
                    int(account_id),
                    int(match_id),
                ),
            )
        self._commit()

    def get_match_detail(self, match_id: int) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute("SELECT payload_json FROM match_details WHERE match_id = %s", (int(match_id),))
            row = self._fetchone_dict(cur)
        if row is None:
            return None
        return self._json_loads(str(row["payload_json"]))

    def get_match_details_for_ids(self, match_ids: list[int]) -> dict[int, dict[str, Any]]:
        unique_ids = [int(match_id) for match_id in set(match_ids) if int(match_id) > 0]
        if not unique_ids:
            return {}
        placeholders = ",".join("%s" for _ in unique_ids)
        query = f"SELECT match_id, payload_json FROM match_details WHERE match_id IN ({placeholders})"
        with self._cursor() as cur:
            cur.execute(query, unique_ids)
            rows = self._fetchall_dicts(cur)
        return {int(row["match_id"]): self._json_loads(str(row["payload_json"])) for row in rows}

    def get_match_user_tags(self, account_id: int, match_id: int) -> list[str]:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT tag_key
                FROM match_user_tags
                WHERE account_id = %s AND match_id = %s
                ORDER BY tag_key ASC
                """,
                (int(account_id), int(match_id)),
            )
            rows = self._fetchall_dicts(cur)
        return [str(row["tag_key"]) for row in rows]

    def get_match_user_tags_for_ids(self, account_id: int, match_ids: list[int]) -> dict[int, list[str]]:
        unique_ids = sorted({int(match_id) for match_id in match_ids if int(match_id) > 0})
        if not unique_ids:
            return {}
        placeholders = ",".join("%s" for _ in unique_ids)
        with self._cursor() as cur:
            cur.execute(
                f"""
                SELECT match_id, tag_key
                FROM match_user_tags
                WHERE account_id = %s AND match_id IN ({placeholders})
                ORDER BY match_id ASC, tag_key ASC
                """,
                [int(account_id), *unique_ids],
            )
            rows = self._fetchall_dicts(cur)
        tags_by_match_id: dict[int, list[str]] = {}
        for row in rows:
            match_id = int(row["match_id"])
            tags_by_match_id.setdefault(match_id, []).append(str(row["tag_key"]))
        return tags_by_match_id

    def replace_match_user_tags(self, account_id: int, match_id: int, tag_keys: list[str]) -> None:
        normalized_tags = sorted({str(tag_key).strip() for tag_key in tag_keys if str(tag_key).strip()})
        with self._cursor() as cur:
            cur.execute(
                "DELETE FROM match_user_tags WHERE account_id = %s AND match_id = %s",
                (int(account_id), int(match_id)),
            )
            if normalized_tags:
                now_iso = self._now_iso()
                cur.executemany(
                    """
                    INSERT INTO match_user_tags (account_id, match_id, tag_key, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    [
                        (int(account_id), int(match_id), tag_key, now_iso, now_iso)
                        for tag_key in normalized_tags
                    ],
                )
        self._commit()

    def get_match_ids_without_details(
        self,
        account_id: int,
        game_mode: int | None = None,
        limit: int | None = None,
    ) -> list[int]:
        clauses = ["pm.account_id = %s"]
        params: list[Any] = [int(account_id)]
        if game_mode is not None:
            clauses.append("(pm.game_mode = %s OR pm.game_mode IS NULL)")
            params.append(int(game_mode))
        query = (
            "SELECT pm.match_id FROM player_matches pm "
            "LEFT JOIN match_details md ON md.match_id = pm.match_id "
            f"WHERE {' AND '.join(clauses)} AND md.match_id IS NULL "
            "ORDER BY pm.start_time DESC"
        )
        if limit is not None:
            query += " LIMIT %s"
            params.append(int(limit))
        with self._cursor() as cur:
            cur.execute(query, params)
            rows = self._fetchall_dicts(cur)
        return [int(row["match_id"]) for row in rows]

    def upsert_match_detail(self, match_id: int, payload: dict[str, Any]) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO match_details (match_id, payload_json, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT(match_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (int(match_id), json.dumps(payload, ensure_ascii=False), self._now_iso()),
            )
        self._commit()

    def get_sync_state(self, account_id: int, scope_key: str) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT account_id, scope_key, last_incremental_sync_at, last_full_sync_at, known_match_count
                FROM sync_state
                WHERE account_id = %s AND scope_key = %s
                """,
                (int(account_id), str(scope_key)),
            )
            row = self._fetchone_dict(cur)
        return row

    def upsert_sync_state(
        self,
        account_id: int,
        scope_key: str,
        *,
        last_incremental_sync_at: str | None = None,
        last_full_sync_at: str | None = None,
        known_match_count: int | None = None,
    ) -> None:
        current = self.get_sync_state(account_id, scope_key) or {}
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO sync_state (account_id, scope_key, last_incremental_sync_at, last_full_sync_at, known_match_count)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(account_id, scope_key) DO UPDATE SET
                    last_incremental_sync_at = excluded.last_incremental_sync_at,
                    last_full_sync_at = excluded.last_full_sync_at,
                    known_match_count = excluded.known_match_count
                """,
                (
                    int(account_id),
                    str(scope_key),
                    last_incremental_sync_at or current.get("last_incremental_sync_at"),
                    last_full_sync_at or current.get("last_full_sync_at"),
                    int(known_match_count if known_match_count is not None else current.get("known_match_count") or 0),
                ),
            )
        self._commit()

    def count_player_matches(self, account_id: int, game_mode: int | None = None) -> int:
        query = "SELECT COUNT(*) AS total FROM player_matches WHERE account_id = %s"
        params: list[Any] = [int(account_id)]
        if game_mode is not None:
            query += " AND (game_mode = %s OR game_mode IS NULL)"
            params.append(int(game_mode))
        with self._cursor() as cur:
            cur.execute(query, params)
            row = self._fetchone_dict(cur)
        return int(row["total"]) if row is not None else 0

    def get_latest_player_match_update(self, account_id: int, game_mode: int | None = None) -> str | None:
        query = "SELECT MAX(updated_at) AS latest_updated_at FROM player_matches WHERE account_id = %s"
        params: list[Any] = [int(account_id)]
        if game_mode is not None:
            query += " AND (game_mode = %s OR game_mode IS NULL)"
            params.append(int(game_mode))
        with self._cursor() as cur:
            cur.execute(query, params)
            row = self._fetchone_dict(cur)
        if row is None:
            return None
        return str(row["latest_updated_at"]) if row["latest_updated_at"] is not None else None

    def get_background_sync_state(
        self,
        account_id: int,
        scope_key: str,
        window_days: int,
    ) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM background_sync_state
                WHERE account_id = %s AND scope_key = %s AND window_days = %s
                """,
                (int(account_id), str(scope_key), int(window_days)),
            )
            row = self._fetchone_dict(cur)
        return row

    def upsert_background_sync_state(
        self,
        account_id: int,
        scope_key: str,
        window_days: int,
        **fields: Any,
    ) -> None:
        current = self.get_background_sync_state(account_id, scope_key, window_days) or {}
        merged = {
            "status": fields.get("status", current.get("status", "idle")),
            "last_started_at": fields.get("last_started_at", current.get("last_started_at")),
            "last_finished_at": fields.get("last_finished_at", current.get("last_finished_at")),
            "last_status": fields.get("last_status", current.get("last_status")),
            "last_error": fields.get("last_error", current.get("last_error")),
            "last_rate_limited_at": fields.get("last_rate_limited_at", current.get("last_rate_limited_at")),
            "next_retry_at": fields.get("next_retry_at", current.get("next_retry_at")),
            "next_stratz_retry_at": fields.get("next_stratz_retry_at", current.get("next_stratz_retry_at")),
            "next_pending_parse_check_at": fields.get("next_pending_parse_check_at", current.get("next_pending_parse_check_at")),
            "last_summary_sync_at": fields.get("last_summary_sync_at", current.get("last_summary_sync_at")),
            "target_match_count": int(fields.get("target_match_count", current.get("target_match_count", 0)) or 0),
            "detail_cached_count": int(fields.get("detail_cached_count", current.get("detail_cached_count", 0)) or 0),
            "timing_ready_count": int(fields.get("timing_ready_count", current.get("timing_ready_count", 0)) or 0),
            "missing_detail_count": int(fields.get("missing_detail_count", current.get("missing_detail_count", 0)) or 0),
            "missing_timing_count": int(fields.get("missing_timing_count", current.get("missing_timing_count", 0)) or 0),
            "pending_parse_count": int(fields.get("pending_parse_count", current.get("pending_parse_count", 0)) or 0),
            "newest_match_start_time": fields.get("newest_match_start_time", current.get("newest_match_start_time")),
            "oldest_match_start_time": fields.get("oldest_match_start_time", current.get("oldest_match_start_time")),
            "newest_fully_cached_start_time": fields.get("newest_fully_cached_start_time", current.get("newest_fully_cached_start_time")),
            "oldest_fully_cached_start_time": fields.get("oldest_fully_cached_start_time", current.get("oldest_fully_cached_start_time")),
            "total_runs": int(fields.get("total_runs", current.get("total_runs", 0)) or 0),
            "total_detail_fetches": int(fields.get("total_detail_fetches", current.get("total_detail_fetches", 0)) or 0),
            "total_parse_requests": int(fields.get("total_parse_requests", current.get("total_parse_requests", 0)) or 0),
        }
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO background_sync_state (
                    account_id, scope_key, window_days, status, last_started_at, last_finished_at, last_status,
                    last_error, last_rate_limited_at, next_retry_at, next_stratz_retry_at, next_pending_parse_check_at, last_summary_sync_at, target_match_count,
                    detail_cached_count, timing_ready_count, missing_detail_count, missing_timing_count,
                    pending_parse_count, newest_match_start_time, oldest_match_start_time,
                    newest_fully_cached_start_time, oldest_fully_cached_start_time,
                    total_runs, total_detail_fetches, total_parse_requests
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(account_id, scope_key, window_days) DO UPDATE SET
                    status = excluded.status,
                    last_started_at = excluded.last_started_at,
                    last_finished_at = excluded.last_finished_at,
                    last_status = excluded.last_status,
                    last_error = excluded.last_error,
                    last_rate_limited_at = excluded.last_rate_limited_at,
                    next_retry_at = excluded.next_retry_at,
                    next_stratz_retry_at = excluded.next_stratz_retry_at,
                    next_pending_parse_check_at = excluded.next_pending_parse_check_at,
                    last_summary_sync_at = excluded.last_summary_sync_at,
                    target_match_count = excluded.target_match_count,
                    detail_cached_count = excluded.detail_cached_count,
                    timing_ready_count = excluded.timing_ready_count,
                    missing_detail_count = excluded.missing_detail_count,
                    missing_timing_count = excluded.missing_timing_count,
                    pending_parse_count = excluded.pending_parse_count,
                    newest_match_start_time = excluded.newest_match_start_time,
                    oldest_match_start_time = excluded.oldest_match_start_time,
                    newest_fully_cached_start_time = excluded.newest_fully_cached_start_time,
                    oldest_fully_cached_start_time = excluded.oldest_fully_cached_start_time,
                    total_runs = excluded.total_runs,
                    total_detail_fetches = excluded.total_detail_fetches,
                    total_parse_requests = excluded.total_parse_requests
                """,
                (
                    int(account_id),
                    str(scope_key),
                    int(window_days),
                    merged["status"],
                    merged["last_started_at"],
                    merged["last_finished_at"],
                    merged["last_status"],
                    merged["last_error"],
                    merged["last_rate_limited_at"],
                    merged["next_retry_at"],
                    merged["next_stratz_retry_at"],
                    merged["next_pending_parse_check_at"],
                    merged["last_summary_sync_at"],
                    merged["target_match_count"],
                    merged["detail_cached_count"],
                    merged["timing_ready_count"],
                    merged["missing_detail_count"],
                    merged["missing_timing_count"],
                    merged["pending_parse_count"],
                    merged["newest_match_start_time"],
                    merged["oldest_match_start_time"],
                    merged["newest_fully_cached_start_time"],
                    merged["oldest_fully_cached_start_time"],
                    merged["total_runs"],
                    merged["total_detail_fetches"],
                    merged["total_parse_requests"],
                ),
            )
        self._commit()

    def insert_background_sync_run(
        self,
        *,
        account_id: int,
        scope_key: str,
        window_days: int,
        started_at: str,
        finished_at: str | None,
        status: str,
        run_source: str,
        summary_new_matches: int,
        total_matches_in_window: int,
        detail_requested: int,
        detail_completed: int,
        parse_requested: int,
        pending_parse_count: int,
        rate_limited: bool,
        next_retry_at: str | None,
        request_targets: str | None,
        data_sources: str | None,
        note: str | None,
    ) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO background_sync_runs (
                    account_id, scope_key, window_days, started_at, finished_at, status,
                    run_source,
                    summary_new_matches, total_matches_in_window, detail_requested, detail_completed,
                    parse_requested, pending_parse_count, rate_limited, next_retry_at, request_targets, data_sources, note
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    int(account_id),
                    str(scope_key),
                    int(window_days),
                    started_at,
                    finished_at,
                    status,
                    str(run_source or "manual"),
                    int(summary_new_matches),
                    int(total_matches_in_window),
                    int(detail_requested),
                    int(detail_completed),
                    int(parse_requested),
                    int(pending_parse_count),
                    1 if rate_limited else 0,
                    next_retry_at,
                    request_targets,
                    data_sources,
                    note,
                ),
            )
        self._commit()

    def list_background_sync_runs(
        self,
        account_id: int,
        scope_key: str,
        window_days: int,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM background_sync_runs
                WHERE account_id = %s AND scope_key = %s AND window_days = %s
                ORDER BY started_at DESC, id DESC
                LIMIT %s
                """,
                (int(account_id), str(scope_key), int(window_days), int(limit)),
            )
            rows = self._fetchall_dicts(cur)
        return rows

    def get_match_parse_request(self, match_id: int) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM match_parse_requests WHERE match_id = %s", (int(match_id),))
            row = self._fetchone_dict(cur)
        return row

    def get_match_parse_requests_for_ids(self, match_ids: list[int]) -> dict[int, dict[str, Any]]:
        unique_ids = [int(match_id) for match_id in set(match_ids) if int(match_id) > 0]
        if not unique_ids:
            return {}
        placeholders = ",".join("%s" for _ in unique_ids)
        query = f"SELECT * FROM match_parse_requests WHERE match_id IN ({placeholders})"
        with self._cursor() as cur:
            cur.execute(query, unique_ids)
            rows = self._fetchall_dicts(cur)
        return {int(row["match_id"]): row for row in rows}

    def upsert_match_parse_request(
        self,
        match_id: int,
        account_id: int,
        *,
        status: str,
        parse_job_id: int | None = None,
        request_source: str | None = None,
        request_reason: str | None = None,
        requested_at: str | None = None,
        last_polled_at: str | None = None,
        completed_at: str | None = None,
        last_error: str | None = None,
        increment_attempts: bool = True,
    ) -> None:
        current = self.get_match_parse_request(match_id) or {}
        current_attempts = int(current.get("attempts") or 0)
        next_attempts = (
            current_attempts + 1
            if increment_attempts and status == "pending" and not current.get("completed_at")
            else current_attempts
        )
        if next_attempts <= 0:
            next_attempts = 1
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO match_parse_requests (
                    match_id, account_id, status, parse_job_id, request_source, request_reason, requested_at, last_polled_at, completed_at, attempts, last_error
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(match_id) DO UPDATE SET
                    account_id = excluded.account_id,
                    status = excluded.status,
                    parse_job_id = COALESCE(excluded.parse_job_id, match_parse_requests.parse_job_id),
                    request_source = COALESCE(excluded.request_source, match_parse_requests.request_source),
                    request_reason = COALESCE(excluded.request_reason, match_parse_requests.request_reason),
                    requested_at = COALESCE(excluded.requested_at, match_parse_requests.requested_at),
                    last_polled_at = COALESCE(excluded.last_polled_at, match_parse_requests.last_polled_at),
                    completed_at = COALESCE(excluded.completed_at, match_parse_requests.completed_at),
                    attempts = excluded.attempts,
                    last_error = excluded.last_error
                """,
                (
                    int(match_id),
                    int(account_id),
                    status,
                    int(parse_job_id) if parse_job_id is not None else current.get("parse_job_id"),
                    request_source or current.get("request_source"),
                    request_reason or current.get("request_reason"),
                    requested_at or current.get("requested_at") or self._now_iso(),
                    last_polled_at or current.get("last_polled_at"),
                    completed_at or current.get("completed_at"),
                    next_attempts,
                    last_error,
                ),
            )
        self._commit()

    def list_match_parse_requests(
        self,
        account_id: int,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [int(account_id)]
        clauses = ["account_id = %s"]
        if status is not None:
            clauses.append("status = %s")
            params.append(str(status))
        params.append(int(limit))
        query = f"""
            SELECT *
            FROM match_parse_requests
            WHERE {' AND '.join(clauses)}
            ORDER BY
                CASE WHEN last_polled_at IS NULL THEN 0 ELSE 1 END ASC,
                COALESCE(last_polled_at, requested_at) ASC,
                requested_at ASC
            LIMIT %s
        """
        with self._cursor() as cur:
            cur.execute(query, params)
            rows = self._fetchall_dicts(cur)
        return rows
