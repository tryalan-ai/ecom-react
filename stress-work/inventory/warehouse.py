"""The ``Warehouse`` service: registration, stock movements and reporting.

The warehouse owns every entity it is told about and every stock record it
creates, which lets it enforce cross-model invariants that a single model
cannot check on its own (for example: an SKU must belong to a registered
product, and a location may never hold more units than its capacity).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from .errors import CapacityExceeded, DuplicateEntity, InsufficientStock, NotFound, ValidationError
from .models import Location, Product, SKU, StockLevel

__all__ = ["Movement", "Warehouse"]


@dataclass(frozen=True)
class Movement:
    """An immutable audit-log entry describing one change to stock."""

    kind: str
    sku_code: str
    location_code: str
    units: int
    reference: Optional[str] = None
    recorded_at: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.recorded_at is None:
            object.__setattr__(self, "recorded_at", datetime.now(timezone.utc))


class Warehouse:
    """A registry of products, SKUs, locations and their stock levels."""

    def __init__(self, name: str = "warehouse") -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValidationError("name must be a non-empty string")
        self.name = name.strip()
        self._products: Dict[str, Product] = {}
        self._skus: Dict[str, SKU] = {}
        self._locations: Dict[str, Location] = {}
        self._stock: Dict[Tuple[str, str], StockLevel] = {}
        self._reorder_defaults: Dict[str, int] = {}
        self._movements: List[Movement] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def add_product(self, product: Product) -> Product:
        """Register ``product``; raise :class:`DuplicateEntity` if seen before."""
        if not isinstance(product, Product):
            raise ValidationError("product must be a Product instance")
        if product.product_id in self._products:
            raise DuplicateEntity(f"product {product.product_id!r} is already registered")
        self._products[product.product_id] = product
        return product

    def add_sku(self, sku: SKU) -> SKU:
        """Register ``sku``; its product must already be registered."""
        if not isinstance(sku, SKU):
            raise ValidationError("sku must be a SKU instance")
        if sku.code in self._skus:
            raise DuplicateEntity(f"sku {sku.code!r} is already registered")
        if sku.product.product_id not in self._products:
            raise NotFound(
                f"cannot register sku {sku.code!r}: product "
                f"{sku.product.product_id!r} is not registered"
            )
        self._skus[sku.code] = sku
        return sku

    def add_location(self, location: Location) -> Location:
        """Register ``location``; raise :class:`DuplicateEntity` if seen before."""
        if not isinstance(location, Location):
            raise ValidationError("location must be a Location instance")
        if location.code in self._locations:
            raise DuplicateEntity(f"location {location.code!r} is already registered")
        self._locations[location.code] = location
        return location

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    @property
    def products(self) -> List[Product]:
        return list(self._products.values())

    @property
    def skus(self) -> List[SKU]:
        return list(self._skus.values())

    @property
    def locations(self) -> List[Location]:
        return list(self._locations.values())

    @property
    def movements(self) -> List[Movement]:
        """The audit log, oldest first."""
        return list(self._movements)

    @property
    def stock_levels(self) -> List[StockLevel]:
        """Every stock record, ordered by SKU code then location code."""
        return sorted(
            self._stock.values(),
            key=lambda record: (record.sku.code, record.location.code),
        )

    def product(self, product_id: str) -> Product:
        try:
            return self._products[product_id]
        except KeyError as exc:
            raise NotFound(f"no product with id {product_id!r}") from exc

    def sku(self, code: str) -> SKU:
        try:
            return self._skus[code]
        except KeyError as exc:
            raise NotFound(f"no sku with code {code!r}") from exc

    def location(self, code: str) -> Location:
        try:
            return self._locations[code]
        except KeyError as exc:
            raise NotFound(f"no location with code {code!r}") from exc

    def stock(self, sku_code: str, location_code: str) -> StockLevel:
        """Return the existing stock record for a SKU/location pair."""
        try:
            return self._stock[(sku_code, location_code)]
        except KeyError as exc:
            raise NotFound(
                f"no stock record for sku {sku_code!r} at location {location_code!r}"
            ) from exc

    def has_stock_record(self, sku_code: str, location_code: str) -> bool:
        return (sku_code, location_code) in self._stock

    def location_occupancy(self, location_code: str) -> int:
        """Total units held at ``location_code`` across every SKU."""
        self.location(location_code)  # raises NotFound for unknown locations
        return sum(
            record.quantity
            for (sku_code, code), record in self._stock.items()
            if code == location_code
        )

    def on_hand(self, sku_code: str) -> int:
        """Total quantity of ``sku_code`` across every location."""
        self.sku(sku_code)  # raises NotFound for unknown SKUs
        return sum(
            record.quantity for (code, _), record in self._stock.items() if code == sku_code
        )

    def available(self, sku_code: str) -> int:
        """Total unreserved quantity of ``sku_code`` across every location."""
        self.sku(sku_code)
        return sum(
            record.available for (code, _), record in self._stock.items() if code == sku_code
        )

    # ------------------------------------------------------------------
    # Movements
    # ------------------------------------------------------------------
    def receive(
        self,
        sku_code: str,
        location_code: str,
        units: int,
        reference: Optional[str] = None,
    ) -> StockLevel:
        """Add ``units`` of a SKU to a location, creating the record if needed."""
        units = _positive(units)
        self.sku(sku_code)
        location = self.location(location_code)
        self._check_capacity(location, units)
        record = self._record(sku_code, location_code)
        record.quantity += units
        self._log("receive", sku_code, location_code, units, reference)
        return record

    def pick(
        self,
        sku_code: str,
        location_code: str,
        units: int,
        reference: Optional[str] = None,
    ) -> StockLevel:
        """Remove ``units`` from on-hand stock, refusing to touch reserved units."""
        units = _positive(units)
        record = self.stock(sku_code, location_code)
        if units > record.available:
            raise InsufficientStock(
                f"cannot pick {units} of {sku_code} at {location_code}: "
                f"only {record.available} available"
            )
        record.quantity -= units
        self._log("pick", sku_code, location_code, units, reference)
        return record

    def reserve(
        self,
        sku_code: str,
        location_code: str,
        units: int,
        reference: Optional[str] = None,
    ) -> StockLevel:
        """Reserve ``units`` against open orders."""
        units = _positive(units)
        record = self.stock(sku_code, location_code)
        record.reserve(units)
        self._log("reserve", sku_code, location_code, units, reference)
        return record

    def release(
        self,
        sku_code: str,
        location_code: str,
        units: int,
        reference: Optional[str] = None,
    ) -> StockLevel:
        """Release previously reserved ``units``."""
        units = _positive(units)
        record = self.stock(sku_code, location_code)
        record.release(units)
        self._log("release", sku_code, location_code, units, reference)
        return record

    def transfer(
        self,
        sku_code: str,
        from_code: str,
        to_code: str,
        units: int,
        reference: Optional[str] = None,
    ) -> Tuple[StockLevel, StockLevel]:
        """Move available stock between two locations."""
        units = _positive(units)
        if from_code == to_code:
            raise ValidationError("source and destination locations must differ")
        source = self.stock(sku_code, from_code)
        destination_location = self.location(to_code)
        if units > source.available:
            raise InsufficientStock(
                f"cannot transfer {units} of {sku_code} from {from_code}: "
                f"only {source.available} available"
            )
        self._check_capacity(destination_location, units)
        destination = self._record(sku_code, to_code)
        source.quantity -= units
        destination.quantity += units
        self._log("transfer-out", sku_code, from_code, units, reference)
        self._log("transfer-in", sku_code, to_code, units, reference)
        return source, destination

    def adjust(
        self,
        sku_code: str,
        location_code: str,
        counted_units: int,
        reference: Optional[str] = None,
    ) -> StockLevel:
        """Set on-hand stock to a stocktake ``counted_units`` value."""
        if isinstance(counted_units, bool) or not isinstance(counted_units, int):
            raise ValidationError("counted_units must be an integer")
        if counted_units < 0:
            raise ValidationError("counted_units must not be negative")
        self.sku(sku_code)
        location = self.location(location_code)
        record = self._record(sku_code, location_code)
        if counted_units < record.reserved:
            raise InsufficientStock(
                f"cannot adjust {sku_code} at {location_code} to {counted_units}: "
                f"{record.reserved} units are reserved"
            )
        delta = counted_units - record.quantity
        self._check_capacity(location, delta)
        record.quantity = counted_units
        self._log("adjust", sku_code, location_code, delta, reference)
        return record

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    def set_reorder_point(self, sku_code: str, units: int) -> List[StockLevel]:
        """Apply a reorder threshold to a SKU, present and future records."""
        if isinstance(units, bool) or not isinstance(units, int):
            raise ValidationError("units must be an integer")
        if units < 0:
            raise ValidationError("units must not be negative")
        self.sku(sku_code)
        self._reorder_defaults[sku_code] = units
        touched = [record for (code, _), record in self._stock.items() if code == sku_code]
        for record in touched:
            record.reorder_point = units
        return touched

    def low_stock(self) -> List[StockLevel]:
        """Every stock record whose available quantity has hit its threshold."""
        return [record for record in self._stock.values() if record.is_low]

    def reorder_point(self, sku_code: str) -> int:
        """The configured reorder threshold for a SKU (``0`` when unset)."""
        self.sku(sku_code)
        return self._reorder_defaults.get(sku_code, 0)

    def records_for(self, sku_code: str) -> List[StockLevel]:
        """Every stock record held for a SKU, ordered by location code."""
        self.sku(sku_code)
        return sorted(
            (record for (code, _), record in self._stock.items() if code == sku_code),
            key=lambda record: record.location.code,
        )

    # ------------------------------------------------------------------
    # Rehydration
    # ------------------------------------------------------------------
    def restore(
        self,
        *,
        stock_levels: Iterable[StockLevel] = (),
        movements: Iterable[Movement] = (),
        reorder_points: Optional[Mapping[str, int]] = None,
    ) -> None:
        """Load persisted state into a warehouse whose catalog is registered.

        This is the seam a repository uses to rebuild the aggregate without
        replaying (and therefore duplicating) its movement history.  The
        catalog -- products, SKUs and locations -- must already be registered
        and is validated against, never replaced.

        The whole snapshot is validated before any state is mutated, and
        restoring onto a warehouse that already holds stock or movements
        raises :class:`ValidationError` so halves of two snapshots cannot be
        silently merged.
        """
        if self._stock or self._movements:
            raise ValidationError(
                "cannot restore into a warehouse that already holds stock or movements"
            )

        defaults: Dict[str, int] = {}
        for sku_code, units in (reorder_points or {}).items():
            if sku_code not in self._skus:
                raise NotFound(f"cannot restore reorder point: no sku {sku_code!r}")
            if isinstance(units, bool) or not isinstance(units, int) or units < 0:
                raise ValidationError(
                    f"reorder point for {sku_code!r} must be a non-negative integer"
                )
            defaults[sku_code] = units

        pending: Dict[Tuple[str, str], StockLevel] = {}
        for record in stock_levels:
            if not isinstance(record, StockLevel):
                raise ValidationError("stock_levels must contain StockLevel instances")
            if record.sku.code not in self._skus:
                raise NotFound(f"cannot restore stock: no sku {record.sku.code!r}")
            if record.location.code not in self._locations:
                raise NotFound(f"cannot restore stock: no location {record.location.code!r}")
            key = (record.sku.code, record.location.code)
            if key in pending:
                raise DuplicateEntity(
                    f"duplicate stock record for {key[0]!r} at {key[1]!r}"
                )
            pending[key] = record

        # Everything below this line is mutation, and cannot fail.
        self._reorder_defaults = defaults
        self._stock.update(pending)
        self._movements = list(movements)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _record(self, sku_code: str, location_code: str) -> StockLevel:
        """Fetch the stock record, creating an empty one when absent."""
        key = (sku_code, location_code)
        record = self._stock.get(key)
        if record is None:
            record = StockLevel(
                sku=self.sku(sku_code),
                location=self.location(location_code),
                reorder_point=self._reorder_defaults.get(sku_code, 0),
            )
            self._stock[key] = record
        return record

    def _check_capacity(self, location: Location, units: int) -> None:
        """Raise if adding ``units`` would push a bounded location over capacity.

        ``units`` is a delta against the location's current occupancy, so the
        same helper serves receives, transfers and stocktake adjustments.
        """
        if units <= 0 or location.capacity is None:
            return
        occupancy = sum(
            record.quantity
            for (_, code), record in self._stock.items()
            if code == location.code
        )
        if occupancy + units > location.capacity:
            raise CapacityExceeded(
                f"location {location.code} holds {occupancy}/{location.capacity} units; "
                f"cannot add {units}"
            )

    def _log(
        self,
        kind: str,
        sku_code: str,
        location_code: str,
        units: int,
        reference: Optional[str],
    ) -> None:
        self._movements.append(
            Movement(
                kind=kind,
                sku_code=sku_code,
                location_code=location_code,
                units=units,
                reference=reference,
            )
        )


def _positive(units: object) -> int:
    """Validate a movement quantity."""
    if isinstance(units, bool) or not isinstance(units, int):
        raise ValidationError("units must be an integer")
    if units <= 0:
        raise ValidationError(f"units must be greater than zero, got {units}")
    return units
