"""Integration tests for the TCP server and client."""

import socket
import tempfile
import unittest

from kvstore.client import KVClient
from kvstore.errors import CommandError
from kvstore.server import KVServer
from kvstore.store import KVStore


class ServerTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = KVStore(self._tmp.name)
        self.server = KVServer(self.store, host="127.0.0.1", port=0).start()
        self.clients = []

    def tearDown(self):
        for client in self.clients:
            client.close()
        self.server.stop()
        self.store.close()
        self._tmp.cleanup()

    def client(self):
        client = KVClient(*self.server.address, timeout=5.0).connect()
        self.clients.append(client)
        return client


class ServerLifecycleTests(ServerTestBase):
    def test_ephemeral_port_assigned(self):
        self.assertGreater(self.server.port, 0)

    def test_address_tuple(self):
        self.assertEqual(self.server.address, ("127.0.0.1", self.server.port))


class ServerStopTests(unittest.TestCase):
    def test_stop_twice_is_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = KVStore(tmp)
            server = KVServer(store, port=0).start()
            server.stop()
            server.stop()  # must not raise or hang
            store.close()

    def test_server_context_manager(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = KVStore(tmp)
            with KVServer(store, port=0) as server:
                with KVClient(*server.address) as client:
                    client.set("k", "v")
                    self.assertEqual(client.get("k"), "v")
            store.close()

    def test_stop_callable_from_other_thread(self):
        import threading

        with tempfile.TemporaryDirectory() as tmp:
            store = KVStore(tmp)
            server = KVServer(store, port=0).start()
            stopper = threading.Thread(target=server.stop)
            stopper.start()
            stopper.join(timeout=5)
            self.assertFalse(stopper.is_alive())
            store.close()


class ClientCommandTests(ServerTestBase):
    def test_ping(self):
        self.assertTrue(self.client().ping())

    def test_set_get(self):
        client = self.client()
        client.set("a", "1")
        self.assertEqual(client.get("a"), "1")

    def test_get_missing(self):
        self.assertIsNone(self.client().get("nope"))
        self.assertEqual(self.client().get("nope", "d"), "d")

    def test_value_with_spaces(self):
        client = self.client()
        client.set("msg", "hello there world")
        self.assertEqual(client.get("msg"), "hello there world")

    def test_delete(self):
        client = self.client()
        client.set("a", "1")
        self.assertTrue(client.delete("a"))
        self.assertFalse(client.delete("a"))

    def test_exists(self):
        client = self.client()
        client.set("a", "1")
        self.assertTrue(client.exists("a"))
        self.assertFalse(client.exists("b"))

    def test_keys_and_length(self):
        client = self.client()
        client.set("b", "2")
        client.set("a", "1")
        self.assertEqual(client.keys(), ["a", "b"])
        self.assertEqual(client.length(), 2)

    def test_snapshot_command(self):
        client = self.client()
        client.set("a", "1")
        self.assertTrue(client.snapshot())
        self.assertEqual(self.store.snapshot_count, 1)

    def test_quit(self):
        client = self.client()
        self.assertTrue(client.quit())

    def test_unknown_command_raises(self):
        client = self.client()
        with self.assertRaises(CommandError):
            client.command("FROBNICATE")

    def test_overwrite(self):
        client = self.client()
        client.set("a", "1")
        client.set("a", "2")
        self.assertEqual(client.get("a"), "2")


class ServerConcurrencyTests(ServerTestBase):
    def test_multiple_clients_share_state(self):
        c1 = self.client()
        c2 = self.client()
        c1.set("shared", "yes")
        self.assertEqual(c2.get("shared"), "yes")

    def test_two_connection_lifecycles(self):
        for _ in range(2):
            with KVClient(*self.server.address) as client:
                self.assertTrue(client.ping())

    def test_context_manager_client(self):
        with KVClient(*self.server.address) as client:
            client.set("x", "1")
            self.assertEqual(client.get("x"), "1")


class RawProtocolTests(ServerTestBase):
    def _raw(self, payload, lines=1):
        sock = socket.create_connection(self.server.address, timeout=5.0)
        try:
            sock.sendall(payload)
            buf = b""
            while buf.count(b"\n") < lines:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
            return buf.decode("utf-8")
        finally:
            sock.close()

    def test_raw_ping(self):
        self.assertEqual(self._raw(b"PING\n"), "+PONG\n")

    def test_raw_set_get(self):
        self._raw(b"SET k v\n")
        self.assertEqual(self._raw(b"GET k\n"), "+VALUE v\n")

    def test_raw_bad_line(self):
        self.assertTrue(self._raw(b"\n").startswith("-ERR"))

    def test_multiple_commands_one_message(self):
        response = self._raw(b"PING\nPING\n", lines=2)
        self.assertEqual(response, "+PONG\n+PONG\n")

    def test_line_too_long_is_rejected(self):
        response = self._raw(b"GET " + b"a" * 70000 + b"\n")
        self.assertTrue(response.startswith("-ERR"))


class ServerPersistenceTests(unittest.TestCase):
    def test_writes_visible_after_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = KVStore(tmp)
            server = KVServer(store, port=0).start()
            try:
                with KVClient(*server.address) as client:
                    client.set("persisted", "value")
                    client.snapshot()
            finally:
                server.stop()
                store.close()

            reopened = KVStore(tmp)
            try:
                self.assertEqual(reopened.get("persisted"), "value")
            finally:
                reopened.close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
