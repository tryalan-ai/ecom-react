"""A dependency-free warehouse inventory system.

Public API::

    from inventory import Warehouse, Product, SKU, Location

The package uses only the Python standard library.
"""

from .errors import (
    CapacityExceeded,
    DuplicateEntity,
    InsufficientStock,
    InventoryError,
    NotFound,
    ValidationError,
)
from .models import Location, Product, SKU, StockLevel
from .warehouse import Movement, Warehouse

__all__ = [
    "Warehouse",
    "Movement",
    "Product",
    "SKU",
    "Location",
    "StockLevel",
    "InventoryError",
    "ValidationError",
    "DuplicateEntity",
    "NotFound",
    "InsufficientStock",
    "CapacityExceeded",
]

__version__ = "1.0.0"
