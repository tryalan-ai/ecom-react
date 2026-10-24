"""Crash-recovery focused tests: torn writes, torn snapshots, replay."""

import os
import random
import tempfile
import unittest

from kvstore.snapshot import snapshot_path
from kvstore.store import KVStore

from .support import (
    append_bytes,
    frame_offsets,
    read_bytes,
    wal_path,
    write_bytes,
)


class TornWriteMatrixTests(unittest.TestCase):
    """Truncating the log anywhere must recover a valid prefix of the writes."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.store = KVStore(os.path.join(self.dir, "src"))

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def _build_log(self, count=20):
        for i in range(count):
            self.store.set("key%02d" % i, "value%02d" % i)
        self.store.wal.close()
        return read_bytes(wal_path(os.path.join(self.dir, "src")))

    def test_every_truncation_point_yields_valid_prefix(self):
        blob = self._build_log(20)
        offsets = frame_offsets(blob)
        self.assertEqual(len(offsets), 20)

        for cut in offsets:
            dest = os.path.join(self.dir, "cut-%d" % cut)
            os.makedirs(dest)
            write_bytes(wal_path(dest), blob[:cut])
            recovered = KVStore(dest)
            complete = sum(1 for end in offsets if end <= cut)
            self.assertEqual(len(recovered), complete, "cut=%d" % cut)
            recovered.close()

    def test_truncation_mid_frame_recovers_prefix(self):
        blob = self._build_log(6)
        offsets = frame_offsets(blob)
        # Cut three bytes into the fourth frame.
        cut = offsets[2] + 3
        dest = os.path.join(self.dir, "mid")
        os.makedirs(dest)
        write_bytes(wal_path(dest), blob[:cut])

        recovered = KVStore(dest)
        self.assertEqual(sorted(recovered.keys()), ["key00", "key01", "key02"])
        self.assertTrue(recovered.wal.torn)
        recovered.close()

    def test_random_tail_garbage_matrix(self):
        blob = self._build_log(10)
        rng = random.Random(1234)
        for _ in range(15):
            dest = os.path.join(self.dir, "rand-%d" % rng.randrange(10 ** 6))
            if os.path.exists(dest):
                continue
            os.makedirs(dest)
            n = rng.randrange(1, 40)
            write_bytes(wal_path(dest), blob + bytes(rng.randrange(256) for _ in range(n)))
            recovered = KVStore(dest)
            self.assertEqual(len(recovered), 10)
            recovered.close()


class TornSnapshotTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_torn_snapshot_with_no_backup_falls_back_to_wal(self):
        store = KVStore(self.dir)
        store.set("a", "1")
        store.set("b", "2")
        store.close()

        # Force a snapshot-shaped file onto disk without a backup, plus keep
        # the WAL: recovery must rebuild from the WAL.
        write_bytes(snapshot_path(self.dir), b"\x00\x00\x00notasnapshot")
        store = KVStore(self.dir)
        self.assertEqual(store.items(), [("a", "1"), ("b", "2")])
        store.close()

    def test_torn_snapshot_uses_backup(self):
        store = KVStore(self.dir)
        store.set("a", "1")
        store.snapshot()  # snapshot #1 (no backup yet)
        store.set("b", "2")
        store.snapshot()  # snapshot #2 -> #1 becomes the backup
        store.close()

        # Torn primary: the store must load the backup (seq 1) and replay WAL.
        write_bytes(snapshot_path(self.dir), b"garbage-snapshot")
        store = KVStore(self.dir)
        self.assertEqual(store.get("a"), "1")
        store.close()

    def test_crash_between_snapshot_and_wal_truncate(self):
        # Snapshot is written but the log was not truncated before the crash.
        store = KVStore(self.dir)
        store.set("a", "1")
        store.set("b", "2")
        store.snapshot()
        store.close()

        wal_blob = encode_extra_wal(("a", "1", 1), ("b", "2", 2))
        append_bytes(wal_path(self.dir), wal_blob)

        # Replaying already-snapshotted records must be idempotent.
        store = KVStore(self.dir)
        self.assertEqual(store.items(), [("a", "1"), ("b", "2")])
        store.close()


def encode_extra_wal(*triples):
    """Build raw WAL frames for ``(key, value, seq)`` triples."""
    import json

    from kvstore.codec import encode
    from kvstore.wal import WAL_MAGIC

    blob = b""
    for key, value, seq in triples:
        payload = json.dumps(
            {"op": "set", "key": key, "value": value, "seq": seq},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        blob += encode(WAL_MAGIC, payload)
    return blob


class ReplayIdempotenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_delete_replayed_after_snapshot(self):
        store = KVStore(self.dir)
        store.set("a", "1")
        store.set("b", "2")
        store.delete("a")
        store.snapshot()
        store.close()

        # Re-append the pre-snapshot records; replay must not resurrect 'a'.
        blob = encode_extra_wal(("a", "1", 1), ("b", "2", 2))
        append_bytes(wal_path(self.dir), blob)
        store = KVStore(self.dir)
        self.assertNotIn("a", store)
        self.assertEqual(store.get("b"), "2")
        store.close()

    def test_stale_records_are_skipped_by_seq(self):
        store = KVStore(self.dir)
        store.set("a", "1")
        store.set("b", "2")
        store.snapshot()  # snapshot at seq 2, log truncated to empty
        store.close()

        # Replay stale records (seq 1, 2) that the snapshot already covers,
        # followed by one genuinely new record (seq 3).
        append_bytes(
            wal_path(self.dir),
            encode_extra_wal(("a", "1", 1), ("b", "2", 2), ("c", "3", 3)),
        )

        store = KVStore(self.dir)
        self.assertEqual(store.items(), [("a", "1"), ("b", "2"), ("c", "3")])
        self.assertEqual(store.seq, 3)
        store.close()

    def test_mixed_ops_replay(self):
        store = KVStore(self.dir)
        store.set("a", "1")
        store.set("b", "2")
        store.delete("a")
        store.set("c", "3")
        store.close()

        store = KVStore(self.dir)
        self.assertEqual(store.items(), [("b", "2"), ("c", "3")])
        store.close()


class RepairThenContinueTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_double_torn_write(self):
        store = KVStore(self.dir)
        store.set("a", "1")
        store.close()

        append_bytes(wal_path(self.dir), b"first-torn")
        store = KVStore(self.dir)  # repairs to 1 record
        store.set("b", "2")
        store.close()

        append_bytes(wal_path(self.dir), b"second-torn")
        store = KVStore(self.dir)  # repairs again
        self.assertEqual(store.items(), [("a", "1"), ("b", "2")])
        store.close()

    def test_repair_preserves_log_size_then_grows_cleanly(self):
        store = KVStore(self.dir)
        store.set("a", "1")
        store.close()
        clean = os.path.getsize(wal_path(self.dir))

        append_bytes(wal_path(self.dir), b"x" * 25)
        store = KVStore(self.dir)
        self.assertEqual(os.path.getsize(wal_path(self.dir)), clean)
        store.set("b", "2")
        store.close()
        self.assertGreater(os.path.getsize(wal_path(self.dir)), clean)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
