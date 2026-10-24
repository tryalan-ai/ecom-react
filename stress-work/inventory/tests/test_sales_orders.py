"""Unit tests for sales orders, reservations and thread-safety.

The concurrency tests here are deliberately adversarial: they release every
worker through a barrier at once so the read-then-write inside an allocation
overlaps as much as a CI machine allows, and they assert conservation rather
than timing.
"""

import sys
import threading
import unittest
from datetime import datetime, timezone

from inventory import (
    SALES_ALLOCATED,
    SALES_CANCELLED,
    SALES_FULFILLED,
    SALES_OPEN,
    SALES_PARTIAL,
    DuplicateEntity,
    InsufficientStock,
    Location,
    NotFound,
    Product,
    SKU,
    SalesOrder,
    SalesOrderError,
    SalesOrderLine,
    ValidationError,
    Warehouse,
)


class SalesOrderModelTests(unittest.TestCase):
    def setUp(self):
        self.product = Product("p-1", "Widget", "9.99")
        self.sku = SKU("s-1", self.product)
        self.other = SKU("s-2", self.product)
        self.bin_a = Location("A-01", "Bin A1")
        self.bin_b = Location("B-01", "Bin B1")

    def line(self, sku=None, location=None, units=10, reserved=0, shipped=0):
        return SalesOrderLine(sku or self.sku, location or self.bin_a, units, reserved, shipped)

    def test_line_tracks_unallocated_and_unshipped_units(self):
        line = self.line(units=10, reserved=3)
        self.assertEqual(line.unallocated, 7)
        self.assertEqual(line.unshipped, 3)
        self.assertFalse(line.is_allocated)
        self.assertFalse(line.is_fulfilled)

    def test_allocating_reduces_what_is_left_to_allocate(self):
        line = self.line(units=10)
        line.allocate(4)
        self.assertEqual((line.reserved_units, line.unallocated), (4, 6))
        line.allocate(6)
        self.assertTrue(line.is_allocated)
        self.assertEqual(line.unallocated, 0)

    def test_shipping_spends_a_reservation_exactly_once(self):
        line = self.line(units=10, reserved=10)
        line.ship(4)
        self.assertEqual((line.reserved_units, line.shipped_units), (6, 4))
        self.assertEqual(line.unallocated, 0)
        line.ship(6)
        self.assertTrue(line.is_fulfilled)
        self.assertEqual((line.reserved_units, line.shipped_units), (0, 10))

    def test_line_refuses_to_over_allocate_or_over_ship(self):
        line = self.line(units=5, reserved=2, shipped=1)
        with self.assertRaises(SalesOrderError):
            line.allocate(3)
        with self.assertRaises(SalesOrderError):
            line.ship(3)
        with self.assertRaises(SalesOrderError):
            line.release(3)

    def test_line_validates_its_quantities(self):
        with self.assertRaises(ValidationError):
            self.line(units=0)
        with self.assertRaises(ValidationError):
            self.line(units=5, reserved=6)
        with self.assertRaises(ValidationError):
            self.line(units=5, reserved=3, shipped=3)
        with self.assertRaises(ValidationError):
            self.line().allocate(0)
        with self.assertRaises(ValidationError):
            SalesOrderLine("s-1", self.bin_a, 1)
        with self.assertRaises(ValidationError):
            SalesOrderLine(self.sku, "A-01", 1)

    def test_order_totals_span_every_line(self):
        order = SalesOrder(
            "SO-1",
            "Ada",
            [
                self.line(units=10, reserved=4, shipped=2),
                self.line(sku=self.other, units=5, reserved=5),
            ],
        )
        self.assertEqual(order.ordered_units, 15)
        self.assertEqual(order.reserved_units, 9)
        self.assertEqual(order.shipped_units, 2)
        self.assertEqual(order.unallocated_units, 4)
        self.assertEqual(order.line_keys, ("s-1", "s-2"))
        self.assertEqual([location.code for location in order.locations], ["A-01"])

    def test_status_is_derived_from_the_lines(self):
        order = SalesOrder("SO-1", "Ada", [self.line(units=10)])
        self.assertEqual(order.status, SALES_OPEN)
        order.line("s-1").allocate(4)
        self.assertEqual(order.status, SALES_PARTIAL)
        order.line("s-1").allocate(6)
        self.assertEqual(order.status, SALES_ALLOCATED)
        order.line("s-1").ship(3)
        self.assertEqual(order.status, SALES_PARTIAL)
        order.line("s-1").ship(7)
        self.assertEqual(order.status, SALES_FULFILLED)
        order.cancelled = True
        self.assertEqual(order.status, SALES_CANCELLED)

    def test_order_requires_at_least_one_line_and_unique_skus(self):
        with self.assertRaises(ValidationError):
            SalesOrder("SO-1", "Ada", [])
        with self.assertRaises(ValidationError):
            SalesOrder("SO-1", "Ada", [self.line(), self.line(location=self.bin_b)])

    def test_order_validates_its_text_and_timestamp(self):
        with self.assertRaises(ValidationError):
            SalesOrder("  ", "Ada", [self.line()])
        with self.assertRaises(ValidationError):
            SalesOrder("SO-1", "", [self.line()])
        with self.assertRaises(ValidationError):
            SalesOrder("SO-1", "Ada", [self.line()], created_at="2024-01-01")
        with self.assertRaises(ValidationError):
            SalesOrder("SO-1", "Ada", [self.line()], cancelled="yes")

    def test_order_defaults_its_timestamp_and_unknown_lines_raise(self):
        before = datetime.now(timezone.utc)
        order = SalesOrder("SO-1", "Ada", [self.line()])
        self.assertGreaterEqual(order.created_at, before)
        self.assertEqual(order.created_at.tzinfo, timezone.utc)
        with self.assertRaises(NotFound):
            order.line("s-404")

    def test_copy_is_detached_from_the_original(self):
        order = SalesOrder("SO-1", "Ada", [self.line(units=10, reserved=2)])
        clone = order.copy()
        self.assertEqual(clone, order)
        clone.line("s-1").ship(1)
        clone.cancelled = True
        self.assertEqual(order.line("s-1").reserved_units, 2)
        self.assertEqual(order.line("s-1").shipped_units, 0)
        self.assertFalse(order.cancelled)


