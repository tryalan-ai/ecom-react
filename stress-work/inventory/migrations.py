"""Numbered SQL migrations for the inventory database.

Migrations are plain, ordered SQL strings.  Each one carries a positive
``version`` and a short ``name``; the version is the primary key of the
``schema_migrations`` ledger, so a migration runs exactly once per database.

Rules for adding a migration:

* never change an existing migration that has shipped -- append a new one;
* start the script with ``CREATE TABLE IF NOT EXISTS`` / ``CREATE INDEX IF NOT
  EXISTS`` where re-running is harmless, so a partially applied script can be
  retried safely;
* keep the version numbers strictly increasing and gap free.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence, Tuple

from .errors import MigrationError

__all__ = ["Migration", "MIGRATIONS", "LATEST_VERSION", "plan_migrations"]


@dataclass(frozen=True)
class Migration:
    """A single versioned, forward-only schema change."""

    version: int
    name: str
    sql: str

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or not isinstance(self.version, int):
            raise MigrationError("migration version must be an integer")
        if self.version < 1:
            raise MigrationError(f"migration version must be positive, got {self.version}")
        if not isinstance(self.name, str) or not self.name.strip():
            raise MigrationError("migration name must be a non-empty string")
        if not isinstance(self.sql, str) or not self.sql.strip():
            raise MigrationError(f"migration {self.version} has no SQL")
        object.__setattr__(self, "name", self.name.strip())


# ---------------------------------------------------------------------------
# 001 -- the catalog: what we stock and where we can put it
# ---------------------------------------------------------------------------
_CREATE_CATALOG = """
CREATE TABLE IF NOT EXISTS products (
    product_id  TEXT    PRIMARY KEY,
    name        TEXT    NOT NULL,
    category    TEXT    NOT NULL,
    -- Money is kept as an exact decimal string: SQLite has no native decimal
    -- type and floats would silently round prices.
    unit_price  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS skus (
    code             TEXT    PRIMARY KEY,
    product_id       TEXT    NOT NULL REFERENCES products (product_id) ON DELETE RESTRICT,
    unit_of_measure  TEXT    NOT NULL,
    barcode          TEXT,
    pack_size        INTEGER NOT NULL CHECK (pack_size >= 1)
);

CREATE TABLE IF NOT EXISTS locations (
    code      TEXT    PRIMARY KEY,
    name      TEXT    NOT NULL,
    zone      TEXT    NOT NULL,
    -- NULL means "unbounded"; a bounded location stores units across all SKUs.
    capacity  INTEGER CHECK (capacity IS NULL OR capacity >= 1)
);
"""

# ---------------------------------------------------------------------------
# 002 -- how much we hold, and every change that got us here
# ---------------------------------------------------------------------------
_CREATE_STOCK = """
CREATE TABLE IF NOT EXISTS stock_levels (
    sku_code       TEXT    NOT NULL REFERENCES skus (code) ON DELETE CASCADE,
    location_code  TEXT    NOT NULL REFERENCES locations (code) ON DELETE CASCADE,
    quantity       INTEGER NOT NULL CHECK (quantity >= 0),
    reserved       INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    reorder_point  INTEGER NOT NULL DEFAULT 0 CHECK (reorder_point >= 0),
    PRIMARY KEY (sku_code, location_code),
    CHECK (reserved <= quantity)
);

CREATE TABLE IF NOT EXISTS movements (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    kind           TEXT    NOT NULL,
    sku_code       TEXT    NOT NULL,
    location_code  TEXT    NOT NULL,
    units          INTEGER NOT NULL,
    reference      TEXT,
    recorded_at    TEXT    NOT NULL
);
"""

# ---------------------------------------------------------------------------
# 003 -- per-SKU reorder defaults (sparse: only configured SKUs are stored)
# ---------------------------------------------------------------------------
_CREATE_REORDER_POINTS = """
CREATE TABLE IF NOT EXISTS reorder_points (
    sku_code  TEXT    PRIMARY KEY REFERENCES skus (code) ON DELETE CASCADE,
    units     INTEGER NOT NULL CHECK (units >= 0)
);

CREATE INDEX IF NOT EXISTS idx_movements_sku ON movements (sku_code, id);
CREATE INDEX IF NOT EXISTS idx_movements_recorded_at ON movements (recorded_at);
CREATE INDEX IF NOT EXISTS idx_stock_low ON stock_levels (reorder_point) WHERE reorder_point > 0;
"""

# ---------------------------------------------------------------------------
# 004 -- purchase orders and the lines that make them up
# ---------------------------------------------------------------------------
_CREATE_PURCHASE_ORDERS = """
CREATE TABLE IF NOT EXISTS purchase_orders (
    reference   TEXT    PRIMARY KEY,
    supplier    TEXT    NOT NULL,
    cancelled   INTEGER NOT NULL DEFAULT 0 CHECK (cancelled IN (0, 1)),
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS purchase_order_lines (
    reference       TEXT    NOT NULL REFERENCES purchase_orders (reference) ON DELETE CASCADE,
    sku_code        TEXT    NOT NULL REFERENCES skus (code) ON DELETE RESTRICT,
    location_code   TEXT    NOT NULL REFERENCES locations (code) ON DELETE RESTRICT,
    ordered_units   INTEGER NOT NULL CHECK (ordered_units >= 1),
    received_units  INTEGER NOT NULL DEFAULT 0 CHECK (received_units >= 0),
    PRIMARY KEY (reference, sku_code),
    CHECK (received_units <= ordered_units)
);

CREATE INDEX IF NOT EXISTS idx_po_lines_sku ON purchase_order_lines (sku_code);
"""

# ---------------------------------------------------------------------------
# 005 -- sales orders and the reservations they hold
# ---------------------------------------------------------------------------
_CREATE_SALES_ORDERS = """
CREATE TABLE IF NOT EXISTS sales_orders (
    reference   TEXT    PRIMARY KEY,
    customer    TEXT    NOT NULL,
    cancelled   INTEGER NOT NULL DEFAULT 0 CHECK (cancelled IN (0, 1)),
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS sales_order_lines (
    reference       TEXT    NOT NULL REFERENCES sales_orders (reference) ON DELETE CASCADE,
    sku_code        TEXT    NOT NULL REFERENCES skus (code) ON DELETE RESTRICT,
    location_code   TEXT    NOT NULL REFERENCES locations (code) ON DELETE RESTRICT,
    ordered_units   INTEGER NOT NULL CHECK (ordered_units >= 1),
    reserved_units  INTEGER NOT NULL DEFAULT 0 CHECK (reserved_units >= 0),
    shipped_units   INTEGER NOT NULL DEFAULT 0 CHECK (shipped_units >= 0),
    PRIMARY KEY (reference, sku_code),
    CHECK (reserved_units + shipped_units <= ordered_units)
);

CREATE INDEX IF NOT EXISTS idx_so_lines_sku ON sales_order_lines (sku_code);
"""


MIGRATIONS: Tuple[Migration, ...] = (
    Migration(version=1, name="create_catalog", sql=_CREATE_CATALOG),
    Migration(version=2, name="create_stock_and_movements", sql=_CREATE_STOCK),
    Migration(version=3, name="create_reorder_points", sql=_CREATE_REORDER_POINTS),
    Migration(version=4, name="create_purchase_orders", sql=_CREATE_PURCHASE_ORDERS),
    Migration(version=5, name="create_sales_orders", sql=_CREATE_SALES_ORDERS),
)

LATEST_VERSION: int = max(migration.version for migration in MIGRATIONS)


def plan_migrations(
    applied_versions: Iterable[int] = (),
    migrations: Sequence[Migration] = MIGRATIONS,
) -> Tuple[Migration, ...]:
    """Return the migrations still to apply, in version order.

    Raises :class:`MigrationError` if ``migrations`` reuses a version number.
    """
    seen = set()
    for migration in migrations:
        if migration.version in seen:
            raise MigrationError(f"duplicate migration version {migration.version}")
        seen.add(migration.version)
    applied = set(applied_versions)
    ordered = sorted(migrations, key=lambda migration: migration.version)
    return tuple(migration for migration in ordered if migration.version not in applied)
