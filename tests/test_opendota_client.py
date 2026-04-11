from __future__ import annotations

from unittest.mock import Mock

import requests

from clients.opendota_client import OpenDotaClient
from utils.exceptions import OpenDotaRateLimitError


def _response(status_code: int, payload: object = None, text: str = ""):
    response = Mock()
    response.status_code = status_code
    response.text = text
    response.json = Mock(return_value=payload)
    return response


def test_opendota_client_retries_transient_522_once_then_succeeds(monkeypatch) -> None:
    client = OpenDotaClient("https://api.opendota.com/api")
    request_mock = Mock(side_effect=[_response(522, text="cloudflare"), _response(200, payload={"ok": True})])
    monkeypatch.setattr(client.session, "request", request_mock)
    monkeypatch.setattr("clients.opendota_client.time.sleep", lambda _seconds: None)

    result = client.get_match_details(123)

    assert result == {"ok": True}
    assert request_mock.call_count == 2


def test_opendota_client_turns_repeated_522_into_temporary_unavailable(monkeypatch) -> None:
    client = OpenDotaClient("https://api.opendota.com/api")
    request_mock = Mock(side_effect=[_response(522, text="cloudflare"), _response(522, text="cloudflare")])
    monkeypatch.setattr(client.session, "request", request_mock)
    monkeypatch.setattr("clients.opendota_client.time.sleep", lambda _seconds: None)

    try:
        client.get_match_details(123)
    except OpenDotaRateLimitError as exc:
        assert "HTTP 522" in str(exc)
    else:
        raise AssertionError("expected OpenDotaRateLimitError")
