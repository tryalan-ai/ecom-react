"""Unit tests for purchase orders: creation, receipt, cancellation and atomicity."""

import unittest
from datetime import datetime, timezone

from inventory import (
    ORDER_CANCELLED,
    ORDER_OPEN,
    ORDER_PARTIAL,
    ORDER_RECEIVED,
    CapacityExceeded,
    DuplicateEntity,
    Location,
    NotFound,
    Product,
    PurchaseOrder,
    PurchaseOrderError,
    PurchaseOrderLine,
    SKU,
    ValidationError,
    Warehouse,
)


class PurchaseOrderModelTests(unittest.TestCase):
    def setUp(self):
        self.product = Product("p-1", "Widget", "9.99")
        self.sku = SKU("s-1", self.product)
        self.other = SKU("s-2", self.product)
        self.bin_a = Location("A-01", "Bin A1")
        self.bin_b = Location("B-01", "Bin B1")

    def line(self, sku=None, location=None, units=10, received=0):
        return PurchaseOrderLine(sku or self.sku, location or self.bin_a, units, received)

    def test_line_tracks_what_is_outstanding(self):
        line = self.line(units=10, received=4)
        self.assertEqual(line.outstanding, 6)
        self.assertFalse(line.is_complete)
        line.receive(6)
        self.assertEqual(line.outstanding, 0)
        self.assertTrue(line.is_complete)

    def test_line_refuses_to_over_receive(self):
        line = self.line(units=10, received=8)
        with self.assertRaises(PurchaseOrderError):
            line.receive(3)
        self.assertEqual(line.received_units, 8)

    def test_line_validates_its_quantities(self):
        with self.assertRaises(ValidationError):
            self.line(units=0)
        with self.assertRaises(ValidationError):
            self.line(units=-1)
        with self.assertRaises(ValidationError):
            self.line(units=5, received=6)
        with self.assertRaises(ValidationError):
            self.line(units="ten")
        with self.assertRaises(ValidationError):
            self.line(units=5).receive(0)

    def test_line_requires_real_sku_and_location_objects(self):
        with self.assertRaises(ValidationError):
            PurchaseOrderLine("s-1", self.bin_a, 1)
        with self.assertRaises(ValidationError):
            PurchaseOrderLine(self.sku, "A-01", 1)

    def test_order_totals_span_every_line(self):
        order = PurchaseOrder(
            "PO-1",
            "Acme",
            [self.line(units=10, received=4), self.line(sku=self.other, units=5)],
        )
        self.assertEqual(order.ordered_units, 15)
        self.assertEqual(order.received_units, 4)
        self.assertEqual(order.outstanding_units, 11)
        self.assertEqual(order.line_keys, ("s-1", "s-2"))

    def test_status_is_derived_from_the_lines(self):
        order = PurchaseOrder("PO-1", "Acme", [self.line(units=10)])
        self.assertEqual(order.status, ORDER_OPEN)
        order.line("s-1").receive(3)
        self.assertEqual(order.status, ORDER_PARTIAL)
        order.line("s-1").receive(7)
        self.assertEqual(order.status, ORDER_RECEIVED)
        order.cancelled = True
        self.assertEqual(order.status, ORDER_CANCELLED)

    def test_order_requires_at_least_one_line(self):
        with self.assertRaises(ValidationError):
            PurchaseOrder("PO-1", "Acme", [])

    def test_order_rejects_two_lines_for_the_same_sku(self):
        with self.assertRaises(ValidationError):
            PurchaseOrder("PO-1", "Acme", [self.line(), self.line(location=self.bin_b)])

    def test_order_validates_its_text_and_timestamp(self):
        with self.assertRaises(ValidationError):
            PurchaseOrder("  ", "Acme", [self.line()])
        with self.assertRaises(ValidationError):
            PurchaseOrder("PO-1", "", [self.line()])
        with self.assertRaises(ValidationError):
            PurchaseOrder("PO-1", "Acme", [self.line()], created_at="2024-01-01")
        with self.assertRaises(ValidationError):
            PurchaseOrder("PO-1", "Acme", [self.line()], cancelled="yes")

    def test_order_defaults_its_timestamp_and_unknown_lines_raise(self):
        before = datetime.now(timezone.utc)
        order = PurchaseOrder("PO-1", "Acme", [self.line()])
        self.assertGreaterEqual(order.created_at, before)
        self.assertEqual(order.created_at.tzinfo, timezone.utc)
        with self.assertRaises(NotFound):
            order.line("s-404")

    def test_copy_is_detached_from_the_original(self):
        order = PurchaseOrder("PO-1", "Acme", [self.line(units=10, received=2)])
        clone = order.copy()
        self.assertEqual(clone, order)
        clone.line("s-1").receive(1)
        clone.cancelled = True
        self.assertEqual(order.line("s-1").received_units, 2)
        self.assertFalse(order.cancelled)
        self.assertIsNot(clone.line("s-1"), order.line("s-1"))


