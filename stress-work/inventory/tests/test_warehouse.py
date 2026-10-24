"""Unit tests for the Warehouse service: registration, movements and reports."""

import unittest

from inventory import (
    CapacityExceeded,
    DuplicateEntity,
    InsufficientStock,
    Location,
    NotFound,
    Product,
    SKU,
    ValidationError,
    Warehouse,
)


class WarehouseTestCase(unittest.TestCase):
    """Shared fixtures: one product, one SKU and three locations."""

    def setUp(self):
        self.warehouse = Warehouse("Main")
        self.product = self.warehouse.add_product(Product("p-1", "Widget", "9.99"))
        self.sku = self.warehouse.add_sku(SKU("s-1", self.product))
        self.bin_a = self.warehouse.add_location(Location("A-01", "Bin A1", capacity=100))
        self.bin_b = self.warehouse.add_location(Location("B-01", "Bin B1", capacity=5))
        self.overflow = self.warehouse.add_location(Location("Z-99", "Overflow Yard"))


class RegistrationTests(WarehouseTestCase):
    def test_duplicate_entities_are_rejected(self):
        with self.assertRaises(DuplicateEntity):
            self.warehouse.add_product(Product("p-1", "Widget again"))
        with self.assertRaises(DuplicateEntity):
            self.warehouse.add_sku(SKU("s-1", self.product))
        with self.assertRaises(DuplicateEntity):
            self.warehouse.add_location(Location("A-01", "Different name"))

    def test_sku_requires_a_registered_product(self):
        orphan = SKU("s-2", Product("p-999", "Ghost"))
        with self.assertRaises(NotFound):
            self.warehouse.add_sku(orphan)
        self.assertFalse(self.warehouse.skus.count(orphan))

    def test_unknown_entities_raise_not_found(self):
        with self.assertRaises(NotFound):
            self.warehouse.product("nope")
        with self.assertRaises(NotFound):
            self.warehouse.sku("nope")
        with self.assertRaises(NotFound):
            self.warehouse.location("nope")


class ReceiveTests(WarehouseTestCase):
    def test_receive_creates_record_and_logs_movement(self):
        record = self.warehouse.receive("s-1", "A-01", 12, reference="PO-1")
        self.assertEqual(record.quantity, 12)
        self.assertEqual(record.location.code, "A-01")
        self.assertEqual(self.warehouse.location_occupancy("A-01"), 12)

        movements = self.warehouse.movements
        self.assertEqual(len(movements), 1)
        self.assertEqual(movements[0].kind, "receive")
        self.assertEqual(movements[0].units, 12)
        self.assertEqual(movements[0].reference, "PO-1")
        self.assertIsNotNone(movements[0].recorded_at)

    def test_receive_accumulates_and_reports_on_hand(self):
        self.warehouse.receive("s-1", "A-01", 12)
        self.warehouse.receive("s-1", "B-01", 3)
        self.warehouse.receive("s-1", "A-01", 8)
        self.assertEqual(self.warehouse.stock("s-1", "A-01").quantity, 20)
        self.assertEqual(self.warehouse.on_hand("s-1"), 23)

    def test_receive_respects_capacity(self):
        self.warehouse.receive("s-1", "B-01", 5)
        with self.assertRaises(CapacityExceeded):
            self.warehouse.receive("s-1", "B-01", 1)
        self.assertEqual(self.warehouse.stock("s-1", "B-01").quantity, 5)

    def test_unbounded_location_has_no_capacity_limit(self):
        self.warehouse.receive("s-1", "Z-99", 5000)
        self.assertEqual(self.warehouse.stock("s-1", "Z-99").quantity, 5000)

    def test_capacity_is_shared_across_skus(self):
        second = self.warehouse.add_sku(SKU("s-2", self.product))
        self.warehouse.receive("s-1", "B-01", 4)
        self.warehouse.receive("s-2", "B-01", 1)
        with self.assertRaises(CapacityExceeded):
            self.warehouse.receive(second.code, "B-01", 1)

    def test_receive_rejects_non_positive_quantities(self):
        for bad in (0, -1, "3", True):
            with self.subTest(units=bad):
                with self.assertRaises(ValidationError):
                    self.warehouse.receive("s-1", "A-01", bad)


class PickAndReserveTests(WarehouseTestCase):
    def test_pick_reduces_on_hand_stock(self):
        self.warehouse.receive("s-1", "A-01", 10)
        record = self.warehouse.pick("s-1", "A-01", 4, reference="SO-7")
        self.assertEqual(record.quantity, 6)
        self.assertEqual(self.warehouse.movements[-1].kind, "pick")

    def test_pick_beyond_availability_raises(self):
        self.warehouse.receive("s-1", "A-01", 10)
        self.warehouse.reserve("s-1", "A-01", 6)
        with self.assertRaises(InsufficientStock):
            self.warehouse.pick("s-1", "A-01", 5)
        self.assertEqual(self.warehouse.stock("s-1", "A-01").quantity, 10)

    def test_reserve_does_not_change_on_hand_but_reduces_availability(self):
        self.warehouse.receive("s-1", "A-01", 10)
        record = self.warehouse.reserve("s-1", "A-01", 4)
        self.assertEqual(record.quantity, 10)
        self.assertEqual(record.reserved, 4)
        self.assertEqual(self.warehouse.available("s-1"), 6)
        self.assertEqual(self.warehouse.on_hand("s-1"), 10)

        record = self.warehouse.release("s-1", "A-01", 4)
        self.assertEqual(record.reserved, 0)
        self.assertEqual(self.warehouse.available("s-1"), 10)

    def test_movements_against_unknown_stock_raise_not_found(self):
        with self.assertRaises(NotFound):
            self.warehouse.pick("s-1", "A-01", 1)
        with self.assertRaises(NotFound):
            self.warehouse.stock("s-1", "A-01")


