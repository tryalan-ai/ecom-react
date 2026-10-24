"""The ``Warehouse`` service: registration, stock movements and reporting.

The warehouse owns every entity it is told about and every stock record it
creates, which lets it enforce cross-model invariants that a single model
cannot check on its own (for example: an SKU must belong to a registered
product, and a location may never hold more units than its capacity).
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from functools import wraps
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Tuple

from .audit import AuditLog, Movement, replay_totals, stock_level_drift
from .errors import (
    AuditLogError,
    CapacityExceeded,
    DuplicateEntity,
    InsufficientStock,
    NotFound,
    PurchaseOrderError,
    SalesOrderError,
    ValidationError,
)
from .models import (
    Location,
    Product,
    PurchaseOrder,
    PurchaseOrderLine,
    SKU,
    SalesOrder,
    SalesOrderLine,
    StockLevel,
)

__all__ = ["Movement", "AuditLog", "Warehouse", "synchronized"]


def synchronized(method):
    """Run ``method`` while holding the warehouse's re-entrant lock.

    Every public warehouse operation takes this lock, so two threads cannot
    interleave the read-then-write inside an allocation and promise the same
    units twice.  It is an ``RLock`` because operations legitimately call one
    another, for example a receipt that opens a transaction and then receives.
    """
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class Warehouse:
    """A registry of products, SKUs, locations, stock levels and orders."""

    def __init__(self, name: str = "warehouse") -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValidationError("name must be a non-empty string")
        self.name = name.strip()
        self._products: Dict[str, Product] = {}
        self._skus: Dict[str, SKU] = {}
        self._locations: Dict[str, Location] = {}
        self._stock: Dict[Tuple[str, str], StockLevel] = {}
        self._reorder_defaults: Dict[str, int] = {}
        self._movements: AuditLog = AuditLog()
        self._purchase_orders: Dict[str, PurchaseOrder] = {}
        self._sales_orders: Dict[str, SalesOrder] = {}
        self._in_transaction = False
        self._lock = threading.RLock()

    @property
    def lock(self) -> threading.RLock:
        """The re-entrant lock guarding every operation, exposed for testing."""
        return self._lock

    # ------------------------------------------------------------------
    # Transactions
    # ------------------------------------------------------------------
    @contextmanager
    def transaction(self) -> Iterator["Warehouse"]:
        """Run a group of changes atomically.

        Everything mutable is snapshotted on entry and restored if the block
        raises, so a multi-line receipt either lands completely or not at all.
        The warehouse lock is held for the whole block, so no other thread can
        observe - or interfere with - a half-applied change.

        A rollback swaps the warehouse's records for the restored copies, which
        means any aggregate handed out before the failure is detached.
        """
        with self._lock:
            if self._in_transaction:
                raise ValidationError("nested warehouse transactions are not supported")
            snapshot = self._snapshot()
            self._in_transaction = True
            try:
                yield self
            except BaseException:
                self._restore(snapshot)
                raise
            finally:
                self._in_transaction = False

    @property
    @synchronized
    def in_transaction(self) -> bool:
        return self._in_transaction

    def _snapshot(self) -> Dict[str, Any]:
        return {
            "products": dict(self._products),
            "skus": dict(self._skus),
            "locations": dict(self._locations),
            "stock": {key: record.copy() for key, record in self._stock.items()},
            "reorder_points": dict(self._reorder_defaults),
            "movements": len(self._movements),
            "orders": {ref: order.copy() for ref, order in self._purchase_orders.items()},
            "sales": {ref: order.copy() for ref, order in self._sales_orders.items()},
        }

    def _restore(self, snapshot: Dict[str, Any]) -> None:
        self._products = snapshot["products"]
        self._skus = snapshot["skus"]
        self._locations = snapshot["locations"]
        self._stock = snapshot["stock"]
        self._reorder_defaults = snapshot["reorder_points"]
        # Only the suffix added since the snapshot is discarded; committed
        # history is never rewritten.
        self._movements.rollback_to(snapshot["movements"])
        self._purchase_orders = snapshot["orders"]
        self._sales_orders = snapshot["sales"]

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    @synchronized
    def add_product(self, product: Product) -> Product:
        """Register ``product``; raise :class:`DuplicateEntity` if seen before."""
        if not isinstance(product, Product):
            raise ValidationError("product must be a Product instance")
        if product.product_id in self._products:
            raise DuplicateEntity(f"product {product.product_id!r} is already registered")
        self._products[product.product_id] = product
        return product

    @synchronized
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

    @synchronized
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
    @synchronized
    def products(self) -> List[Product]:
        return list(self._products.values())

    @property
    @synchronized
    def skus(self) -> List[SKU]:
        return list(self._skus.values())

    @property
    @synchronized
    def locations(self) -> List[Location]:
        return list(self._locations.values())

    @property
    @synchronized
    def movements(self) -> List[Movement]:
        """A snapshot list of the audit log, oldest first."""
        return list(self._movements)

    @property
    @synchronized
    def audit_log(self) -> AuditLog:
        """The live append-only log every stock change is written to."""
        return self._movements

    @synchronized
    def stock_level_drift(self) -> List[str]:
        """How the live records disagree with the audit log (empty when healthy)."""
        return stock_level_drift(self._movements, self._stock.values())

    @synchronized
    def verify_stock_levels(self) -> None:
        """Raise :class:`AuditLogError` unless the records match the log."""
        problems = stock_level_drift(self._movements, self._stock.values())
        if problems:
            raise AuditLogError(
                "stock levels disagree with the audit log: " + "; ".join(problems)
            )

    @synchronized
    def rebuild_stock_levels(self) -> List[StockLevel]:
        """Rebuild every stock record by replaying the audit log from scratch.

        The log is the source of truth, so this discards the current records and
        reconstructs them: quantities and reservations come from the replayed
        movements, and reorder points from the per-SKU defaults.  A log that
        cannot describe a real warehouse raises
        :class:`~inventory.errors.AuditLogError` and leaves the records alone.
        """
        totals = replay_totals(self._movements)

        rebuilt: Dict[Tuple[str, str], StockLevel] = {}
        for (sku_code, location_code), (quantity, reserved) in totals.items():
            try:
                sku = self._skus[sku_code]
            except KeyError as exc:
                raise NotFound(
                    f"the audit log names sku {sku_code!r}, which is not registered"
                ) from exc
            try:
                location = self._locations[location_code]
            except KeyError as exc:
                raise NotFound(
                    f"the audit log names location {location_code!r}, which is not registered"
                ) from exc
            rebuilt[(sku_code, location_code)] = StockLevel(
                sku=sku,
                location=location,
                quantity=quantity,
                reserved=reserved,
                reorder_point=self._reorder_defaults.get(sku_code, 0),
            )

        self._stock = rebuilt
        return self.stock_levels

    @property
    @synchronized
    def stock_levels(self) -> List[StockLevel]:
        """Every stock record, ordered by SKU code then location code."""
        return sorted(
            self._stock.values(),
            key=lambda record: (record.sku.code, record.location.code),
        )

    @synchronized
    def product(self, product_id: str) -> Product:
        try:
            return self._products[product_id]
        except KeyError as exc:
            raise NotFound(f"no product with id {product_id!r}") from exc

    @synchronized
    def sku(self, code: str) -> SKU:
        try:
            return self._skus[code]
        except KeyError as exc:
            raise NotFound(f"no sku with code {code!r}") from exc

    @synchronized
    def location(self, code: str) -> Location:
        try:
            return self._locations[code]
        except KeyError as exc:
            raise NotFound(f"no location with code {code!r}") from exc

    @synchronized
    def stock(self, sku_code: str, location_code: str) -> StockLevel:
        """Return the existing stock record for a SKU/location pair."""
        try:
            return self._stock[(sku_code, location_code)]
        except KeyError as exc:
            raise NotFound(
                f"no stock record for sku {sku_code!r} at location {location_code!r}"
            ) from exc

    @synchronized
    def has_stock_record(self, sku_code: str, location_code: str) -> bool:
        return (sku_code, location_code) in self._stock

    @synchronized
    def location_occupancy(self, location_code: str) -> int:
        """Total units held at ``location_code`` across every SKU."""
        self.location(location_code)  # raises NotFound for unknown locations
        return sum(
            record.quantity
            for (sku_code, code), record in self._stock.items()
            if code == location_code
        )

    @synchronized
    def on_hand(self, sku_code: str) -> int:
        """Total quantity of ``sku_code`` across every location."""
        self.sku(sku_code)  # raises NotFound for unknown SKUs
        return sum(
            record.quantity for (code, _), record in self._stock.items() if code == sku_code
        )

    @synchronized
    def available(self, sku_code: str) -> int:
        """Total unreserved quantity of ``sku_code`` across every location."""
        self.sku(sku_code)
        return sum(
            record.available for (code, _), record in self._stock.items() if code == sku_code
        )

    # ------------------------------------------------------------------
    # Movements
    # ------------------------------------------------------------------
    @synchronized
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

    @synchronized
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

    @synchronized
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

    @synchronized
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

    @synchronized
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

    @synchronized
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
        # Check against the existing record without creating one: a stocktake
        # that is refused must not leave a record the audit log knows nothing
        # about, or rebuilding from the log would stop matching live state.
        existing = self._stock.get((sku_code, location_code))
        reserved = existing.reserved if existing is not None else 0
        if counted_units < reserved:
            raise InsufficientStock(
                f"cannot adjust {sku_code} at {location_code} to {counted_units}: "
                f"{reserved} units are reserved"
            )
        record = self._record(sku_code, location_code)
        delta = counted_units - record.quantity
        self._check_capacity(location, delta)
        record.quantity = counted_units
        self._log("adjust", sku_code, location_code, delta, reference)
        return record

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    @synchronized
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

    @synchronized
    def low_stock(self) -> List[StockLevel]:
        """Every stock record whose available quantity has hit its threshold."""
        return [record for record in self._stock.values() if record.is_low]

    @synchronized
    def reorder_point(self, sku_code: str) -> int:
        """The configured reorder threshold for a SKU (``0`` when unset)."""
        self.sku(sku_code)
        return self._reorder_defaults.get(sku_code, 0)

    @synchronized
    def records_for(self, sku_code: str) -> List[StockLevel]:
        """Every stock record held for a SKU, ordered by location code."""
        self.sku(sku_code)
        return sorted(
            (record for (code, _), record in self._stock.items() if code == sku_code),
            key=lambda record: record.location.code,
        )

    # ------------------------------------------------------------------
    # Purchase orders
    # ------------------------------------------------------------------
    @property
    @synchronized
    def purchase_orders(self) -> List[PurchaseOrder]:
        """Every purchase order, ordered by reference."""
        return sorted(self._purchase_orders.values(), key=lambda order: order.reference)

    @synchronized
    def purchase_order(self, reference: str) -> PurchaseOrder:
        """The live (mutable) purchase order with this reference."""
        try:
            return self._purchase_orders[reference]
        except KeyError as exc:
            raise NotFound(f"no purchase order with reference {reference!r}") from exc

    @synchronized
    def create_purchase_order(
        self,
        reference: str,
        supplier: str,
        lines: Iterable[PurchaseOrderLine],
    ) -> PurchaseOrder:
        """Raise an order for goods we expect to arrive.

        Each line is normalised onto the *registered* SKU and location objects,
        and every order starts with nothing received.
        """
        if reference in self._purchase_orders:
            raise DuplicateEntity(f"purchase order {reference!r} already exists")

        normalised: List[PurchaseOrderLine] = []
        for line in lines:
            if not isinstance(line, PurchaseOrderLine):
                raise ValidationError("lines must contain PurchaseOrderLine instances")
            sku = self._skus.get(line.sku.code)
            if sku is None:
                raise NotFound(f"cannot order sku {line.sku.code!r}: it is not registered")
            location = self._locations.get(line.location.code)
            if location is None:
                raise NotFound(
                    f"cannot order into location {line.location.code!r}: it is not registered"
                )
            normalised.append(
                PurchaseOrderLine(
                    sku=sku, location=location, ordered_units=line.ordered_units
                )
            )

        order = PurchaseOrder(reference=reference, supplier=supplier, lines=normalised)
        self._purchase_orders[order.reference] = order
        return order

    @synchronized
    def receive_purchase_order(
        self,
        reference: str,
        receipts: Optional[Mapping[str, int]] = None,
    ) -> PurchaseOrder:
        """Book goods in against an order, updating stock atomically.

        ``receipts`` maps SKU code to units for a partial receipt.  Pass
        ``None`` to receive everything still outstanding.  The single
        transaction covers both the lines' received counts and the stock they
        create, so an over-capacity bin on any line leaves the order and the
        stock exactly as they were.
        """
        order = self.purchase_order(reference)
        if order.cancelled:
            raise PurchaseOrderError(f"purchase order {reference!r} is cancelled")
        if order.is_fully_received:
            raise PurchaseOrderError(f"purchase order {reference!r} is already fully received")

        planned = self._plan_receipts(order, receipts)
        with self.transaction():
            for sku_code, units in planned.items():
                line = order.line(sku_code)
                line.receive(units)
                self.receive(sku_code, line.location.code, units, reference=order.reference)
        return order

    @synchronized
    def cancel_purchase_order(self, reference: str) -> PurchaseOrder:
        """Cancel an order that nothing has been received against yet."""
        order = self.purchase_order(reference)
        if order.cancelled:
            raise PurchaseOrderError(f"purchase order {reference!r} is already cancelled")
        if order.received_units:
            raise PurchaseOrderError(
                f"cannot cancel purchase order {reference!r}: "
                f"{order.received_units} units have already been received"
            )
        order.cancelled = True
        return order

    def _plan_receipts(
        self, order: PurchaseOrder, receipts: Optional[Mapping[str, int]]
    ) -> Dict[str, int]:
        """Validate a receipt request and return {sku_code: units} to book."""
        if receipts is None:
            planned = {
                line.sku.code: line.outstanding for line in order.lines if line.outstanding
            }
            if not planned:
                raise PurchaseOrderError(
                    f"purchase order {order.reference!r} has nothing outstanding"
                )
            return planned

        if not isinstance(receipts, Mapping):
            raise ValidationError("receipts must be a mapping of sku code to units, or None")
        if not receipts:
            raise ValidationError(
                "receipts must not be empty; pass None to receive everything outstanding"
            )

        planned = {}
        for sku_code, units in receipts.items():
            if isinstance(units, bool) or not isinstance(units, int):
                raise ValidationError(f"receipt for {sku_code!r} must be a whole number")
            if units <= 0:
                raise ValidationError(
                    f"receipt for {sku_code!r} must be greater than zero, got {units}"
                )
            if sku_code not in order.line_keys:
                raise ValidationError(
                    f"purchase order {order.reference!r} has no line for sku {sku_code!r}"
                )
            line = order.line(sku_code)
            if units > line.outstanding:
                raise PurchaseOrderError(
                    f"cannot receive {units} of {sku_code}: "
                    f"only {line.outstanding} outstanding on this line"
                )
            planned[sku_code] = units
        return planned

    # ------------------------------------------------------------------
    # Sales orders
    # ------------------------------------------------------------------
    @property
    @synchronized
    def sales_orders(self) -> List[SalesOrder]:
        """Every sales order, ordered by reference."""
        return sorted(self._sales_orders.values(), key=lambda order: order.reference)

    @synchronized
    def sales_order(self, reference: str) -> SalesOrder:
        """The live (mutable) sales order with this reference."""
        try:
            return self._sales_orders[reference]
        except KeyError as exc:
            raise NotFound(f"no sales order with reference {reference!r}") from exc

    @synchronized
    def create_sales_order(
        self,
        reference: str,
        customer: str,
        lines: Iterable[SalesOrderLine],
    ) -> SalesOrder:
        """Take a customer order without claiming any stock yet.

        Creation never fails for want of stock, so backorders are representable;
        :meth:`allocate_sales_order` is what turns a line into reservations.
        """
        if reference in self._sales_orders:
            raise DuplicateEntity(f"sales order {reference!r} already exists")

        normalised: List[SalesOrderLine] = []
        for line in lines:
            if not isinstance(line, SalesOrderLine):
                raise ValidationError("lines must contain SalesOrderLine instances")
            sku = self._skus.get(line.sku.code)
            if sku is None:
                raise NotFound(f"cannot sell sku {line.sku.code!r}: it is not registered")
            location = self._locations.get(line.location.code)
            if location is None:
                raise NotFound(
                    f"cannot sell from location {line.location.code!r}: it is not registered"
                )
            normalised.append(
                SalesOrderLine(sku=sku, location=location, ordered_units=line.ordered_units)
            )

        order = SalesOrder(reference=reference, customer=customer, lines=normalised)
        self._sales_orders[order.reference] = order
        return order

    @synchronized
    def allocate_sales_order(
        self,
        reference: str,
        quantities: Optional[Mapping[str, int]] = None,
    ) -> SalesOrder:
        """Reserve stock for an order so no other order can promise it.

        ``quantities`` maps SKU code to units for a partial allocation; pass
        ``None`` to claim everything still unallocated.  The reservation and the
        line's claim move together inside one transaction, so a shortfall on any
        line leaves the order - and the stock - untouched.  Availability is
        checked while holding the warehouse lock, which is what stops two
        threads from reserving the same unit.
        """
        order = self.sales_order(reference)
        if order.cancelled:
            raise SalesOrderError(f"sales order {reference!r} is cancelled")
        if order.is_fulfilled:
            raise SalesOrderError(f"sales order {reference!r} is already fulfilled")

        planned = self._plan_allocations(order, quantities)
        with self.transaction():
            for sku_code, units in planned.items():
                line = order.line(sku_code)
                self.reserve(sku_code, line.location.code, units, reference=order.reference)
                line.allocate(units)
        return order

    @synchronized
    def ship_sales_order(
        self,
        reference: str,
        quantities: Optional[Mapping[str, int]] = None,
    ) -> SalesOrder:
        """Ship reserved stock, spending the reservation exactly once.

        ``quantities`` maps SKU code to units; pass ``None`` to ship everything
        reserved.  Only reserved units can ship, and shipping decrements on-hand
        and reserved together, so a unit can be sold at most once.
        """
        order = self.sales_order(reference)
        if order.cancelled:
            raise SalesOrderError(f"sales order {reference!r} is cancelled")
        if order.is_fulfilled:
            raise SalesOrderError(f"sales order {reference!r} is already fulfilled")

        planned = self._plan_shipments(order, quantities)
        with self.transaction():
            for sku_code, units in planned.items():
                line = order.line(sku_code)
                record = self.stock(sku_code, line.location.code)
                record.ship(units)
                line.ship(units)
                self._log("ship", sku_code, line.location.code, units, order.reference)
        return order

    @synchronized
    def cancel_sales_order(self, reference: str) -> SalesOrder:
        """Cancel an order, releasing whatever stock it still holds."""
        order = self.sales_order(reference)
        if order.cancelled:
            raise SalesOrderError(f"sales order {reference!r} is already cancelled")
        if order.shipped_units:
            raise SalesOrderError(
                f"cannot cancel sales order {reference!r}: "
                f"{order.shipped_units} units have already shipped"
            )
        with self.transaction():
            for line in order.lines:
                if line.reserved_units:
                    self.release(
                        line.sku.code,
                        line.location.code,
                        line.reserved_units,
                        reference=order.reference,
                    )
                    line.release(line.reserved_units)
            order.cancelled = True
        return order

    def _plan_allocations(
        self, order: SalesOrder, quantities: Optional[Mapping[str, int]]
    ) -> Dict[str, int]:
        """Validate an allocation request and return {sku_code: units} to claim."""
        if quantities is None:
            planned = {
                line.sku.code: line.unallocated for line in order.lines if line.unallocated
            }
            if not planned:
                raise SalesOrderError(
                    f"sales order {order.reference!r} has nothing left to allocate"
                )
            return planned
        return self._plan_order_quantities(
            order, quantities, "allocate", lambda line: line.unallocated
        )

    def _plan_shipments(
        self, order: SalesOrder, quantities: Optional[Mapping[str, int]]
    ) -> Dict[str, int]:
        """Validate a shipment request and return {sku_code: units} to ship."""
        if quantities is None:
            planned = {
                line.sku.code: line.reserved_units for line in order.lines if line.reserved_units
            }
            if not planned:
                raise SalesOrderError(
                    f"sales order {order.reference!r} has nothing reserved to ship"
                )
            return planned
        return self._plan_order_quantities(
            order, quantities, "ship", lambda line: line.reserved_units
        )

    @staticmethod
    def _plan_order_quantities(
        order: SalesOrder,
        quantities: Mapping[str, int],
        verb: str,
        ceiling,
    ) -> Dict[str, int]:
        """Shared validation for sales-order quantity mappings."""
        if not isinstance(quantities, Mapping):
            raise ValidationError(
                f"{verb} quantities must be a mapping of sku code to units, or None"
            )
        if not quantities:
            raise ValidationError(
                f"{verb} quantities must not be empty; pass None to use every line"
            )
        planned: Dict[str, int] = {}
        for sku_code, units in quantities.items():
            if isinstance(units, bool) or not isinstance(units, int):
                raise ValidationError(f"{verb} quantity for {sku_code!r} must be a whole number")
            if units <= 0:
                raise ValidationError(
                    f"{verb} quantity for {sku_code!r} must be greater than zero, got {units}"
                )
            if sku_code not in order.line_keys:
                raise ValidationError(
                    f"sales order {order.reference!r} has no line for sku {sku_code!r}"
                )
            line = order.line(sku_code)
            limit = ceiling(line)
            if units > limit:
                raise SalesOrderError(
                    f"cannot {verb} {units} of {sku_code}: only {limit} available on this line"
                )
            planned[sku_code] = units
        return planned

    # ------------------------------------------------------------------
    # Rehydration
    # ------------------------------------------------------------------
    @synchronized
    def restore(
        self,
        *,
        stock_levels: Iterable[StockLevel] = (),
        movements: Iterable[Movement] = (),
        reorder_points: Optional[Mapping[str, int]] = None,
        purchase_orders: Iterable[PurchaseOrder] = (),
        sales_orders: Iterable[SalesOrder] = (),
    ) -> None:
        """Load persisted state into a warehouse whose catalog is registered.

        This is the seam a repository uses to rebuild the aggregate without
        replaying (and therefore duplicating) its movement history.  The
        catalog -- products, SKUs and locations -- must already be registered
        and is validated against, never replaced.

        The whole snapshot is validated before any state is mutated, and
        restoring onto a warehouse that already holds state raises
        :class:`ValidationError` so halves of two snapshots cannot be silently
        merged.
        """
        if self._stock or self._movements or self._purchase_orders or self._sales_orders:
            raise ValidationError(
                "cannot restore into a warehouse that already holds state"
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

        pending_orders: Dict[str, PurchaseOrder] = {}
        for order in purchase_orders:
            if not isinstance(order, PurchaseOrder):
                raise ValidationError("purchase_orders must contain PurchaseOrder instances")
            if order.reference in pending_orders:
                raise DuplicateEntity(f"duplicate purchase order {order.reference!r}")
            for line in order.lines:
                if line.sku.code not in self._skus:
                    raise NotFound(f"cannot restore order: no sku {line.sku.code!r}")
                if line.location.code not in self._locations:
                    raise NotFound(
                        f"cannot restore order: no location {line.location.code!r}"
                    )
            pending_orders[order.reference] = order

        pending_sales: Dict[str, SalesOrder] = {}
        for order in sales_orders:
            if not isinstance(order, SalesOrder):
                raise ValidationError("sales_orders must contain SalesOrder instances")
            if order.reference in pending_sales:
                raise DuplicateEntity(f"duplicate sales order {order.reference!r}")
            for line in order.lines:
                if line.sku.code not in self._skus:
                    raise NotFound(f"cannot restore order: no sku {line.sku.code!r}")
                if line.location.code not in self._locations:
                    raise NotFound(
                        f"cannot restore order: no location {line.location.code!r}"
                    )
                # A reservation must be backed by stock we actually hold.
                record = pending.get((line.sku.code, line.location.code))
                if line.reserved_units and (
                    record is None or record.reserved < line.reserved_units
                ):
                    raise ValidationError(
                        f"cannot restore sales order {order.reference!r}: "
                        f"{line.reserved_units} units of {line.sku.code!r} are reserved "
                        f"but the stock record does not match"
                    )
            pending_sales[order.reference] = order

        # Everything below this line is mutation, and cannot fail.
        self._reorder_defaults = defaults
        self._stock.update(pending)
        self._purchase_orders = pending_orders
        self._sales_orders = pending_sales
        self._movements = AuditLog(movements)

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
