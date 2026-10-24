"""Tests for the append-only audit log, replay, and rebuild-from-log.

The central claim under test is simple and strong: replaying the audit log from
an empty warehouse reproduces the live stock levels exactly, so a rebuild can be
trusted to repair drift.
"""

import contextlib
import dataclasses
import io
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

import inventory
from inventory import (
    STOCK_EFFECTS,
    AuditLog,
    AuditLogError,
    CapacityExceeded,
    Location,
    Movement,
    NotFound,
    Product,
    PurchaseOrderError,
    PurchaseOrderLine,
    SKU,
    SQLiteStore,
    SalesOrderLine,
    StockLevel,
    StorageError,
    Warehouse,
    movement_delta,
    replay_totals,
    stock_level_drift,
)
from inventory.__main__ import main

PACKAGE_ROOT = pathlib.Path(inventory.__file__).resolve().parent.parent


class MovementTests(unittest.TestCase):
    def test_a_movement_defaults_to_an_aware_utc_timestamp(self):
        before = datetime.now(timezone.utc)
        movement = Movement("receive", "s-1", "A-01", 5)
        self.assertGreaterEqual(movement.recorded_at, before)
        self.assertEqual(movement.recorded_at.tzinfo, timezone.utc)

    def test_a_movement_keeps_the_key_it_applies_to(self):
        self.assertEqual(Movement("pick", "s-1", "A-01", 2).key, ("s-1", "A-01"))

    def test_movements_are_immutable(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            Movement("receive", "s-1", "A-01", 1).units = 2  # type: ignore[misc]


class StockEffectTests(unittest.TestCase):
    def test_every_kind_has_an_effect(self):
        self.assertEqual(
            set(STOCK_EFFECTS),
            {
                "receive",
                "pick",
                "reserve",
                "release",
                "transfer-out",
                "transfer-in",
                "adjust",
                "ship",
            },
        )

    def test_effects_have_the_expected_signs(self):
        expected = {
            "receive": (5, 0),
            "transfer-in": (5, 0),
            "adjust": (5, 0),
            "pick": (-5, 0),
            "transfer-out": (-5, 0),
            "reserve": (0, 5),
            "release": (0, -5),
            "ship": (-5, -5),
        }
        for kind, delta in expected.items():
            with self.subTest(kind=kind):
                self.assertEqual(movement_delta(Movement(kind, "s-1", "A-01", 5)), delta)

    def test_a_signed_adjustment_delta_is_applied_as_written(self):
        self.assertEqual(movement_delta(Movement("adjust", "s-1", "A-01", -7)), (-7, 0))

    def test_an_unknown_kind_cannot_be_replayed(self):
        with self.assertRaises(AuditLogError):
            movement_delta(Movement("mystery", "s-1", "A-01", 1))

    def test_only_movements_can_be_replayed(self):
        with self.assertRaises(AuditLogError):
            movement_delta("receive")


class ReplayTests(unittest.TestCase):
    def test_an_empty_log_replays_to_nothing(self):
        self.assertEqual(replay_totals([]), {})

    def test_a_single_receipt_becomes_a_quantity(self):
        self.assertEqual(
            replay_totals([Movement("receive", "s-1", "A-01", 10)]), {("s-1", "A-01"): (10, 0)}
        )

    def test_a_whole_lifecycle_replays(self):
        movements = [
            Movement("receive", "s-1", "A-01", 100),
            Movement("reserve", "s-1", "A-01", 30),
            Movement("release", "s-1", "A-01", 10),
            Movement("pick", "s-1", "A-01", 40),
            Movement("transfer-out", "s-1", "A-01", 15),
            Movement("transfer-in", "s-1", "B-01", 15),
            Movement("reserve", "s-1", "B-01", 8),
            Movement("ship", "s-1", "B-01", 5),
            Movement("adjust", "s-2", "A-01", 3),
        ]
        totals = replay_totals(movements)
        self.assertEqual(totals[("s-1", "A-01")], (100 - 40 - 15, 30 - 10))
        self.assertEqual(totals[("s-1", "B-01")], (15 - 5, 8 - 5))
        self.assertEqual(totals[("s-2", "A-01")], (3, 0))

    def test_each_location_is_tracked_separately(self):
        totals = replay_totals(
            [
                Movement("receive", "s-1", "A-01", 5),
                Movement("receive", "s-1", "B-01", 7),
                Movement("receive", "s-2", "A-01", 2),
            ]
        )
        self.assertEqual(
            totals,
            {("s-1", "A-01"): (5, 0), ("s-1", "B-01"): (7, 0), ("s-2", "A-01"): (2, 0)},
        )

    def test_a_log_that_ships_stock_it_never_received_is_rejected(self):
        with self.assertRaises(AuditLogError) as caught:
            replay_totals([Movement("pick", "s-1", "A-01", 1)])
        self.assertIn("negative quantity", str(caught.exception))

    def test_a_log_that_over_reserves_is_rejected(self):
        with self.assertRaises(AuditLogError) as caught:
            replay_totals(
                [Movement("receive", "s-1", "A-01", 5), Movement("reserve", "s-1", "A-01", 6)]
            )
        self.assertIn("reserves more than it holds", str(caught.exception))

    def test_a_log_that_releases_unreserved_stock_is_rejected(self):
        with self.assertRaises(AuditLogError) as caught:
            replay_totals(
                [Movement("receive", "s-1", "A-01", 5), Movement("release", "s-1", "A-01", 1)]
            )
        self.assertIn("negative reservation", str(caught.exception))


class AuditLogTests(unittest.TestCase):
    def setUp(self):
        self.log = AuditLog()
        self.movement = Movement("receive", "s-1", "A-01", 5)

    def test_appending_is_allowed_and_returns_the_entry(self):
        self.assertIs(self.log.append(self.movement), self.movement)
        self.assertEqual(len(self.log), 1)
        self.assertEqual(self.log.entry(0), self.movement)

    def test_extend_appends_in_order(self):
        first = Movement("receive", "s-1", "A-01", 1)
        second = Movement("pick", "s-1", "A-01", 1)
        self.log.extend([first, second])
        self.assertEqual(list(self.log), [first, second])
        self.assertEqual(self.log.kinds(), ("receive", "pick"))

    def test_a_log_can_be_compared_with_other_sequences(self):
        other = AuditLog([self.movement])
        self.assertEqual(other, AuditLog([self.movement]))
        self.assertEqual(other, [self.movement])
        self.assertEqual(other, (self.movement,))
        self.assertNotEqual(other, AuditLog())

    def test_entries_and_slices_are_snapshots(self):
        self.log.extend([self.movement, Movement("pick", "s-1", "A-01", 1)])
        self.assertEqual(len(self.log.entries()), 2)
        self.assertEqual(self.log[0], self.movement)
        self.assertEqual(len(self.log[0:1]), 1)
        self.assertEqual([m.kind for m in self.log], ["receive", "pick"])
        self.assertIn(self.movement, self.log)
        self.assertEqual(self.log.count(self.movement), 1)

    def test_the_log_refuses_every_mutating_sequence_operation(self):
        self.log.append(self.movement)
        attempts = {
            "assignment": lambda: self.log.__setitem__(0, self.movement),
            "deletion": lambda: self.log.__delitem__(0),
            "insertion": lambda: self.log.insert(0, self.movement),
            "popping": lambda: self.log.pop(),
            "removal": lambda: self.log.remove(self.movement),
            "clearing": lambda: self.log.clear(),
            "reordering": lambda: self.log.reverse(),
            "sorting": lambda: self.log.sort(),
            "in-place concatenation": lambda: self.log.__iadd__([self.movement]),
        }
        for label, attempt in attempts.items():
            with self.subTest(operation=label):
                with self.assertRaises(AuditLogError) as caught:
                    attempt()
                self.assertIn("append-only", str(caught.exception))
        self.assertEqual(len(self.log), 1)

    def test_only_movements_can_be_appended(self):
        for bad in ("receive", 42, None, {"kind": "receive"}):
            with self.subTest(entry=bad):
                with self.assertRaises(AuditLogError):
                    self.log.append(bad)
        with self.assertRaises(AuditLogError):
            self.log.extend("receive")
        self.assertEqual(len(self.log), 0)

    def test_missing_entries_raise_a_log_error(self):
        with self.assertRaises(AuditLogError):
            AuditLog().entry(0)

    def test_rollback_discards_only_an_uncommitted_suffix(self):
        first = Movement("receive", "s-1", "A-01", 1)
        self.log.extend([first, Movement("pick", "s-1", "A-01", 1)])
        self.log.rollback_to(1)
        self.assertEqual(list(self.log), [first])

    def test_rollback_refuses_an_impossible_length(self):
        self.log.append(self.movement)
        for bad in (-1, 2, "1", True):
            with self.subTest(length=bad):
                with self.assertRaises(AuditLogError):
                    self.log.rollback_to(bad)
        self.assertEqual(len(self.log), 1)

    def test_rollback_to_the_current_length_is_a_no_op(self):
        self.log.append(self.movement)
        self.log.rollback_to(1)
        self.assertEqual(len(self.log), 1)

    def test_repr_reports_the_size(self):
        self.log.append(self.movement)
        self.assertEqual(repr(self.log), "AuditLog(1 entries)")


class StockLevelDriftTests(unittest.TestCase):
    def setUp(self):
        self.product = Product("p-1", "Widget", "9.99")
        self.sku = SKU("s-1", self.product)
        self.bin = Location("A-01", "Bin A1")

    def record(self, quantity=10, reserved=0):
        return StockLevel(sku=self.sku, location=self.bin, quantity=quantity, reserved=reserved)

    def test_matching_state_reports_nothing(self):
        movements = [Movement("receive", "s-1", "A-01", 10)]
        self.assertEqual(stock_level_drift(movements, [self.record()]), [])

    def test_a_wrong_quantity_is_reported(self):
        problems = stock_level_drift([Movement("receive", "s-1", "A-01", 10)], [self.record(7)])
        self.assertEqual(len(problems), 1)
        self.assertIn("s-1@A-01", problems[0])
        self.assertIn("quantity=10", problems[0])
        self.assertIn("quantity=7", problems[0])

    def test_a_missing_record_is_reported(self):
        problems = stock_level_drift([Movement("receive", "s-1", "A-01", 10)], [])
        self.assertEqual(len(problems), 1)
        self.assertIn("no record", problems[0])

    def test_a_record_the_log_never_mentions_is_reported(self):
        problems = stock_level_drift([], [self.record()])
        self.assertEqual(len(problems), 1)
        self.assertIn("never mentions it", problems[0])

    def test_a_reservation_disagreement_is_reported(self):
        movements = [
            Movement("receive", "s-1", "A-01", 10),
            Movement("reserve", "s-1", "A-01", 4),
        ]
        self.assertEqual(stock_level_drift(movements, [self.record(10, 4)]), [])
        self.assertEqual(len(stock_level_drift(movements, [self.record(10, 0)])), 1)


class RecordedWarehouseTestCase(unittest.TestCase):
    """A warehouse with stock in two bins, able to exercise every movement kind."""

    def build(self):
        warehouse = Warehouse("Main")
        product = warehouse.add_product(Product("p-1", "Widget", "9.99"))
        gadget = warehouse.add_product(Product("p-2", "Gadget", "4.50"))
        warehouse.add_sku(SKU("s-1", product))
        warehouse.add_sku(SKU("s-2", gadget))
        warehouse.add_location(Location("A-01", "Bin A1", capacity=10_000))
        warehouse.add_location(Location("B-01", "Bin B1", capacity=10_000))
        return warehouse

    def populate(self, warehouse):
        """Drive a warehouse through every operation that moves stock."""
        warehouse.receive("s-1", "A-01", 100)
        warehouse.receive("s-2", "A-01", 40)
        warehouse.set_reorder_point("s-1", 20)

        warehouse.reserve("s-1", "A-01", 30)
        warehouse.release("s-1", "A-01", 10)
        warehouse.pick("s-1", "A-01", 20)
        warehouse.adjust("s-1", "A-01", 60)
        warehouse.adjust("s-2", "A-01", 0)

        warehouse.transfer("s-1", "A-01", "B-01", 15)
        warehouse.receive("s-2", "B-01", 5)

        warehouse.create_purchase_order(
            "PO-1",
            "Acme Supply",
            [PurchaseOrderLine(warehouse.sku("s-1"), warehouse.location("B-01"), 8)],
        )
        warehouse.receive_purchase_order("PO-1", {"s-1": 3})
        warehouse.receive_purchase_order("PO-1")

        warehouse.create_sales_order(
            "SO-1",
            "Ada Lovelace",
            [SalesOrderLine(warehouse.sku("s-1"), warehouse.location("A-01"), 12)],
        )
        warehouse.allocate_sales_order("SO-1")
        warehouse.ship_sales_order("SO-1", {"s-1": 5})
        warehouse.create_sales_order(
            "SO-2",
            "Grace Hopper",
            [SalesOrderLine(warehouse.sku("s-1"), warehouse.location("B-01"), 6)],
        )
        warehouse.allocate_sales_order("SO-2")
        warehouse.cancel_sales_order("SO-2")
        return warehouse

    def snapshot(self, warehouse):
        return [
            (
                record.sku.code,
                record.location.code,
                record.quantity,
                record.reserved,
                record.reorder_point,
            )
            for record in warehouse.stock_levels
        ]


class WarehouseAuditTests(RecordedWarehouseTestCase):
    def test_stock_changes_append_exactly_one_entry_each(self):
        warehouse = self.build()
        warehouse.receive("s-1", "A-01", 10)
        warehouse.transfer("s-1", "A-01", "B-01", 4)
        self.assertEqual(warehouse.audit_log.kinds(), ("receive", "transfer-out", "transfer-in"))
        self.assertEqual(len(warehouse.audit_log), 3)

    def test_each_entry_names_the_sku_the_bin_and_the_units(self):
        warehouse = self.build()
        warehouse.receive("s-1", "A-01", 10, reference="PO-9")
        entry = warehouse.audit_log.entry(0)
        self.assertEqual(entry.kind, "receive")
        self.assertEqual(entry.key, ("s-1", "A-01"))
        self.assertEqual(entry.units, 10)
        self.assertEqual(entry.reference, "PO-9")

    def test_a_transfer_is_recorded_as_two_halves(self):
        warehouse = self.build()
        warehouse.receive("s-1", "A-01", 10)
        warehouse.transfer("s-1", "A-01", "B-01", 4)
        halves = warehouse.audit_log[-2:]
        self.assertEqual([half.kind for half in halves], ["transfer-out", "transfer-in"])
        self.assertEqual(halves[0].key, ("s-1", "A-01"))
        self.assertEqual(halves[1].key, ("s-1", "B-01"))

    def test_the_whole_populated_log_uses_every_known_kind(self):
        warehouse = self.populate(self.build())
        self.assertEqual(set(warehouse.audit_log.kinds()), set(STOCK_EFFECTS))

    def test_the_log_cannot_be_edited_through_the_warehouse(self):
        warehouse = self.populate(self.build())
        size = len(warehouse.audit_log)
        with self.assertRaises(AuditLogError):
            warehouse.audit_log.pop()
        with self.assertRaises(AuditLogError):
            warehouse.audit_log.clear()
        with self.assertRaises(AuditLogError):
            warehouse.audit_log[0] = Movement("receive", "s-1", "A-01", 1)
        self.assertEqual(len(warehouse.audit_log), size)

    def test_the_movements_list_is_a_snapshot_copy(self):
        warehouse = self.build()
        warehouse.receive("s-1", "A-01", 5)
        snapshot = warehouse.movements
        snapshot.append("not a movement")
        self.assertEqual(len(warehouse.audit_log), 1)

    def test_a_rolled_back_transaction_leaves_no_entries(self):
        warehouse = self.build()
        warehouse.receive("s-1", "A-01", 5)
        with self.assertRaises(ValueError):
            with warehouse.transaction():
                warehouse.receive("s-1", "A-01", 5)
                raise ValueError("boom")
        self.assertEqual(len(warehouse.audit_log), 1)
        self.assertEqual(warehouse.audit_log.entry(0).units, 5)
        self.assertEqual(warehouse.stock("s-1", "A-01").quantity, 5)

    def test_a_failed_multi_line_receipt_leaves_no_entries(self):
        warehouse = Warehouse("Tight")
        product = warehouse.add_product(Product("p-1", "Widget", "9.99"))
        warehouse.add_sku(SKU("s-1", product))
        warehouse.add_sku(SKU("s-2", product))
        warehouse.add_location(Location("A-01", "Bin A1", capacity=100))
        warehouse.add_location(Location("B-01", "Small", capacity=2))
        warehouse.create_purchase_order(
            "PO-1",
            "Acme",
            [
                PurchaseOrderLine(warehouse.sku("s-1"), warehouse.location("A-01"), 5),
                PurchaseOrderLine(warehouse.sku("s-2"), warehouse.location("B-01"), 5),
            ],
        )
        with self.assertRaises(PurchaseOrderError):
            warehouse.receive_purchase_order("PO-1", {"s-1": 6})
        # B-01 only holds 2, so the second line cannot fit.
        with self.assertRaises(CapacityExceeded):
            warehouse.receive_purchase_order("PO-1")
        self.assertEqual(len(warehouse.audit_log), 0)
        self.assertEqual(warehouse.stock_levels, [])


class WarehouseRebuildTests(RecordedWarehouseTestCase):
    def test_a_populated_warehouse_has_no_drift(self):
        warehouse = self.populate(self.build())
        self.assertEqual(warehouse.stock_level_drift(), [])
        warehouse.verify_stock_levels()

    def test_rebuild_reproduces_the_live_state_exactly(self):
        warehouse = self.populate(self.build())
        live = self.snapshot(warehouse)
        self.assertTrue(live)

        rebuilt = warehouse.rebuild_stock_levels()

        self.assertEqual(self.snapshot(warehouse), live)
        self.assertEqual(
            [(record.sku.code, record.location.code) for record in rebuilt],
            [(row[0], row[1]) for row in live],
        )
        self.assertEqual(warehouse.stock_level_drift(), [])

    def test_rebuild_produces_the_same_quantities_a_fresh_run_would(self):
        warehouse = self.populate(self.build())
        expected = {
            ("s-1", "A-01"): (warehouse.stock("s-1", "A-01").quantity,
                              warehouse.stock("s-1", "A-01").reserved),
            ("s-1", "B-01"): (warehouse.stock("s-1", "B-01").quantity,
                              warehouse.stock("s-1", "B-01").reserved),
            ("s-2", "A-01"): (0, 0),
        }
        warehouse.rebuild_stock_levels()
        for key, totals in expected.items():
            with self.subTest(key=key):
                record = warehouse.stock(*key)
                self.assertEqual((record.quantity, record.reserved), totals)

    def test_rebuild_is_idempotent(self):
        warehouse = self.populate(self.build())
        first = self.snapshot(warehouse)
        warehouse.rebuild_stock_levels()
        warehouse.rebuild_stock_levels()
        self.assertEqual(self.snapshot(warehouse), first)

    def test_rebuild_keeps_reorder_points(self):
        warehouse = self.populate(self.build())
        before = sorted((r.sku.code, r.reorder_point) for r in warehouse.stock_levels)
        warehouse.rebuild_stock_levels()
        after = sorted((r.sku.code, r.reorder_point) for r in warehouse.stock_levels)
        self.assertEqual(after, before)
        self.assertEqual(warehouse.reorder_point("s-1"), 20)
        self.assertEqual(warehouse.stock("s-1", "A-01").reorder_point, 20)

    def test_rebuild_keeps_zero_quantity_records_the_log_knows_about(self):
        warehouse = self.build()
        warehouse.receive("s-1", "A-01", 5)
        warehouse.pick("s-1", "A-01", 5)
        warehouse.rebuild_stock_levels()
        record = warehouse.stock("s-1", "A-01")
        self.assertEqual((record.quantity, record.reserved), (0, 0))
        self.assertEqual(warehouse.stock_level_drift(), [])

    def test_rebuild_repairs_a_corrupted_record(self):
        warehouse = self.populate(self.build())
        live = self.snapshot(warehouse)
        warehouse.stock("s-1", "A-01").quantity += 7

        problems = warehouse.stock_level_drift()
        self.assertEqual(len(problems), 1)
        self.assertIn("s-1@A-01", problems[0])
        with self.assertRaises(AuditLogError):
            warehouse.verify_stock_levels()

        warehouse.rebuild_stock_levels()
        self.assertEqual(self.snapshot(warehouse), live)
        self.assertEqual(warehouse.stock_level_drift(), [])

    def test_rebuild_repairs_a_dropped_record(self):
        warehouse = self.populate(self.build())
        live = self.snapshot(warehouse)
        warehouse._stock.clear()  # simulate a lost row

        self.assertEqual(len(warehouse.stock_level_drift()), len(live))
        warehouse.rebuild_stock_levels()
        self.assertEqual(self.snapshot(warehouse), live)

    def test_rebuild_drops_records_the_log_never_mentions(self):
        warehouse = self.build()
        warehouse.restore(
            stock_levels=[
                StockLevel(
                    sku=warehouse.sku("s-1"),
                    location=warehouse.location("A-01"),
                    quantity=9,
                )
            ]
        )
        self.assertEqual(len(warehouse.stock_level_drift()), 1)
        self.assertEqual(warehouse.rebuild_stock_levels(), [])
        self.assertEqual(warehouse.stock_levels, [])
        self.assertEqual(warehouse.stock_level_drift(), [])

    def test_an_empty_warehouse_rebuilds_to_nothing(self):
        warehouse = self.build()
        self.assertEqual(warehouse.rebuild_stock_levels(), [])
        self.assertEqual(warehouse.stock_levels, [])

    def test_rebuild_refuses_a_log_naming_an_unregistered_sku(self):
        warehouse = self.build()
        warehouse.restore(movements=[Movement("receive", "s-404", "A-01", 5)])
        with self.assertRaises(NotFound):
            warehouse.rebuild_stock_levels()

    def test_rebuild_refuses_a_log_naming_an_unregistered_location(self):
        warehouse = self.build()
        warehouse.restore(movements=[Movement("receive", "s-1", "L-404", 5)])
        with self.assertRaises(NotFound):
            warehouse.rebuild_stock_levels()

    def test_rebuild_refuses_an_unreplayable_log_and_changes_nothing(self):
        warehouse = self.populate(self.build())
        live = self.snapshot(warehouse)
        warehouse.audit_log.append(Movement("mystery", "s-1", "A-01", 5))

        with self.assertRaises(AuditLogError):
            warehouse.rebuild_stock_levels()
        self.assertEqual(self.snapshot(warehouse), live)

    def test_rebuild_after_a_rolled_back_receipt_still_matches(self):
        warehouse = self.build()
        warehouse.receive("s-1", "A-01", 10)
        with self.assertRaises(ValueError):
            with warehouse.transaction():
                warehouse.receive("s-1", "A-01", 5)
                raise ValueError("boom")
        live = self.snapshot(warehouse)
        warehouse.rebuild_stock_levels()
        self.assertEqual(self.snapshot(warehouse), live)
        self.assertEqual(warehouse.stock_level_drift(), [])


class SQLiteRebuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "audit.db")

    def populated_store(self):
        warehouse = Warehouse("Main")
        product = warehouse.add_product(Product("p-1", "Widget", "9.99"))
        warehouse.add_sku(SKU("s-1", product))
        warehouse.add_location(Location("A-01", "Bin A1", capacity=10_000))
        warehouse.add_location(Location("B-01", "Bin B1", capacity=10_000))
        warehouse.set_reorder_point("s-1", 4)
        warehouse.receive("s-1", "A-01", 50, reference="PO-1")
        warehouse.reserve("s-1", "A-01", 10)
        warehouse.transfer("s-1", "A-01", "B-01", 5)
        warehouse.adjust("s-1", "B-01", 9)

        store = SQLiteStore(self.path)
        self.addCleanup(store.close)
        store.save_warehouse(warehouse)
        return store

    def rows(self, store):
        return sorted(
            (
                record.sku.code,
                record.location.code,
                record.quantity,
                record.reserved,
                record.reorder_point,
            )
            for record in store.list_stock_levels()
        )

    def corrupt(self, store):
        store.connection.execute(
            "UPDATE stock_levels SET quantity = 999, reserved = 0 WHERE sku_code = 's-1'"
        )

    def test_the_stored_log_round_trips(self):
        store = self.populated_store()
        log = store.audit_log()
        self.assertIsInstance(log, AuditLog)
        self.assertEqual(
            log.kinds(), ("receive", "reserve", "transfer-out", "transfer-in", "adjust")
        )
        self.assertEqual(log.entry(0).reference, "PO-1")

    def test_a_freshly_saved_warehouse_has_no_drift(self):
        store = self.populated_store()
        self.assertEqual(store.stock_level_drift(), [])
        store.verify_stock_levels()

    def test_drift_is_detected_in_the_database(self):
        store = self.populated_store()
        self.corrupt(store)
        self.assertTrue(store.stock_level_drift())
        with self.assertRaises(StorageError):
            store.verify_stock_levels()

    def test_rebuild_repairs_drifted_rows(self):
        store = self.populated_store()
        before = self.rows(store)
        self.corrupt(store)
        self.assertTrue(store.stock_level_drift())

        rebuilt = store.rebuild_stock_levels()

        self.assertEqual(self.rows(store), before)
        self.assertEqual(rebuilt, len(before))
        self.assertEqual(store.stock_level_drift(), [])

    def test_rebuild_drops_rows_the_log_never_mentions(self):
        store = self.populated_store()
        store.save_stock_level(
            StockLevel(
                sku=store.get_sku("s-1"), location=store.get_location("B-01"), quantity=77
            )
        )
        self.assertTrue(store.stock_level_drift())
        store.rebuild_stock_levels()
        self.assertEqual(store.get_stock_level("s-1", "B-01").quantity, 9)
        self.assertEqual(store.stock_level_drift(), [])

    def test_a_rebuilt_warehouse_matches_the_one_that_was_saved(self):
        store = self.populated_store()
        expected = store.load_warehouse("Main")
        live = [
            (r.sku.code, r.location.code, r.quantity, r.reserved, r.reorder_point)
            for r in expected.stock_levels
        ]

        store.rebuild_stock_levels()
        rebuilt = store.load_warehouse("Main")

        self.assertEqual(
            [
                (r.sku.code, r.location.code, r.quantity, r.reserved, r.reorder_point)
                for r in rebuilt.stock_levels
            ],
            live,
        )
        self.assertEqual(rebuilt.stock_level_drift(), [])
        self.assertEqual(rebuilt.stock_levels, expected.stock_levels)

    def test_rebuild_refuses_a_log_naming_an_unknown_sku_and_changes_nothing(self):
        store = self.populated_store()
        store.connection.execute(
            "INSERT INTO movements (kind, sku_code, location_code, units, recorded_at) "
            "VALUES ('receive', 's-404', 'A-01', 5, '2024-01-01T00:00:00+00:00')"
        )
        before = self.rows(store)
        with self.assertRaises(NotFound):
            store.rebuild_stock_levels()
        self.assertEqual(self.rows(store), before)

    def test_rebuild_on_a_database_with_no_movements_clears_the_rows(self):
        store = SQLiteStore(self.path)
        self.addCleanup(store.close)
        store.save_product(Product("p-1", "Widget", "9.99"))
        store.save_sku(SKU("s-1", store.get_product("p-1")))
        store.save_location(Location("A-01", "Bin A1"))
        store.save_stock_level(
            StockLevel(
                sku=store.get_sku("s-1"), location=store.get_location("A-01"), quantity=3
            )
        )
        self.assertEqual(store.rebuild_stock_levels(), 0)
        self.assertEqual(store.list_stock_levels(), [])


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "command.db")

        store = SQLiteStore(self.path)
        self.addCleanup(store.close)
        warehouse = Warehouse("Main")
        product = warehouse.add_product(Product("p-1", "Widget", "9.99"))
        warehouse.add_sku(SKU("s-1", product))
        warehouse.add_location(Location("A-01", "Bin A1"))
        warehouse.receive("s-1", "A-01", 12)
        warehouse.pick("s-1", "A-01", 2)
        store.save_warehouse(warehouse)
        self.store = store

    def run_main(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
            code = main(argv)
        return code, buffer.getvalue()

    def corrupt(self):
        self.store.connection.execute(
            "UPDATE stock_levels SET quantity = 99 WHERE sku_code = 's-1'"
        )

    def test_verify_succeeds_on_a_consistent_database(self):
        code, output = self.run_main(["verify", self.path])
        self.assertEqual(code, 0)
        self.assertIn("match the audit log", output)
        self.assertIn("2 movement(s)", output)

    def test_verify_reports_drift_and_exits_non_zero(self):
        self.corrupt()
        code, output = self.run_main(["verify", self.path])
        self.assertEqual(code, 1)
        self.assertIn("disagree", output)
        self.assertIn("s-1@A-01", output)
        self.assertIn("rebuild", output)

    def test_rebuild_repairs_the_database(self):
        self.corrupt()
        code, output = self.run_main(["rebuild", self.path])
        self.assertEqual(code, 0)
        self.assertIn("rebuilt 1 stock record(s)", output)

        code, _ = self.run_main(["verify", self.path])
        self.assertEqual(code, 0)
        self.assertEqual(self.store.get_stock_level("s-1", "A-01").quantity, 10)

    def test_an_unopenable_database_is_reported(self):
        code, _ = self.run_main(
            ["verify", os.path.join(self.tmp.name, "missing-directory", "db.sqlite")]
        )
        self.assertEqual(code, 2)

    def test_the_parser_demands_a_known_subcommand_and_a_database(self):
        for argv in ([], ["frobnicate", self.path], ["verify"]):
            with self.subTest(argv=argv):
                with self.assertRaises(SystemExit):
                    with contextlib.redirect_stderr(io.StringIO()):
                        main(argv)

    def _run_module(self, *args):
        with subprocess.Popen(
            [sys.executable, "-m", "inventory", *args],
            cwd=str(PACKAGE_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as process:
            stdout, stderr = process.communicate(timeout=120)
        return process.returncode, stdout, stderr

    def test_the_real_command_runs_as_a_module(self):
        code, stdout, stderr = self._run_module("verify", self.path)
        self.assertEqual(code, 0, stderr)
        self.assertIn("match the audit log", stdout)

    def test_the_real_command_reports_drift_and_can_repair_it(self):
        self.corrupt()
        self.store.close()

        code, stdout, stderr = self._run_module("verify", self.path)
        self.assertEqual(code, 1, stderr)
        self.assertIn("s-1@A-01", stdout)

        code, stdout, stderr = self._run_module("rebuild", self.path)
        self.assertEqual(code, 0, stderr)
        self.assertIn("rebuilt", stdout)

        reopened = SQLiteStore(self.path)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.get_stock_level("s-1", "A-01").quantity, 10)
        self.assertEqual(reopened.stock_level_drift(), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
