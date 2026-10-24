"""Point-in-time snapshots of the whole key space.

A snapshot is a single frame (see :mod:`kvstore.codec`) whose payload is a JSON
document::

    {"seq": 42, "data": {"key": "value", ...}}

Snapshots are written to a temporary file and moved into place with
:func:`os.replace`, which is atomic on POSIX and Windows.  Before the move the
previous snapshot is copied to ``<path>.bak`` so that a snapshot that turns out
to be unreadable (for example because a test forced a torn file) can fall back
to the last known good copy.

``seq`` records the highest log sequence number included in the snapshot.  A
recovering store replays only log records with a larger sequence number, which
makes crash recovery between "snapshot written" and "log truncated" safe.
"""

import json
import os
import shutil

from .codec import FrameError, decode, encode

#: Magic used for the single snapshot frame.
SNAPSHOT_MAGIC = b"SNAP"

#: Suffix of the previous-generation snapshot kept for fallback.
BACKUP_SUFFIX = ".bak"


def snapshot_path(data_dir):
    """Return the default snapshot path inside ``data_dir``."""
    return os.path.join(os.fspath(data_dir), "snapshot.kv")


def encode_snapshot(seq, data):
    """Return the bytes of a snapshot frame for ``data`` at sequence ``seq``."""
    payload = json.dumps(
        {"seq": int(seq), "data": data},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return encode(SNAPSHOT_MAGIC, payload)


def decode_snapshot(blob):
    """Decode snapshot bytes into a ``(seq, data)`` tuple.

    Raises :class:`kvstore.codec.FrameError` if the frame is unreadable and
    :class:`ValueError` if the payload is not a valid snapshot document.
    """
    payload, _ = decode(blob, 0, SNAPSHOT_MAGIC)
    obj = json.loads(payload.decode("utf-8"))
    data = obj["data"]
    if not isinstance(data, dict):
        raise ValueError("snapshot data must be an object")
    return int(obj.get("seq", 0)), data


def save_snapshot(path, seq, data, fsync=False):
    """Atomically write a snapshot to ``path``.

    Any existing snapshot is first copied to ``path + BACKUP_SUFFIX``.  The new
    content is written to ``path + ".tmp"`` and moved into place with
    :func:`os.replace`.
    """
    path = os.fspath(path)
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)

    if os.path.exists(path):
        shutil.copyfile(path, path + BACKUP_SUFFIX)

    tmp = path + ".tmp"
    blob = encode_snapshot(seq, data)
    with open(tmp, "wb") as handle:
        handle.write(blob)
        handle.flush()
        if fsync:
            os.fsync(handle.fileno())
    os.replace(tmp, path)
    if fsync:
        _fsync_dir(parent)
    return blob


def load_snapshot(path):
    """Load ``path``, falling back to ``path + BACKUP_SUFFIX``.

    Returns ``(seq, data)``.  Returns ``None`` when neither the snapshot nor
    its backup exists or can be decoded, which signals the caller to rebuild
    state purely from the log.
    """
    for candidate in (os.fspath(path), os.fspath(path) + BACKUP_SUFFIX):
        if not os.path.exists(candidate):
            continue
        try:
            with open(candidate, "rb") as handle:
                blob = handle.read()
            return decode_snapshot(blob)
        except (FrameError, ValueError, KeyError, UnicodeDecodeError, OSError):
            continue
    return None


def _fsync_dir(path):
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
