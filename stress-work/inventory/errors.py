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


class MigrationError(InventoryError):
    """Raised when a migration set is malformed, e.g. duplicate versions."""


class PurchaseOrderError(InventoryError):
    """Raised when a purchase-order operation is invalid for the order's state.

    Over-receiving, receiving against a cancelled or completed order, and
    cancelling an order that already has receipts all land here.
    """


class SalesOrderError(InventoryError):
    """Raised when a sales-order operation is invalid for the order's state.

    Allocating or shipping against a cancelled or fulfilled order, shipping
    stock that was never reserved, and cancelling an order that has already
    shipped all land here.  A request for more stock than is *available*
    raises :class:`InsufficientStock` instead.
    """


class AuditLogError(InventoryError):
    """Raised when the movement log is treated as mutable, or cannot be replayed.

    Appending is always allowed; editing, reordering or removing committed
    entries is not.  Replaying raises this too, for an unknown movement kind or
    a log that describes impossible stock.
    """


class StorageError(InventoryError):
    """Raised when the SQLite persistence layer cannot satisfy a request."""
