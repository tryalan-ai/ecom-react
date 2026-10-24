"""Exception hierarchy for the warehouse inventory system.

Every error raised by :mod:`inventory` derives from :class:`InventoryError`,
so callers can catch the whole family with a single ``except`` clause while
still being able to distinguish the individual failure modes.
"""


class InventoryError(Exception):
    """Base class for all inventory errors."""


class ValidationError(InventoryError):
    """Raised when a model is constructed with invalid data."""


class DuplicateEntity(InventoryError):
    """Raised when registering an entity whose identifier already exists."""


class NotFound(InventoryError):
    """Raised when a referenced entity or stock record does not exist."""


class InsufficientStock(InventoryError):
    """Raised when an operation would drive a quantity below zero."""


class CapacityExceeded(InventoryError):
    """Raised when a location cannot physically hold any more units."""
