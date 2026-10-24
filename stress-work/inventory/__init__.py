"""A dependency-free warehouse inventory system.

Public API::

    from inventory import Warehouse, Product, SKU, Location
    from inventory import SQLiteStore, MIGRATIONS

The package uses only the Python standard library.
"""

from .errors import (
    CapacityExceeded,
    DuplicateEntity,
    InsufficientStock,
    InventoryError,
    MigrationError,
    NotFound,
    PurchaseOrderError,
    StorageError,
    ValidationError,
)
from .migrations import LATEST_VERSION, MIGRATIONS, Migration, plan_migrations
from .models import (
    ORDER_CANCELLED,
    ORDER_OPEN,
    ORDER_PARTIAL,
    ORDER_RECEIVED,
    Location,
    Product,
    PurchaseOrder,
    PurchaseOrderLine,
    SKU,
    StockLevel,
)
from .storage import SQLiteStore
from .warehouse import Movement, Warehouse

__all__ = [
    "Warehouse",
    "Movement",
    "Product",
    "SKU",
    "Location",
    "StockLevel",
    "PurchaseOrder",
    "PurchaseOrderLine",
    "ORDER_OPEN",
    "ORDER_PARTIAL",
    "ORDER_RECEIVED",
    "ORDER_CANCELLED",
    "SQLiteStore",
    "Migration",
    "MIGRATIONS",
    "LATEST_VERSION",
    "plan_migrations",
    "InventoryError",
    "ValidationError",
    "DuplicateEntity",
    "NotFound",
    "InsufficientStock",
    "CapacityExceeded",
    "MigrationError",
    "PurchaseOrderError",
    "StorageError",
]

__version__ = "3.0.0"
