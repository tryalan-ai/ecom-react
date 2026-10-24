"""Unit tests for the SQLite persistence layer."""

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from inventory import (
    LATEST_VERSION,
    MIGRATIONS,
    CapacityExceeded,
    Location,
    Migration,
    Movement,
    NotFound,
    Product,
    SKU,
    SQLiteStore,
    StorageError,
    StockLevel,
    ValidationError,
    Warehouse,
)

TABLE_NAMES = {
    "products",
    "skus",
    "locations",
    "stock_levels",
    "movements",
    "reorder_points",
    "schema_migrations",
}


class StoreTestCase(unittest.TestCase):
    """A fresh in-memory store with one product, one SKU and two bins."""

    def setUp(self):
        self.store = SQLiteStore()
        self.addCleanup(self.store.close)
        self.product = self.store.save_product(
            Product("p-1", "Widget", "9.99", category="toys")
        )
        self.sku = self.store.save_sku(SKU("s-1", self.product, barcode="0123456789"))
        self.bin_a = self.store.save_location(Location("A-01", "Bin A1", capacity=100))
        self.bin_b = self.store.save_location(Location("B-01", "Bin B1", capacity=5))


class MigrationApplicationTests(StoreTestCase):
    def test_opening_applies_every_migration(self):
        self.assertEqual(self.store.schema_version, LATEST_VERSION)
        self.assertEqual(
            [migration.version for migration in self.store.applied_migrations()],
            [migration.version for migration in MIGRATIONS],
        )

    def test_migrate_is_idempotent(self):
        self.assertEqual(self.store.migrate(), [])
        self.assertEqual(self.store.schema_version, LATEST_VERSION)

    def test_schema_holds_the_expected_tables(self):
        names = {
            row["name"]
            for row in self.store.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        self.assertTrue(TABLE_NAMES.issubset(names), sorted(TABLE_NAMES - names))

    def test_a_failing_migration_is_reported_and_not_recorded(self):
        broken = Migration(LATEST_VERSION + 1, "broken", "THIS IS NOT VALID SQL")
        with self.assertRaises(StorageError):
            self.store.migrate(list(MIGRATIONS) + [broken])
        self.assertEqual(self.store.schema_version, LATEST_VERSION)

    def test_a_schema_from_a_newer_build_is_refused(self):
        self.store.connection.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (LATEST_VERSION + 5, "from the future", datetime.now(timezone.utc).isoformat()),
        )
        with self.assertRaises(StorageError):
            self.store.applied_migrations()

    def test_blank_path_is_rejected(self):
        with self.assertRaises(StorageError):
            SQLiteStore("   ")


class ProductPersistenceTests(StoreTestCase):
    def test_product_round_trips_exactly(self):
        loaded = self.store.get_product("p-1")
        self.assertEqual(loaded, self.product)
        self.assertEqual(loaded.unit_price, Decimal("9.99"))
        self.assertEqual(loaded.category, "toys")

    def test_money_is_stored_as_an_exact_decimal_string(self):
        self.store.save_product(Product("p-2", "Gadget", "2.5"))
        row = self.store.connection.execute(
            "SELECT unit_price FROM products WHERE product_id = 'p-2'"
        ).fetchone()
        self.assertEqual(row["unit_price"], "2.50")
        self.assertEqual(self.store.get_product("p-2").unit_price, Decimal("2.50"))

    def test_saving_the_same_product_updates_it(self):
        self.store.save_product(Product("p-1", "Widget Mk II", "12.00", category="tools"))
        loaded = self.store.get_product("p-1")
        self.assertEqual(loaded.name, "Widget Mk II")
        self.assertEqual(loaded.unit_price, Decimal("12.00"))
        self.assertEqual(loaded.category, "tools")
        self.assertEqual(self.store.count_products(), 1)

    def test_missing_product_raises_not_found(self):
        with self.assertRaises(NotFound):
            self.store.get_product("p-404")

    def test_products_are_listed_in_id_order(self):
        self.store.save_products([Product("p-3", "Zeta"), Product("p-2", "Beta")])
        self.assertEqual([p.product_id for p in self.store.list_products()], ["p-1", "p-2", "p-3"])