class TransferTests(WarehouseTestCase):
    def test_transfer_moves_units_and_logs_both_sides(self):
        self.warehouse.receive("s-1", "A-01", 10)
        source, destination = self.warehouse.transfer("s-1", "A-01", "Z-99", 4)
        self.assertEqual(source.quantity, 6)
        self.assertEqual(destination.quantity, 4)
        self.assertEqual([m.kind for m in self.warehouse.movements[-2:]], ["transfer-out", "transfer-in"])

    def test_transfer_into_full_destination_leaves_stock_untouched(self):
        self.warehouse.receive("s-1", "A-01", 10)
        self.warehouse.receive("s-1", "B-01", 3)
        with self.assertRaises(CapacityExceeded):
            self.warehouse.transfer("s-1", "A-01", "B-01", 4)
        self.assertEqual(self.warehouse.stock("s-1", "A-01").quantity, 10)
        self.assertEqual(self.warehouse.stock("s-1", "B-01").quantity, 3)

    def test_transfer_cannot_move_reserved_stock_or_into_itself(self):
        self.warehouse.receive("s-1", "A-01", 5)
        self.warehouse.reserve("s-1", "A-01", 4)
        with self.assertRaises(InsufficientStock):
            self.warehouse.transfer("s-1", "A-01", "Z-99", 2)
        with self.assertRaises(ValidationError):
            self.warehouse.transfer("s-1", "A-01", "A-01", 1)


class AdjustTests(WarehouseTestCase):
    def test_adjust_sets_the_counted_quantity_and_logs_the_delta(self):
        self.warehouse.receive("s-1", "A-01", 10)
        record = self.warehouse.adjust("s-1", "A-01", 7, reference="stocktake-1")
        self.assertEqual(record.quantity, 7)
        self.assertEqual(self.warehouse.movements[-1].kind, "adjust")
        self.assertEqual(self.warehouse.movements[-1].units, -3)

        record = self.warehouse.adjust("s-1", "A-01", 25)
        self.assertEqual(record.quantity, 25)
        self.assertEqual(self.warehouse.movements[-1].units, 18)

    def test_adjust_cannot_drop_below_reserved(self):
        self.warehouse.receive("s-1", "A-01", 10)
        self.warehouse.reserve("s-1", "A-01", 6)
        with self.assertRaises(InsufficientStock):
            self.warehouse.adjust("s-1", "A-01", 5)
        self.assertEqual(self.warehouse.stock("s-1", "A-01").quantity, 10)

    def test_adjust_respects_capacity(self):
        with self.assertRaises(CapacityExceeded):
            self.warehouse.adjust("s-1", "B-01", 6)
        with self.assertRaises(ValidationError):
            self.warehouse.adjust("s-1", "B-01", -1)


class ReportingTests(WarehouseTestCase):
    def test_reorder_points_apply_to_existing_and_future_records(self):
        self.warehouse.set_reorder_point("s-1", 5)
        record = self.warehouse.receive("s-1", "A-01", 5)
        self.assertEqual(record.reorder_point, 5)
        self.assertTrue(record.is_low)
        self.assertEqual(self.warehouse.low_stock(), [record])

        self.warehouse.receive("s-1", "A-01", 1)
        self.assertEqual(self.warehouse.low_stock(), [])

        future = self.warehouse.receive("s-1", "Z-99", 2)
        self.assertEqual(future.reorder_point, 5)
        self.assertIn(future, self.warehouse.low_stock())

    def test_records_for_is_sorted_by_location_code(self):
        self.warehouse.receive("s-1", "Z-99", 1)
        self.warehouse.receive("s-1", "A-01", 2)
        codes = [record.location.code for record in self.warehouse.records_for("s-1")]
        self.assertEqual(codes, ["A-01", "Z-99"])
        self.assertEqual([record.quantity for record in self.warehouse.records_for("s-1")], [2, 1])

    def test_movements_property_returns_a_defensive_copy(self):
        self.warehouse.receive("s-1", "A-01", 1)
        snapshot = self.warehouse.movements
        snapshot.append("not a movement")
        self.assertEqual(len(self.warehouse.movements), 1)

    def test_reports_on_unknown_skus_raise_not_found(self):
        with self.assertRaises(NotFound):
            self.warehouse.on_hand("s-404")
        with self.assertRaises(NotFound):
            self.warehouse.available("s-404")
        with self.assertRaises(NotFound):
            self.warehouse.location_occupancy("L-404")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
