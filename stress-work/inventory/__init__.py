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
    StorageError,
    ValidationError,
)
from .migrations import LATEST_VERSION, MIGRATIONS, Migration, plan_migrations
from .models import Location, Product, SKU, StockLevel
from .storage import SQLiteStore
from .warehouse import Movement, Warehouse

__all__ = [
    "Warehouse",
    "Movement",
    "Product",
    "SKU",
    "Location",
    "StockLevel",
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
    "StorageError",
]

__version__ = "2.0.0"
