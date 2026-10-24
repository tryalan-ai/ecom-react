"""Tests for :mod:`ledger.cli`."""

import contextlib
import io
import os
import tempfile
import unittest

from ledger.cli import build_parser, main

STATEMENT = (
    "date,description,amount\n"
    "2024-01-15,Salary January,2500.00\n"
    "2024-01-18,Tesco groceries,-45.50\n"
    "2024-02-02,Starbucks coffee,-3.20\n"
)


class ParserTests(unittest.TestCase):
    def test_parser_has_all_commands(self):
        parser = build_parser()
        for command in ("summary", "list", "categorize"):
            with self.subTest(command=command):
                args = parser.parse_args([command, "file.csv"])
                self.assertEqual(args.command, command)

    def test_default_delimiter(self):
        args = build_parser().parse_args(["summary", "file.csv"])
        self.assertEqual(args.delimiter, ",")


class MainTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
        handle.write(STATEMENT)
        handle.close()
        self.path = handle.name

    def tearDown(self):
        os.unlink(self.path)

    def _run(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(argv)
        return code, buffer.getvalue()

    def test_summary_exit_code_and_output(self):
        code, output = self._run(["summary", self.path])
        self.assertEqual(code, 0)
        self.assertIn("2024-01", output)
        self.assertIn("2024-02", output)

    def test_summary_single_month(self):
        code, output = self._run(["summary", self.path, "--month", "2024-02"])
        self.assertEqual(code, 0)
        self.assertIn("2024-02", output)
        self.assertNotIn("2024-01", output)

    def test_list_filters_by_category(self):
        code, output = self._run(["list", self.path, "--category", "Groceries"])
        self.assertEqual(code, 0)
        self.assertIn("Tesco groceries", output)
        self.assertNotIn("Salary January", output)

    def test_categorize_to_stdout(self):
        code, output = self._run(["categorize", self.path])
        self.assertEqual(code, 0)
        self.assertIn("category", output)
        self.assertIn("Groceries", output)

    def test_categorize_to_file(self):
        out_path = self.path + ".out.csv"
        try:
            code, _ = self._run(["categorize", self.path, "--output", out_path])
            self.assertEqual(code, 0)
            with open(out_path, encoding="utf-8") as handle:
                contents = handle.read()
            self.assertIn("Groceries", contents)
        finally:
            if os.path.exists(out_path):
                os.unlink(out_path)

    def test_missing_file_returns_two(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(["summary", self.path + ".missing"])
        self.assertEqual(code, 2)
        self.assertIn("error", stderr.getvalue())

    def test_parse_error_returns_two(self):
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
        handle.write("date,description,amount\n2024-01-15,Salary,oops\n")
        handle.close()
        try:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = main(["summary", handle.name])
            self.assertEqual(code, 2)
        finally:
            os.unlink(handle.name)


if __name__ == "__main__":
    unittest.main()
