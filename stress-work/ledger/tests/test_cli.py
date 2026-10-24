"""Tests for :mod:`ledger.cli` (the import/summary/budget/export subcommands)."""

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

BUDGETS = "category,limit\nGroceries,40.00\nTransport,100.00\n"


class ParserTests(unittest.TestCase):
    def test_parser_has_all_commands(self):
        parser = build_parser()
        for command in ("import", "summary", "budget", "export"):
            with self.subTest(command=command):
                args = parser.parse_args(
                    ["budget", "file.csv", "--budgets", "b.csv"]
                    if command == "budget"
                    else [command, "file.csv"]
                )
                self.assertEqual(args.command, command)

    def test_export_defaults_to_monthly(self):
        args = build_parser().parse_args(["export", "file.csv"])
        self.assertEqual(args.what, "monthly")

    def test_budget_requires_budgets_file(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                build_parser().parse_args(["budget", "file.csv"])


class MainTests(unittest.TestCase):
    def setUp(self):
        self.statement = self._write(STATEMENT)
        self.budgets = self._write(BUDGETS)

    def tearDown(self):
        for path in (self.statement, self.budgets):
            if os.path.exists(path):
                os.unlink(path)

    @staticmethod
    def _write(text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
        handle.write(text)
        handle.close()
        return handle.name

    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_import_to_stdout(self):
        code, output, _ = self._run(["import", self.statement])
        self.assertEqual(code, 0)
        self.assertIn("category", output)
        self.assertIn("Groceries", output)

    def test_import_to_file(self):
        out_path = self.statement + ".imported.csv"
        try:
            code, _, _ = self._run(["import", self.statement, "--output", out_path])
            self.assertEqual(code, 0)
            with open(out_path, encoding="utf-8") as handle:
                self.assertIn("Groceries", handle.read())
        finally:
            if os.path.exists(out_path):
                os.unlink(out_path)

    def test_summary_monthly(self):
        code, output, _ = self._run(["summary", self.statement])
        self.assertEqual(code, 0)
        self.assertIn("2024-01", output)
        self.assertIn("2024-02", output)

    def test_summary_single_month(self):
        code, output, _ = self._run(["summary", self.statement, "--month", "2024-02"])
        self.assertEqual(code, 0)
        self.assertIn("2024-02", output)
        self.assertNotIn("2024-01", output)

    def test_budget_reports_overspend(self):
        code, output, _ = self._run(["budget", self.statement, "--budgets", self.budgets])
        self.assertEqual(code, 0)
        self.assertIn("Groceries", output)
        self.assertIn("OVER", output)
        self.assertIn("OVER BUDGET", output)

    def test_budget_within_limit_not_over(self):
        code, output, _ = self._run(["budget", self.statement, "--budgets", self.budgets])
        self.assertIn("Transport", output)

    def test_budget_alerts_only(self):
        code, output, _ = self._run(
            ["budget", self.statement, "--budgets", self.budgets, "--alerts-only"]
        )
        self.assertEqual(code, 0)
        self.assertIn("Groceries", output)
        self.assertNotIn("Transport", output)

    def test_export_monthly(self):
        code, output, _ = self._run(["export", self.statement])
        self.assertEqual(code, 0)
        self.assertIn("month,income,expenses,net,count", output)

    def test_export_category(self):
        code, output, _ = self._run(["export", self.statement, "--categorise", "--what", "category"])
        self.assertEqual(code, 0)
        self.assertIn("category,total", output)
        self.assertIn("Groceries", output)

    def test_export_transactions(self):
        code, output, _ = self._run(["export", self.statement, "--what", "transactions"])
        self.assertEqual(code, 0)
        self.assertIn("date,description,amount,category", output)

    def test_export_include_categories(self):
        code, output, _ = self._run(["export", self.statement, "--include-categories"])
        self.assertEqual(code, 0)
        self.assertIn("month,category,total", output)

    def test_export_to_file(self):
        out_path = self.statement + ".totals.csv"
        try:
            code, _, _ = self._run(["export", self.statement, "--what", "category", "-o", out_path])
            self.assertEqual(code, 0)
            with open(out_path, encoding="utf-8") as handle:
                self.assertIn("category,total", handle.read())
        finally:
            if os.path.exists(out_path):
                os.unlink(out_path)

    def test_missing_file_returns_two(self):
        code, _, err = self._run(["summary", self.statement + ".missing"])
        self.assertEqual(code, 2)
        self.assertIn("error", err)

    def test_parse_error_returns_two(self):
        bad = self._write("date,description,amount\n2024-01-15,Salary,oops\n")
        try:
            code, _, _ = self._run(["summary", bad])
            self.assertEqual(code, 2)
        finally:
            os.unlink(bad)

    def test_missing_budgets_file_returns_two(self):
        code, _, _ = self._run(["budget", self.statement, "--budgets", self.budgets + ".missing"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
