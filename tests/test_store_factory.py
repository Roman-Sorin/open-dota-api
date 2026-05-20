from __future__ import annotations

from pathlib import Path

from utils.store_factory import build_match_store, get_last_store_warning


class _Settings:
    def __init__(
        self,
        database_url: str | None,
        *,
        google_drive_service_account_json: str | None = None,
        google_drive_folder_id: str | None = None,
        google_drive_snapshot_name: str | None = None,
        google_drive_min_upload_interval_seconds: int = 60,
    ) -> None:
        self.database_url = database_url
        self.google_drive_service_account_json = google_drive_service_account_json
        self.google_drive_folder_id = google_drive_folder_id
        self.google_drive_snapshot_name = google_drive_snapshot_name
        self.google_drive_min_upload_interval_seconds = google_drive_min_upload_interval_seconds


def test_build_match_store_uses_sqlite_when_database_url_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    store = build_match_store(_Settings(database_url=None))
    try:
        store.upsert_player_matches(
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
        rows = store.query_player_matches(123, game_mode=23)
    finally:
        store.close()

    assert len(rows) == 1
    assert rows[0]["match_id"] == 8760879094


def test_build_match_store_uses_google_drive_snapshot_when_configured(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    captured: dict[str, object] = {}

    class _FakeManager:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def restore_if_available(self) -> bool:
            captured["restore_called"] = True
            return False

        def sync_if_due(self, *, force: bool = False) -> bool:
            captured["last_force"] = force
            return True

    class _FakeModule:
        GoogleDriveSnapshotManager = _FakeManager

    monkeypatch.setattr("importlib.import_module", lambda name: _FakeModule())
    monkeypatch.setattr("importlib.reload", lambda module: module)

    store = build_match_store(
        _Settings(
            database_url=None,
            google_drive_service_account_json='{"type":"service_account"}',
            google_drive_folder_id="folder123",
        )
    )
    try:
        store.upsert_player_matches(
            123,
            [
                {
                    "match_id": 1,
                    "start_time": 1775500000,
                    "player_slot": 0,
                    "radiant_win": True,
                    "kills": 1,
                    "deaths": 1,
                    "assists": 1,
                    "duration": 1200,
                    "hero_id": 1,
                    "game_mode": 23,
                }
            ],
        )
        store.flush_persistent_snapshot(force=True)
    finally:
        store.close()

    assert captured["folder_id"] == "folder123"
    assert captured["snapshot_name"] == "matches.sqlite3"
    assert captured["restore_called"] is True
    assert captured["last_force"] is True


def test_build_match_store_uses_postgres_when_database_url_present(monkeypatch) -> None:
    captured: list[str] = []

    class _FakePostgresStore:
        def __init__(self, database_url: str) -> None:
            captured.append(database_url)

    class _FakeModule:
        PostgresMatchStore = _FakePostgresStore

    monkeypatch.setattr("importlib.import_module", lambda name: _FakeModule())
    monkeypatch.setattr("importlib.reload", lambda module: module)

    store = build_match_store(_Settings(database_url="postgresql://example"))

    assert captured == ["postgresql://example"]
    assert isinstance(store, _FakePostgresStore)


def test_build_match_store_falls_back_to_sqlite_when_postgres_connect_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    class _BrokenPostgresStore:
        def __init__(self, database_url: str) -> None:
            raise RuntimeError("boom")

    class _FakeModule:
        PostgresMatchStore = _BrokenPostgresStore

    monkeypatch.setattr("importlib.import_module", lambda name: _FakeModule())
    monkeypatch.setattr("importlib.reload", lambda module: module)

    store = build_match_store(_Settings(database_url="postgresql://broken"))
    try:
        store.upsert_player_matches(
            7,
            [
                {
                    "match_id": 7001,
                    "start_time": 1775500001,
                    "player_slot": 0,
                    "radiant_win": False,
                    "kills": 1,
                    "deaths": 1,
                    "assists": 1,
                    "duration": 900,
                    "hero_id": 2,
                    "game_mode": 23,
                }
            ],
        )
        rows = store.query_player_matches(7, game_mode=23)
    finally:
        store.close()

    assert len(rows) == 1
    assert "Failed to connect to DATABASE_URL" in (get_last_store_warning() or "")
