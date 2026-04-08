class OpenDotaError(Exception):
    """Base exception for OpenDota client and service failures."""


class OpenDotaRateLimitError(OpenDotaError):
    """Raised when API rate limits the request."""


class OpenDotaNotFoundError(OpenDotaError):
    """Raised when requested entity is missing."""


class ValidationError(OpenDotaError):
    """Raised for user input validation issues."""


class StratzError(Exception):
    """Base exception for STRATZ client and enrichment failures."""


class StratzRateLimitError(StratzError):
    """Raised when STRATZ rate limits the request."""
