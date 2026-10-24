"""Append-only write-ahead log with torn-write tolerant recovery.

The log is a sequence of frames (see :mod:`kvstore.codec`) whose payloads are
compact JSON objects::

    {"op": "set", "key": "k", "value": "v", "seq": 7}
    {"op": "del", "key": "k", "value": null, "seq": 8}

Because every frame carries a length and a CRC-32, a write that is cut short
by a crash (a *torn write*) is detected on the next open.  Recovery stops at
the first frame that cannot be fully and correctly decoded, discards
everything after it, and truncates the file so that subsequent appends start
from a clean boundary.
"""

import json
import os
import threading
from typing import NamedTuple, Optional

from .codec import FrameError, decode, encode

#: Magic used for every WAL frame.
WAL_MAGIC = b"WAL1"

#: Operation names understood by the log.
OP_SET = "set"
OP_DEL = "del"
OP_CHOICES = (OP_SET, OP_DEL)


class Record(NamedTuple):
    """A single decoded log record."""

    op: str
    key: str
    value: Optional[str]
    seq: int


class WriteAheadLog:
    """A durable, append-only log of mutations.

    Parameters
    ----------
    path:
        File that backs the log.  Parent directories are created on demand.
    fsync:
        When true, every append is flushed to stable storage with
        :func:`os.fsync` before returning.
    """

    def __init__(self, path, fsync=False):
        self.path = os.fspath(path)
        self.fsync = fsync
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        self._file = None
        self._lock = threading.Lock()
        # Recovery bookkeeping, exposed for tests and diagnostics.
        self.torn = False
        self.discarded_bytes = 0
        self.valid_end = 0

    # -- lifecycle ------------------------------------------------------
    def recover(self):
        """Read all valid records, repairing any torn tail.

        Returns the list of records that were durably written and fully
        intact.  Must be called before :meth:`open`.
        """
        with self._lock:
            return self._recover_locked()

    def _recover_locked(self):
        self.torn = False
        self.discarded_bytes = 0
        self.valid_end = 0
        if not os.path.exists(self.path):
            return []

        with open(self.path, "rb") as handle:
            data = handle.read()

        records = []
        pos = 0
        total = len(data)
        while pos < total:
            try:
                payload, nxt = decode(data, pos, WAL_MAGIC)
            except FrameError:
                break
            try:
                obj = json.loads(payload.decode("utf-8"))
                record = Record(
                    op=obj["op"],
                    key=obj["key"],
                    value=obj.get("value"),
                    seq=int(obj.get("seq", 0)),
                )
            except (ValueError, KeyError, TypeError, UnicodeDecodeError):
                break
            records.append(record)
            pos = nxt

        if pos < total:
            self.torn = True
            self.discarded_bytes = total - pos
            with open(self.path, "r+b") as handle:
                handle.truncate(pos)
                handle.flush()
                if self.fsync:
                    os.fsync(handle.fileno())

        self.valid_end = pos
        return records

    def open(self):
        """Open the log for appending."""
        with self._lock:
            if self._file is None:
                self._file = open(self.path, "ab")
            return self

    def close(self):
        with self._lock:
            if self._file is not None:
                try:
                    self._file.flush()
                    if self.fsync:
                        os.fsync(self._file.fileno())
                finally:
                    self._file.close()
                    self._file = None

    # -- mutation -------------------------------------------------------
    def append(self, op, key, value=None, seq=0):
        """Append one record and return its byte length."""
        if op not in OP_CHOICES:
            raise ValueError("unknown op %r" % (op,))
        payload = json.dumps(
            {"op": op, "key": key, "value": value, "seq": int(seq)},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        frame = encode(WAL_MAGIC, payload)
        with self._lock:
            if self._file is None:
                self._file = open(self.path, "ab")
            self._file.write(frame)
            self._file.flush()
            if self.fsync:
                os.fsync(self._file.fileno())
            self.valid_end += len(frame)
        return len(frame)

    def truncate(self):
        """Discard every record, keeping the file open for appends.

        The file object is opened in append mode, so it always seeks to the
        (now zero) end before the next write.
        """
        with self._lock:
            if self._file is not None:
                self._file.flush()
            with open(self.path, "wb") as handle:
                if self.fsync:
                    os.fsync(handle.fileno())
            self.valid_end = 0
            self.torn = False
            self.discarded_bytes = 0

    def size(self):
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0

    # -- context manager ------------------------------------------------
    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False
