from __future__ import annotations

from pathlib import Path

from utils.store_factory import build_match_store, get_last_store_warning


class _Settings:
    def __init__(self, database_url: str | None) -> None:
        self.database_url = database_url


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


def test_build_match_store_uses_postgres_when_database_url_present(monkeypatch) -> None:
    captured: list[str] = []

    class _FakePostgresStore:
        def __init__(self, database_url: str) -> None:
            captured.append(database_url)

    monkeypatch.setattr("utils.store_factory.PostgresMatchStore", _FakePostgresStore)

    store = build_match_store(_Settings(database_url="postgresql://example"))

    assert captured == ["postgresql://example"]
    assert isinstance(store, _FakePostgresStore)


def test_build_match_store_falls_back_to_sqlite_when_postgres_connect_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    class _BrokenPostgresStore:
        def __init__(self, database_url: str) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr("utils.store_factory.PostgresMatchStore", _BrokenPostgresStore)

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
