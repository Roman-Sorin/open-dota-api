from __future__ import annotations

from types import SimpleNamespace

from webapp.app_runtime import build_service


class _FakeOpenDotaClient:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def get_constants_heroes(self) -> dict:
        return {"1": {"id": 1, "localized_name": "Axe", "img": "/apps/dota2/images/heroes/axe.png"}}

    def get_constants_items(self) -> dict:
        return {}

    def get_constants_patch(self) -> list[dict]:
        return [{"name": "7.40", "date": "2025-01-01T00:00:00Z"}]


class _FakeCache:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self._store: dict[str, object] = {}

    def get(self, key: str, max_age=None):
        return self._store.get(key)

    def set(self, key: str, value: object) -> None:
        self._store[key] = value


def test_build_service_does_not_import_or_enable_stratz(monkeypatch) -> None:
    imported_modules: list[str] = []

    def fake_import_module(name: str):
        imported_modules.append(name)
        if name == "utils.config":
            return SimpleNamespace(
                get_settings=lambda: SimpleNamespace(
                    api_key="key",
                    stratz_token="should-be-ignored",
                    stratz_base_url="https://api.stratz.com/graphql",
                    timeout_seconds=20.0,
                    cache_ttl_hours=24,
                    google_drive_service_account_json=None,
                    google_drive_folder_id=None,
                    database_url=None,
                    google_drive_snapshot_name=None,
                    google_drive_min_upload_interval_seconds=60,
                    base_url="https://api.opendota.com/api",
                ),
                get_cache_dir=lambda: ".cache",
            )
        if name == "utils.cache":
            return SimpleNamespace(JsonFileCache=_FakeCache)
        if name == "utils.exceptions":
            return SimpleNamespace()
        if name == "clients.opendota_client":
            return SimpleNamespace(OpenDotaClient=_FakeOpenDotaClient)
        if name == "utils.match_store":
            return SimpleNamespace()
        if name == "utils.store_factory":
            return SimpleNamespace(build_match_store=lambda settings: None)
        if name == "services.analytics_service":
            from services.analytics_service import DotaAnalyticsService

            return SimpleNamespace(DotaAnalyticsService=DotaAnalyticsService)
        raise AssertionError(f"Unexpected import: {name}")

    monkeypatch.setattr("importlib.import_module", fake_import_module)
    monkeypatch.setattr("importlib.reload", lambda module: module)

    service = build_service()

    assert "clients.stratz_client" not in imported_modules
    assert service.stratz_client is None