class PurchaseOrderTestCase(unittest.TestCase):
    """A warehouse holding two SKUs and a small, capacity-bound bin."""

    def setUp(self):
        self.warehouse = Warehouse("Main")
        self.product = self.warehouse.add_product(Product("p-1", "Widget", "9.99"))
        self.gadget = self.warehouse.add_product(Product("p-2", "Gadget", "4.50"))
        self.sku = self.warehouse.add_sku(SKU("s-1", self.product))
        self.sku_two = self.warehouse.add_sku(SKU("s-2", self.gadget))
        self.bin_a = self.warehouse.add_location(Location("A-01", "Bin A1", capacity=100))
        self.bin_b = self.warehouse.add_location(Location("B-01", "Bin B1", capacity=5))

    def line(self, sku=None, location=None, units=10):
        return PurchaseOrderLine(sku or self.sku, location or self.bin_a, units)

    def order(self, reference="PO-1", lines=None, supplier="Acme Supply"):
        return self.warehouse.create_purchase_order(
            reference, supplier, lines if lines is not None else [self.line()]
        )


class CreatePurchaseOrderTests(PurchaseOrderTestCase):
    def test_creating_returns_an_open_order(self):
        order = self.order()
        self.assertEqual(order.status, ORDER_OPEN)
        self.assertEqual(order.reference, "PO-1")
        self.assertEqual(order.supplier, "Acme Supply")
        self.assertEqual(order.ordered_units, 10)
        self.assertEqual(order.received_units, 0)
        self.assertEqual(order.outstanding_units, 10)
        self.assertEqual(self.warehouse.movements, [])
        self.assertFalse(self.warehouse.has_stock_record("s-1", "A-01"))

    def test_lines_are_normalised_onto_the_registered_objects(self):
        order = self.order(
            lines=[PurchaseOrderLine(SKU("s-1", self.product), Location("A-01", "A1"), 4)]
        )
        self.assertIs(order.line("s-1").sku, self.sku)
        self.assertIs(order.line("s-1").location, self.bin_a)

    def test_a_new_order_starts_with_nothing_received(self):
        order = self.order(lines=[PurchaseOrderLine(self.sku, self.bin_a, 10, 4)])
        self.assertEqual(order.received_units, 0)
        self.assertEqual(order.status, ORDER_OPEN)

    def test_duplicate_references_are_refused(self):
        self.order()
        with self.assertRaises(DuplicateEntity):
            self.order()
        self.assertEqual(len(self.warehouse.purchase_orders), 1)

    def test_unregistered_skus_and_locations_are_refused(self):
        with self.assertRaises(NotFound):
            self.order(lines=[PurchaseOrderLine(SKU("s-404", self.product), self.bin_a, 1)])
        with self.assertRaises(NotFound):
            self.order(lines=[PurchaseOrderLine(self.sku, Location("L-404", "Ghost"), 1)])
        self.assertEqual(self.warehouse.purchase_orders, [])

    def test_an_empty_or_malformed_line_list_is_refused(self):
        with self.assertRaises(ValidationError):
            self.order(lines=[])
        with self.assertRaises(ValidationError):
            self.order(lines=[("s-1", "A-01", 4)])

    def test_orders_are_listed_in_reference_order(self):
        self.order("PO-3")
        self.order("PO-1")
        self.assertEqual(
            [order.reference for order in self.warehouse.purchase_orders],
            ["PO-1", "PO-3"],
        )

    def test_an_unknown_reference_raises_not_found(self):
        with self.assertRaises(NotFound):
            self.warehouse.purchase_order("PO-404")
        with self.assertRaises(NotFound):
            self.warehouse.receive_purchase_order("PO-404")
        with self.assertRaises(NotFound):
            self.warehouse.cancel_purchase_order("PO-404")


