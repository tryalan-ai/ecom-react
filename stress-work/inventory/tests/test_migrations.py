"""Unit tests for the numbered SQL migration registry."""

import dataclasses
import unittest

from inventory import LATEST_VERSION, MIGRATIONS, Migration, MigrationError, plan_migrations


class MigrationRegistryTests(unittest.TestCase):
    def test_versions_are_unique_positive_and_gap_free(self):
        versions = [migration.version for migration in MIGRATIONS]
        self.assertEqual(len(versions), len(set(versions)), "versions must be unique")
        self.assertEqual(versions, sorted(versions), "versions must ascend in registry order")
        self.assertEqual(versions[0], 1, "versions must start at 1")
        self.assertEqual(versions, list(range(1, len(versions) + 1)), "versions must be gap free")
        self.assertEqual(LATEST_VERSION, versions[-1])

    def test_every_migration_carries_real_sql(self):
        for migration in MIGRATIONS:
            with self.subTest(version=migration.version):
                self.assertTrue(migration.name)
                self.assertIn("CREATE", migration.sql.upper())

    def test_migrations_are_immutable(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            MIGRATIONS[0].version = 99  # type: ignore[misc]

    def test_migration_rejects_invalid_definitions(self):
        for kwargs in (
            {"version": 0, "name": "zero", "sql": "SELECT 1"},
            {"version": -1, "name": "negative", "sql": "SELECT 1"},
            {"version": "1", "name": "text", "sql": "SELECT 1"},
            {"version": True, "name": "bool", "sql": "SELECT 1"},
            {"version": 1, "name": "   ", "sql": "SELECT 1"},
            {"version": 1, "name": "empty sql", "sql": "   "},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(MigrationError):
                    Migration(**kwargs)

    def test_migration_trims_its_name(self):
        self.assertEqual(Migration(7, "  spaced  ", "SELECT 1").name, "spaced")


class PlanMigrationsTests(unittest.TestCase):
    def test_blank_database_plans_everything_in_order(self):
        pending = plan_migrations()
        self.assertEqual(pending, MIGRATIONS)

    def test_applied_versions_are_skipped(self):
        versions = [migration.version for migration in MIGRATIONS]
        pending = plan_migrations(versions[:-1])
        self.assertEqual([migration.version for migration in pending], [versions[-1]])

    def test_unknown_ahead_versions_change_nothing(self):
        pending = plan_migrations([version for version in range(1, 100)])
        self.assertEqual(pending, ())

    def test_planning_is_ordered_independently_of_registry_order(self):
        unordered = (
            MIGRATIONS[2],
            MIGRATIONS[0],
            MIGRATIONS[1],
        )
        self.assertEqual(
            [migration.version for migration in plan_migrations((), unordered)],
            [1, 2, 3],
        )

    def test_duplicate_versions_are_rejected(self):
        with self.assertRaises(MigrationError):
            plan_migrations((), (MIGRATIONS[0], MIGRATIONS[0]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
