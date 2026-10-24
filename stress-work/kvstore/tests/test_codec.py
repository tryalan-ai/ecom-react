"""Tests for :mod:`kvstore.codec`."""

import unittest
import zlib

from kvstore.codec import (
    HEADER_SIZE,
    CorruptFrame,
    IncompleteFrame,
    crc32,
    decode,
    encode,
)


class CrcTests(unittest.TestCase):
    def test_crc32_matches_stdlib(self):
        self.assertEqual(crc32(b"hello"), zlib.crc32(b"hello") & 0xFFFFFFFF)

    def test_crc32_is_unsigned(self):
        self.assertGreaterEqual(crc32(b"\xff\xff\xff\xff"), 0)
        self.assertLess(crc32(b"anything"), 2 ** 32)


class EncodeDecodeTests(unittest.TestCase):
    def test_roundtrip(self):
        frame = encode(b"TEST", b"payload-bytes")
        payload, nxt = decode(frame, 0, b"TEST")
        self.assertEqual(payload, b"payload-bytes")
        self.assertEqual(nxt, len(frame))

    def test_empty_payload_roundtrip(self):
        frame = encode(b"TEST", b"")
        payload, nxt = decode(frame, 0, b"TEST")
        self.assertEqual(payload, b"")
        self.assertEqual(nxt, HEADER_SIZE)

    def test_str_magic_accepted(self):
        frame = encode("TEST", b"abc")
        payload, _ = decode(frame, 0, "TEST")
        self.assertEqual(payload, b"abc")

    def test_bad_magic_length_rejected(self):
        with self.assertRaises(ValueError):
            encode(b"TOOLONG", b"x")

    def test_payload_must_be_bytes(self):
        with self.assertRaises(TypeError):
            encode(b"TEST", "a string")

    def test_sequential_frames(self):
        blob = encode(b"TEST", b"one") + encode(b"TEST", b"two") + encode(b"TEST", b"three")
        first, pos = decode(blob, 0, b"TEST")
        second, pos = decode(blob, pos, b"TEST")
        third, pos = decode(blob, pos, b"TEST")
        self.assertEqual((first, second, third), (b"one", b"two", b"three"))
        self.assertEqual(pos, len(blob))

    def test_offset_decode(self):
        prefix = b"GARBAGE"
        frame = encode(b"TEST", b"value")
        payload, nxt = decode(prefix + frame, len(prefix), b"TEST")
        self.assertEqual(payload, b"value")
        self.assertEqual(nxt, len(prefix) + len(frame))


class CorruptFrameTests(unittest.TestCase):
    def test_incomplete_header(self):
        with self.assertRaises(IncompleteFrame):
            decode(b"ab", 0, b"TEST")

    def test_incomplete_payload(self):
        frame = encode(b"TEST", b"0123456789")
        with self.assertRaises(IncompleteFrame):
            decode(frame[:-1], 0, b"TEST")

    def test_checksum_mismatch(self):
        frame = bytearray(encode(b"TEST", b"payload"))
        frame[-1] ^= 0xFF
        with self.assertRaises(CorruptFrame):
            decode(bytes(frame), 0, b"TEST")

    def test_wrong_magic(self):
        frame = encode(b"NOPE", b"payload")
        with self.assertRaises(CorruptFrame):
            decode(frame, 0, b"TEST")

    def test_forced_bad_crc_constructor(self):
        frame = encode(b"TEST", b"payload", crc=12345)
        with self.assertRaises(CorruptFrame):
            decode(frame, 0, b"TEST")

    def test_negative_offset_rejected(self):
        with self.assertRaises(ValueError):
            decode(b"", -1, b"TEST")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