class ReceivePurchaseOrderTests(PurchaseOrderTestCase):
    def test_a_partial_receipt_moves_stock_and_marks_the_order_partial(self):
        self.order()
        order = self.warehouse.receive_purchase_order("PO-1", {"s-1": 4})
        self.assertEqual(order.status, ORDER_PARTIAL)
        self.assertEqual(order.received_units, 4)
        self.assertEqual(order.outstanding_units, 6)
        self.assertEqual(self.warehouse.on_hand("s-1"), 4)
        self.assertEqual(self.warehouse.stock("s-1", "A-01").quantity, 4)

    def test_a_receipt_is_traceable_in_the_movement_log(self):
        self.order()
        self.warehouse.receive_purchase_order("PO-1", {"s-1": 4})
        movements = self.warehouse.movements
        self.assertEqual(len(movements), 1)
        self.assertEqual(movements[0].kind, "receive")
        self.assertEqual(movements[0].reference, "PO-1")
        self.assertEqual(movements[0].units, 4)

    def test_successive_partial_receipts_add_up(self):
        self.order()
        self.warehouse.receive_purchase_order("PO-1", {"s-1": 4})
        order = self.warehouse.receive_purchase_order("PO-1", {"s-1": 6})
        self.assertEqual(order.status, ORDER_RECEIVED)
        self.assertEqual(self.warehouse.on_hand("s-1"), 10)

    def test_receiving_more_than_is_outstanding_is_refused(self):
        self.order()
        self.warehouse.receive_purchase_order("PO-1", {"s-1": 4})
        with self.assertRaises(PurchaseOrderError):
            self.warehouse.receive_purchase_order("PO-1", {"s-1": 7})
        order = self.warehouse.purchase_order("PO-1")
        self.assertEqual(order.received_units, 4)
        self.assertEqual(self.warehouse.on_hand("s-1"), 4)
        self.assertEqual(len(self.warehouse.movements), 1)

    def test_receipts_must_name_a_line_on_the_order(self):
        self.order()
        with self.assertRaises(ValidationError):
            self.warehouse.receive_purchase_order("PO-1", {"s-2": 1})
        self.assertEqual(self.warehouse.purchase_order("PO-1").status, ORDER_OPEN)

    def test_receipt_quantities_must_be_positive_whole_numbers(self):
        self.order()
        for bad in (0, -1, 2.5, "4", True):
            with self.subTest(units=bad):
                with self.assertRaises(ValidationError):
                    self.warehouse.receive_purchase_order("PO-1", {"s-1": bad})
        with self.assertRaises(ValidationError):
            self.warehouse.receive_purchase_order("PO-1", {})
        with self.assertRaises(ValidationError):
            self.warehouse.receive_purchase_order("PO-1", ["s-1", 4])
        self.assertEqual(self.warehouse.purchase_order("PO-1").status, ORDER_OPEN)

    def test_a_full_receipt_takes_everything_outstanding(self):
        self.order()
        order = self.warehouse.receive_purchase_order("PO-1")
        self.assertEqual(order.status, ORDER_RECEIVED)
        self.assertEqual(order.outstanding_units, 0)
        self.assertEqual(self.warehouse.on_hand("s-1"), 10)

    def test_a_full_receipt_completes_what_a_partial_receipt_started(self):
        self.order()
        self.warehouse.receive_purchase_order("PO-1", {"s-1": 4})
        order = self.warehouse.receive_purchase_order("PO-1")
        self.assertEqual(order.status, ORDER_RECEIVED)
        self.assertEqual(order.received_units, 10)
        self.assertEqual(self.warehouse.on_hand("s-1"), 10)

    def test_receiving_a_completed_order_again_is_refused(self):
        self.order()
        self.warehouse.receive_purchase_order("PO-1")
        with self.assertRaises(PurchaseOrderError):
            self.warehouse.receive_purchase_order("PO-1")
        with self.assertRaises(PurchaseOrderError):
            self.warehouse.receive_purchase_order("PO-1", {"s-1": 1})
        self.assertEqual(self.warehouse.on_hand("s-1"), 10)

    def test_a_multi_line_full_receipt_books_every_line(self):
        self.order(
            lines=[
                self.line(sku=self.sku, location=self.bin_a, units=7),
                self.line(sku=self.sku_two, location=self.bin_b, units=4),
            ]
        )
        order = self.warehouse.receive_purchase_order("PO-1")
        self.assertEqual(order.status, ORDER_RECEIVED)
        self.assertEqual(self.warehouse.stock("s-1", "A-01").quantity, 7)
        self.assertEqual(self.warehouse.stock("s-2", "B-01").quantity, 4)
        self.assertEqual(len(self.warehouse.movements), 2)

    def test_receipts_share_the_bin_with_stock_already_there(self):
        self.warehouse.receive("s-1", "A-01", 3)
        self.order()
        self.warehouse.receive_purchase_order("PO-1", {"s-1": 10})
        self.assertEqual(self.warehouse.on_hand("s-1"), 13)

    def test_receipts_leave_reserved_stock_alone(self):
        self.warehouse.receive("s-1", "A-01", 10)
        self.warehouse.reserve("s-1", "A-01", 6)
        self.order()
        self.warehouse.receive_purchase_order("PO-1", {"s-1": 10})
        record = self.warehouse.stock("s-1", "A-01")
        self.assertEqual(record.quantity, 20)
        self.assertEqual(record.reserved, 6)
        self.assertEqual(record.available, 14)


