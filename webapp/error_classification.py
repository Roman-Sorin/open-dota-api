from __future__ import annotations


def _has_exception_name(exc: BaseException, *names: str) -> bool:
    return any(cls.__name__ in names for cls in type(exc).__mro__)


def is_opendota_not_found_error(exc: BaseException) -> bool:
    return _has_exception_name(exc, "OpenDotaNotFoundError")


def is_opendota_rate_limit_error(exc: BaseException) -> bool:
    return _has_exception_name(exc, "OpenDotaRateLimitError")


def is_validation_error(exc: BaseException) -> bool:
    return _has_exception_name(exc, "ValidationError")


def is_opendota_error(exc: BaseException) -> bool:
    return _has_exception_name(
        exc,
        "OpenDotaError",
        "OpenDotaRateLimitError",
        "OpenDotaNotFoundError",
        "ValidationError",
    )
