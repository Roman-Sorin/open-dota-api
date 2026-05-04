from __future__ import annotations

from pathlib import Path

from services.analytics_service import DotaAnalyticsService
from utils.cache import JsonFileCache
from utils.exceptions import OpenDotaRateLimitError


class _RateLimitedClient:
    def __init__(self) -> None:
        self.hero_calls = 0
        self.item_calls = 0
        self.patch_calls = 0

    def get_constants_heroes(self) -> dict:
        self.hero_calls += 1
        raise OpenDotaRateLimitError("OpenDota temporarily unavailable (HTTP 522)")

    def get_constants_items(self) -> dict:
        self.item_calls += 1
        raise OpenDotaRateLimitError("OpenDota temporarily unavailable (HTTP 522)")

    def get_constants_patch(self) -> list[dict]:
        self.patch_calls += 1
        raise OpenDotaRateLimitError("OpenDota temporarily unavailable (HTTP 522)")


def test_service_uses_bundled_reference_data_when_constants_are_unavailable(tmp_path: Path) -> None:
    client = _RateLimitedClient()
    cache = JsonFileCache(tmp_path / "json-cache")

    service = DotaAnalyticsService(client=client, cache=cache)

    assert service.resolve_hero_name(2) == "Axe"
    assert service.references.item_names_by_id[1] == "Blink Dagger"
    assert service._patch_names[-1]
    assert cache.get("constants_heroes") is not None
    assert cache.get("constants_items") is not None
    assert cache.get("constants_patch") is not None
    assert client.hero_calls == 1
    assert client.item_calls == 1
    assert client.patch_calls == 1


def test_service_reuses_cached_reference_data_after_bundled_fallback(tmp_path: Path) -> None:
    first_client = _RateLimitedClient()
    cache = JsonFileCache(tmp_path / "json-cache")

    DotaAnalyticsService(client=first_client, cache=cache)

    second_client = _RateLimitedClient()
    service = DotaAnalyticsService(client=second_client, cache=cache)

    assert service.resolve_hero_name(2) == "Axe"
    assert second_client.hero_calls == 0
    assert second_client.item_calls == 0
    assert second_client.patch_calls == 0
