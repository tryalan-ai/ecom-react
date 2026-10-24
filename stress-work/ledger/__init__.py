"""``ledger`` -- a small standard-library toolkit for CSV bank statements.

Modules
-------
``csv_parser``   parsing CSV exports into :class:`Transaction` objects.
``categorizer``  rule-based categorisation of transactions.
``summary``      monthly and per-category aggregation.
``cli``          an ``argparse`` command line front end.
"""

from .categorizer import Categorizer, Rule, categorizer_with_defaults, default_rules
from .csv_parser import ParseError, Transaction, parse_amount, parse_csv, parse_date
from .summary import MonthlySummary, category_totals, monthly_summaries, render_summary

__version__ = "1.0.0"

__all__ = [
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
    "__version__",
]
