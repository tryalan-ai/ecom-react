"""A blocking client for the kvstore text protocol."""

import socket

from .errors import CommandError
from .protocol import ERR_PREFIX, OK_PREFIX

#: Default socket timeout in seconds.
DEFAULT_TIMEOUT = 5.0


class KVClient:
    """Minimal blocking client.

    Each method sends one request and returns a plain Python value.  On an
    error response the method raises :class:`~kvstore.errors.CommandError`.
    """

    def __init__(self, host="127.0.0.1", port=0, timeout=DEFAULT_TIMEOUT):
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self._sock = None
        self._buffer = b""

    # -- connection -----------------------------------------------------
    def connect(self):
        self._sock = socket.create_connection((self.host, self.port), self.timeout)
        self._sock.settimeout(self.timeout)
        return self

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
                self._buffer = b""

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    # -- low level ------------------------------------------------------
    def _read_line(self):
        while b"\n" not in self._buffer:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("connection closed by server")
            self._buffer += chunk
        line, _, rest = self._buffer.partition(b"\n")
        self._buffer = rest
        return line.decode("utf-8")

    def command(self, line):
        """Send a raw request line and return the raw response line."""
        if self._sock is None:
            raise ConnectionError("client is not connected")
        self._sock.sendall((line + "\n").encode("utf-8"))
        response = self._read_line()
        if response.startswith(ERR_PREFIX):
            raise CommandError(response[len(ERR_PREFIX):].strip())
        return response

    def _send_ok(self, line, expected="+OK"):
        response = self.command(line)
        if response != expected and not response.startswith(expected + " "):
            raise CommandError("unexpected response: %s" % response)
        return response

    # -- commands -------------------------------------------------------
    def ping(self):
        return self.command("PING") == "+PONG"

    def set(self, key, value):
        self._send_ok("SET %s %s" % (key, value))
        return True

    def get(self, key, default=None):
        response = self.command("GET %s" % key)
        if response == "+NIL":
            return default
        if response.startswith("+VALUE"):
            return response[len("+VALUE"):].lstrip(" ")
        raise CommandError("unexpected response: %s" % response)

    def delete(self, key):
        response = self._send_ok("DEL %s" % key)
        return response == "+OK 1"

    def exists(self, key):
        response = self._send_ok("EXISTS %s" % key)
        return response == "+OK 1"

    def keys(self):
        response = self._send_ok("KEYS", "+KEYS")
        if response == "+KEYS":
            return []
        return response[len("+KEYS "):].split(" ")

    def length(self):
        response = self._send_ok("LEN", "+LEN")
        return int(response.split(" ", 1)[1])

    def snapshot(self):
        self._send_ok("SNAPSHOT")
        return True

    def quit(self):
        try:
            return self.command("QUIT") == "+BYE"
        finally:
            self.close()
