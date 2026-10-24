"""The in-process key-value store built on the log and snapshots."""

import os
import threading

from .snapshot import load_snapshot, save_snapshot, snapshot_path
from .wal import OP_DEL, OP_SET, WriteAheadLog

#: Default WAL file name inside the data directory.
WAL_NAME = "wal.log"


class KVStore:
    """A crash-safe, embedding friendly key-value store.

    Parameters
    ----------
    data_dir:
        Directory holding ``wal.log`` and ``snapshot.kv``.  Created if missing.
    snapshot_every:
        When greater than zero, a snapshot is taken automatically after this
        many successful writes.  ``0`` (the default) disables auto snapshots.
    fsync:
        When true, every write and snapshot is flushed to stable storage.
    """

    def __init__(self, data_dir, snapshot_every=0, fsync=False):
        self.data_dir = os.fspath(data_dir)
        os.makedirs(self.data_dir, exist_ok=True)
        self.wal_path = os.path.join(self.data_dir, WAL_NAME)
        self.snapshot_path = snapshot_path(self.data_dir)
        self.snapshot_every = int(snapshot_every)
        self.fsync = bool(fsync)

        self._data = {}
        self._seq = 0
        self._writes_since_snapshot = 0
        self._snapshots = 0
        self._closed = False
        self._lock = threading.RLock()

        self.wal = WriteAheadLog(self.wal_path, fsync=self.fsync)
        self._recover()
        self.wal.open()

    # -- recovery -------------------------------------------------------
    def _recover(self):
        """Rebuild in-memory state from the snapshot and the log."""
        loaded = load_snapshot(self.snapshot_path)
        if loaded is not None:
            self._seq, data = loaded
            self._data = dict(data)

        records = self.wal.recover()
        applied = 0
        for record in records:
            if record.seq and record.seq <= self._seq:
                # Already represented by the snapshot.
                continue
            self._apply(record.op, record.key, record.value)
            if record.seq:
                self._seq = max(self._seq, record.seq)
            applied += 1
        self._last_replayed = applied
        self._writes_since_snapshot = 0

    def _apply(self, op, key, value):
        if op == OP_SET:
            self._data[key] = value
        elif op == OP_DEL:
            self._data.pop(key, None)
        else:  # pragma: no cover - the WAL never emits unknown ops
            raise ValueError("unknown op %r" % (op,))

    # -- validation -----------------------------------------------------
    @staticmethod
    def _check_text(value, name):
        if not isinstance(value, str):
            raise TypeError("%s must be a str, got %s" % (name, type(value).__name__))
        return value

    # -- public API -----------------------------------------------------
    def set(self, key, value):
        """Store ``value`` under ``key`` durably and return ``True``."""
        key = self._check_text(key, "key")
        value = self._check_text(value, "value")
        if not key:
            raise ValueError("key must not be empty")
        with self._lock:
            self._ensure_open()
            self._seq += 1
            self.wal.append(OP_SET, key, value, self._seq)
            self._data[key] = value
            self._writes_since_snapshot += 1
            self._maybe_snapshot()
        return True

    def get(self, key, default=None):
        """Return the value stored under ``key`` or ``default``."""
        self._check_text(key, "key")
        with self._lock:
            return self._data.get(key, default)

    def delete(self, key):
        """Remove ``key``; return ``True`` if it existed."""
        key = self._check_text(key, "key")
        with self._lock:
            self._ensure_open()
            existed = key in self._data
            self._seq += 1
            self.wal.append(OP_DEL, key, None, self._seq)
            self._data.pop(key, None)
            self._writes_since_snapshot += 1
            self._maybe_snapshot()
        return existed

    def exists(self, key):
        """Return ``True`` if ``key`` is present."""
        return key in self

    def keys(self):
        """Return a sorted snapshot of the current keys."""
        with self._lock:
            return sorted(self._data)

    def items(self):
        """Return a sorted list of ``(key, value)`` pairs."""
        with self._lock:
            return sorted(self._data.items())

    def __len__(self):
        with self._lock:
            return len(self._data)

    def __contains__(self, key):
        with self._lock:
            return key in self._data

    @property
    def seq(self):
        """Highest sequence number assigned so far."""
        with self._lock:
            return self._seq

    @property
    def snapshot_count(self):
        """How many snapshots this process has written."""
        with self._lock:
            return self._snapshots

    def snapshot(self):
        """Force a snapshot and truncate the log.  Returns the sequence."""
        with self._lock:
            self._ensure_open()
            self._snapshot_locked()
            return self._seq

    def _maybe_snapshot(self):
        if self.snapshot_every and self._writes_since_snapshot >= self.snapshot_every:
            self._snapshot_locked()

    def _snapshot_locked(self):
        save_snapshot(self.snapshot_path, self._seq, self._data, fsync=self.fsync)
        self.wal.truncate()
        self._writes_since_snapshot = 0
        self._snapshots += 1

    def close(self):
        """Flush and release the log.  Idempotent."""
        with self._lock:
            if not self._closed:
                self.wal.close()
                self._closed = True

    def _ensure_open(self):
        if self._closed:
            raise ValueError("store is closed")

    # -- context manager ------------------------------------------------
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def __repr__(self):  # pragma: no cover - debugging helper
        return "KVStore(data_dir=%r, keys=%d, seq=%d)" % (
            self.data_dir,
            len(self._data),
            self._seq,
        )