class SkuPersistenceTests(StoreTestCase):
    def test_sku_round_trips_with_its_product(self):
        loaded = self.store.get_sku("s-1")
        self.assertEqual(loaded, self.sku)
        self.assertEqual(loaded.product, self.product)
        self.assertEqual(loaded.barcode, "0123456789")
        self.assertTrue(loaded.is_scannable)
        self.assertEqual(loaded.pack_size, 1)

    def test_sku_without_a_barcode_round_trips_as_none(self):
        self.store.save_sku(SKU("s-2", self.product, unit_of_measure="case", pack_size=12))
        loaded = self.store.get_sku("s-2")
        self.assertIsNone(loaded.barcode)
        self.assertFalse(loaded.is_scannable)
        self.assertEqual(loaded.unit_of_measure, "case")
        self.assertEqual(loaded.pack_size, 12)

    def test_sku_cannot_be_stored_without_its_product(self):
        with self.assertRaises(NotFound):
            self.store.save_sku(SKU("s-9", Product("p-404", "Ghost")))
        with self.assertRaises(NotFound):
            self.store.get_sku("s-9")

    def test_storing_an_sku_does_not_store_its_product_implicitly(self):
        with self.assertRaises(NotFound):
            self.store.get_product("p-404")

    def test_foreign_key_blocks_deleting_a_product_in_use(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute("DELETE FROM products WHERE product_id = 'p-1'")


class LocationPersistenceTests(StoreTestCase):
    def test_bounded_location_round_trips(self):
        self.assertEqual(self.store.get_location("A-01"), self.bin_a)
        self.assertTrue(self.store.get_location("A-01").is_bounded)

    def test_unbounded_capacity_round_trips_as_none(self):
        self.store.save_location(Location("Z-99", "Overflow Yard"))
        loaded = self.store.get_location("Z-99")
        self.assertIsNone(loaded.capacity)
        self.assertFalse(loaded.is_bounded)

    def test_locations_are_listed_in_code_order(self):
        self.store.save_locations([Location("C-01", "C"), Location("B-02", "B")])
        self.assertEqual(
            [location.code for location in self.store.list_locations()],
            ["A-01", "B-01", "B-02", "C-01"],
        )

    def test_missing_location_raises_not_found(self):
        with self.assertRaises(NotFound):
            self.store.get_location("L-404")


class StockLevelPersistenceTests(StoreTestCase):
    def record(self, **kwargs):
        defaults = {
            "sku": self.sku,
            "location": self.bin_a,
            "quantity": 10,
            "reserved": 4,
            "reorder_point": 3,
        }
        defaults.update(kwargs)
        return StockLevel(**defaults)

    def test_stock_level_round_trips(self):
        saved = self.store.save_stock_level(self.record())
        loaded = self.store.get_stock_level("s-1", "A-01")
        self.assertEqual(loaded.quantity, 10)
        self.assertEqual(loaded.reserved, 4)
        self.assertEqual(loaded.reorder_point, 3)
        self.assertEqual(loaded.available, 6)
        self.assertEqual(loaded.sku, saved.sku)
        self.assertEqual(loaded.location, saved.location)

    def test_stock_levels_can_be_updated_in_place(self):
        self.store.save_stock_level(self.record())
        self.store.save_stock_level(self.record(quantity=25, reserved=0))
        loaded = self.store.get_stock_level("s-1", "A-01")
        self.assertEqual((loaded.quantity, loaded.reserved), (25, 0))
        self.assertEqual(len(self.store.list_stock_levels()), 1)

    def test_stock_cannot_be_stored_for_an_unknown_sku_or_location(self):
        with self.assertRaises(NotFound):
            self.store.save_stock_level(self.record(sku=SKU("s-404", self.product)))
        with self.assertRaises(NotFound):
            self.store.save_stock_level(self.record(location=Location("L-404", "Ghost")))

    def test_missing_stock_record_raises_not_found(self):
        with self.assertRaises(NotFound):
            self.store.get_stock_level("s-1", "B-01")

    def test_stock_levels_are_ordered_and_filterable(self):
        self.store.save_stock_levels(
            [self.record(location=self.bin_b, quantity=2, reserved=0), self.record()]
        )
        self.assertEqual(
            [
                (record.sku.code, record.location.code)
                for record in self.store.list_stock_levels()
            ],
            [("s-1", "A-01"), ("s-1", "B-01")],
        )
        self.assertEqual(len(self.store.list_stock_for("s-1")), 2)
        self.assertEqual(self.store.list_stock_for("s-404"), [])

    def test_schema_forbids_negative_quantity(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "INSERT INTO stock_levels (sku_code, location_code, quantity) "
                "VALUES ('s-1', 'A-01', -1)"
            )

    def test_schema_forbids_reserving_more_than_is_held(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "INSERT INTO stock_levels (sku_code, location_code, quantity, reserved) "
                "VALUES ('s-1', 'A-01', 1, 2)"
            )

    def test_schema_forbids_a_non_positive_pack_size(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "INSERT INTO skus (code, product_id, unit_of_measure, pack_size) "
                "VALUES ('s-bad', 'p-1', 'each', 0)"
            )


class MovementPersistenceTests(StoreTestCase):
    def test_movements_round_trip_in_order_with_their_timestamp(self):
        warehouse = Warehouse("Main")
        warehouse.add_product(self.product)
        warehouse.add_sku(self.sku)
        warehouse.add_location(self.bin_a)
        warehouse.receive("s-1", "A-01", 10, reference="PO-1")
        warehouse.reserve("s-1", "A-01", 4)
        self.store.save_movements(warehouse.movements)

        loaded = self.store.list_movements()
        self.assertEqual([movement.kind for movement in loaded], ["receive", "reserve"])
        self.assertEqual(loaded[0].reference, "PO-1")
        self.assertIsNone(loaded[1].reference)
        self.assertEqual(loaded[0].recorded_at, warehouse.movements[0].recorded_at)
        self.assertEqual(loaded[0].recorded_at.tzinfo, timezone.utc)

    def test_the_log_is_append_only(self):
        movement = _movement("adjust", "s-1", "A-01", -3)
        self.store.save_movement(movement)
        self.store.save_movement(movement)
        self.assertEqual(self.store.count_movements(), 2)

    def test_movements_can_be_filtered_and_capped(self):
        self.store.save_movements(
            [
                _movement("receive", "s-1", "A-01", 10),
                _movement("receive", "s-2", "A-01", 5),
                _movement("pick", "s-1", "A-01", 2),
            ]
        )
        self.assertEqual(len(self.store.list_movements()), 3)
        self.assertEqual(
            [movement.kind for movement in self.store.list_movements(sku_code="s-1")],
            ["receive", "pick"],
        )
        self.assertEqual(len(self.store.list_movements(limit=2)), 2)
        self.assertEqual(self.store.list_movements(limit=0), [])

    def test_an_invalid_limit_is_rejected(self):
        for bad in (-1, "2", True):
            with self.subTest(limit=bad):
                with self.assertRaises(StorageError):
                    self.store.list_movements(limit=bad)


class ReorderPointPersistenceTests(StoreTestCase):
    def test_reorder_points_default_to_zero_and_round_trip(self):
        self.assertEqual(self.store.get_reorder_point("s-1"), 0)
        self.store.set_reorder_point("s-1", 8)
        self.assertEqual(self.store.get_reorder_point("s-1"), 8)
        self.assertEqual(self.store.list_reorder_points(), {"s-1": 8})

    def test_setting_a_reorder_point_twice_overwrites_it(self):
        self.store.set_reorder_point("s-1", 8)
        self.store.set_reorder_point("s-1", 2)
        self.assertEqual(self.store.list_reorder_points(), {"s-1": 2})

    def test_reorder_points_need_a_real_sku_and_sane_units(self):
        with self.assertRaises(NotFound):
            self.store.set_reorder_point("s-404", 1)
        with self.assertRaises(StorageError):
            self.store.set_reorder_point("s-1", -1)
        with self.assertRaises(StorageError):
            self.store.set_reorder_point("s-1", True)


class TransactionTests(StoreTestCase):
    def test_a_committed_transaction_persists(self):
        with self.store.transaction():
            self.store.connection.execute(
                "INSERT INTO locations (code, name, zone, capacity) VALUES ('L-1', 'One', 'z', NULL)"
            )
        self.assertEqual(self.store.get_location("L-1").name, "One")

    def test_a_failed_transaction_rolls_everything_back(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.transaction():
                self.store.connection.execute(
                    "INSERT INTO locations (code, name, zone, capacity) "
                    "VALUES ('L-1', 'One', 'z', NULL)"
                )
                self.store.connection.execute(
                    "INSERT INTO locations (code, name, zone, capacity) "
                    "VALUES ('L-1', 'Duplicate', 'z', NULL)"
                )
        self.assertEqual(self.store.list_locations(), [self.bin_a, self.bin_b])

    def test_transactions_do_not_nest(self):
        with self.assertRaises(StorageError):
            with self.store.transaction():
                with self.store.transaction():
                    pass  # pragma: no cover - the inner block must not be reached

    def test_the_store_is_a_context_manager(self):
        store = SQLiteStore()
        with store as managed:
            self.assertIs(managed, store)
        with self.assertRaises(sqlite3.ProgrammingError):
            store.connection.execute("SELECT 1")


class WarehouseRoundTripTests(unittest.TestCase):
    def build(self):
        warehouse = Warehouse("Main")
        product = warehouse.add_product(Product("p-1", "Widget", "9.99", category="toys"))
        warehouse.add_sku(SKU("s-1", product, barcode="0123456789"))
        warehouse.add_location(Location("A-01", "Bin A1", capacity=100))
        warehouse.add_location(Location("B-01", "Bin B1", capacity=5))
        warehouse.set_reorder_point("s-1", 5)
        warehouse.receive("s-1", "A-01", 10, reference="PO-1")
        warehouse.reserve("s-1", "A-01", 4)
        warehouse.transfer("s-1", "A-01", "B-01", 3)
        return warehouse

    def test_a_whole_warehouse_survives_a_round_trip(self):
        warehouse = self.build()
        with SQLiteStore() as store:
            store.save_warehouse(warehouse)
            loaded = store.load_warehouse("Main")

            self.assertEqual(loaded.name, "Main")
            self.assertEqual(loaded.products, warehouse.products)
            self.assertEqual(loaded.skus, warehouse.skus)
            self.assertEqual(loaded.locations, warehouse.locations)
            self.assertEqual(loaded.stock_levels, warehouse.stock_levels)
            self.assertEqual(loaded.on_hand("s-1"), 10)
            self.assertEqual(loaded.available("s-1"), 6)
            self.assertEqual(loaded.stock("s-1", "B-01").quantity, 3)
            self.assertEqual(loaded.reorder_point("s-1"), 5)
            self.assertEqual(loaded.movements, warehouse.movements)
            self.assertEqual(len(loaded.movements), 4)
            # A-01 is down to 3 available (7 on hand, 4 reserved) and B-01 holds
            # 3, so both sit at or under the reorder point of 5.
            self.assertEqual(
                sorted((r.location.code, r.available) for r in loaded.low_stock()),
                sorted((r.location.code, r.available) for r in warehouse.low_stock()),
            )
            self.assertEqual(
                [(r.location.code, r.available) for r in loaded.low_stock()],
                [("A-01", 3), ("B-01", 3)],
            )

    def test_a_loaded_warehouse_still_enforces_its_invariants(self):
        with SQLiteStore() as store:
            store.save_warehouse(self.build())
            loaded = store.load_warehouse()
            self.assertEqual(loaded.stock("s-1", "B-01").quantity, 3)
            loaded.receive("s-1", "B-01", 2)
            with self.assertRaises(CapacityExceeded):
                loaded.receive("s-1", "B-01", 1)
            with self.assertRaises(ValidationError):
                loaded.restore(stock_levels=[])

    def test_saving_the_same_warehouse_twice_does_not_duplicate_rows(self):
        warehouse = self.build()
        with SQLiteStore() as store:
            store.save_warehouse(warehouse)
            store.save_warehouse(warehouse)
            self.assertEqual(store.count_products(), 1)
            self.assertEqual(store.count_movements(), 4)
            self.assertEqual(len(store.list_stock_levels()), 2)
            self.assertEqual(store.list_reorder_points(), {"s-1": 5})

    def test_saving_a_non_warehouse_is_refused(self):
        with SQLiteStore() as store:
            with self.assertRaises(StorageError):
                store.save_warehouse("not a warehouse")

    def test_low_stock_survives_a_round_trip(self):
        warehouse = Warehouse("Main")
        product = warehouse.add_product(Product("p-1", "Widget", "9.99"))
        warehouse.add_sku(SKU("s-1", product))
        warehouse.add_location(Location("A-01", "Bin A1"))
        warehouse.set_reorder_point("s-1", 5)
        warehouse.receive("s-1", "A-01", 2)

        with SQLiteStore() as store:
            store.save_warehouse(warehouse)
            loaded = store.load_warehouse()
            self.assertEqual(len(loaded.low_stock()), 1)
            self.assertTrue(loaded.low_stock()[0].is_low)


class FileStorageTests(unittest.TestCase):
    def test_a_file_database_persists_across_reopening(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "inventory.db")
            with SQLiteStore(path) as first:
                first.save_product(Product("p-1", "Widget", "9.99"))
                first.save_location(Location("A-01", "Bin A1", capacity=10))
            self.assertTrue(os.path.exists(path))

            with SQLiteStore(path) as second:
                self.assertEqual(second.schema_version, LATEST_VERSION)
                self.assertEqual(second.migrate(), [])
                self.assertEqual(second.get_product("p-1").unit_price, Decimal("9.99"))
                self.assertEqual(second.get_location("A-01").capacity, 10)


def _movement(kind, sku_code, location_code, units, reference=None):
    """Build a Movement without going through a Warehouse."""
    return Movement(
        kind=kind,
        sku_code=sku_code,
        location_code=location_code,
        units=units,
        reference=reference,
    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
