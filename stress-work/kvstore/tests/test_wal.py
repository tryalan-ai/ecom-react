"""Tests for :mod:`kvstore.wal`."""

import os
import tempfile
import unittest

from kvstore.codec import encode
from kvstore.wal import OP_DEL, OP_SET, Record, WriteAheadLog

from .support import append_bytes, read_bytes, truncate_to, wal_path


class WalTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.path = wal_path(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def fresh_log(self):
        log = WriteAheadLog(self.path)
        log.open()
        return log


class AppendReplayTests(WalTestBase):
    def test_empty_log_replays_empty(self):
        log = WriteAheadLog(self.path)
        self.assertEqual(log.recover(), [])

    def test_single_record_roundtrip(self):
        log = self.fresh_log()
        log.append(OP_SET, "a", "1", 1)
        log.close()

        records = WriteAheadLog(self.path).recover()
        self.assertEqual(records, [Record(OP_SET, "a", "1", 1)])

    def test_order_is_preserved(self):
        log = self.fresh_log()
        log.append(OP_SET, "a", "1", 1)
        log.append(OP_SET, "b", "2", 2)
        log.append(OP_DEL, "a", None, 3)
        log.close()

        records = WriteAheadLog(self.path).recover()
        self.assertEqual([r.op for r in records], [OP_SET, OP_SET, OP_DEL])
        self.assertEqual([r.key for r in records], ["a", "b", "a"])
        self.assertEqual([r.seq for r in records], [1, 2, 3])

    def test_value_with_spaces_and_unicode(self):
        log = self.fresh_log()
        log.append(OP_SET, "greeting", "hello world \u00e9\u00e8", 1)
        log.close()

        records = WriteAheadLog(self.path).recover()
        self.assertEqual(records[0].value, "hello world \u00e9\u00e8")

    def test_append_returns_frame_size(self):
        log = self.fresh_log()
        size = log.append(OP_SET, "k", "v", 1)
        log.close()
        self.assertEqual(os.path.getsize(self.path), size)

    def test_unknown_op_rejected(self):
        log = self.fresh_log()
        with self.assertRaises(ValueError):
            log.append("frobnicate", "k", "v", 1)
        log.close()

    def test_append_after_recover_resumes(self):
        log = self.fresh_log()
        log.append(OP_SET, "a", "1", 1)
        log.close()

        log = WriteAheadLog(self.path)
        log.recover()
        log.open()
        log.append(OP_SET, "b", "2", 2)
        log.close()

        records = WriteAheadLog(self.path).recover()
        self.assertEqual([r.key for r in records], ["a", "b"])


class TornWriteTests(WalTestBase):
    def test_partial_trailing_frame_is_discarded(self):
        log = self.fresh_log()
        log.append(OP_SET, "a", "1", 1)
        log.append(OP_SET, "b", "2", 2)
        log.close()

        # Chop the last frame in half: a classic torn write.
        good = read_bytes(self.path)
        append_bytes(self.path, encode(b"WAL1", b'{"op":"set","key":"c","value":"3","seq":3}')[:7])

        log = WriteAheadLog(self.path)
        records = log.recover()
        self.assertEqual([r.key for r in records], ["a", "b"])
        self.assertTrue(log.torn)
        self.assertGreater(log.discarded_bytes, 0)
        self.assertEqual(read_bytes(self.path), good)

    def test_garbage_tail_is_discarded(self):
        log = self.fresh_log()
        log.append(OP_SET, "a", "1", 1)
        log.close()

        append_bytes(self.path, b"\x00\x01\x02not-a-frame")
        log = WriteAheadLog(self.path)
        records = log.recover()
        self.assertEqual([r.key for r in records], ["a"])
        self.assertTrue(log.torn)

    def test_corrupt_crc_in_tail_stops_recovery(self):
        log = self.fresh_log()
        log.append(OP_SET, "a", "1", 1)
        log.append(OP_SET, "b", "2", 2)
        log.close()

        blob = bytearray(read_bytes(self.path))
        blob[-1] ^= 0xFF  # corrupt the payload of the last record
        truncate_to(self.path, 0)
        append_bytes(self.path, bytes(blob))

        log = WriteAheadLog(self.path)
        records = log.recover()
        self.assertEqual([r.key for r in records], ["a"])
        self.assertTrue(log.torn)

    def test_bad_magic_mid_file_stops_recovery(self):
        good = encode(b"WAL1", b'{"op":"set","key":"a","value":"1","seq":1}')
        # A frame with a valid length and checksum but a wrong magic.
        bad = encode(b"XXXX", b'{"op":"set","key":"b","value":"2","seq":2}')
        append_bytes(self.path, good + bad)

        log = WriteAheadLog(self.path)
        records = log.recover()
        self.assertEqual([r.key for r in records], ["a"])
        self.assertTrue(log.torn)
        self.assertEqual(read_bytes(self.path), good)

    def test_repair_allows_new_appends(self):
        log = self.fresh_log()
        log.append(OP_SET, "a", "1", 1)
        log.close()
        append_bytes(self.path, b"torn")

        log = WriteAheadLog(self.path)
        log.recover()
        log.open()
        log.append(OP_SET, "b", "2", 2)
        log.close()

        records = WriteAheadLog(self.path).recover()
        self.assertEqual([r.key for r in records], ["a", "b"])

    def test_clean_log_is_not_flagged_torn(self):
        log = self.fresh_log()
        log.append(OP_SET, "a", "1", 1)
        log.close()

        log = WriteAheadLog(self.path)
        log.recover()
        self.assertFalse(log.torn)
        self.assertEqual(log.discarded_bytes, 0)
        self.assertEqual(log.valid_end, os.path.getsize(self.path))

    def test_truncate_clears_records(self):
        log = self.fresh_log()
        log.append(OP_SET, "a", "1", 1)
        log.truncate()
        self.assertEqual(log.size(), 0)
        log.append(OP_SET, "b", "2", 2)
        log.close()

        records = WriteAheadLog(self.path).recover()
        self.assertEqual([r.key for r in records], ["b"])


class WalLifecycleTests(WalTestBase):
    def test_context_manager(self):
        with WriteAheadLog(self.path) as log:
            log.append(OP_SET, "a", "1", 1)
        records = WriteAheadLog(self.path).recover()
        self.assertEqual(len(records), 1)

    def test_close_is_idempotent(self):
        log = self.fresh_log()
        log.close()
        log.close()  # must not raise
        self.assertIsNone(log._file)

    def test_size_missing_file_is_zero(self):
        log = WriteAheadLog(os.path.join(self.dir, "nope.log"))
        self.assertEqual(log.size(), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
