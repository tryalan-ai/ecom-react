"""Command line interface for the :mod:`ledger` package.

Subcommands
-----------
``import``   parse a statement, categorise it and write categorised CSV.
``summary``  print monthly totals (optionally for one month).
``budget``   compare spending against per-category budgets and alert on overspend.
``export``   write summaries or category totals to CSV.

Usage examples::

    python -m ledger import statement.csv --output categorised.csv
    python -m ledger summary statement.csv --month 2024-03
    python -m ledger budget statement.csv --budgets budgets.csv
    python -m ledger export statement.csv --what category --output totals.csv

The CLI is built with :mod:`argparse` only and returns integer exit codes so it
can be driven from tests without spawning a subprocess.
"""

from __future__ import annotations

import argparse
import sys
from typing import Callable, Sequence

from .budget import Budgets, load_budgets, render_budget_status
from .categorizer import categorizer_with_defaults
from .csv_parser import ParseError, Transaction, parse_csv
from .exporter import (
    budget_status_to_csv,
    category_totals_to_csv,
    summaries_to_csv,
    transactions_to_csv,
    write_csv,
)
from .summary import category_totals, monthly_summaries, render_summary, summarise

__all__ = ["build_parser", "main"]

VERSION = "ledger 1.1.0"


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", help="path to the CSV statement")
    parser.add_argument("--delimiter", default=",", help="CSV field delimiter (default: ',')")
    parser.add_argument(
        "--categorise",
        action="store_true",
        help="apply the default rule set before working on the data",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="ledger", description="Parse, categorise and summarise CSV bank statements."
    )
    parser.add_argument("--version", action="version", version=VERSION)
    subparsers = parser.add_subparsers(dest="command", required=True)

    importer = subparsers.add_parser("import", help="categorise a statement and write CSV")
    _add_common(importer)
    importer.add_argument("--output", "-o", help="write to this file instead of stdout")

    summary = subparsers.add_parser("summary", help="show monthly totals")
    _add_common(summary)
    summary.add_argument("--month", help="restrict to a single YYYY-MM month")

    budget = subparsers.add_parser("budget", help="compare spending against budgets")
    _add_common(budget)
    budget.add_argument("--budgets", "-b", required=True, help="path to a budgets CSV (category,limit)")
    budget.add_argument("--month", help="restrict to a single YYYY-MM month")
    budget.add_argument(
        "--alerts-only",
        "-a",
        action="store_true",
        help="print only over-budget categories",
    )

    export = subparsers.add_parser("export", help="write summaries or category totals to CSV")
    _add_common(export)
    export.add_argument("--output", "-o", help="write to this file instead of stdout")
    export.add_argument(
        "--what",
        choices=("monthly", "category", "transactions"),
        default="monthly",
        help="what to export (default: monthly)",
    )
    export.add_argument(
        "--include-categories",
        action="store_true",
        help="for monthly exports, append a per-category breakdown block",
    )

    return parser


def _load(args: argparse.Namespace) -> list[Transaction]:
    transactions = parse_csv(args.source, delimiter=args.delimiter)
    if args.categorise:
        transactions = categorizer_with_defaults().categorize_all(transactions)
    return transactions


def _run_import(args: argparse.Namespace) -> int:
    transactions = parse_csv(args.source, delimiter=args.delimiter)
    transactions = categorizer_with_defaults().categorize_all(transactions)
    write_csv(transactions_to_csv(transactions, delimiter=args.delimiter), args.output)
    return 0


def _run_summary(args: argparse.Namespace) -> int:
    transactions = _load(args)
    if args.month:
        result = summarise(transactions, month=args.month)
        print(f"Month: {result.month}")
        print(render_summary([result]))
    else:
        print(render_summary(monthly_summaries(transactions)))
    return 0


def _run_budget(args: argparse.Namespace) -> int:
    transactions = parse_csv(args.source, delimiter=args.delimiter)
    transactions = categorizer_with_defaults().categorize_all(transactions)
    budgets: Budgets = load_budgets(args.budgets)
    statuses = budgets.evaluate(transactions, month=args.month)
    if args.alerts_only:
        statuses = budgets.alerts(transactions, month=args.month)
    if not statuses:
        print("No over-budget categories." if args.alerts_only else "No budgets defined.")
        return 0
    print(render_budget_status(statuses))
    over = [status for status in statuses if status.is_over]
    if over:
        print()
        for status in over:
            print(status.alert())
    return 0


def _run_export(args: argparse.Namespace) -> int:
    transactions = _load(args)
    if args.what == "transactions":
        text = transactions_to_csv(transactions, delimiter=args.delimiter)
    elif args.what == "category":
        text = category_totals_to_csv(category_totals(transactions), delimiter=args.delimiter)
    else:
        text = summaries_to_csv(
            monthly_summaries(transactions),
            delimiter=args.delimiter,
            include_categories=args.include_categories,
        )
    write_csv(text, args.output)
    return 0


_COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "import": _run_import,
    "summary": _run_summary,
    "budget": _run_budget,
    "export": _run_export,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = _COMMANDS[args.command]
    try:
        return handler(args)
    except (ParseError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
