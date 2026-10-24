"""Tests for :mod:`ledger.budget`."""

import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal

from ledger.budget import (
    Budget,
    BudgetStatus,
    Budgets,
    budgets_to_csv,
    load_budgets,
    render_budget_status,
    spend_by_category,
)
from ledger.csv_parser import ParseError, Transaction


def tx(amount, category=None, month=1):
    return Transaction(
        date=date(2024, month, 1),
        description="x",
        amount=Decimal(amount),
        category=category,
    )


SAMPLE = [
    tx("-120.00", "Groceries"),
    tx("-80.00", "Groceries"),
    tx("-30.00", "Transport"),
    tx("2000.00", "Income"),
    tx("-50.00", "Groceries", month=2),
]


class BudgetTests(unittest.TestCase):
    def test_limit_coerced_from_string(self):
        self.assertEqual(Budget("Groceries", "200").limit, Decimal("200"))

    def test_negative_limit_rejected(self):
        with self.assertRaises(ValueError):
            Budget("Groceries", "-1")

    def test_empty_category_rejected(self):
        with self.assertRaises(ValueError):
            Budget("  ", "10")

    def test_to_row(self):
        self.assertEqual(Budget("Groceries", Decimal("150.00")).to_row(), ["Groceries", "150.00"])


class BudgetStatusTests(unittest.TestCase):
    def test_remaining(self):
        status = BudgetStatus("Groceries", Decimal("200"), Decimal("150"))
        self.assertEqual(status.remaining, Decimal("50.00"))

    def test_remaining_negative_when_over(self):
        status = BudgetStatus("Groceries", Decimal("100"), Decimal("150"))
        self.assertEqual(status.remaining, Decimal("-50.00"))

    def test_overspend_only_when_over(self):
        self.assertEqual(BudgetStatus("G", Decimal("100"), Decimal("150")).overspend, Decimal("50.00"))
        self.assertEqual(BudgetStatus("G", Decimal("100"), Decimal("40")).overspend, Decimal("0.00"))

    def test_is_over(self):
        self.assertTrue(BudgetStatus("G", Decimal("100"), Decimal("100.01")).is_over)
        self.assertFalse(BudgetStatus("G", Decimal("100"), Decimal("100")).is_over)

    def test_ratio(self):
        self.assertEqual(BudgetStatus("G", Decimal("200"), Decimal("150")).ratio, Decimal("75.00"))

    def test_ratio_zero_limit_no_spend(self):
        self.assertEqual(BudgetStatus("G", Decimal("0"), Decimal("0")).ratio, Decimal("0"))

    def test_ratio_zero_limit_with_spend_is_infinite(self):
        self.assertEqual(BudgetStatus("G", Decimal("0"), Decimal("5")).ratio, Decimal("Infinity"))

    def test_alert_when_over(self):
        self.assertIn("OVER BUDGET", BudgetStatus("G", Decimal("100"), Decimal("150")).alert())

    def test_alert_when_ok(self):
        self.assertIn("OK:", BudgetStatus("G", Decimal("100"), Decimal("40")).alert())


class SpendByCategoryTests(unittest.TestCase):
    def test_expenses_as_positive_magnitudes(self):
        totals = spend_by_category(SAMPLE)
        self.assertEqual(totals["Groceries"], Decimal("250.00"))
        self.assertEqual(totals["Transport"], Decimal("30.00"))

    def test_income_ignored(self):
        self.assertNotIn("Income", spend_by_category(SAMPLE))

    def test_month_filter(self):
        totals = spend_by_category(SAMPLE, month="2024-02")
        self.assertEqual(totals, {"Groceries": Decimal("50.00")})

    def test_uncategorised_bucket(self):
        totals = spend_by_category([tx("-5.00")])
        self.assertEqual(totals, {"Uncategorised": Decimal("5.00")})


class BudgetsTests(unittest.TestCase):
    def test_built_from_mapping(self):
        budgets = Budgets({"Groceries": "200", "Transport": Decimal("50")})
        self.assertEqual(len(budgets), 2)
        self.assertIn("Groceries", budgets)
        self.assertEqual(budgets.limit_for("Transport"), Decimal("50"))

    def test_built_from_budget_iterable(self):
        budgets = Budgets([Budget("Groceries", "200")])
        self.assertEqual(budgets.categories(), ["Groceries"])

    def test_add_returns_self_and_replaces(self):
        budgets = Budgets()
        returned = budgets.add(Budget("Groceries", "100"))
        self.assertIs(returned, budgets)
        budgets.add(Budget("Groceries", "300"))
        self.assertEqual(len(budgets), 1)
        self.assertEqual(budgets.limit_for("Groceries"), Decimal("300"))

    def test_limit_for_unknown_is_zero(self):
        self.assertEqual(Budgets().limit_for("Nope"), Decimal("0"))

    def test_evaluate_includes_zero_spend_categories(self):
        budgets = Budgets({"Groceries": "300", "Dining": "100"})
        statuses = budgets.evaluate(SAMPLE)
        by_category = {status.category: status for status in statuses}
        self.assertEqual(by_category["Dining"].spent, Decimal("0.00"))
        self.assertFalse(by_category["Dining"].is_over)

    def test_evaluate_month_scoped(self):
        budgets = Budgets({"Groceries": "300"})
        statuses = budgets.evaluate(SAMPLE, month="2024-02")
        self.assertEqual(statuses[0].spent, Decimal("50.00"))

    def test_alerts_sorted_by_overspend(self):
        budgets = Budgets({"Groceries": "200", "Transport": "10"})
        alerts = budgets.alerts(SAMPLE)
        self.assertEqual([a.category for a in alerts], ["Groceries", "Transport"])
        self.assertEqual(alerts[0].overspend, Decimal("50.00"))

    def test_alerts_empty_when_within_budget(self):
        budgets = Budgets({"Groceries": "999"})
        self.assertEqual(budgets.alerts(SAMPLE), [])


class LoadBudgetsTests(unittest.TestCase):
    def test_load_from_text(self):
        budgets = load_budgets("category,limit\nGroceries,200\nTransport,50.00\n")
        self.assertEqual(budgets.limit_for("Groceries"), Decimal("200"))
        self.assertEqual(budgets.limit_for("Transport"), Decimal("50.00"))

    def test_load_from_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
            handle.write("category,limit\nGroceries,200\n")
            path = handle.name
        try:
            self.assertEqual(load_budgets(path).limit_for("Groceries"), Decimal("200"))
        finally:
            os.unlink(path)

    def test_empty_source_gives_empty_budgets(self):
        self.assertEqual(len(load_budgets("")), 0)

    def test_missing_columns_raises(self):
        with self.assertRaises(ParseError):
            load_budgets("name,budget\nGroceries,200\n")

    def test_bad_limit_raises_with_line(self):
        with self.assertRaises(ParseError) as ctx:
            load_budgets("category,limit\nGroceries,oops\n")
        self.assertIn("line 2", str(ctx.exception))


class SerialisationTests(unittest.TestCase):
    def test_budgets_to_csv(self):
        text = budgets_to_csv([Budget("Groceries", "200"), Budget("Transport", "50")])
        self.assertIn("category,limit", text)
        self.assertIn("Groceries,200", text)

    def test_render_budget_status_flags_over(self):
        statuses = [
            BudgetStatus("Groceries", Decimal("200"), Decimal("250")),
            BudgetStatus("Transport", Decimal("50"), Decimal("10")),
        ]
        text = render_budget_status(statuses)
        self.assertIn("OVER", text)
        self.assertIn("Groceries", text)


if __name__ == "__main__":
    unittest.main()
