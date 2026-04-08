from __future__ import annotations

from typing import Any

import requests


class StratzError(Exception):
    """Base exception for STRATZ client and enrichment failures."""


class StratzRateLimitError(StratzError):
    """Raised when STRATZ rate limits the request."""


class StratzClient:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://api.stratz.com/graphql",
        timeout_seconds: float = 20.0,
        user_agent: str = "STRATZ_API",
    ) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "User-Agent": user_agent,
            }
        )

    def _query(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.session.post(
                self.base_url,
                json={"query": query, "variables": variables},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise StratzError(f"Network error while calling STRATZ: {exc}") from exc

        if response.status_code == 429:
            raise StratzRateLimitError("STRATZ API rate limit reached")

        if response.status_code >= 400:
            raise StratzError(f"STRATZ API error {response.status_code}: {response.text[:300]}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise StratzError("STRATZ returned non-JSON response") from exc

        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            message = "; ".join(str(err.get("message") or "Unknown STRATZ error") for err in errors if isinstance(err, dict))
            raise StratzError(message or "Unknown STRATZ GraphQL error")

        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def get_match_item_purchases(self, match_id: int) -> list[dict[str, Any]]:
        query = """
        query GetMatchItemPurchases($id: Long!) {
          match(id: $id) {
            id
            players {
              steamAccountId
              playerSlot
              heroId
              stats {
                itemPurchases {
                  itemId
                  time
                }
              }
            }
          }
        }
        """
        data = self._query(query, {"id": int(match_id)})
        match_payload = data.get("match")
        if not isinstance(match_payload, dict):
            return []
        players = match_payload.get("players")
        return players if isinstance(players, list) else []
