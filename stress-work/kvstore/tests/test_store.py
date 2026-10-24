"""Tests for :mod:`kvstore.store` (the in-process API)."""

import os
import tempfile
import unittest

from kvstore.store import KVStore

from .support import append_bytes, read_bytes, snapshot_path, wal_path


class StoreTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def open_store(self, **kwargs):
        return KVStore(self.dir, **kwargs)


class BasicApiTests(StoreTestBase):
    def test_set_and_get(self):
        with self.open_store() as store:
            self.assertTrue(store.set("a", "1"))
            self.assertEqual(store.get("a"), "1")

    def test_get_missing_returns_default(self):
        with self.open_store() as store:
            self.assertIsNone(store.get("nope"))
            self.assertEqual(store.get("nope", "d"), "d")

    def test_overwrite(self):
        with self.open_store() as store:
            store.set("a", "1")
            store.set("a", "2")
            self.assertEqual(store.get("a"), "2")

    def test_delete_existing(self):
        with self.open_store() as store:
            store.set("a", "1")
            self.assertTrue(store.delete("a"))
            self.assertIsNone(store.get("a"))

    def test_delete_missing(self):
        with self.open_store() as store:
            self.assertFalse(store.delete("ghost"))

    def test_keys_sorted(self):
        with self.open_store() as store:
            store.set("b", "2")
            store.set("a", "1")
            store.set("c", "3")
            self.assertEqual(store.keys(), ["a", "b", "c"])

    def test_items(self):
        with self.open_store() as store:
            store.set("b", "2")
            store.set("a", "1")
            self.assertEqual(store.items(), [("a", "1"), ("b", "2")])

    def test_len_and_contains(self):
        with self.open_store() as store:
            store.set("a", "1")
            self.assertEqual(len(store), 1)
            self.assertIn("a", store)
            self.assertNotIn("b", store)
            self.assertTrue(store.exists("a"))

    def test_empty_value_allowed(self):
        with self.open_store() as store:
            store.set("a", "")
            self.assertEqual(store.get("a"), "")

    def test_unicode_value(self):
        with self.open_store() as store:
            store.set("g", "caf\u00e9 \u2603")
            self.assertEqual(store.get("g"), "caf\u00e9 \u2603")

    def test_empty_key_rejected(self):
        with self.open_store() as store:
            with self.assertRaises(ValueError):
                store.set("", "v")

    def test_non_string_value_rejected(self):
        with self.open_store() as store:
            with self.assertRaises(TypeError):
                store.set("a", 123)

    def test_seq_advances(self):
        with self.open_store() as store:
            self.assertEqual(store.seq, 0)
            store.set("a", "1")
            store.set("b", "2")
            store.delete("a")
            self.assertEqual(store.seq, 3)


class PersistenceTests(StoreTestBase):
    def test_survives_reopen(self):
        store = self.open_store()
        store.set("a", "1")
        store.set("b", "2")
        store.close()

        store = self.open_store()
        self.assertEqual(store.get("a"), "1")
        self.assertEqual(store.get("b"), "2")
        store.close()

    def test_delete_survives_reopen(self):
        store = self.open_store()
        store.set("a", "1")
        store.delete("a")
        store.close()

        store = self.open_store()
        self.assertIsNone(store.get("a"))
        store.close()

    def test_overwrite_survives_reopen(self):
        store = self.open_store()
        store.set("a", "1")
        store.set("a", "final")
        store.close()

        store = self.open_store()
        self.assertEqual(store.get("a"), "final")
        store.close()

    def test_snapshot_then_reopen(self):
        store = self.open_store()
        store.set("a", "1")
        store.set("b", "2")
        store.snapshot()
        store.close()

        self.assertEqual(os.path.getsize(wal_path(self.dir)), 0)
        store = self.open_store()
        self.assertEqual(store.items(), [("a", "1"), ("b", "2")])
        store.close()

    def test_snapshot_plus_new_writes_survive(self):
        store = self.open_store()
        store.set("a", "1")
        store.snapshot()
        store.set("b", "2")
        store.close()

        store = self.open_store()
        self.assertEqual(store.items(), [("a", "1"), ("b", "2")])
        store.close()

    def test_auto_snapshot_triggers(self):
        store = self.open_store(snapshot_every=3)
        store.set("a", "1")
        store.set("b", "2")
        self.assertEqual(store.snapshot_count, 0)
        store.set("c", "3")
        self.assertEqual(store.snapshot_count, 1)
        self.assertEqual(os.path.getsize(wal_path(self.dir)), 0)
        store.close()

    def test_auto_snapshot_persists(self):
        store = self.open_store(snapshot_every=2)
        for i in range(5):
            store.set("k%d" % i, str(i))
        store.close()

        store = self.open_store()
        self.assertEqual(len(store), 5)
        self.assertEqual(store.get("k4"), "4")
        store.close()

    def test_snapshot_returns_seq(self):
        with self.open_store() as store:
            store.set("a", "1")
            self.assertEqual(store.snapshot(), 1)

    def test_manual_snapshot_counted(self):
        with self.open_store() as store:
            self.assertEqual(store.snapshot_count, 0)
            store.snapshot()
            store.snapshot()
            self.assertEqual(store.snapshot_count, 2)

    def test_fsync_store_roundtrip(self):
        store = self.open_store(fsync=True)
        store.set("a", "1")
        store.snapshot()
        store.close()

        store = self.open_store(fsync=True)
        self.assertEqual(store.get("a"), "1")
        store.close()

    def test_snapshot_file_written(self):
        with self.open_store() as store:
            store.set("a", "1")
            store.snapshot()
        self.assertTrue(os.path.exists(snapshot_path(self.dir)))


class LifecycleTests(StoreTestBase):
    def test_context_manager_closes(self):
        with self.open_store() as store:
            store.set("a", "1")
        self.assertTrue(store._closed)

    def test_use_after_close_raises(self):
        store = self.open_store()
        store.close()
        with self.assertRaises(ValueError):
            store.set("a", "1")

    def test_get_after_close_still_reads_memory(self):
        store = self.open_store()
        store.set("a", "1")
        store.close()
        self.assertEqual(store.get("a"), "1")

    def test_close_is_idempotent(self):
        store = self.open_store()
        store.close()
        store.close()

    def test_repr_mentions_size(self):
        with self.open_store() as store:
            store.set("a", "1")
            self.assertIn("keys=1", repr(store))


class TornWalIntegrationTests(StoreTestBase):
    def test_torn_tail_dropped_on_reopen(self):
        store = self.open_store()
        store.set("a", "1")
        store.set("b", "2")
        store.close()

        # Simulate a crash mid-append by bolting a partial frame on the end.
        append_bytes(wal_path(self.dir), b"\x00\x00\x00\x00partial")

        store = self.open_store()
        self.assertEqual(store.items(), [("a", "1"), ("b", "2")])
        store.close()

    def test_recovered_log_is_repaired(self):
        store = self.open_store()
        store.set("a", "1")
        store.close()
        good_size = os.path.getsize(wal_path(self.dir))
        append_bytes(wal_path(self.dir), b"junk-tail")

        store = self.open_store()
        self.assertEqual(os.path.getsize(wal_path(self.dir)), good_size)
        self.assertTrue(store.wal.torn)
        store.close()

    def test_in_memory_state_matches_log(self):
        store = self.open_store()
        store.set("a", "1")
        store.set("b", "2")
        store.delete("a")
        store.set("c", "3")
        store.close()

        store = self.open_store()
        self.assertEqual(store.items(), [("b", "2"), ("c", "3")])
        store.close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
