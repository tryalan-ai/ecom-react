"""kvstore: an embedded, crash-safe key-value store.

The package is deliberately dependency free and uses only the Python
standard library.  It provides:

* an append-only write-ahead log (WAL) with per-record checksums,
* point-in-time snapshots written atomically,
* crash recovery that treats a partially written (torn) record as the end
  of the log and repairs the file,
* a small in-process :class:`KVStore` API,
* a tiny line oriented TCP server/client pair.

Typical use::

    from kvstore import KVStore

    with KVStore("/var/lib/mykv") as store:
        store.set("hello", "world")
        store.snapshot()
"""

from .codec import CorruptFrame, FrameError, IncompleteFrame
from .errors import CommandError, KVError, ProtocolError
from .store import KVStore
from .wal import Record, WriteAheadLog

__all__ = [
    "KVStore",
    "WriteAheadLog",
    "Record",
    "KVError",
    "ProtocolError",
    "CommandError",
    "FrameError",
    "IncompleteFrame",
    "CorruptFrame",
]

__version__ = "1.0.0"
