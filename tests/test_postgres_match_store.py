from __future__ import annotations

import importlib
import sys
import types


def _load_module_with_fake_pg8000():
    fake_dbapi = types.SimpleNamespace(connect=lambda **kwargs: None)
    fake_pg8000 = types.SimpleNamespace(dbapi=fake_dbapi)
    sys.modules.setdefault("pg8000", fake_pg8000)
    sys.modules.setdefault("pg8000.dbapi", fake_dbapi)
    return importlib.import_module("utils.postgres_match_store")


def test_connect_from_url_enables_psycopg_autocommit(monkeypatch) -> None:
    module = _load_module_with_fake_pg8000()
    captured: dict[str, object] = {}

    class _FakePsycopg:
        @staticmethod
        def connect(url: str, *, autocommit: bool, row_factory):
            captured["url"] = url
            captured["autocommit"] = autocommit
            captured["row_factory"] = row_factory
            return object()

    monkeypatch.setattr(module, "psycopg", _FakePsycopg)
    monkeypatch.setattr(module, "dict_row", object())

    store = module.PostgresMatchStore.__new__(module.PostgresMatchStore)
    conn = store._connect_from_url("postgresql://example")

    assert conn is not None
    assert captured["url"] == "postgresql://example"
    assert captured["autocommit"] is True


def test_connect_from_url_enables_pg8000_autocommit(monkeypatch) -> None:
    module = _load_module_with_fake_pg8000()
    captured: dict[str, object] = {}

    class _FakeConnection:
        def __init__(self) -> None:
            self.autocommit = False

    def _fake_connect(**kwargs):
        captured.update(kwargs)
        return _FakeConnection()

    monkeypatch.setattr(module, "psycopg", None)
    monkeypatch.setattr(module.pg8000.dbapi, "connect", _fake_connect)

    store = module.PostgresMatchStore.__new__(module.PostgresMatchStore)
    conn = store._connect_from_url("postgresql://user:pass@example.com:5432/neondb?sslmode=require")

    assert conn.autocommit is True
    assert captured["host"] == "example.com"
    assert captured["database"] == "neondb"
