"""A small threaded TCP server speaking the kvstore text protocol."""

import socketserver

from .protocol import MAX_LINE, execute


class _Handler(socketserver.StreamRequestHandler):
    """Handle one client connection, one request line at a time."""

    def handle(self):
        store = self.server.store
        while True:
            raw = self.rfile.readline(MAX_LINE)
            if not raw:
                break
            if not raw.endswith(b"\n") and len(raw) >= MAX_LINE:
                self.wfile.write(b"-ERR line too long\n")
                break
            try:
                line = raw.decode("utf-8")
            except UnicodeDecodeError:
                self.wfile.write(b"-ERR invalid utf-8\n")
                continue
            response, close = execute(store, line)
            self.wfile.write(response)
            self.wfile.flush()
            if close:
                break


class _ThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class KVServer:
    """Serve a :class:`~kvstore.store.KVStore` over TCP.

    Use :meth:`serve_forever` for a blocking server, or :meth:`start` /
    :meth:`stop` to run it on a background thread (handy in tests).  When
    ``port`` is 0 the operating system picks a free port, available as
    :attr:`port` after construction.
    """

    def __init__(self, store, host="127.0.0.1", port=0):
        self.store = store
        self._server = _ThreadingTCPServer((host, port), _Handler)
        self._server.store = store
        self._thread = None
        self.host = self._server.server_address[0]
        self.port = self._server.server_address[1]

    @property
    def address(self):
        return (self.host, self.port)

    def serve_forever(self):
        self._server.serve_forever()

    def start(self):
        """Run the server on a daemon background thread."""
        import threading

        self._thread = threading.Thread(
            target=self._server.serve_forever, name="kvstore-server", daemon=True
        )
        self._thread.start()
        return self

    def stop(self):
        """Stop serving and wait for the background thread to finish."""
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        self.stop()
        return False
