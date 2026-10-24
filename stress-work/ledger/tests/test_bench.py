"""Tests for :mod:`ledger.bench`."""

import contextlib
import io
import os
import tempfile
import unittest

from ledger.bench import DEFAULT_COUNT, DEFAULT_PATH, generate, main, run
from ledger.csv_parser import parse_csv


class GenerateTests(unittest.TestCase):
    def test_writes_header_and_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "small.csv")
            generate(path, 250)
            transactions = parse_csv(path)
            self.assertEqual(len(transactions), 250)

    def test_is_deterministic_for_a_seed(self):
        with tempfile.TemporaryDirectory() as folder:
            first = os.path.join(folder, "a.csv")
            second = os.path.join(folder, "b.csv")
            generate(first, 100, seed=42)
            generate(second, 100, seed=42)
            with open(first, encoding="utf-8") as handle_a, open(second, encoding="utf-8") as handle_b:
                self.assertEqual(handle_a.read(), handle_b.read())

    def test_different_seeds_differ(self):
        with tempfile.TemporaryDirectory() as folder:
            first = os.path.join(folder, "a.csv")
            second = os.path.join(folder, "b.csv")
            generate(first, 100, seed=1)
            generate(second, 100, seed=2)
            with open(first, encoding="utf-8") as handle_a, open(second, encoding="utf-8") as handle_b:
                self.assertNotEqual(handle_a.read(), handle_b.read())

    def test_header_is_date_description_amount(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "small.csv")
            generate(path, 5)
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(handle.readline().strip(), "date,description,amount")


class RunTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
        handle.close()
        self.path = handle.name
        generate(self.path, 400)

    def tearDown(self):
        if os.path.exists(self.path):
            os.unlink(self.path)

    def test_run_returns_timings(self):
        with contextlib.redirect_stdout(io.StringIO()):
            timings = run(self.path, 400)
        self.assertEqual(set(timings), {"parse", "summary", "total"})
        self.assertAlmostEqual(timings["total"], timings["parse"] + timings["summary"])
        self.assertGreaterEqual(timings["total"], 0.0)

    def test_run_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            run(self.path + ".missing", 0)

    def test_main_skip_generate_returns_zero(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(["--path", self.path, "--count", "400", "--skip-generate"])
        self.assertEqual(code, 0)


class DefaultsTests(unittest.TestCase):
    def test_default_count_is_two_million(self):
        self.assertEqual(DEFAULT_COUNT, 2_000_000)

    def test_default_path(self):
        self.assertEqual(DEFAULT_PATH, "/tmp/ledger-bench.csv")


if __name__ == "__main__":
    unittest.main()
