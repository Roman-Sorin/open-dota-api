from __future__ import annotations

from typing import Any

import requests

from utils.exceptions import OpenDotaError, OpenDotaNotFoundError, OpenDotaRateLimitError


class OpenDotaClient:
    def __init__(self, base_url: str, timeout_seconds: float = 20.0, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key
        self.session = requests.Session()

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        query = dict(params or {})
        if self.api_key:
            query["api_key"] = self.api_key

        try:
            response = self.session.request(method=method, url=url, params=query, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise OpenDotaError(f"Network error while calling OpenDota: {exc}") from exc

        if response.status_code == 404:
            raise OpenDotaNotFoundError("Requested entity was not found in OpenDota")

        if response.status_code == 429:
            raise OpenDotaRateLimitError("OpenDota API rate limit reached")

        if response.status_code >= 400:
            raise OpenDotaError(f"OpenDota API error {response.status_code}: {response.text[:300]}")

        try:
            return response.json()
        except ValueError as exc:
            raise OpenDotaError("OpenDota returned non-JSON response") from exc

    def get_player_profile(self, account_id: int) -> dict[str, Any]:
        return self._request("GET", f"players/{account_id}")

    def get_player_matches(
        self,
        account_id: int,
        hero_id: int | None = None,
        game_mode: int | None = None,
        days: int | None = None,
        limit: int | None = None,
        significant: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if hero_id is not None:
            params["hero_id"] = hero_id
        if game_mode is not None:
            params["game_mode"] = game_mode
        if days is not None:
            params["date"] = days
        if limit is not None:
            params["limit"] = limit
        if significant is not None:
            params["significant"] = significant
        if offset is not None:
            params["offset"] = offset

        result = self._request("GET", f"players/{account_id}/matches", params=params)
        return result if isinstance(result, list) else []

    def get_player_recent_matches(self, account_id: int) -> list[dict[str, Any]]:
        result = self._request("GET", f"players/{account_id}/recentMatches")
        return result if isinstance(result, list) else []

    def get_player_heroes(
        self,
        account_id: int,
        game_mode: int | None = None,
        days: int | None = None,
        significant: int | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if game_mode is not None:
            params["game_mode"] = game_mode
        if days is not None:
            params["date"] = days
        if significant is not None:
            params["significant"] = significant
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset

        result = self._request("GET", f"players/{account_id}/heroes", params=params)
        return result if isinstance(result, list) else []

    def get_constants_heroes(self) -> dict[str, Any]:
        result = self._request("GET", "constants/heroes")
        return result if isinstance(result, dict) else {}

    def get_constants_items(self) -> dict[str, Any]:
        result = self._request("GET", "constants/items")
        return result if isinstance(result, dict) else {}

    def get_match_details(self, match_id: int) -> dict[str, Any]:
        result = self._request("GET", f"matches/{match_id}")
        return result if isinstance(result, dict) else {}
