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
    SalesOrderError,
    StorageError,
    ValidationError,
)
from .migrations import LATEST_VERSION, MIGRATIONS, Migration, plan_migrations
from .models import (
    ORDER_CANCELLED,
    ORDER_OPEN,
    ORDER_PARTIAL,
    ORDER_RECEIVED,
    SALES_ALLOCATED,
    SALES_CANCELLED,
    SALES_FULFILLED,
    SALES_OPEN,
    SALES_PARTIAL,
    Location,
    Product,
    PurchaseOrder,
    PurchaseOrderLine,
    SKU,
    SalesOrder,
    SalesOrderLine,
    StockLevel,
)
from .storage import SQLiteStore
from .warehouse import Movement, Warehouse, synchronized

__all__ = [
    "Warehouse",
    "Movement",
    "synchronized",
    "Product",
    "SKU",
    "Location",
    "StockLevel",
    "PurchaseOrder",
    "PurchaseOrderLine",
    "SalesOrder",
    "SalesOrderLine",
    "ORDER_OPEN",
    "ORDER_PARTIAL",
    "ORDER_RECEIVED",
    "ORDER_CANCELLED",
    "SALES_OPEN",
    "SALES_PARTIAL",
    "SALES_ALLOCATED",
    "SALES_FULFILLED",
    "SALES_CANCELLED",
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
    "SalesOrderError",
    "StorageError",
]

__version__ = "4.0.0"
