"""Tests for :mod:`kvstore.snapshot`."""

import os
import tempfile
import unittest

from kvstore.codec import encode
from kvstore.snapshot import (
    BACKUP_SUFFIX,
    SNAPSHOT_MAGIC,
    decode_snapshot,
    encode_snapshot,
    load_snapshot,
    save_snapshot,
    snapshot_path,
)

from .support import write_bytes


class SnapshotCodecTests(unittest.TestCase):
    def test_encode_decode_roundtrip(self):
        blob = encode_snapshot(5, {"a": "1", "b": "2"})
        seq, data = decode_snapshot(blob)
        self.assertEqual(seq, 5)
        self.assertEqual(data, {"a": "1", "b": "2"})

    def test_empty_data(self):
        seq, data = decode_snapshot(encode_snapshot(0, {}))
        self.assertEqual(seq, 0)
        self.assertEqual(data, {})

    def test_torn_blob_raises(self):
        blob = encode_snapshot(1, {"a": "1"})
        with self.assertRaises(Exception):
            decode_snapshot(blob[:-2])

    def test_wrong_magic_raises(self):
        with self.assertRaises(Exception):
            decode_snapshot(encode(b"NOPE", b'{"seq":1,"data":{}}'))

    def test_non_object_data_rejected(self):
        payload = b'{"seq":1,"data":[1,2,3]}'
        with self.assertRaises(ValueError):
            decode_snapshot(encode(SNAPSHOT_MAGIC, payload))


class SnapshotFileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.path = snapshot_path(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_then_load(self):
        save_snapshot(self.path, 3, {"x": "y"})
        self.assertEqual(load_snapshot(self.path), (3, {"x": "y"}))

    def test_load_missing_returns_none(self):
        self.assertIsNone(load_snapshot(self.path))

    def test_save_creates_backup_on_second_write(self):
        save_snapshot(self.path, 1, {"a": "1"})
        save_snapshot(self.path, 2, {"a": "2"})
        self.assertTrue(os.path.exists(self.path + BACKUP_SUFFIX))
        self.assertEqual(load_snapshot(self.path), (2, {"a": "2"}))

    def test_torn_snapshot_falls_back_to_backup(self):
        save_snapshot(self.path, 1, {"a": "1"})
        save_snapshot(self.path, 2, {"a": "2"})  # backup now holds seq 1
        # Simulate a torn write of the primary snapshot.
        write_bytes(self.path, b"\x00" * 8)
        self.assertEqual(load_snapshot(self.path), (1, {"a": "1"}))

    def test_no_backup_and_torn_returns_none(self):
        save_snapshot(self.path, 1, {"a": "1"})
        write_bytes(self.path, b"partial")
        self.assertIsNone(load_snapshot(self.path))

    def test_atomic_write_leaves_no_tmp(self):
        save_snapshot(self.path, 1, {"a": "1"})
        self.assertFalse(os.path.exists(self.path + ".tmp"))

    def test_save_does_not_corrupt_when_replacing(self):
        save_snapshot(self.path, 1, {"a": "1"})
        first = load_snapshot(self.path)
        save_snapshot(self.path, 2, {"a": "1", "b": "2"})
        self.assertEqual(first, (1, {"a": "1"}))
        self.assertEqual(load_snapshot(self.path), (2, {"a": "1", "b": "2"}))

    def test_fsync_roundtrip(self):
        save_snapshot(self.path, 9, {"k": "v"}, fsync=True)
        self.assertEqual(load_snapshot(self.path), (9, {"k": "v"}))

    def test_nested_directory_created(self):
        nested = os.path.join(self.dir, "a", "b", "snapshot.kv")
        save_snapshot(nested, 1, {"deep": "yes"})
        self.assertEqual(load_snapshot(nested), (1, {"deep": "yes"}))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
