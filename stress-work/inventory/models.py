"""Immutable-ish domain models for a warehouse inventory system.

The models are deliberately dependency free: only the standard library is
used.  ``Product``, ``SKU`` and ``Location`` are frozen value objects so they
can be used as dictionary keys and shared safely.  ``StockLevel`` is the one
mutable model, because on-hand quantities change constantly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple

from .errors import (
    InsufficientStock,
    NotFound,
    PurchaseOrderError,
    SalesOrderError,
    ValidationError,
)

__all__ = [
    "Product",
    "SKU",
    "Location",
    "StockLevel",
    "PurchaseOrderLine",
    "PurchaseOrder",
    "SalesOrderLine",
    "SalesOrder",
    "ORDER_OPEN",
    "ORDER_PARTIAL",
    "ORDER_RECEIVED",
    "ORDER_CANCELLED",
    "SALES_OPEN",
    "SALES_PARTIAL",
    "SALES_ALLOCATED",
    "SALES_FULFILLED",
    "SALES_CANCELLED",
]


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

    def ship(self, units: int) -> None:
        """Consume a reservation and take ``units`` off the shelf.

        Shipping is the only operation that may touch reserved stock: it
        decrements ``quantity`` and ``reserved`` together, so a reservation is
        spent exactly once.
        """
        units = _require_positive(units, "units")
        if units > self.reserved:
            raise InsufficientStock(
                f"cannot ship {units} of {self.sku.code} at {self.location.code}: "
                f"only {self.reserved} reserved"
            )
        self.quantity -= units
        self.reserved -= units

    def copy(self) -> "StockLevel":
        """A detached duplicate of this record, used for transaction snapshots."""
        return StockLevel(
            sku=self.sku,
            location=self.location,
            quantity=self.quantity,
            reserved=self.reserved,
            reorder_point=self.reorder_point,
        )

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.sku.code}@{self.location.code}={self.quantity}({self.reserved} reserved)"


# Purchase order lifecycle states.  An order's status is always derived from
# its lines and its cancellation flag, never stored, so the two cannot drift.
ORDER_OPEN = "open"
ORDER_PARTIAL = "partial"
ORDER_RECEIVED = "received"
ORDER_CANCELLED = "cancelled"

PURCHASE_ORDER_STATES: Tuple[str, ...] = (
    ORDER_OPEN,
    ORDER_PARTIAL,
    ORDER_RECEIVED,
    ORDER_CANCELLED,
)


@dataclass
class PurchaseOrderLine:
    """One SKU bought from a supplier, and the bin it should land in."""

    sku: SKU
    location: Location
    ordered_units: int
    received_units: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.sku, SKU):
            raise ValidationError("sku must be a SKU instance")
        if not isinstance(self.location, Location):
            raise ValidationError("location must be a Location instance")
        self.ordered_units = _require_positive(self.ordered_units, "ordered_units")
        self.received_units = _require_non_negative(self.received_units, "received_units")
        if self.received_units > self.ordered_units:
            raise ValidationError("received_units cannot exceed ordered_units")

    @property
    def outstanding(self) -> int:
        """Units still awaited on this line."""
        return self.ordered_units - self.received_units

    @property
    def is_complete(self) -> bool:
        """Return ``True`` once the whole ordered quantity has been booked in."""
        return self.received_units == self.ordered_units

    def receive(self, units: int) -> None:
        """Book ``units`` against this line, refusing to over-receive."""
        units = _require_positive(units, "units")
        if units > self.outstanding:
            raise PurchaseOrderError(
                f"cannot receive {units} of {self.sku.code}: "
                f"only {self.outstanding} outstanding on this line"
            )
        self.received_units += units

    def copy(self) -> "PurchaseOrderLine":
        """A detached duplicate, used for transaction snapshots."""
        return PurchaseOrderLine(
            sku=self.sku,
            location=self.location,
            ordered_units=self.ordered_units,
            received_units=self.received_units,
        )


@dataclass
class PurchaseOrder:
    """What a supplier owes us, and how much of it has arrived.

    ``cancelled`` is settable at construction only so a persisted or cloned
    order can be rebuilt; use :meth:`Warehouse.cancel_purchase_order` to
    cancel one.  ``status`` is derived from ``cancelled`` and the lines.
    """

    reference: str
    supplier: str
    lines: List[PurchaseOrderLine]
    cancelled: bool = False
    created_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        self.reference = _require_text(self.reference, "reference")
        self.supplier = _require_text(self.supplier, "supplier")
        if not isinstance(self.cancelled, bool):
            raise ValidationError("cancelled must be a bool")

        lines = list(self.lines)
        if not lines:
            raise ValidationError("a purchase order needs at least one line")
        seen = set()
        for line in lines:
            if not isinstance(line, PurchaseOrderLine):
                raise ValidationError("lines must contain PurchaseOrderLine instances")
            if line.sku.code in seen:
                raise ValidationError(
                    f"purchase order {self.reference!r} has two lines for "
                    f"sku {line.sku.code!r}; order each SKU on one line"
                )
            seen.add(line.sku.code)
        self.lines = lines

        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        elif not isinstance(self.created_at, datetime):
            raise ValidationError("created_at must be a datetime")

    @property
    def line_keys(self) -> Tuple[str, ...]:
        """The SKU code of every line, in order."""
        return tuple(line.sku.code for line in self.lines)

    @property
    def ordered_units(self) -> int:
        return sum(line.ordered_units for line in self.lines)

    @property
    def received_units(self) -> int:
        return sum(line.received_units for line in self.lines)

    @property
    def outstanding_units(self) -> int:
        return sum(line.outstanding for line in self.lines)

    @property
    def is_fully_received(self) -> bool:
        return all(line.is_complete for line in self.lines)

    @property
    def status(self) -> str:
        """One of ``open``, ``partial``, ``received`` or ``cancelled``."""
        if self.cancelled:
            return ORDER_CANCELLED
        if self.is_fully_received:
            return ORDER_RECEIVED
        if self.received_units:
            return ORDER_PARTIAL
        return ORDER_OPEN

    def line(self, sku_code: str) -> PurchaseOrderLine:
        """The line for ``sku_code``; raises :class:`NotFound` if absent."""
        for line in self.lines:
            if line.sku.code == sku_code:
                return line
        raise NotFound(
            f"purchase order {self.reference!r} has no line for sku {sku_code!r}"
        )

    def copy(self) -> "PurchaseOrder":
        """A detached duplicate, used for transaction snapshots."""
        return PurchaseOrder(
            reference=self.reference,
            supplier=self.supplier,
            lines=[line.copy() for line in self.lines],
            cancelled=self.cancelled,
            created_at=self.created_at,
        )

    def __str__(self) -> str:  # pragma: no cover - trivial
        return (
            f"{self.reference} ({self.supplier}) {self.status} "
            f"{self.received_units}/{self.ordered_units}"
        )


# Sales order lifecycle states, derived the same way as purchase orders.
SALES_OPEN = "open"
SALES_PARTIAL = "partial"
SALES_ALLOCATED = "allocated"
SALES_FULFILLED = "fulfilled"
SALES_CANCELLED = "cancelled"

SALES_ORDER_STATES: Tuple[str, ...] = (
    SALES_OPEN,
    SALES_PARTIAL,
    SALES_ALLOCATED,
    SALES_FULFILLED,
    SALES_CANCELLED,
)


@dataclass
class SalesOrderLine:
    """One SKU promised to a customer, and the bin it should ship from.

    ``reserved_units`` is a *live* claim on stock: it goes down when units ship
    or when the order is cancelled, and it is exactly the quantity held aside so
    no other order can promise the same units.  ``shipped_units`` is cumulative.
    """

    sku: SKU
    location: Location
    ordered_units: int
    reserved_units: int = 0
    shipped_units: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.sku, SKU):
            raise ValidationError("sku must be a SKU instance")
        if not isinstance(self.location, Location):
            raise ValidationError("location must be a Location instance")
        self.ordered_units = _require_positive(self.ordered_units, "ordered_units")
        self.reserved_units = _require_non_negative(self.reserved_units, "reserved_units")
        self.shipped_units = _require_non_negative(self.shipped_units, "shipped_units")
        if self.reserved_units + self.shipped_units > self.ordered_units:
            raise ValidationError(
                "reserved_units plus shipped_units cannot exceed ordered_units"
            )

    @property
    def unallocated(self) -> int:
        """Units on this line that no reservation covers yet."""
        return self.ordered_units - self.reserved_units - self.shipped_units

    @property
    def unshipped(self) -> int:
        """Reserved units still sitting in the bin."""
        return self.reserved_units

    @property
    def is_allocated(self) -> bool:
        return self.unallocated == 0

    @property
    def is_fulfilled(self) -> bool:
        return self.shipped_units == self.ordered_units

    def allocate(self, units: int) -> None:
        """Claim ``units`` of stock for this line."""
        units = _require_positive(units, "units")
        if units > self.unallocated:
            raise SalesOrderError(
                f"cannot allocate {units} of {self.sku.code}: "
                f"only {self.unallocated} unallocated on this line"
            )
        self.reserved_units += units

    def release(self, units: int) -> None:
        """Give up ``units`` of this line's claim without shipping them."""
        units = _require_positive(units, "units")
        if units > self.reserved_units:
            raise SalesOrderError(
                f"cannot release {units} of {self.sku.code}: "
                f"only {self.reserved_units} reserved on this line"
            )
        self.reserved_units -= units

    def ship(self, units: int) -> None:
        """Turn ``units`` of this line's claim into a shipment."""
        units = _require_positive(units, "units")
        if units > self.reserved_units:
            raise SalesOrderError(
                f"cannot ship {units} of {self.sku.code}: "
                f"only {self.reserved_units} reserved on this line"
            )
        self.reserved_units -= units
        self.shipped_units += units

    def copy(self) -> "SalesOrderLine":
        """A detached duplicate, used for transaction snapshots."""
        return SalesOrderLine(
            sku=self.sku,
            location=self.location,
            ordered_units=self.ordered_units,
            reserved_units=self.reserved_units,
            shipped_units=self.shipped_units,
        )


