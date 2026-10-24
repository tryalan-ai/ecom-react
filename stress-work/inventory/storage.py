"""SQLite persistence for the inventory domain.

:class:`SQLiteStore` owns a :mod:`sqlite3` connection, applies the numbered
migrations in :mod:`inventory.migrations` on open, and maps every domain model
to and from tables.  Saving is upsert-shaped, so re-saving a changed model
converges instead of failing.

Two conventions worth knowing:

* the connection runs in autocommit mode (``isolation_level=None``); anything
  that must be atomic is wrapped in :meth:`SQLiteStore.transaction`;
* round-tripping a model always rebuilds it through its constructor, so the
  write path and the read path cannot drift apart from the model's own
  validation rules.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Iterable, Iterator, List, Optional, Sequence

from .errors import NotFound, StorageError
from .migrations import LATEST_VERSION, MIGRATIONS, Migration, plan_migrations
from .models import Location, Product, SKU, StockLevel
from .warehouse import Movement, Warehouse

__all__ = ["SQLiteStore"]

_LEDGER_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    applied_at  TEXT    NOT NULL
);
"""


class SQLiteStore:
    """A SQLite-backed home for products, SKUs, locations, stock and movements."""

    def __init__(self, path: str = ":memory:") -> None:
        if not isinstance(path, str) or not path.strip():
            raise StorageError("database path must be a non-empty string")
        self.path = path
        try:
            self._conn = sqlite3.connect(path, isolation_level=None)
        except sqlite3.Error as exc:  # pragma: no cover - environment dependent
            raise StorageError(f"cannot open database at {path!r}: {exc}") from exc
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self.migrate()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    @property
    def connection(self) -> sqlite3.Connection:
        """The underlying connection, for callers that need raw SQL."""
        return self._conn

    def close(self) -> None:
        """Roll back anything in flight and close the connection."""
        if self._conn.in_transaction:
            self._conn.execute("ROLLBACK")
        self._conn.close()

    def __enter__(self) -> "SQLiteStore":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.close()
        return False

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Group writes into one atomic unit.

        Nesting is refused rather than silently flattened, because SQLite would
        otherwise commit the inner block as a side effect of the outer one.
        """
        if self._conn.in_transaction:
            raise StorageError("nested transactions are not supported")
        self._conn.execute("BEGIN")
        try:
            yield self._conn
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")

    # ------------------------------------------------------------------
    # Migrations
    # ------------------------------------------------------------------
    def migrate(self, migrations: Sequence[Migration] = MIGRATIONS) -> List[Migration]:
        """Apply every pending migration and return the ones that ran.

        Calling this again applies nothing, so opening an up-to-date database is
        cheap and idempotent.
        """
        self._conn.executescript(_LEDGER_SQL)
        applied = {
            row["version"]
            for row in self._conn.execute("SELECT version FROM schema_migrations")
        }
        pending = plan_migrations(applied, migrations)
        for migration in pending:
            try:
                self._conn.executescript(migration.sql)
            except sqlite3.Error as exc:
                raise StorageError(
                    f"migration {migration.version} ({migration.name}) failed: {exc}"
                ) from exc
            self._conn.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                (
                    migration.version,
                    migration.name,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return list(pending)

    @property
    def schema_version(self) -> int:
        """The highest applied migration version, or ``0`` for a blank database."""
        row = self._conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
        ).fetchone()
        return int(row["version"])

    def applied_migrations(
        self, migrations: Sequence[Migration] = MIGRATIONS
    ) -> List[Migration]:
        """Applied migrations as objects, oldest first.

        Raises :class:`StorageError` when the database records a version this
        build does not know about, which means the file was written by a newer
        release and must not be touched.
        """
        known = {migration.version: migration for migration in migrations}
        applied: List[Migration] = []
        for row in self._conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ):
            migration = known.get(row["version"])
            if migration is None:
                raise StorageError(
                    f"database schema version {row['version']} is unknown to this build "
                    f"(latest known is {LATEST_VERSION})"
                )
            applied.append(migration)
        return applied

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------
    def save_product(self, product: Product) -> Product:
        """Insert or update a product."""
        with self.transaction():
            _upsert_product(self._conn, product)
        return product

    def save_products(self, products: Iterable[Product]) -> List[Product]:
        """Insert or update many products in one transaction."""
        batch = list(products)
        with self.transaction():
            for product in batch:
                _upsert_product(self._conn, product)
        return batch

    def get_product(self, product_id: str) -> Product:
        row = self._conn.execute(
            "SELECT * FROM products WHERE product_id = ?", (product_id,)
        ).fetchone()
        if row is None:
            raise NotFound(f"no product with id {product_id!r}")
        return _product_from_row(row)

    def list_products(self) -> List[Product]:
        rows = self._conn.execute("SELECT * FROM products ORDER BY product_id")
        return [_product_from_row(row) for row in rows]

    def count_products(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"])

    # ------------------------------------------------------------------
    # SKUs
    # ------------------------------------------------------------------
    def save_sku(self, sku: SKU) -> SKU:
        """Insert or update an SKU; its product must already be stored."""
        with self.transaction():
            _upsert_sku(self._conn, sku)
        return sku

    def save_skus(self, skus: Iterable[SKU]) -> List[SKU]:
        batch = list(skus)
        with self.transaction():
            for sku in batch:
                _upsert_sku(self._conn, sku)
        return batch

    def get_sku(self, code: str) -> SKU:
        row = self._conn.execute("SELECT * FROM skus WHERE code = ?", (code,)).fetchone()
        if row is None:
            raise NotFound(f"no sku with code {code!r}")
        return _sku_from_row(row, self.get_product(row["product_id"]))

    def list_skus(self) -> List[SKU]:
        rows = self._conn.execute("SELECT * FROM skus ORDER BY code").fetchall()
        return [_sku_from_row(row, self.get_product(row["product_id"])) for row in rows]

    # ------------------------------------------------------------------
    # Locations
    # ------------------------------------------------------------------
    def save_location(self, location: Location) -> Location:
        """Insert or update a location."""
        with self.transaction():
            _upsert_location(self._conn, location)
        return location

    def save_locations(self, locations: Iterable[Location]) -> List[Location]:
        batch = list(locations)
        with self.transaction():
            for location in batch:
                _upsert_location(self._conn, location)
        return batch

    def get_location(self, code: str) -> Location:
        row = self._conn.execute(
            "SELECT * FROM locations WHERE code = ?", (code,)
        ).fetchone()
        if row is None:
            raise NotFound(f"no location with code {code!r}")
        return _location_from_row(row)

    def list_locations(self) -> List[Location]:
        rows = self._conn.execute("SELECT * FROM locations ORDER BY code")
        return [_location_from_row(row) for row in rows]

    # ------------------------------------------------------------------
    # Stock levels
    # ------------------------------------------------------------------
    def save_stock_level(self, record: StockLevel) -> StockLevel:
        """Insert or update a stock level; its SKU and location must be stored."""
        with self.transaction():
            _upsert_stock_level(self._conn, record)
        return record

    def save_stock_levels(self, records: Iterable[StockLevel]) -> List[StockLevel]:
        batch = list(records)
        with self.transaction():
            for record in batch:
                _upsert_stock_level(self._conn, record)
        return batch

    def get_stock_level(self, sku_code: str, location_code: str) -> StockLevel:
        row = self._conn.execute(
            "SELECT * FROM stock_levels WHERE sku_code = ? AND location_code = ?",
            (sku_code, location_code),
        ).fetchone()
        if row is None:
            raise NotFound(f"no stock record for sku {sku_code!r} at {location_code!r}")
        return _stock_level_from_row(row, self)

    def list_stock_levels(self) -> List[StockLevel]:
        """Every stock record, ordered by SKU code then location code."""
        rows = self._conn.execute(
            "SELECT * FROM stock_levels ORDER BY sku_code, location_code"
        ).fetchall()
        return [_stock_level_from_row(row, self) for row in rows]

    def list_stock_for(self, sku_code: str) -> List[StockLevel]:
        rows = self._conn.execute(
            "SELECT * FROM stock_levels WHERE sku_code = ? ORDER BY location_code",
            (sku_code,),
        ).fetchall()
        return [_stock_level_from_row(row, self) for row in rows]

    # ------------------------------------------------------------------
    # Movements
    # ------------------------------------------------------------------
    def save_movement(self, movement: Movement) -> Movement:
        """Append one audit-log entry."""
        with self.transaction():
            _insert_movement(self._conn, movement)
        return movement

    def save_movements(self, movements: Iterable[Movement]) -> List[Movement]:
        """Append many audit-log entries in one transaction, preserving order."""
        batch = list(movements)
        with self.transaction():
            for movement in batch:
                _insert_movement(self._conn, movement)
        return batch

    def list_movements(
        self, sku_code: Optional[str] = None, limit: Optional[int] = None
    ) -> List[Movement]:
        """Movements oldest first, optionally filtered by SKU and capped."""
        if limit is not None:
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
                raise StorageError("limit must be a non-negative integer or None")
        sql = "SELECT * FROM movements"
        params: List[object] = []
        if sku_code is not None:
            sql += " WHERE sku_code = ?"
            params.append(sku_code)
        sql += " ORDER BY id"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return [_movement_from_row(row) for row in self._conn.execute(sql, params)]

    def count_movements(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) AS n FROM movements").fetchone()["n"])

    # ------------------------------------------------------------------
    # Reorder points
    # ------------------------------------------------------------------
    def set_reorder_point(self, sku_code: str, units: int) -> int:
        """Store the reorder threshold for one SKU."""
        if isinstance(units, bool) or not isinstance(units, int):
            raise StorageError("units must be an integer")
        if units < 0:
            raise StorageError("units must not be negative")
        if not self._sku_exists(sku_code):
            raise NotFound(f"no sku with code {sku_code!r}")
        with self.transaction():
            self._conn.execute(
                "INSERT INTO reorder_points (sku_code, units) VALUES (?, ?) "
                "ON CONFLICT(sku_code) DO UPDATE SET units = excluded.units",
                (sku_code, units),
            )
        return units

    def get_reorder_point(self, sku_code: str) -> int:
        row = self._conn.execute(
            "SELECT units FROM reorder_points WHERE sku_code = ?", (sku_code,)
        ).fetchone()
        return int(row["units"]) if row is not None else 0

    def list_reorder_points(self) -> Dict[str, int]:
        return {
            row["sku_code"]: int(row["units"])
            for row in self._conn.execute(
                "SELECT sku_code, units FROM reorder_points ORDER BY sku_code"
            )
        }

    # ------------------------------------------------------------------
    # Whole-aggregate round trip
    # ------------------------------------------------------------------
    def save_warehouse(self, warehouse: Warehouse) -> Warehouse:
        """Persist a whole warehouse in a single transaction.

        Saving twice is safe: catalog rows are upserted and the movement log is
        replaced with the warehouse's current history, so the database mirrors
        the in-memory aggregate instead of accumulating duplicates.
        """
        if not isinstance(warehouse, Warehouse):
            raise StorageError("warehouse must be a Warehouse instance")
        with self.transaction():
            for product in warehouse.products:
                _upsert_product(self._conn, product)
            for sku in warehouse.skus:
                _upsert_sku(self._conn, sku)
            for location in warehouse.locations:
                _upsert_location(self._conn, location)
            for record in warehouse.stock_levels:
                _upsert_stock_level(self._conn, record)
            self._conn.execute("DELETE FROM movements")
            for movement in warehouse.movements:
                _insert_movement(self._conn, movement)
            self._conn.execute("DELETE FROM reorder_points")
            for sku in warehouse.skus:
                self._conn.execute(
                    "INSERT INTO reorder_points (sku_code, units) VALUES (?, ?)",
                    (sku.code, warehouse.reorder_point(sku.code)),
                )
        return warehouse

    def load_warehouse(self, name: str = "warehouse") -> Warehouse:
        """Rebuild a warehouse from the database."""
        warehouse = Warehouse(name)
        for product in self.list_products():
            warehouse.add_product(product)
        for sku in self.list_skus():
            warehouse.add_sku(sku)
        for location in self.list_locations():
            warehouse.add_location(location)
        warehouse.restore(
            stock_levels=self.list_stock_levels(),
            movements=self.list_movements(),
            reorder_points=self.list_reorder_points(),
        )
        return warehouse

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _sku_exists(self, sku_code: str) -> bool:
        return (
            self._conn.execute(
                "SELECT 1 FROM skus WHERE code = ?", (sku_code,)
            ).fetchone()
            is not None
        )


# ----------------------------------------------------------------------
# Row <-> model mapping
# ----------------------------------------------------------------------
def _upsert_product(conn: sqlite3.Connection, product: Product) -> None:
    conn.execute(
        "INSERT INTO products (product_id, name, category, unit_price) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(product_id) DO UPDATE SET "
        "name = excluded.name, category = excluded.category, unit_price = excluded.unit_price",
        (product.product_id, product.name, product.category, str(product.unit_price)),
    )


def _upsert_sku(conn: sqlite3.Connection, sku: SKU) -> None:
    if conn.execute(
        "SELECT 1 FROM products WHERE product_id = ?", (sku.product.product_id,)
    ).fetchone() is None:
        raise NotFound(
            f"cannot store sku {sku.code!r}: product {sku.product.product_id!r} "
            "is not stored"
        )
    conn.execute(
        "INSERT INTO skus (code, product_id, unit_of_measure, barcode, pack_size) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(code) DO UPDATE SET "
        "product_id = excluded.product_id, unit_of_measure = excluded.unit_of_measure, "
        "barcode = excluded.barcode, pack_size = excluded.pack_size",
        (
            sku.code,
            sku.product.product_id,
            sku.unit_of_measure,
            sku.barcode,
            sku.pack_size,
        ),
    )


def _upsert_location(conn: sqlite3.Connection, location: Location) -> None:
    conn.execute(
        "INSERT INTO locations (code, name, zone, capacity) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(code) DO UPDATE SET "
        "name = excluded.name, zone = excluded.zone, capacity = excluded.capacity",
        (location.code, location.name, location.zone, location.capacity),
    )


def _upsert_stock_level(conn: sqlite3.Connection, record: StockLevel) -> None:
    for code, table in (
        (record.sku.code, "skus"),
        (record.location.code, "locations"),
    ):
        if conn.execute(f"SELECT 1 FROM {table} WHERE code = ?", (code,)).fetchone() is None:
            raise NotFound(f"cannot store stock record: {code!r} is not stored")
    conn.execute(
        "INSERT INTO stock_levels "
        "(sku_code, location_code, quantity, reserved, reorder_point) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(sku_code, location_code) DO UPDATE SET "
        "quantity = excluded.quantity, reserved = excluded.reserved, "
        "reorder_point = excluded.reorder_point",
        (
            record.sku.code,
            record.location.code,
            record.quantity,
            record.reserved,
            record.reorder_point,
        ),
    )


def _insert_movement(conn: sqlite3.Connection, movement: Movement) -> None:
    conn.execute(
        "INSERT INTO movements (kind, sku_code, location_code, units, reference, recorded_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            movement.kind,
            movement.sku_code,
            movement.location_code,
            movement.units,
            movement.reference,
            _as_utc(movement.recorded_at).isoformat(),
        ),
    )


def _product_from_row(row: sqlite3.Row) -> Product:
    return Product(
        product_id=row["product_id"],
        name=row["name"],
        unit_price=Decimal(row["unit_price"]),
        category=row["category"],
    )


def _sku_from_row(row: sqlite3.Row, product: Product) -> SKU:
    return SKU(
        code=row["code"],
        product=product,
        unit_of_measure=row["unit_of_measure"],
        barcode=row["barcode"],
        pack_size=row["pack_size"],
    )


def _location_from_row(row: sqlite3.Row) -> Location:
    return Location(
        code=row["code"],
        name=row["name"],
        zone=row["zone"],
        capacity=row["capacity"],
    )


def _stock_level_from_row(row: sqlite3.Row, store: SQLiteStore) -> StockLevel:
    return StockLevel(
        sku=store.get_sku(row["sku_code"]),
        location=store.get_location(row["location_code"]),
        quantity=row["quantity"],
        reserved=row["reserved"],
        reorder_point=row["reorder_point"],
    )


def _movement_from_row(row: sqlite3.Row) -> Movement:
    recorded_at = datetime.fromisoformat(row["recorded_at"])
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)
    return Movement(
        kind=row["kind"],
        sku_code=row["sku_code"],
        location_code=row["location_code"],
        units=row["units"],
        reference=row["reference"],
        recorded_at=recorded_at,
    )


def _as_utc(moment: datetime) -> datetime:
    """Normalise a timestamp to UTC so stored text sorts chronologically."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)
