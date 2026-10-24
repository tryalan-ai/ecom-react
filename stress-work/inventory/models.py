"""Immutable-ish domain models for a warehouse inventory system.

The models are deliberately dependency free: only the standard library is
used.  ``Product``, ``SKU`` and ``Location`` are frozen value objects so they
can be used as dictionary keys and shared safely.  ``StockLevel`` is the one
mutable model, because on-hand quantities change constantly.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from .errors import InsufficientStock, ValidationError

__all__ = ["Product", "SKU", "Location", "StockLevel"]


def _require_text(value: object, field_name: str) -> str:
    """Return ``value`` stripped, or raise if it is not a non-empty string."""
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string, got {type(value).__name__}")
    stripped = value.strip()
    if not stripped:
        raise ValidationError(f"{field_name} must be a non-empty string")
    return stripped


def _require_integer(value: object, field_name: str) -> int:
    """Return ``value`` if it is a real integer (``bool`` excluded)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field_name} must be an integer, got {type(value).__name__}")
    return value


def _require_positive(value: object, field_name: str) -> int:
    """Return ``value`` if it is an integer greater than zero."""
    number = _require_integer(value, field_name)
    if number <= 0:
        raise ValidationError(f"{field_name} must be greater than zero, got {number}")
    return number


def _require_non_negative(value: object, field_name: str) -> int:
    """Return ``value`` if it is an integer greater than or equal to zero."""
    number = _require_integer(value, field_name)
    if number < 0:
        raise ValidationError(f"{field_name} must not be negative, got {number}")
    return number


def _require_decimal(value: object, field_name: str) -> Decimal:
    """Return ``value`` coerced to a non-negative ``Decimal``."""
    if isinstance(value, Decimal):
        price = value
    elif isinstance(value, bool):
        raise ValidationError(f"{field_name} must be a number, got bool")
    elif isinstance(value, (int, float, str)):
        try:
            price = Decimal(str(value))
        except InvalidOperation as exc:  # pragma: no cover - defensive
            raise ValidationError(f"{field_name} must be a number, got {value!r}") from exc
    else:
        raise ValidationError(f"{field_name} must be a number, got {type(value).__name__}")
    if not price.is_finite():
        raise ValidationError(f"{field_name} must be finite, got {value!r}")
    if price < 0:
        raise ValidationError(f"{field_name} must not be negative, got {price}")
    return price


@dataclass(frozen=True)
class Product:
    """A product that the warehouse may hold.

    ``unit_price`` is stored as a :class:`~decimal.Decimal` rounded to two
    decimal places so that money arithmetic never drifts.
    """

    product_id: str
    name: str
    unit_price: Decimal = Decimal("0.00")
    category: str = "uncategorized"

    def __post_init__(self) -> None:
        object.__setattr__(self, "product_id", _require_text(self.product_id, "product_id"))
        object.__setattr__(self, "name", _require_text(self.name, "name"))
        object.__setattr__(self, "category", _require_text(self.category, "category"))
        price = _require_decimal(self.unit_price, "unit_price")
        object.__setattr__(self, "unit_price", price.quantize(Decimal("0.01")))

    @property
    def is_free(self) -> bool:
        """Return ``True`` when the product costs nothing."""
        return self.unit_price == Decimal("0.00")


@dataclass(frozen=True)
class SKU:
    """A stock keeping unit: the smallest tracked unit of a :class:`Product`."""

    code: str
    product: Product
    unit_of_measure: str = "each"
    barcode: Optional[str] = None
    pack_size: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _require_text(self.code, "code"))
        if not isinstance(self.product, Product):
            raise ValidationError("product must be a Product instance")
        object.__setattr__(
            self, "unit_of_measure", _require_text(self.unit_of_measure, "unit_of_measure")
        )
        if self.barcode is not None:
            object.__setattr__(self, "barcode", _require_text(self.barcode, "barcode"))
        object.__setattr__(self, "pack_size", _require_positive(self.pack_size, "pack_size"))

    @property
    def is_scannable(self) -> bool:
        """Return ``True`` when the SKU carries a barcode."""
        return self.barcode is not None


@dataclass(frozen=True)
class Location:
    """A physical storage location, such as a bin, shelf or aisle."""

    code: str
    name: str
    zone: str = "default"
    capacity: Optional[int] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _require_text(self.code, "code"))
        object.__setattr__(self, "name", _require_text(self.name, "name"))
        object.__setattr__(self, "zone", _require_text(self.zone, "zone"))
        if self.capacity is not None:
            object.__setattr__(self, "capacity", _require_positive(self.capacity, "capacity"))

    @property
    def is_bounded(self) -> bool:
        """Return ``True`` when the location declares a finite capacity."""
        return self.capacity is not None


@dataclass
class StockLevel:
    """How many units of one SKU sit at one location.

    ``quantity`` is the physical on-hand count; ``reserved`` is the part of it
    already promised to open orders.  ``available`` is the difference, which is
    what new work may consume.

    A ``reorder_point`` of zero means "no reorder threshold configured", in
    which case :attr:`is_low` is always ``False``.
    """

    sku: SKU
    location: Location
    quantity: int = 0
    reserved: int = 0
    reorder_point: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.sku, SKU):
            raise ValidationError("sku must be a SKU instance")
        if not isinstance(self.location, Location):
            raise ValidationError("location must be a Location instance")
        self.quantity = _require_non_negative(self.quantity, "quantity")
        self.reserved = _require_non_negative(self.reserved, "reserved")
        self.reorder_point = _require_non_negative(self.reorder_point, "reorder_point")
        if self.reserved > self.quantity:
            raise ValidationError("reserved cannot exceed quantity")

    @property
    def available(self) -> int:
        """Units that are on hand and not yet reserved."""
        return self.quantity - self.reserved

    @property
    def is_empty(self) -> bool:
        """Return ``True`` when nothing is physically on hand."""
        return self.quantity == 0

    @property
    def is_low(self) -> bool:
        """Return ``True`` when available stock has hit the reorder point."""
        return self.reorder_point > 0 and self.available <= self.reorder_point

    def reserve(self, units: int) -> None:
        """Promised ``units`` to open orders."""
        units = _require_positive(units, "units")
        if units > self.available:
            raise InsufficientStock(
                f"cannot reserve {units} of {self.sku.code} at {self.location.code}: "
                f"only {self.available} available"
            )
        self.reserved += units

    def release(self, units: int) -> None:
        """Return previously reserved ``units`` to availability."""
        units = _require_positive(units, "units")
        if units > self.reserved:
            raise InsufficientStock(
                f"cannot release {units} of {self.sku.code} at {self.location.code}: "
                f"only {self.reserved} reserved"
            )
        self.reserved -= units

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.sku.code}@{self.location.code}={self.quantity}({self.reserved} reserved)"