class SalesOrderTestCase(unittest.TestCase):
    """A warehouse holding 100 widgets, plus a small capacity-bound bin."""

    def setUp(self):
        self.warehouse = Warehouse("Main")
        self.product = self.warehouse.add_product(Product("p-1", "Widget", "9.99"))
        self.gadget = self.warehouse.add_product(Product("p-2", "Gadget", "4.50"))
        self.sku = self.warehouse.add_sku(SKU("s-1", self.product))
        self.sku_two = self.warehouse.add_sku(SKU("s-2", self.gadget))
        self.bin_a = self.warehouse.add_location(Location("A-01", "Bin A1", capacity=1000))
        self.bin_b = self.warehouse.add_location(Location("B-01", "Bin B1", capacity=1000))

    def line(self, sku=None, location=None, units=10):
        return SalesOrderLine(sku or self.sku, location or self.bin_a, units)

    def order(self, reference="SO-1", lines=None, customer="Ada Lovelace"):
        return self.warehouse.create_sales_order(
            reference, customer, lines if lines is not None else [self.line()]
        )

    def stock(self, sku_code="s-1", location_code="A-01"):
        return self.warehouse.stock(sku_code, location_code)


class CreateSalesOrderTests(SalesOrderTestCase):
    def test_creating_takes_an_order_without_claiming_stock(self):
        order = self.order()
        self.assertEqual(order.status, SALES_OPEN)
        self.assertEqual(order.customer, "Ada Lovelace")
        self.assertEqual(order.ordered_units, 10)
        self.assertEqual(order.reserved_units, 0)
        self.assertFalse(self.warehouse.has_stock_record("s-1", "A-01"))
        self.assertEqual(self.warehouse.movements, [])

    def test_lines_are_normalised_onto_the_registered_objects(self):
        order = self.order(
            lines=[SalesOrderLine(SKU("s-1", self.product), Location("A-01", "A1"), 4)]
        )
        self.assertIs(order.line("s-1").sku, self.sku)
        self.assertIs(order.line("s-1").location, self.bin_a)

    def test_an_order_can_be_taken_with_no_stock_on_hand(self):
        order = self.order()
        self.assertEqual(order.status, SALES_OPEN)
        self.assertEqual(self.warehouse.available("s-1"), 0)

    def test_duplicate_references_and_unknown_catalog_entries_are_refused(self):
        self.order()
        with self.assertRaises(DuplicateEntity):
            self.order()
        with self.assertRaises(NotFound):
            self.order("SO-2", lines=[SalesOrderLine(SKU("s-404", self.product), self.bin_a, 1)])
        with self.assertRaises(NotFound):
            self.order("SO-3", lines=[SalesOrderLine(self.sku, Location("L-404", "Ghost"), 1)])
        self.assertEqual(len(self.warehouse.sales_orders), 1)

    def test_an_empty_or_malformed_line_list_is_refused(self):
        with self.assertRaises(ValidationError):
            self.order(lines=[])
        with self.assertRaises(ValidationError):
            self.order(lines=[("s-1", "A-01", 4)])

    def test_orders_are_listed_in_reference_order(self):
        self.order("SO-3")
        self.order("SO-1")
        self.assertEqual(
            [order.reference for order in self.warehouse.sales_orders], ["SO-1", "SO-3"]
        )

    def test_an_unknown_reference_raises_not_found(self):
        for call in (
            self.warehouse.sales_order,
            self.warehouse.allocate_sales_order,
            self.warehouse.ship_sales_order,
            self.warehouse.cancel_sales_order,
        ):
            with self.subTest(call=call.__name__):
                with self.assertRaises(NotFound):
                    call("SO-404")


