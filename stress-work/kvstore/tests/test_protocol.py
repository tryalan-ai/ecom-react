"""Tests for :mod:`kvstore.protocol` (no sockets involved)."""

import os
import tempfile
import unittest

from kvstore.store import KVStore


class FakeStore:
    """A dict-backed stand-in used for fast protocol tests."""

    def __init__(self):
        self.data = {}
        self.snapshots = 0

    def set(self, key, value):
        self.data[key] = value
        return True

    def get(self, key, default=None):
        return self.data.get(key, default)

    def delete(self, key):
        return self.data.pop(key, None) is not None

    def keys(self):
        return sorted(self.data)

    def snapshot(self):
        self.snapshots += 1
        return 0

    def __len__(self):
        return len(self.data)

    def __contains__(self, key):
        return key in self.data


class ParseTests(unittest.TestCase):
    def test_parse_ping(self):
        from kvstore.protocol import parse_request

        self.assertEqual(parse_request("PING\n"), ("PING", ""))

    def test_parse_is_case_insensitive(self):
        from kvstore.protocol import parse_request

        self.assertEqual(parse_request("set k v\n"), ("SET", "k v"))

    def test_parse_set_keeps_spaces_in_value(self):
        from kvstore.protocol import parse_request

        self.assertEqual(parse_request("SET k hello world"), ("SET", "k hello world"))

    def test_parse_strips_carriage_return(self):
        from kvstore.protocol import parse_request

        self.assertEqual(parse_request("GET k\r\n"), ("GET", "k"))

    def test_parse_blank_raises(self):
        from kvstore.errors import ProtocolError
        from kvstore.protocol import parse_request

        with self.assertRaises(ProtocolError):
            parse_request("\n")

    def test_parse_whitespace_only_raises(self):
        from kvstore.errors import ProtocolError
        from kvstore.protocol import parse_request

        with self.assertRaises(ProtocolError):
            parse_request("   \n")

    def test_parse_non_text_raises(self):
        from kvstore.errors import ProtocolError
        from kvstore.protocol import parse_request

        with self.assertRaises(ProtocolError):
            parse_request(b"PING\n")


class ExecuteTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()

    def ex(self, line):
        from kvstore.protocol import execute

        body, close = execute(self.store, line)
        return body.decode("utf-8").rstrip("\n"), close

    def test_ping(self):
        self.assertEqual(self.ex("PING"), ("+PONG", False))

    def test_set_ok(self):
        self.assertEqual(self.ex("SET k v"), ("+OK", False))
        self.assertEqual(self.store.data, {"k": "v"})

    def test_set_value_with_spaces(self):
        self.ex("SET k a b c")
        self.assertEqual(self.store.data["k"], "a b c")

    def test_set_empty_value(self):
        self.ex("SET k")
        self.assertEqual(self.store.data["k"], "")

    def test_set_missing_key_errors(self):
        body, _ = self.ex("SET")
        self.assertTrue(body.startswith("-ERR"))

    def test_get_value(self):
        self.store.data["k"] = "v"
        self.assertEqual(self.ex("GET k"), ("+VALUE v", False))

    def test_get_value_with_spaces(self):
        self.store.data["k"] = "a b c"
        self.assertEqual(self.ex("GET k"), ("+VALUE a b c", False))

    def test_get_missing_is_nil(self):
        self.assertEqual(self.ex("GET nope"), ("+NIL", False))

    def test_get_missing_key_errors(self):
        body, _ = self.ex("GET")
        self.assertTrue(body.startswith("-ERR"))

    def test_get_key_with_space_errors(self):
        body, _ = self.ex("GET a b")
        self.assertTrue(body.startswith("-ERR"))

    def test_del_existing_and_missing(self):
        self.store.data["k"] = "v"
        self.assertEqual(self.ex("DEL k"), ("+OK 1", False))
        self.assertEqual(self.ex("DEL k"), ("+OK 0", False))

    def test_exists(self):
        self.store.data["k"] = "v"
        self.assertEqual(self.ex("EXISTS k"), ("+OK 1", False))
        self.assertEqual(self.ex("EXISTS z"), ("+OK 0", False))

    def test_keys_empty(self):
        self.assertEqual(self.ex("KEYS"), ("+KEYS", False))

    def test_keys_sorted(self):
        self.store.data.update({"b": "2", "a": "1"})
        self.assertEqual(self.ex("KEYS"), ("+KEYS a b", False))

    def test_len(self):
        self.store.data.update({"a": "1", "b": "2"})
        self.assertEqual(self.ex("LEN"), ("+LEN 2", False))

    def test_snapshot(self):
        self.assertEqual(self.ex("SNAPSHOT"), ("+OK", False))
        self.assertEqual(self.store.snapshots, 1)

    def test_quit_closes(self):
        self.assertEqual(self.ex("QUIT"), ("+BYE", True))

    def test_unknown_command(self):
        body, close = self.ex("WAT")
        self.assertTrue(body.startswith("-ERR"))
        self.assertFalse(close)

    def test_blank_line_error(self):
        body, close = self.ex("\n")
        self.assertTrue(body.startswith("-ERR"))
        self.assertFalse(close)

    def test_error_from_store_is_reported(self):
        class Boom(FakeStore):
            def set(self, key, value):
                raise ValueError("boom")

        from kvstore.protocol import execute

        body, _ = execute(Boom(), "SET k v")
        self.assertIn("boom", body.decode())

    def test_command_case_insensitive_execution(self):
        self.assertEqual(self.ex("ping"), ("+PONG", False))

    def test_trailing_spaces_on_get(self):
        self.store.data["k"] = "v"
        self.assertEqual(self.ex("GET k   "), ("+VALUE v", False))


class ProtocolAgainstRealStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = KVStore(self._tmp.name)

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def ex(self, line):
        from kvstore.protocol import execute

        body, close = execute(self.store, line)
        return body.decode("utf-8").rstrip("\n"), close

    def test_end_to_end_commands(self):
        self.assertEqual(self.ex("SET a 1")[0], "+OK")
        self.assertEqual(self.ex("GET a")[0], "+VALUE 1")
        self.assertEqual(self.ex("LEN")[0], "+LEN 1")
        self.assertEqual(self.ex("DEL a")[0], "+OK 1")
        self.assertEqual(self.ex("GET a")[0], "+NIL")
        self.assertEqual(self.ex("SNAPSHOT")[0], "+OK")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
