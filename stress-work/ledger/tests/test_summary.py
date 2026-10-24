"""Tests for :mod:`ledger.summary`."""

import unittest
from datetime import date
from decimal import Decimal

from ledger.csv_parser import Transaction
from ledger.summary import (
    MonthlySummary,
    category_totals,
    month_key,
    monthly_summaries,
    render_summary,
    summarise,
)


def tx(day, amount, category=None, month=1, year=2024):
    return Transaction(
        date=date(year, month, day),
        description="x",
        amount=Decimal(amount),
        category=category,
    )


SAMPLE = [
    tx(1, "2000", "Income"),
    tx(2, "-500", "Groceries"),
    tx(3, "-100", "Transport"),
    tx(1, "-300", "Groceries", month=2),
]


class MonthKeyTests(unittest.TestCase):
    def test_month_key(self):
        self.assertEqual(month_key(date(2024, 3, 9)), "2024-03")

    def test_month_key_pads_single_digit(self):
        self.assertEqual(month_key(date(2024, 1, 1)), "2024-01")


class MonthlySummaryTests(unittest.TestCase):
    def test_income_expenses_net(self):
        summary = summarise(SAMPLE)
        self.assertEqual(summary.income, Decimal("2000"))
        self.assertEqual(summary.expenses, Decimal("900"))
        self.assertEqual(summary.net, Decimal("1100"))
        self.assertEqual(summary.count, 4)

    def test_savings_rate(self):
        summary = MonthlySummary(month="2024-01", income=Decimal("2000"), expenses=Decimal("500"))
        self.assertEqual(summary.savings_rate, Decimal("0.7500"))

    def test_savings_rate_zero_income(self):
        summary = MonthlySummary(month="2024-01", expenses=Decimal("500"))
        self.assertEqual(summary.savings_rate, Decimal("0"))

    def test_by_category_totals(self):
        summary = summarise(SAMPLE)
        self.assertEqual(summary.by_category["Groceries"], Decimal("-800"))
        self.assertEqual(summary.by_category["Income"], Decimal("2000"))

    def test_monthly_summaries_groups_and_sorts(self):
        result = monthly_summaries(SAMPLE)
        self.assertEqual(list(result), ["2024-01", "2024-02"])
        self.assertEqual(result["2024-01"].count, 3)

    def test_summarise_filters_month(self):
        summary = summarise(SAMPLE, month="2024-02")
        self.assertEqual(summary.count, 1)
        self.assertEqual(summary.expenses, Decimal("300"))

    def test_summarise_all_uses_all_key(self):
        self.assertEqual(summarise(SAMPLE).month, "all")


class CategoryTotalsTests(unittest.TestCase):
    def test_totals_sorted_by_absolute_value(self):
        totals = category_totals(SAMPLE)
        self.assertEqual(list(totals), ["Income", "Groceries", "Transport"])
        self.assertEqual(totals["Groceries"], Decimal("-800"))

    def test_uncategorised_bucket(self):
        totals = category_totals([tx(1, "-5")])
        self.assertEqual(totals, {"Uncategorised": Decimal("-5")})


class RenderSummaryTests(unittest.TestCase):
    def test_render_contains_header_and_totals(self):
        text = render_summary(monthly_summaries(SAMPLE))
        self.assertIn("Month", text)
        self.assertIn("2024-01", text)
        self.assertIn("2000", text)

    def test_render_empty(self):
        self.assertIn("Month", render_summary([]))


if __name__ == "__main__":
    unittest.main()
