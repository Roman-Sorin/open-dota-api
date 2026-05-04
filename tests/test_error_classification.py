from __future__ import annotations

import importlib

import utils.exceptions as exceptions_module
from webapp.error_classification import (
    is_opendota_error,
    is_opendota_not_found_error,
    is_opendota_rate_limit_error,
    is_validation_error,
)


def test_error_classification_handles_reloaded_opendota_exceptions() -> None:
    stale_module = exceptions_module
    stale_rate_limit_cls = stale_module.OpenDotaRateLimitError
    stale_not_found_cls = stale_module.OpenDotaNotFoundError
    stale_validation_cls = stale_module.ValidationError

    fresh_module = importlib.reload(exceptions_module)

    fresh_rate_limit_error = fresh_module.OpenDotaRateLimitError("OpenDota temporarily unavailable (HTTP 522)")
    fresh_not_found_error = fresh_module.OpenDotaNotFoundError("missing")
    fresh_validation_error = fresh_module.ValidationError("bad input")

    assert stale_rate_limit_cls is not fresh_module.OpenDotaRateLimitError
    assert stale_not_found_cls is not fresh_module.OpenDotaNotFoundError
    assert stale_validation_cls is not fresh_module.ValidationError

    assert is_opendota_rate_limit_error(fresh_rate_limit_error)
    assert is_opendota_error(fresh_rate_limit_error)
    assert is_opendota_not_found_error(fresh_not_found_error)
    assert is_opendota_error(fresh_not_found_error)
    assert is_validation_error(fresh_validation_error)
    assert is_opendota_error(fresh_validation_error)