class TransactionalReceiptTests(PurchaseOrderTestCase):
    def two_line_order(self):
        return self.order(
            lines=[
                self.line(sku=self.sku, location=self.bin_a, units=10),
                self.line(sku=self.sku_two, location=self.bin_b, units=10),
            ]
        )

    def test_a_failing_line_rolls_back_the_whole_receipt(self):
        self.two_line_order()
        # B-01 only holds 5 units, so the second line cannot fit.
        with self.assertRaises(CapacityExceeded):
            self.warehouse.receive_purchase_order("PO-1")

        order = self.warehouse.purchase_order("PO-1")
        self.assertEqual(order.status, ORDER_OPEN)
        self.assertEqual(order.received_units, 0)
        self.assertFalse(self.warehouse.has_stock_record("s-1", "A-01"))
        self.assertFalse(self.warehouse.has_stock_record("s-2", "B-01"))
        self.assertEqual(self.warehouse.movements, [])

    def test_a_failed_receipt_leaves_earlier_receipts_intact(self):
        self.two_line_order()
        self.warehouse.receive_purchase_order("PO-1", {"s-1": 4, "s-2": 1})
        self.assertEqual(self.warehouse.on_hand("s-2"), 1)

        with self.assertRaises(CapacityExceeded):
            self.warehouse.receive_purchase_order("PO-1", {"s-1": 1, "s-2": 5})

        order = self.warehouse.purchase_order("PO-1")
        self.assertEqual(order.line("s-1").received_units, 4)
        self.assertEqual(order.line("s-2").received_units, 1)
        self.assertEqual(self.warehouse.on_hand("s-1"), 4)
        self.assertEqual(self.warehouse.on_hand("s-2"), 1)
        self.assertEqual(len(self.warehouse.movements), 2)

    def test_a_successful_receipt_commits(self):
        self.order()
        self.warehouse.receive_purchase_order("PO-1", {"s-1": 5})
        self.assertEqual(self.warehouse.on_hand("s-1"), 5)
        self.assertFalse(self.warehouse.in_transaction)


