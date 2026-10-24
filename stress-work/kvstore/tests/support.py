"""Shared helpers for the kvstore test suite."""

import os
import struct


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def write_bytes(path, data):
    with open(path, "wb") as handle:
        handle.write(data)


def append_bytes(path, data):
    with open(path, "ab") as handle:
        handle.write(data)


def truncate_to(path, size):
    with open(path, "r+b") as handle:
        handle.truncate(size)


def frame_offsets(blob):
    """Return the byte offset at which each complete frame in ``blob`` ends."""
    offsets = []
    pos = 0
    header = struct.Struct(">4sII")
    while len(blob) - pos >= header.size:
        _, length, _ = header.unpack_from(blob, pos)
        end = pos + header.size + length
        if end > len(blob):
            break
        offsets.append(end)
        pos = end
    return offsets


def wal_path(data_dir):
    return os.path.join(os.fspath(data_dir), "wal.log")


def snapshot_path(data_dir):
    return os.path.join(os.fspath(data_dir), "snapshot.kv")
