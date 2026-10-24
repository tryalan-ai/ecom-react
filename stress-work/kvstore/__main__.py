"""Run the kvstore TCP server: ``python -m kvstore --dir ./data --port 7654``."""

import argparse
import signal
import threading

from .server import KVServer
from .store import KVStore


def main(argv=None):
    parser = argparse.ArgumentParser(prog="kvstore", description="kvstore TCP server")
    parser.add_argument("--dir", default="./kvdata", help="data directory")
    parser.add_argument("--host", default="127.0.0.1", help="bind host")
    parser.add_argument("--port", type=int, default=7654, help="bind port (0 = ephemeral)")
    parser.add_argument(
        "--snapshot-every",
        type=int,
        default=0,
        help="take a snapshot every N writes (0 disables)",
    )
    parser.add_argument("--fsync", action="store_true", help="fsync every write")
    args = parser.parse_args(argv)

    store = KVStore(args.dir, snapshot_every=args.snapshot_every, fsync=args.fsync)
    server = KVServer(store, host=args.host, port=args.port)

    def _shutdown(signum, frame):
        # socketserver.shutdown() must not run on the thread that is inside
        # serve_forever(), so hand it to a helper thread.
        threading.Thread(target=server.stop, daemon=True).start()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    print("kvstore listening on %s:%d (dir=%s)" % (server.host, server.port, args.dir))
    try:
        server.serve_forever()
    finally:
        store.close()


if __name__ == "__main__":  # pragma: no cover
    main()