class WarehouseTransactionTests(PurchaseOrderTestCase):
    def test_a_successful_transaction_commits_its_work(self):
        with self.warehouse.transaction():
            self.warehouse.receive("s-1", "A-01", 5)
            self.warehouse.reserve("s-1", "A-01", 2)
        record = self.warehouse.stock("s-1", "A-01")
        self.assertEqual((record.quantity, record.reserved), (5, 2))
        self.assertEqual(len(self.warehouse.movements), 2)
        self.assertFalse(self.warehouse.in_transaction)

    def test_a_failed_transaction_rolls_everything_back(self):
        self.warehouse.receive("s-1", "A-01", 3)
        with self.assertRaises(ValueError):
            with self.warehouse.transaction():
                self.warehouse.receive("s-1", "A-01", 5)
                self.warehouse.reserve("s-1", "A-01", 1)
                self.warehouse.create_purchase_order("PO-9", "Acme", [self.line()])
                raise ValueError("boom")

        record = self.warehouse.stock("s-1", "A-01")
        self.assertEqual((record.quantity, record.reserved), (3, 0))
        self.assertEqual(len(self.warehouse.movements), 1)
        self.assertEqual(self.warehouse.purchase_orders, [])
        self.assertFalse(self.warehouse.in_transaction)

    def test_transactions_do_not_nest(self):
        with self.assertRaises(ValidationError):
            with self.warehouse.transaction():
                with self.warehouse.transaction():
                    pass  # pragma: no cover - the inner block must not be reached
        self.assertFalse(self.warehouse.in_transaction)

    def test_a_receipt_cannot_be_nested_inside_another_transaction(self):
        self.order()
        with self.assertRaises(ValidationError):
            with self.warehouse.transaction():
                self.warehouse.receive_purchase_order("PO-1", {"s-1": 1})
        self.assertEqual(self.warehouse.purchase_order("PO-1").status, ORDER_OPEN)
        self.assertFalse(self.warehouse.has_stock_record("s-1", "A-01"))


class CancelPurchaseOrderTests(PurchaseOrderTestCase):
    def test_cancelling_an_untouched_order_marks_it_cancelled(self):
        self.order()
        order = self.warehouse.cancel_purchase_order("PO-1")
        self.assertEqual(order.status, ORDER_CANCELLED)
        self.assertTrue(order.cancelled)
        self.assertEqual(self.warehouse.movements, [])

    def test_cancelling_twice_is_refused(self):
        self.order()
        self.warehouse.cancel_purchase_order("PO-1")
        with self.assertRaises(PurchaseOrderError):
            self.warehouse.cancel_purchase_order("PO-1")

    def test_an_order_with_receipts_cannot_be_cancelled(self):
        self.order()
        self.warehouse.receive_purchase_order("PO-1", {"s-1": 2})
        with self.assertRaises(PurchaseOrderError):
            self.warehouse.cancel_purchase_order("PO-1")
        order = self.warehouse.purchase_order("PO-1")
        self.assertEqual(order.status, ORDER_PARTIAL)
        self.assertFalse(order.cancelled)

    def test_a_completed_order_cannot_be_cancelled(self):
        self.order()
        self.warehouse.receive_purchase_order("PO-1")
        with self.assertRaises(PurchaseOrderError):
            self.warehouse.cancel_purchase_order("PO-1")

    def test_cancelled_orders_accept_no_further_receipts(self):
        self.order()
        self.warehouse.cancel_purchase_order("PO-1")
        with self.assertRaises(PurchaseOrderError):
            self.warehouse.receive_purchase_order("PO-1")
        with self.assertRaises(PurchaseOrderError):
            self.warehouse.receive_purchase_order("PO-1", {"s-1": 1})
        self.assertFalse(self.warehouse.has_stock_record("s-1", "A-01"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