@dataclass
class SalesOrder:
    """What we owe a customer, and how much of it has been claimed and shipped.

    An order that has been allocated holds real reservations against
    :class:`StockLevel` records, so the same units cannot be promised to a
    second order.  ``status`` is derived from the lines and ``cancelled``.
    """

    reference: str
    customer: str
    lines: List[SalesOrderLine]
    cancelled: bool = False
    created_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        self.reference = _require_text(self.reference, "reference")
        self.customer = _require_text(self.customer, "customer")
        if not isinstance(self.cancelled, bool):
            raise ValidationError("cancelled must be a bool")

        lines = list(self.lines)
        if not lines:
            raise ValidationError("a sales order needs at least one line")
        seen = set()
        for line in lines:
            if not isinstance(line, SalesOrderLine):
                raise ValidationError("lines must contain SalesOrderLine instances")
            if line.sku.code in seen:
                raise ValidationError(
                    f"sales order {self.reference!r} has two lines for "
                    f"sku {line.sku.code!r}; order each SKU on one line"
                )
            seen.add(line.sku.code)
        self.lines = lines

        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        elif not isinstance(self.created_at, datetime):
            raise ValidationError("created_at must be a datetime")

    @property
    def line_keys(self) -> Tuple[str, ...]:
        """The SKU code of every line, in order."""
        return tuple(line.sku.code for line in self.lines)

    @property
    def ordered_units(self) -> int:
        return sum(line.ordered_units for line in self.lines)

    @property
    def reserved_units(self) -> int:
        """Units currently held aside on stock records for this order."""
        return sum(line.reserved_units for line in self.lines)

    @property
    def shipped_units(self) -> int:
        return sum(line.shipped_units for line in self.lines)

    @property
    def unallocated_units(self) -> int:
        return sum(line.unallocated for line in self.lines)

    @property
    def is_fully_allocated(self) -> bool:
        return all(line.is_allocated for line in self.lines)

    @property
    def is_fulfilled(self) -> bool:
        return all(line.is_fulfilled for line in self.lines)

    @property
    def locations(self) -> Tuple[Location, ...]:
        """The distinct bins this order ships from, in line order."""
        seen: List[Location] = []
        for line in self.lines:
            if all(existing.code != line.location.code for existing in seen):
                seen.append(line.location)
        return tuple(seen)

    @property
    def status(self) -> str:
        """One of ``open``, ``partial``, ``allocated``, ``fulfilled``, ``cancelled``."""
        if self.cancelled:
            return SALES_CANCELLED
        if self.is_fulfilled:
            return SALES_FULFILLED
        if self.shipped_units:
            return SALES_PARTIAL
        if self.is_fully_allocated:
            return SALES_ALLOCATED
        if self.reserved_units:
            return SALES_PARTIAL
        return SALES_OPEN

    def line(self, sku_code: str) -> SalesOrderLine:
        """The line for ``sku_code``; raises :class:`NotFound` if absent."""
        for line in self.lines:
            if line.sku.code == sku_code:
                return line
        raise NotFound(f"sales order {self.reference!r} has no line for sku {sku_code!r}")

    def copy(self) -> "SalesOrder":
        """A detached duplicate, used for transaction snapshots."""
        return SalesOrder(
            reference=self.reference,
            customer=self.customer,
            lines=[line.copy() for line in self.lines],
            cancelled=self.cancelled,
            created_at=self.created_at,
        )

    def __str__(self) -> str:  # pragma: no cover - trivial
        return (
            f"{self.reference} ({self.customer}) {self.status} "
            f"reserved={self.reserved_units} shipped={self.shipped_units}"
            f"/{self.ordered_units}"
        )
