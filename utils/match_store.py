from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any


class SQLiteMatchStore:
    def __init__(self, db_path: Path | str) -> None:
        db_target = str(db_path)
        if db_target != ":memory:":
            Path(db_target).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_target, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS player_matches (
                account_id INTEGER NOT NULL,
                match_id INTEGER NOT NULL,
                start_time INTEGER NOT NULL,
                player_slot INTEGER NOT NULL,
                radiant_win INTEGER NOT NULL,
                kills INTEGER NOT NULL,
                deaths INTEGER NOT NULL,
                assists INTEGER NOT NULL,
                duration INTEGER NOT NULL,
                hero_id INTEGER,
                game_mode INTEGER,
                net_worth INTEGER,
                hero_damage INTEGER,
                lane_efficiency_pct REAL,
                item_0 INTEGER NOT NULL DEFAULT 0,
                item_1 INTEGER NOT NULL DEFAULT 0,
                item_2 INTEGER NOT NULL DEFAULT 0,
                item_3 INTEGER NOT NULL DEFAULT 0,
                item_4 INTEGER NOT NULL DEFAULT 0,
                item_5 INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (account_id, match_id)
            );

            CREATE INDEX IF NOT EXISTS idx_player_matches_lookup
            ON player_matches (account_id, game_mode, hero_id, start_time DESC);

            CREATE TABLE IF NOT EXISTS match_details (
                match_id INTEGER PRIMARY KEY,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sync_state (
                account_id INTEGER NOT NULL,
                scope_key TEXT NOT NULL,
                last_incremental_sync_at TEXT,
                last_full_sync_at TEXT,
                known_match_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (account_id, scope_key)
            );

            CREATE TABLE IF NOT EXISTS background_sync_state (
                account_id INTEGER NOT NULL,
                scope_key TEXT NOT NULL,
                window_days INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'idle',
                last_started_at TEXT,
                last_finished_at TEXT,
                last_status TEXT,
                last_error TEXT,
                last_rate_limited_at TEXT,
                next_retry_at TEXT,
                last_summary_sync_at TEXT,
                target_match_count INTEGER NOT NULL DEFAULT 0,
                detail_cached_count INTEGER NOT NULL DEFAULT 0,
                timing_ready_count INTEGER NOT NULL DEFAULT 0,
                missing_detail_count INTEGER NOT NULL DEFAULT 0,
                missing_timing_count INTEGER NOT NULL DEFAULT 0,
                pending_parse_count INTEGER NOT NULL DEFAULT 0,
                newest_match_start_time INTEGER,
                oldest_match_start_time INTEGER,
                newest_fully_cached_start_time INTEGER,
                oldest_fully_cached_start_time INTEGER,
                total_runs INTEGER NOT NULL DEFAULT 0,
                total_detail_fetches INTEGER NOT NULL DEFAULT 0,
                total_parse_requests INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (account_id, scope_key, window_days)
            );

            CREATE TABLE IF NOT EXISTS background_sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                scope_key TEXT NOT NULL,
                window_days INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                summary_new_matches INTEGER NOT NULL DEFAULT 0,
                total_matches_in_window INTEGER NOT NULL DEFAULT 0,
                detail_requested INTEGER NOT NULL DEFAULT 0,
                detail_completed INTEGER NOT NULL DEFAULT 0,
                parse_requested INTEGER NOT NULL DEFAULT 0,
                pending_parse_count INTEGER NOT NULL DEFAULT 0,
                rate_limited INTEGER NOT NULL DEFAULT 0,
                next_retry_at TEXT,
                note TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_background_sync_runs_lookup
            ON background_sync_runs (account_id, scope_key, window_days, started_at DESC);

            CREATE TABLE IF NOT EXISTS match_parse_requests (
                match_id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                last_polled_at TEXT,
                completed_at TEXT,
                attempts INTEGER NOT NULL DEFAULT 1,
                last_error TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_match_parse_requests_lookup
            ON match_parse_requests (account_id, status, requested_at DESC);
            """
        )
        self._conn.commit()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(tz=timezone.utc).isoformat()

    @staticmethod
    def _json_loads(payload: str) -> dict[str, Any]:
        value = json.loads(payload)
        return value if isinstance(value, dict) else {}

    def get_existing_match_ids(self, account_id: int, match_ids: list[int]) -> set[int]:
        unique_ids = [int(match_id) for match_id in set(match_ids) if int(match_id) > 0]
        if not unique_ids:
            return set()
        placeholders = ",".join("?" for _ in unique_ids)
        rows = self._conn.execute(
            f"SELECT match_id FROM player_matches WHERE account_id = ? AND match_id IN ({placeholders})",
            [int(account_id), *unique_ids],
        ).fetchall()
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
                    1 if bool(row.get("radiant_win")) else 0,
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
        self._conn.executemany(
            """
            INSERT INTO player_matches (
                account_id, match_id, start_time, player_slot, radiant_win, kills, deaths, assists,
                duration, hero_id, game_mode, net_worth, hero_damage, lane_efficiency_pct,
                item_0, item_1, item_2, item_3, item_4, item_5, payload_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        self._conn.commit()

    def query_player_matches(
        self,
        account_id: int,
        hero_id: int | None = None,
        game_mode: int | None = None,
        min_start_time: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["account_id = ?"]
        params: list[Any] = [int(account_id)]
        if hero_id is not None:
            clauses.append("hero_id = ?")
            params.append(int(hero_id))
        if game_mode is not None:
            clauses.append("(game_mode = ? OR game_mode IS NULL)")
            params.append(int(game_mode))
        if min_start_time is not None:
            clauses.append("start_time >= ?")
            params.append(int(min_start_time))
        query = (
            "SELECT payload_json FROM player_matches "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY start_time DESC"
        )
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))
        rows = self._conn.execute(query, params).fetchall()
        return [self._json_loads(str(row["payload_json"])) for row in rows]

    def query_player_match_status_rows(
        self,
        account_id: int,
        hero_id: int | None = None,
        game_mode: int | None = None,
        min_start_time: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["pm.account_id = ?"]
        params: list[Any] = [int(account_id)]
        if hero_id is not None:
            clauses.append("pm.hero_id = ?")
            params.append(int(hero_id))
        if game_mode is not None:
            clauses.append("(pm.game_mode = ? OR pm.game_mode IS NULL)")
            params.append(int(game_mode))
        if min_start_time is not None:
            clauses.append("pm.start_time >= ?")
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
            query += " LIMIT ?"
            params.append(int(limit))

        rows = self._conn.execute(query, params).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "match_id": int(row["match_id"]),
                    "payload": self._json_loads(str(row["payload_json"])),
                    "summary_updated_at": str(row["summary_updated_at"]) if row["summary_updated_at"] is not None else None,
                    "detail_updated_at": str(row["detail_updated_at"]) if row["detail_updated_at"] is not None else None,
                }
            )
        return result

    def update_player_match_enrichment(
        self,
        account_id: int,
        match_id: int,
        *,
        hero_damage: int | None = None,
        net_worth: int | None = None,
        lane_efficiency_pct: float | None = None,
    ) -> None:
        existing = self._conn.execute(
            "SELECT payload_json FROM player_matches WHERE account_id = ? AND match_id = ?",
            (int(account_id), int(match_id)),
        ).fetchone()
        if existing is None:
            return
        payload = self._json_loads(str(existing["payload_json"]))
        if hero_damage is not None and hero_damage > 0:
            payload["hero_damage"] = int(hero_damage)
        if net_worth is not None and net_worth > 0:
            payload["net_worth"] = int(net_worth)
        if lane_efficiency_pct is not None:
            payload["lane_efficiency_pct"] = float(lane_efficiency_pct)
        self._conn.execute(
            """
            UPDATE player_matches
            SET hero_damage = COALESCE(?, hero_damage),
                net_worth = COALESCE(?, net_worth),
                lane_efficiency_pct = COALESCE(?, lane_efficiency_pct),
                payload_json = ?,
                updated_at = ?
            WHERE account_id = ? AND match_id = ?
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
        self._conn.commit()

    def get_match_detail(self, match_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT payload_json FROM match_details WHERE match_id = ?",
            (int(match_id),),
        ).fetchone()
        if row is None:
            return None
        return self._json_loads(str(row["payload_json"]))

    def get_match_ids_without_details(
        self,
        account_id: int,
        game_mode: int | None = None,
        limit: int | None = None,
    ) -> list[int]:
        clauses = ["pm.account_id = ?"]
        params: list[Any] = [int(account_id)]
        if game_mode is not None:
            clauses.append("(pm.game_mode = ? OR pm.game_mode IS NULL)")
            params.append(int(game_mode))
        query = (
            "SELECT pm.match_id FROM player_matches pm "
            "LEFT JOIN match_details md ON md.match_id = pm.match_id "
            f"WHERE {' AND '.join(clauses)} AND md.match_id IS NULL "
            "ORDER BY pm.start_time DESC"
        )
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))
        rows = self._conn.execute(query, params).fetchall()
        return [int(row["match_id"]) for row in rows]

    def upsert_match_detail(self, match_id: int, payload: dict[str, Any]) -> None:
        self._conn.execute(
            """
            INSERT INTO match_details (match_id, payload_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (int(match_id), json.dumps(payload, ensure_ascii=False), self._now_iso()),
        )
        self._conn.commit()

    def get_sync_state(self, account_id: int, scope_key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT account_id, scope_key, last_incremental_sync_at, last_full_sync_at, known_match_count
            FROM sync_state
            WHERE account_id = ? AND scope_key = ?
            """,
            (int(account_id), str(scope_key)),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

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
        self._conn.execute(
            """
            INSERT INTO sync_state (account_id, scope_key, last_incremental_sync_at, last_full_sync_at, known_match_count)
            VALUES (?, ?, ?, ?, ?)
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
        self._conn.commit()

    def count_player_matches(self, account_id: int, game_mode: int | None = None) -> int:
        if game_mode is None:
            row = self._conn.execute(
                "SELECT COUNT(*) AS total FROM player_matches WHERE account_id = ?",
                (int(account_id),),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) AS total FROM player_matches WHERE account_id = ? AND (game_mode = ? OR game_mode IS NULL)",
                (int(account_id), int(game_mode)),
            ).fetchone()
        return int(row["total"]) if row is not None else 0

    def get_latest_player_match_update(self, account_id: int, game_mode: int | None = None) -> str | None:
        if game_mode is None:
            row = self._conn.execute(
                "SELECT MAX(updated_at) AS latest_updated_at FROM player_matches WHERE account_id = ?",
                (int(account_id),),
            ).fetchone()
        else:
            row = self._conn.execute(
                """
                SELECT MAX(updated_at) AS latest_updated_at
                FROM player_matches
                WHERE account_id = ? AND (game_mode = ? OR game_mode IS NULL)
                """,
                (int(account_id), int(game_mode)),
            ).fetchone()
        if row is None:
            return None
        return str(row["latest_updated_at"]) if row["latest_updated_at"] is not None else None

    def get_background_sync_state(
        self,
        account_id: int,
        scope_key: str,
        window_days: int,
    ) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT *
            FROM background_sync_state
            WHERE account_id = ? AND scope_key = ? AND window_days = ?
            """,
            (int(account_id), str(scope_key), int(window_days)),
        ).fetchone()
        return dict(row) if row is not None else None

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
            "last_summary_sync_at": fields.get("last_summary_sync_at", current.get("last_summary_sync_at")),
            "target_match_count": int(fields.get("target_match_count", current.get("target_match_count", 0)) or 0),
            "detail_cached_count": int(fields.get("detail_cached_count", current.get("detail_cached_count", 0)) or 0),
            "timing_ready_count": int(fields.get("timing_ready_count", current.get("timing_ready_count", 0)) or 0),
            "missing_detail_count": int(fields.get("missing_detail_count", current.get("missing_detail_count", 0)) or 0),
            "missing_timing_count": int(fields.get("missing_timing_count", current.get("missing_timing_count", 0)) or 0),
            "pending_parse_count": int(fields.get("pending_parse_count", current.get("pending_parse_count", 0)) or 0),
            "newest_match_start_time": fields.get("newest_match_start_time", current.get("newest_match_start_time")),
            "oldest_match_start_time": fields.get("oldest_match_start_time", current.get("oldest_match_start_time")),
            "newest_fully_cached_start_time": fields.get(
                "newest_fully_cached_start_time",
                current.get("newest_fully_cached_start_time"),
            ),
            "oldest_fully_cached_start_time": fields.get(
                "oldest_fully_cached_start_time",
                current.get("oldest_fully_cached_start_time"),
            ),
            "total_runs": int(fields.get("total_runs", current.get("total_runs", 0)) or 0),
            "total_detail_fetches": int(fields.get("total_detail_fetches", current.get("total_detail_fetches", 0)) or 0),
            "total_parse_requests": int(fields.get("total_parse_requests", current.get("total_parse_requests", 0)) or 0),
        }
        self._conn.execute(
            """
            INSERT INTO background_sync_state (
                account_id, scope_key, window_days, status, last_started_at, last_finished_at, last_status,
                last_error, last_rate_limited_at, next_retry_at, last_summary_sync_at, target_match_count,
                detail_cached_count, timing_ready_count, missing_detail_count, missing_timing_count,
                pending_parse_count, newest_match_start_time, oldest_match_start_time,
                newest_fully_cached_start_time, oldest_fully_cached_start_time,
                total_runs, total_detail_fetches, total_parse_requests
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, scope_key, window_days) DO UPDATE SET
                status = excluded.status,
                last_started_at = excluded.last_started_at,
                last_finished_at = excluded.last_finished_at,
                last_status = excluded.last_status,
                last_error = excluded.last_error,
                last_rate_limited_at = excluded.last_rate_limited_at,
                next_retry_at = excluded.next_retry_at,
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
        self._conn.commit()

    def insert_background_sync_run(
        self,
        *,
        account_id: int,
        scope_key: str,
        window_days: int,
        started_at: str,
        finished_at: str | None,
        status: str,
        summary_new_matches: int,
        total_matches_in_window: int,
        detail_requested: int,
        detail_completed: int,
        parse_requested: int,
        pending_parse_count: int,
        rate_limited: bool,
        next_retry_at: str | None,
        note: str | None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO background_sync_runs (
                account_id, scope_key, window_days, started_at, finished_at, status,
                summary_new_matches, total_matches_in_window, detail_requested, detail_completed,
                parse_requested, pending_parse_count, rate_limited, next_retry_at, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(account_id),
                str(scope_key),
                int(window_days),
                started_at,
                finished_at,
                status,
                int(summary_new_matches),
                int(total_matches_in_window),
                int(detail_requested),
                int(detail_completed),
                int(parse_requested),
                int(pending_parse_count),
                1 if rate_limited else 0,
                next_retry_at,
                note,
            ),
        )
        self._conn.commit()

    def list_background_sync_runs(
        self,
        account_id: int,
        scope_key: str,
        window_days: int,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT *
            FROM background_sync_runs
            WHERE account_id = ? AND scope_key = ? AND window_days = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (int(account_id), str(scope_key), int(window_days), int(limit)),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_match_parse_request(self, match_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM match_parse_requests WHERE match_id = ?",
            (int(match_id),),
        ).fetchone()
        return dict(row) if row is not None else None

    def upsert_match_parse_request(
        self,
        match_id: int,
        account_id: int,
        *,
        status: str,
        requested_at: str | None = None,
        last_polled_at: str | None = None,
        completed_at: str | None = None,
        last_error: str | None = None,
    ) -> None:
        current = self.get_match_parse_request(match_id) or {}
        current_attempts = int(current.get("attempts") or 0)
        next_attempts = current_attempts + 1 if status == "pending" and not current.get("completed_at") else current_attempts
        if next_attempts <= 0:
            next_attempts = 1
        self._conn.execute(
            """
            INSERT INTO match_parse_requests (
                match_id, account_id, status, requested_at, last_polled_at, completed_at, attempts, last_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
                account_id = excluded.account_id,
                status = excluded.status,
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
                requested_at or current.get("requested_at") or self._now_iso(),
                last_polled_at or current.get("last_polled_at"),
                completed_at or current.get("completed_at"),
                next_attempts,
                last_error,
            ),
        )
        self._conn.commit()

    def list_match_parse_requests(
        self,
        account_id: int,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [int(account_id)]
        clauses = ["account_id = ?"]
        if status is not None:
            clauses.append("status = ?")
            params.append(str(status))
        params.append(int(limit))
        rows = self._conn.execute(
            f"""
            SELECT *
            FROM match_parse_requests
            WHERE {' AND '.join(clauses)}
            ORDER BY requested_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