class AllocateSalesOrderTests(SalesOrderTestCase):
    def test_allocating_reserves_stock_without_moving_it(self):
        self.warehouse.receive("s-1", "A-01", 100)
        order = self.order()
        self.warehouse.allocate_sales_order("SO-1")

        record = self.stock()
        self.assertEqual(record.quantity, 100)
        self.assertEqual(record.reserved, 10)
        self.assertEqual(record.available, 90)
        self.assertEqual(self.warehouse.on_hand("s-1"), 100)
        self.assertEqual(self.warehouse.available("s-1"), 90)
        self.assertEqual(order.status, SALES_ALLOCATED)
        self.assertEqual(order.reserved_units, 10)

    def test_a_partial_allocation_leaves_the_order_partial(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        order = self.warehouse.allocate_sales_order("SO-1", {"s-1": 4})
        self.assertEqual(order.status, SALES_PARTIAL)
        self.assertEqual(order.line("s-1").unallocated, 6)
        self.assertEqual(self.stock().reserved, 4)
        self.assertEqual(self.warehouse.available("s-1"), 96)

    def test_allocating_twice_claims_the_remainder(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        self.warehouse.allocate_sales_order("SO-1", {"s-1": 4})
        order = self.warehouse.allocate_sales_order("SO-1")
        self.assertEqual(order.status, SALES_ALLOCATED)
        self.assertEqual(self.stock().reserved, 10)

    def test_reserved_stock_cannot_be_promised_to_a_second_order(self):
        self.warehouse.receive("s-1", "A-01", 10)
        self.order("SO-1")
        self.order("SO-2")
        self.warehouse.allocate_sales_order("SO-1")
        self.assertEqual(self.warehouse.available("s-1"), 0)

        with self.assertRaises(InsufficientStock):
            self.warehouse.allocate_sales_order("SO-2")
        with self.assertRaises(InsufficientStock):
            self.warehouse.allocate_sales_order("SO-2", {"s-1": 1})

        self.assertEqual(self.warehouse.sales_order("SO-2").status, SALES_OPEN)
        self.assertEqual(self.warehouse.sales_order("SO-2").reserved_units, 0)
        record = self.stock()
        self.assertEqual((record.quantity, record.reserved), (10, 10))

    def test_a_shortfall_on_one_line_leaves_the_order_and_stock_untouched(self):
        self.warehouse.receive("s-1", "A-01", 10)
        self.warehouse.receive("s-2", "B-01", 2)
        self.order(
            lines=[
                self.line(sku=self.sku, location=self.bin_a, units=10),
                self.line(sku=self.sku_two, location=self.bin_b, units=5),
            ]
        )
        with self.assertRaises(InsufficientStock):
            self.warehouse.allocate_sales_order("SO-1", {"s-1": 10, "s-2": 5})

        order = self.warehouse.sales_order("SO-1")
        self.assertEqual(order.status, SALES_OPEN)
        self.assertEqual(order.reserved_units, 0)
        self.assertEqual(self.stock("s-1", "A-01").reserved, 0)
        self.assertEqual(self.stock("s-2", "B-01").reserved, 0)
        self.assertEqual(
            [movement.kind for movement in self.warehouse.movements], ["receive", "receive"]
        )

    def test_allocating_more_than_the_line_ordered_is_refused(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        with self.assertRaises(SalesOrderError):
            self.warehouse.allocate_sales_order("SO-1", {"s-1": 11})
        self.assertEqual(self.stock().reserved, 0)

    def test_allocation_requests_are_validated(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        with self.assertRaises(ValidationError):
            self.warehouse.allocate_sales_order("SO-1", {})
        with self.assertRaises(ValidationError):
            self.warehouse.allocate_sales_order("SO-1", ["s-1", 4])
        with self.assertRaises(ValidationError):
            self.warehouse.allocate_sales_order("SO-1", {"s-2": 1})
        for bad in (0, -1, 2.5, "4", True):
            with self.subTest(units=bad):
                with self.assertRaises(ValidationError):
                    self.warehouse.allocate_sales_order("SO-1", {"s-1": bad})
        self.assertEqual(self.stock().reserved, 0)

    def test_allocation_is_traceable_in_the_movement_log(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        self.warehouse.allocate_sales_order("SO-1")
        movements = self.warehouse.movements
        self.assertEqual([movement.kind for movement in movements], ["receive", "reserve"])
        self.assertEqual(movements[-1].reference, "SO-1")
        self.assertEqual(movements[-1].units, 10)

    def test_a_fulfilled_order_has_nothing_left_to_allocate(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        self.warehouse.allocate_sales_order("SO-1")
        self.warehouse.ship_sales_order("SO-1")
        with self.assertRaises(SalesOrderError):
            self.warehouse.allocate_sales_order("SO-1")

    def test_a_cancelled_order_cannot_be_allocated(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        self.warehouse.cancel_sales_order("SO-1")
        with self.assertRaises(SalesOrderError):
            self.warehouse.allocate_sales_order("SO-1")
        self.assertEqual([m.kind for m in self.warehouse.movements], ["receive"])


class ShipSalesOrderTests(SalesOrderTestCase):
    def test_shipping_spends_the_reservation_and_takes_stock_off_the_shelf(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        self.warehouse.allocate_sales_order("SO-1")
        order = self.warehouse.ship_sales_order("SO-1", {"s-1": 4})

        record = self.stock()
        self.assertEqual(record.quantity, 96)
        self.assertEqual(record.reserved, 6)
        self.assertEqual(record.available, 90)
        self.assertEqual(order.shipped_units, 4)
        self.assertEqual(order.reserved_units, 6)
        self.assertEqual(order.status, SALES_PARTIAL)

    def test_shipping_everything_fulfils_the_order(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        self.warehouse.allocate_sales_order("SO-1")
        order = self.warehouse.ship_sales_order("SO-1")
        self.assertEqual(order.status, SALES_FULFILLED)
        self.assertEqual(order.shipped_units, 10)
        self.assertEqual(order.reserved_units, 0)
        self.assertEqual(self.stock().quantity, 90)
        self.assertEqual(self.warehouse.on_hand("s-1"), 90)
        self.assertEqual(self.stock().reserved, 0)
        self.assertEqual(self.warehouse.available("s-1"), 90)

    def test_a_shipment_is_traceable_in_the_movement_log(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        self.warehouse.allocate_sales_order("SO-1")
        self.warehouse.ship_sales_order("SO-1", {"s-1": 3})
        movement = self.warehouse.movements[-1]
        self.assertEqual(movement.kind, "ship")
        self.assertEqual(movement.reference, "SO-1")
        self.assertEqual(movement.units, 3)

    def test_unreserved_stock_cannot_be_shipped(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        with self.assertRaises(SalesOrderError):
            self.warehouse.ship_sales_order("SO-1")
        with self.assertRaises(SalesOrderError):
            self.warehouse.ship_sales_order("SO-1", {"s-1": 1})
        self.assertEqual(self.stock().quantity, 100)
        self.assertEqual(self.stock().reserved, 0)

    def test_shipping_more_than_is_reserved_is_refused(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        self.warehouse.allocate_sales_order("SO-1", {"s-1": 4})
        with self.assertRaises(SalesOrderError):
            self.warehouse.ship_sales_order("SO-1", {"s-1": 5})
        record = self.stock()
        self.assertEqual((record.quantity, record.reserved), (100, 4))
        self.assertEqual(self.warehouse.sales_order("SO-1").shipped_units, 0)

    def test_a_second_shipment_continues_where_the_first_stopped(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        self.warehouse.allocate_sales_order("SO-1")
        self.warehouse.ship_sales_order("SO-1", {"s-1": 4})
        order = self.warehouse.ship_sales_order("SO-1")
        self.assertEqual(order.status, SALES_FULFILLED)
        self.assertEqual(self.stock().quantity, 90)

    def test_fulfilled_orders_accept_no_further_shipments(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        self.warehouse.allocate_sales_order("SO-1")
        self.warehouse.ship_sales_order("SO-1")
        with self.assertRaises(SalesOrderError):
            self.warehouse.ship_sales_order("SO-1")
        self.assertEqual(self.stock().quantity, 90)

    def test_shipping_cannot_reach_stock_reserved_by_another_order(self):
        self.warehouse.receive("s-1", "A-01", 20)
        self.order("SO-1", lines=[self.line(units=10)])
        self.order("SO-2", lines=[self.line(units=10)])
        self.warehouse.allocate_sales_order("SO-1")
        self.warehouse.allocate_sales_order("SO-2")
        self.assertEqual(self.stock().reserved, 20)
        self.warehouse.ship_sales_order("SO-1")
        record = self.stock()
        self.assertEqual(record.quantity, 10)
        self.assertEqual(record.reserved, 10)
        self.assertEqual(record.available, 0)

    def test_shipment_requests_are_validated(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        self.warehouse.allocate_sales_order("SO-1")
        with self.assertRaises(ValidationError):
            self.warehouse.ship_sales_order("SO-1", {})
        with self.assertRaises(ValidationError):
            self.warehouse.ship_sales_order("SO-1", {"s-2": 1})
        with self.assertRaises(ValidationError):
            self.warehouse.ship_sales_order("SO-1", {"s-1": 0})
        self.assertEqual(self.stock().quantity, 100)


class CancelSalesOrderTests(SalesOrderTestCase):
    def test_cancelling_an_open_order_marks_it_cancelled(self):
        self.order()
        order = self.warehouse.cancel_sales_order("SO-1")
        self.assertEqual(order.status, SALES_CANCELLED)
        self.assertTrue(order.cancelled)

    def test_cancelling_releases_the_reservation(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        self.warehouse.allocate_sales_order("SO-1")
        self.assertEqual(self.warehouse.available("s-1"), 90)

        order = self.warehouse.cancel_sales_order("SO-1")
        self.assertEqual(order.reserved_units, 0)
        record = self.stock()
        self.assertEqual((record.quantity, record.reserved), (100, 0))
        self.assertEqual(self.warehouse.available("s-1"), 100)

    def test_released_stock_can_be_promised_to_another_order(self):
        self.warehouse.receive("s-1", "A-01", 10)
        self.order("SO-1")
        self.order("SO-2")
        self.warehouse.allocate_sales_order("SO-1")
        with self.assertRaises(InsufficientStock):
            self.warehouse.allocate_sales_order("SO-2")

        self.warehouse.cancel_sales_order("SO-1")
        self.warehouse.allocate_sales_order("SO-2")
        self.assertEqual(self.warehouse.sales_order("SO-2").status, SALES_ALLOCATED)
        self.assertEqual(self.stock().reserved, 10)

    def test_cancelling_twice_is_refused(self):
        self.order()
        self.warehouse.cancel_sales_order("SO-1")
        with self.assertRaises(SalesOrderError):
            self.warehouse.cancel_sales_order("SO-1")

    def test_an_order_that_has_shipped_cannot_be_cancelled(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        self.warehouse.allocate_sales_order("SO-1")
        self.warehouse.ship_sales_order("SO-1", {"s-1": 2})
        with self.assertRaises(SalesOrderError):
            self.warehouse.cancel_sales_order("SO-1")
        self.assertFalse(self.warehouse.sales_order("SO-1").cancelled)
        self.assertEqual(self.stock().reserved, 8)


class SalesOrderTransactionTests(SalesOrderTestCase):
    def test_a_failed_allocation_rolls_back_the_movement_log(self):
        self.warehouse.receive("s-1", "A-01", 4)
        self.order()
        with self.assertRaises(InsufficientStock):
            self.warehouse.allocate_sales_order("SO-1")
        self.assertEqual([movement.kind for movement in self.warehouse.movements], ["receive"])

    def test_a_rejected_shipment_changes_nothing(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.warehouse.receive("s-2", "B-01", 100)
        self.order(
            lines=[
                self.line(sku=self.sku, location=self.bin_a, units=10),
                self.line(sku=self.sku_two, location=self.bin_b, units=10),
            ]
        )
        self.warehouse.allocate_sales_order("SO-1")
        # s-2 is only reserved for 10, so asking to ship 11 is rejected before
        # any of the order's stock moves.
        with self.assertRaises(SalesOrderError):
            self.warehouse.ship_sales_order("SO-1", {"s-1": 10, "s-2": 11})

        order = self.warehouse.sales_order("SO-1")
        self.assertEqual(order.shipped_units, 0)
        self.assertEqual(order.reserved_units, 20)
        self.assertEqual(self.stock("s-1", "A-01").quantity, 100)
        self.assertEqual(self.stock("s-2", "B-01").quantity, 100)

    def test_a_failed_cancellation_changes_nothing(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        self.warehouse.allocate_sales_order("SO-1")
        self.warehouse.ship_sales_order("SO-1", {"s-1": 2})

        with self.assertRaises(SalesOrderError):
            self.warehouse.cancel_sales_order("SO-1")

        order = self.warehouse.sales_order("SO-1")
        self.assertFalse(order.cancelled)
        self.assertEqual(order.reserved_units, 8)
        self.assertEqual(self.stock().reserved, 8)
        self.assertEqual(self.stock().quantity, 98)

    def test_restoring_requires_reservations_to_match_stock(self):
        warehouse = Warehouse("Other")
        product = warehouse.add_product(Product("p-1", "Widget", "9.99"))
        warehouse.add_sku(SKU("s-1", product))
        warehouse.add_location(Location("A-01", "Bin A1"))
        warehouse.receive("s-1", "A-01", 50)
        warehouse.create_sales_order(
            "SO-1",
            "Ada",
            [SalesOrderLine(warehouse.sku("s-1"), warehouse.location("A-01"), 10)],
        )
        warehouse.allocate_sales_order("SO-1")

        target = Warehouse("Target")
        target.add_product(product)
        target.add_sku(SKU("s-1", product))
        target.add_location(Location("A-01", "Bin A1"))
        # No stock record backs the reservation, so the snapshot is inconsistent.
        with self.assertRaises(ValidationError):
            target.restore(sales_orders=warehouse.sales_orders)

    def test_a_restored_warehouse_can_ship_what_was_reserved(self):
        self.warehouse.receive("s-1", "A-01", 100)
        self.order()
        self.warehouse.allocate_sales_order("SO-1")

        restored = Warehouse("Restored")
        restored.add_product(self.product)
        restored.add_sku(self.sku)
        restored.add_location(self.bin_a)
        restored.restore(
            stock_levels=self.warehouse.stock_levels,
            movements=self.warehouse.movements,
            sales_orders=self.warehouse.sales_orders,
        )
        restored.ship_sales_order("SO-1")
        self.assertEqual(restored.stock("s-1", "A-01").quantity, 90)
        self.assertEqual(restored.sales_order("SO-1").status, SALES_FULFILLED)


class ThreadedTestCase(unittest.TestCase):
    """Helpers for running workers that all start at the same moment."""

    def run_concurrently(self, worker, count):
        """Run ``worker(index, barrier)`` in ``count`` threads, released together."""
        barrier = threading.Barrier(count, timeout=30)
        results, errors = [], []
        guard = threading.Lock()

        def target(index):
            try:
                barrier.wait()
                outcome = worker(index, barrier)
            except BaseException as exc:  # noqa: BLE001 - surfaced as a failure
                with guard:
                    errors.append(exc)
            else:
                with guard:
                    results.append(outcome)

        threads = [
            threading.Thread(target=target, args=(index,), daemon=True)
            for index in range(count)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertFalse([thread for thread in threads if thread.is_alive()], "worker hung")
        self.assertEqual(errors, [], f"unexpected worker errors: {errors!r}")
        return results


class SalesOrderConcurrencyTests(SalesOrderTestCase, ThreadedTestCase):
    """Adversarial threading tests for the reservation invariants.

    ``sys.setswitchinterval`` is turned right down and every assertion is
    repeated over several rounds, so a missing lock surfaces as a wrong count
    rather than as an occasional flake.  Each test here fails when the
    warehouse lock is replaced by a no-op.
    """

    ROUNDS = 10

    def setUp(self):
        super().setUp()
        self._switch_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)

    def tearDown(self):
        sys.setswitchinterval(self._switch_interval)
        super().tearDown()

    def fresh_warehouse(self, on_hand, capacity=100_000):
        """A warehouse with a single SKU and a single bin."""
        warehouse = Warehouse("Round")
        product = warehouse.add_product(Product("p-1", "Widget", "9.99"))
        warehouse.add_sku(SKU("s-1", product))
        warehouse.add_location(Location("A-01", "Bin A1", capacity=capacity))
        if on_hand:
            warehouse.receive("s-1", "A-01", on_hand)
        return warehouse

    def place_order(self, warehouse, reference, units):
        warehouse.create_sales_order(
            reference,
            f"Customer {reference}",
            [SalesOrderLine(warehouse.sku("s-1"), warehouse.location("A-01"), units)],
        )

    def test_concurrent_allocations_cannot_reserve_the_same_units(self):
        threads, per_order, on_hand = 20, 10, 100
        for round_number in range(self.ROUNDS):
            with self.subTest(round=round_number):
                warehouse = self.fresh_warehouse(on_hand)

                def worker(index, barrier, warehouse=warehouse):
                    reference = f"SO-{index}"
                    self.place_order(warehouse, reference, per_order)
                    try:
                        warehouse.allocate_sales_order(reference)
                    except InsufficientStock:
                        return "refused"
                    return "allocated"

                results = self.run_concurrently(worker, threads)
                record = warehouse.stock("s-1", "A-01")
                winners = on_hand // per_order
                self.assertEqual(results.count("allocated"), winners)
                self.assertEqual(results.count("refused"), threads - winners)
                self.assertEqual(record.quantity, on_hand)
                self.assertEqual(record.reserved, on_hand)
                self.assertEqual(record.available, 0)
                # Every reserved unit belongs to exactly one order.
                self.assertEqual(
                    sum(order.reserved_units for order in warehouse.sales_orders), on_hand
                )

    def test_concurrent_allocations_settle_the_last_units_exactly(self):
        threads, per_order, on_hand = 10, 5, 25
        for round_number in range(self.ROUNDS):
            with self.subTest(round=round_number):
                warehouse = self.fresh_warehouse(on_hand)

                def worker(index, barrier, warehouse=warehouse):
                    reference = f"SO-{index}"
                    self.place_order(warehouse, reference, per_order)
                    try:
                        warehouse.allocate_sales_order(reference)
                    except InsufficientStock:
                        return "refused"
                    return "allocated"

                results = self.run_concurrently(worker, threads)
                record = warehouse.stock("s-1", "A-01")
                self.assertEqual(results.count("allocated"), 5)
                self.assertEqual(record.reserved, 25)
                self.assertEqual(record.available, 0)

    def test_concurrent_creation_keeps_one_order_per_reference(self):
        threads = 12
        for round_number in range(self.ROUNDS):
            with self.subTest(round=round_number):
                warehouse = self.fresh_warehouse(0)

                def worker(index, barrier, warehouse=warehouse):
                    try:
                        warehouse.create_sales_order("SO-SAME", "Customer", [
                            SalesOrderLine(
                                warehouse.sku("s-1"), warehouse.location("A-01"), 1
                            )
                        ])
                    except DuplicateEntity:
                        return "rejected"
                    return "created"

                results = self.run_concurrently(worker, threads)
                self.assertEqual(results.count("created"), 1)
                self.assertEqual(results.count("rejected"), threads - 1)
                self.assertEqual(len(warehouse.sales_orders), 1)

    def test_concurrent_shipments_cannot_spend_a_reservation_twice(self):
        threads, per_shipment, reserved, on_hand = 15, 2, 20, 100
        for round_number in range(self.ROUNDS):
            with self.subTest(round=round_number):
                warehouse = self.fresh_warehouse(on_hand)
                self.place_order(warehouse, "SO-1", reserved)
                warehouse.allocate_sales_order("SO-1")

                def worker(index, barrier, warehouse=warehouse):
                    try:
                        warehouse.ship_sales_order("SO-1", {"s-1": per_shipment})
                    except SalesOrderError:
                        return "refused"
                    return "shipped"

                results = self.run_concurrently(worker, threads)
                record = warehouse.stock("s-1", "A-01")
                winners = reserved // per_shipment
                self.assertEqual(results.count("shipped"), winners)
                self.assertEqual(results.count("refused"), threads - winners)
                self.assertEqual(record.quantity, on_hand - reserved)
                self.assertEqual(record.reserved, 0)

    def test_concurrent_cancellations_release_each_reservation_once(self):
        orders, per_order, on_hand = 10, 10, 100
        for round_number in range(self.ROUNDS):
            with self.subTest(round=round_number):
                warehouse = self.fresh_warehouse(on_hand)
                for index in range(orders):
                    reference = f"SO-{index}"
                    self.place_order(warehouse, reference, per_order)
                    warehouse.allocate_sales_order(reference)
                self.assertEqual(warehouse.stock("s-1", "A-01").reserved, on_hand)

                def worker(index, barrier, warehouse=warehouse):
                    warehouse.cancel_sales_order(f"SO-{index}")
                    return "cancelled"

                results = self.run_concurrently(worker, orders)
                record = warehouse.stock("s-1", "A-01")
                self.assertEqual(results.count("cancelled"), orders)
                self.assertEqual(record.quantity, on_hand)
                self.assertEqual(record.reserved, 0)
                self.assertEqual(record.available, on_hand)

    def test_concurrent_allocate_and_ship_conserve_every_unit(self):
        threads, per_order, on_hand = 20, 10, 100
        for round_number in range(self.ROUNDS):
            with self.subTest(round=round_number):
                warehouse = self.fresh_warehouse(on_hand)

                def worker(index, barrier, warehouse=warehouse):
                    reference = f"SO-{index}"
                    self.place_order(warehouse, reference, per_order)
                    try:
                        warehouse.allocate_sales_order(reference)
                    except InsufficientStock:
                        return "refused"
                    warehouse.ship_sales_order(reference)
                    return "fulfilled"

                results = self.run_concurrently(worker, threads)
                fulfilled = results.count("fulfilled")
                self.assertEqual(fulfilled + results.count("refused"), threads)
                self.assertGreaterEqual(fulfilled, on_hand // per_order)

                record = warehouse.stock("s-1", "A-01")
                self.assertEqual(record.quantity, on_hand - per_order * fulfilled)
                self.assertEqual(record.reserved, 0)
                self.assertEqual(record.available, record.quantity)
                shipped = sum(order.shipped_units for order in warehouse.sales_orders)
                self.assertEqual(shipped, per_order * fulfilled)
                self.assertLessEqual(shipped, on_hand)
                for order in warehouse.sales_orders:
                    if order.shipped_units:
                        self.assertEqual(order.status, SALES_FULFILLED)

    def test_a_watcher_never_sees_reserved_stock_exceed_on_hand_stock(self):
        self.warehouse.receive("s-1", "A-01", 200)
        stop = threading.Event()
        violations = []
        guard = threading.Lock()

        def watcher():
            while not stop.is_set():
                record = self.warehouse.stock("s-1", "A-01")
                if not 0 <= record.reserved <= record.quantity:
                    with guard:
                        violations.append((record.quantity, record.reserved))
                if self.warehouse.available("s-1") < 0:
                    with guard:
                        violations.append("negative availability")

        def worker(index, barrier):
            for round_number in range(15):
                reference = f"SO-{index}-{round_number}"
                self.place_order(self.warehouse, reference, 5)
                try:
                    self.warehouse.allocate_sales_order(reference)
                except InsufficientStock:
                    continue
                self.warehouse.ship_sales_order(reference)
            return "done"

        observer = threading.Thread(target=watcher, daemon=True)
        observer.start()
        try:
            results = self.run_concurrently(worker, 8)
        finally:
            stop.set()
            observer.join(timeout=10)

        self.assertEqual(results, ["done"] * 8)
        self.assertEqual(violations, [])
        record = self.warehouse.stock("s-1", "A-01")
        self.assertEqual(record.reserved, 0)
        self.assertLessEqual(record.quantity, 200)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
