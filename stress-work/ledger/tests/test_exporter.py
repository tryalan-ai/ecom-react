"""Tests for :mod:`ledger.exporter`."""

import io
import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal

from ledger.budget import BudgetStatus
from ledger.csv_parser import Transaction
from ledger.exporter import (
    budget_status_to_csv,
    category_totals_to_csv,
    summaries_to_csv,
    transactions_to_csv,
    write_csv,
)
from ledger.summary import MonthlySummary, monthly_summaries


def tx(amount, category, month=1):
    return Transaction(
        date=date(2024, month, 10),
        description=f"desc {category}",
        amount=Decimal(amount),
        category=category,
    )


SAMPLE = [tx("2000", "Income"), tx("-500", "Groceries"), tx("-100", "Transport", month=2)]


class TransactionsToCsvTests(unittest.TestCase):
    def test_header_and_rows(self):
        text = transactions_to_csv([tx("-5", "Groceries")])
        lines = text.strip().splitlines()
        self.assertEqual(lines[0], "date,description,amount,category")
        self.assertIn("Groceries", lines[1])
        self.assertIn("-5", lines[1])

    def test_custom_delimiter(self):
        text = transactions_to_csv([tx("-5", "Groceries")], delimiter=";")
        self.assertIn("date;description", text)

    def test_uncategorised_blank_category(self):
        text = transactions_to_csv([Transaction(date(2024, 1, 1), "x", Decimal("-1"))])
        self.assertTrue(text.strip().splitlines()[1].endswith(","))


class SummariesToCsvTests(unittest.TestCase):
    def test_header_and_month_rows(self):
        text = summaries_to_csv(monthly_summaries(SAMPLE))
        lines = text.strip().splitlines()
        self.assertEqual(lines[0], "month,income,expenses,net,count")
        self.assertTrue(any(line.startswith("2024-01") for line in lines))
        self.assertTrue(any(line.startswith("2024-02") for line in lines))

    def test_accepts_iterable_of_summaries(self):
        summary = MonthlySummary(month="2024-01", income=Decimal("10"), expenses=Decimal("5"), count=2)
        text = summaries_to_csv([summary])
        self.assertIn("2024-01,10,5,5.00,2", text)

    def test_include_categories_appends_block(self):
        text = summaries_to_csv(monthly_summaries(SAMPLE), include_categories=True)
        self.assertIn("month,category,total", text)
        self.assertIn("2024-01,Groceries,-500", text)


class CategoryTotalsToCsvTests(unittest.TestCase):
    def test_mapping_input(self):
        text = category_totals_to_csv({"Groceries": Decimal("-500")})
        self.assertEqual(text.strip().splitlines(), ["category,total", "Groceries,-500"])

    def test_iterable_input(self):
        text = category_totals_to_csv([("Income", Decimal("2000"))])
        self.assertIn("Income,2000", text)


class BudgetStatusToCsvTests(unittest.TestCase):
    def test_rows_include_over_flag(self):
        statuses = [
            BudgetStatus("Groceries", Decimal("200"), Decimal("250")),
            BudgetStatus("Transport", Decimal("100"), Decimal("40")),
        ]
        text = budget_status_to_csv(statuses)
        lines = text.strip().splitlines()
        self.assertEqual(lines[0], "category,limit,spent,remaining,over,overspend")
        self.assertIn("Groceries,200,250,-50.00,yes,50.00", lines[1])
        self.assertIn("Transport,100,40,60.00,no,0.00", lines[2])


class WriteCsvTests(unittest.TestCase):
    def test_write_to_file_object(self):
        buffer = io.StringIO()
        write_csv("hello\n", buffer)
        self.assertEqual(buffer.getvalue(), "hello\n")

    def test_write_to_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "out.csv")
            write_csv("a,b\n1,2\n", path)
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "a,b\n1,2\n")

    def test_write_dash_is_stdout(self):
        import contextlib

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            write_csv("to stdout\n", "-")
        self.assertEqual(buffer.getvalue(), "to stdout\n")


if __name__ == "__main__":
    unittest.main()
