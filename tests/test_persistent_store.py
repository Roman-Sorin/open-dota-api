from __future__ import annotations

from pathlib import Path
import shutil

from utils.match_store import SQLiteMatchStore
from utils.persistent_store import bootstrap_match_store


class _Settings:
    def __init__(self) -> None:
        self.match_store_s3_bucket = ""
        self.match_store_s3_key = ""
        self.match_store_s3_endpoint_url = None
        self.match_store_s3_region = None


def test_sqlite_match_store_calls_after_commit_hook_for_persistent_replica(tmp_path: Path) -> None:
    db_path = tmp_path / "matches.sqlite3"
    callback_calls: list[str] = []

    store = SQLiteMatchStore(db_path, after_commit=lambda: callback_calls.append("commit"))
    store.upsert_player_matches(
        123,
        [
            {
                "match_id": 1,
                "start_time": 100,
                "player_slot": 0,
                "radiant_win": True,
                "kills": 5,
                "deaths": 2,
                "assists": 9,
                "duration": 1800,
                "hero_id": 1,
                "game_mode": 23,
            }
        ],
    )

    assert callback_calls


def test_match_store_can_restore_from_durable_replica_after_local_file_loss(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "cache" / "matches.sqlite3"
    backup_path = tmp_path / "remote" / "matches.sqlite3"
    backup_path.parent.mkdir(parents=True, exist_ok=True)

    class _FakeReplica:
        def bootstrap(self) -> None:
            if backup_path.exists():
                db_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_path, db_path)

        def sync_from_local(self) -> None:
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db_path, backup_path)

    monkeypatch.setattr(
        "utils.persistent_store.build_match_store_replica",
        lambda settings, path: _FakeReplica(),
    )

    settings = _Settings()
    match_store_path, after_commit = bootstrap_match_store(settings, db_path)
    first_store = SQLiteMatchStore(match_store_path, after_commit=after_commit)
    first_store.upsert_player_matches(
        123,
        [
            {
                "match_id": 8760879094,
                "start_time": 1775500000,
                "player_slot": 0,
                "radiant_win": True,
                "kills": 13,
                "deaths": 6,
                "assists": 17,
                "duration": 1645,
                "hero_id": 67,
                "game_mode": 23,
            }
        ],
    )

    assert backup_path.exists()
    first_store.close()
    db_path.unlink(missing_ok=True)

    restored_path, restored_after_commit = bootstrap_match_store(settings, db_path)
    second_store = SQLiteMatchStore(restored_path, after_commit=restored_after_commit)
    rows = second_store.query_player_matches(123, game_mode=23)

    assert len(rows) == 1
    assert rows[0]["match_id"] == 8760879094
    second_store.close()
