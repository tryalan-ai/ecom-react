"""Binary framing shared by the write-ahead log and snapshots.

Every durable unit of data is written as a *frame*::

    +--------+--------+--------+----------------+
    | magic  | length |  crc32 |    payload     |
    | 4 byte | 4 byte | 4 byte |  `length` byte |
    +--------+--------+--------+----------------+

All integers are big-endian unsigned.  ``crc32`` is the CRC-32 (as produced
by :func:`zlib.crc32`) of the payload bytes only.

A reader that encounters a frame whose header or payload is truncated, whose
magic does not match, or whose checksum does not match, must treat the data
from that offset onwards as unusable.  :func:`decode` reports these
conditions with :class:`IncompleteFrame` (not enough bytes yet) and
:class:`CorruptFrame` (bytes present but inconsistent).
"""

import struct
import zlib

#: Header layout: 4 byte magic, 4 byte payload length, 4 byte CRC-32.
HEADER = struct.Struct(">4sII")

#: Size in bytes of a frame header.
HEADER_SIZE = HEADER.size


class FrameError(Exception):
    """Base class for problems decoding a frame."""


class IncompleteFrame(FrameError):
    """There are not enough bytes to decode a whole frame."""


class CorruptFrame(FrameError):
    """The frame bytes are present but internally inconsistent."""


def crc32(data):
    """Return the unsigned 32-bit CRC of ``data``."""
    return zlib.crc32(data) & 0xFFFFFFFF


def _as_magic(magic):
    if isinstance(magic, str):
        magic = magic.encode("ascii")
    if not isinstance(magic, (bytes, bytearray)):
        raise TypeError("magic must be str or bytes")
    if len(magic) != 4:
        raise ValueError("magic must be exactly 4 bytes")
    return bytes(magic)


def encode(magic, payload, crc=None):
    """Encode a single frame.

    ``crc`` may be supplied to force an incorrect checksum, which is handy
    when testing corruption handling.
    """
    magic = _as_magic(magic)
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be bytes")
    payload = bytes(payload)
    if crc is None:
        crc = crc32(payload)
    return HEADER.pack(magic, len(payload), crc) + payload


def decode(data, offset=0, magic=None):
    """Decode the frame starting at ``offset`` in ``data``.

    Returns a ``(payload, next_offset)`` tuple.  Raises
    :class:`IncompleteFrame` if the frame is not fully present and
    :class:`CorruptFrame` if ``magic`` is given and does not match or the
    checksum disagrees.
    """
    if offset < 0:
        raise ValueError("offset must not be negative")
    if len(data) - offset < HEADER_SIZE:
        raise IncompleteFrame("header truncated")

    found_magic, length, stored_crc = HEADER.unpack_from(data, offset)
    if magic is not None:
        magic = _as_magic(magic)
        if found_magic != magic:
            raise CorruptFrame("bad magic %r" % (found_magic,))

    payload_start = offset + HEADER_SIZE
    payload_end = payload_start + length
    if payload_end > len(data):
        raise IncompleteFrame("payload truncated")

    payload = bytes(data[payload_start:payload_end])
    if crc32(payload) != stored_crc:
        raise CorruptFrame("checksum mismatch")

    return payload, payload_end
