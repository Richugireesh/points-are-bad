"""Domain exception hierarchy for points-are-bad.

All package-specific errors derive from :class:`PointsAreBadError` so callers
can catch the base class when they want to handle any application error, or
catch a specific subclass for fine-grained handling.
"""

from __future__ import annotations

__all__ = [
    "ApiError",
    "DataValidationError",
    "PointsAreBadError",
    "StorageError",
]


class PointsAreBadError(Exception):
    """Base class for all points-are-bad errors."""


class ApiError(PointsAreBadError):
    """Raised when an external API call fails unrecoverably.

    Note: most API failures are handled gracefully (returning ``None``); this
    exception is reserved for programming errors or unexpected state that the
    caller must handle explicitly.
    """


class StorageError(PointsAreBadError):
    """Raised when reading from or writing to the data file fails."""


class DataValidationError(PointsAreBadError):
    """Raised when loaded data does not conform to the expected schema."""
