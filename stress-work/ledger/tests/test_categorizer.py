"""Tests for :mod:`ledger.categorizer`."""

import unittest
from datetime import date
from decimal import Decimal

from ledger.categorizer import (
    Categorizer,
    Rule,
    categorizer_with_defaults,
    default_rules,
)
from ledger.csv_parser import Transaction


def tx(description, amount, category=None):
    return Transaction(date=date(2024, 1, 1), description=description, amount=Decimal(amount), category=category)


class RuleTests(unittest.TestCase):
    def test_contains_match(self):
        rule = Rule("Coffee", "coffee")
        self.assertTrue(rule.matches(tx("Morning Coffee", "-3.00")))

    def test_regex_match_is_case_insensitive(self):
        rule = Rule("Groceries", pattern=r"tesco|aldi", match="regex")
        self.assertTrue(rule.matches(tx("TESCO STORES", "-20.00")))

    def test_exact_match(self):
        rule = Rule("Rent", "rent", match="exact")
        self.assertTrue(rule.matches(tx("Rent", "-1000")))
        self.assertFalse(rule.matches(tx("Rent payment", "-1000")))

    def test_startswith_match(self):
        rule = Rule("Amazon", "amazon", match="startswith")
        self.assertTrue(rule.matches(tx("Amazon UK", "-5")))
        self.assertFalse(rule.matches(tx("Buy Amazon", "-5")))

    def test_direction_income(self):
        rule = Rule("Income", "salary", direction="income")
        self.assertTrue(rule.matches(tx("Salary", "2000")))
        self.assertFalse(rule.matches(tx("Salary reversal", "-20")))

    def test_direction_expense(self):
        rule = Rule("Spend", "shop", direction="expense")
        self.assertTrue(rule.matches(tx("Shop", "-10")))
        self.assertFalse(rule.matches(tx("Shop refund", "10")))

    def test_amount_bounds(self):
        rule = Rule("Big", min_amount=Decimal("-500"), max_amount=Decimal("-100"))
        self.assertTrue(rule.matches(tx("anything", "-200")))
        self.assertFalse(rule.matches(tx("anything", "-50")))

    def test_invalid_match_type(self):
        with self.assertRaises(ValueError):
            Rule("X", "y", match="fuzzy")


class CategorizerTests(unittest.TestCase):
    def test_first_match_wins_by_priority(self):
        categorizer = Categorizer([
            Rule("Low", "coffee", priority=1),
            Rule("High", "coffee", priority=10),
        ])
        self.assertEqual(categorizer.categorize(tx("coffee", "-3")).category, "High")

    def test_default_fallback(self):
        categorizer = Categorizer([Rule("Coffee", "coffee")], default="Misc")
        self.assertEqual(categorizer.categorize(tx("unknown", "-3")).category, "Misc")

    def test_existing_category_preserved(self):
        categorizer = Categorizer([Rule("Coffee", "coffee")])
        result = categorizer.categorize(tx("coffee", "-3", category="Custom"))
        self.assertEqual(result.category, "Custom")

    def test_categorize_all_preserves_order(self):
        categorizer = Categorizer([Rule("Coffee", "coffee")])
        result = categorizer.categorize_all([tx("coffee", "-3"), tx("bread", "-2")])
        self.assertEqual([r.category for r in result], ["Coffee", "Uncategorised"])

    def test_add_rule_returns_self_and_reorders(self):
        categorizer = Categorizer([Rule("Low", "coffee", priority=1)])
        returned = categorizer.add_rule(Rule("High", "coffee", priority=5))
        self.assertIs(returned, categorizer)
        self.assertEqual(categorizer.rules[0].category, "High")

    def test_matching_rule_none_when_no_match(self):
        categorizer = Categorizer([Rule("Coffee", "coffee")])
        self.assertIsNone(categorizer.matching_rule(tx("nope", "-1")))

    def test_explain_with_rule(self):
        categorizer = Categorizer([Rule("Coffee", "coffee")])
        self.assertIn("Coffee", categorizer.explain(tx("coffee", "-3")))

    def test_explain_without_rule(self):
        categorizer = Categorizer([], default="Misc")
        self.assertIn("no matching rule", categorizer.explain(tx("nope", "-1")))


class DefaultRulesTests(unittest.TestCase):
    def test_groceries_categorised(self):
        result = categorizer_with_defaults().categorize(tx("TESCO STORE 1234", "-30"))
        self.assertEqual(result.category, "Groceries")

    def test_salary_is_income(self):
        result = categorizer_with_defaults().categorize(tx("Salary January", "2500"))
        self.assertEqual(result.category, "Income")

    def test_income_rule_does_not_match_expense(self):
        rules = default_rules()
        income_rule = next(r for r in rules if r.category == "Income")
        self.assertFalse(income_rule.matches(tx("salary", "-2500")))

    def test_default_rules_have_unique_priorities_for_common_categories(self):
        categories = {rule.category for rule in default_rules()}
        self.assertIn("Groceries", categories)
        self.assertIn("Transport", categories)


if __name__ == "__main__":
    unittest.main()
