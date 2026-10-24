"""Tests for :mod:`ledger.csv_parser`."""

import io
import tempfile
import unittest
from datetime import date
from decimal import Decimal

from ledger.csv_parser import (
    ParseError,
    Transaction,
    parse_amount,
    parse_csv,
    parse_date,
    total,
)


class ParseAmountTests(unittest.TestCase):
    def test_plain_decimal(self):
        self.assertEqual(parse_amount("12.34"), Decimal("12.34"))

    def test_thousands_separator(self):
        self.assertEqual(parse_amount("1,234.56"), Decimal("1234.56"))

    def test_currency_symbol(self):
        self.assertEqual(parse_amount("$1,234.56"), Decimal("1234.56"))

    def test_parentheses_is_negative(self):
        self.assertEqual(parse_amount("(12.34)"), Decimal("-12.34"))

    def test_trailing_minus_is_negative(self):
        self.assertEqual(parse_amount("12.34-"), Decimal("-12.34"))

    def test_leading_plus(self):
        self.assertEqual(parse_amount("+5.00"), Decimal("5.00"))

    def test_lone_sign_is_zero(self):
        self.assertEqual(parse_amount("-"), Decimal("0"))

    def test_int_and_decimal_passthrough(self):
        self.assertEqual(parse_amount(5), Decimal("5"))
        self.assertEqual(parse_amount(Decimal("1.5")), Decimal("1.5"))

    def test_empty_raises(self):
        with self.assertRaises(ParseError):
            parse_amount("")

    def test_garbage_raises(self):
        with self.assertRaises(ParseError):
            parse_amount("abc")


class ParseDateTests(unittest.TestCase):
    def test_iso_format(self):
        self.assertEqual(parse_date("2024-01-15"), date(2024, 1, 15))

    def test_slash_dmy(self):
        self.assertEqual(parse_date("15/01/2024"), date(2024, 1, 15))

    def test_explicit_format(self):
        self.assertEqual(parse_date("31.12.2023", "%d.%m.%Y"), date(2023, 12, 31))

    def test_date_passthrough(self):
        self.assertEqual(parse_date(date(2020, 5, 1)), date(2020, 5, 1))

    def test_invalid_raises(self):
        with self.assertRaises(ParseError):
            parse_date("not-a-date")


class ParseCsvTests(unittest.TestCase):
    BASIC = "date,description,amount\n2024-01-15,Salary,2500.00\n2024-01-18,Tesco,-45.50\n"

    def test_basic_parse(self):
        txs = parse_csv(self.BASIC)
        self.assertEqual(len(txs), 2)
        self.assertEqual(txs[0].date, date(2024, 1, 15))
        self.assertEqual(txs[0].amount, Decimal("2500.00"))
        self.assertEqual(txs[1].amount, Decimal("-45.50"))
        self.assertTrue(txs[0].is_income())
        self.assertTrue(txs[1].is_expense())

    def test_from_file_object(self):
        txs = parse_csv(io.StringIO(self.BASIC))
        self.assertEqual(len(txs), 2)

    def test_from_path(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
            handle.write(self.BASIC)
            path = handle.name
        self.assertEqual(len(parse_csv(path)), 2)

    def test_debit_credit_columns(self):
        text = "date,description,debit,credit\n2024-01-15,Salary,,2500.00\n2024-01-18,Tesco,45.50,\n"
        txs = parse_csv(text)
        self.assertEqual(txs[0].amount, Decimal("2500.00"))
        self.assertEqual(txs[1].amount, Decimal("-45.50"))

    def test_header_aliases(self):
        text = "Transaction Date,Narrative,Value\n2024-01-15,Salary,2500.00\n"
        txs = parse_csv(text)
        self.assertEqual(txs[0].description, "Salary")
        self.assertEqual(txs[0].amount, Decimal("2500.00"))

    def test_currency_in_amount_column(self):
        text = "date,description,amount\n2024-01-15,Salary,\"$2,500.00\"\n"
        txs = parse_csv(text)
        self.assertEqual(txs[0].amount, Decimal("2500.00"))

    def test_semicolon_delimiter(self):
        text = "date;description;amount\n2024-01-15;Salary;2500.00\n"
        txs = parse_csv(text, delimiter=";")
        self.assertEqual(txs[0].amount, Decimal("2500.00"))

    def test_empty_rows_skipped(self):
        text = "date,description,amount\n\n2024-01-15,Salary,2500.00\n\n"
        self.assertEqual(len(parse_csv(text)), 1)

    def test_empty_source(self):
        self.assertEqual(parse_csv(""), [])

    def test_invalid_row_raises_with_line_number(self):
        text = "date,description,amount\n2024-01-15,Salary,oops\n"
        with self.assertRaises(ParseError) as ctx:
            parse_csv(text)
        self.assertIn("line 2", str(ctx.exception))

    def test_skip_invalid(self):
        text = "date,description,amount\n2024-01-15,Salary,oops\n2024-01-18,Tesco,-45.50\n"
        self.assertEqual(len(parse_csv(text, skip_invalid=True)), 1)

    def test_missing_date_column_raises(self):
        with self.assertRaises(ParseError):
            parse_csv("description,amount\nSalary,2500\n")

    def test_missing_amount_column_raises(self):
        with self.assertRaises(ParseError):
            parse_csv("date,description\n2024-01-15,Salary\n")

    def test_explicit_column_map(self):
        text = "when,what,howmuch\n2024-01-15,Salary,2500.00\n"
        txs = parse_csv(text, column_map={"date": "when", "description": "what", "amount": "howmuch"})
        self.assertEqual(txs[0].amount, Decimal("2500.00"))

    def test_category_column(self):
        text = "date,description,amount,category\n2024-01-15,Salary,2500.00,Income\n"
        self.assertEqual(parse_csv(text)[0].category, "Income")

    def test_total_helper(self):
        self.assertEqual(total(parse_csv(self.BASIC)), Decimal("2454.50"))

    def test_with_category_returns_copy(self):
        tx = parse_csv(self.BASIC)[0]
        tagged = tx.with_category("Income")
        self.assertIsNone(tx.category)
        self.assertEqual(tagged.category, "Income")


if __name__ == "__main__":
    unittest.main()
