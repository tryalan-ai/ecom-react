"""``ledger`` -- a small standard-library toolkit for CSV bank statements.

Modules
-------
``csv_parser``   parsing CSV exports into :class:`Transaction` objects.
``categorizer``  rule-based categorisation of transactions.
``summary``      monthly and per-category aggregation.
``budget``       per-category budgets and over-budget alerts.
``exporter``     CSV export of summaries, totals and transactions.
``cli``          an ``argparse`` command line front end.
"""

from .budget import Budget, BudgetStatus, Budgets, budgets_to_csv, load_budgets, spend_by_category
from .categorizer import Categorizer, Rule, categorizer_with_defaults, default_rules
from .csv_parser import ParseError, Transaction, parse_amount, parse_csv, parse_date
from .exporter import summaries_to_csv, transactions_to_csv, write_csv
from .summary import MonthlySummary, category_totals, monthly_summaries, render_summary

__version__ = "1.1.0"

__all__ = [
    "Budget",
    "BudgetStatus",
    "Budgets",
    "budgets_to_csv",
    "load_budgets",
    "spend_by_category",
    "Categorizer",
    "Rule",
    "categorizer_with_defaults",
    "default_rules",
    "ParseError",
    "Transaction",
    "parse_amount",
    "parse_csv",
    "parse_date",
    "MonthlySummary",
    "category_totals",
    "monthly_summaries",
    "render_summary",
    "summaries_to_csv",
    "transactions_to_csv",
    "write_csv",
    "__version__",
]
