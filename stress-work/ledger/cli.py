"""Command line interface for the :mod:`ledger` package.

Usage examples::

    python -m ledger summary statement.csv
    python -m ledger summary statement.csv --month 2024-03
    python -m ledger list statement.csv --category Groceries
    python -m ledger categorize statement.csv --output categorised.csv

The CLI is built with :mod:`argparse` only and returns integer exit codes so it
can be driven from tests without spawning a subprocess.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from typing import Sequence

from .categorizer import Categorizer, categorizer_with_defaults
from .csv_parser import ParseError, Transaction, parse_csv
from .summary import monthly_summaries, render_summary, summarise


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(prog="ledger", description="Parse and summarise CSV bank statements.")
    parser.add_argument("--version", action="version", version="ledger 1.0.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    summary = subparsers.add_parser("summary", help="show monthly totals")
    summary.add_argument("source", help="path to the CSV statement")
    summary.add_argument("--month", help="restrict to a single YYYY-MM month")
    summary.add_argument("--delimiter", default=",", help="CSV field delimiter (default: ',')")
    summary.add_argument("--categorise", action="store_true", help="apply the default rule set first")

    listing = subparsers.add_parser("list", help="list transactions")
    listing.add_argument("source", help="path to the CSV statement")
    listing.add_argument("--category", help="only show transactions in this category")
    listing.add_argument("--delimiter", default=",", help="CSV field delimiter (default: ',')")

    categorize = subparsers.add_parser("categorize", help="write categorised transactions to CSV")
    categorize.add_argument("source", help="path to the CSV statement")
    categorize.add_argument("--output", "-o", help="write to this file instead of stdout")
    categorize.add_argument("--delimiter", default=",", help="CSV field delimiter (default: ',')")

    return parser


def _load(source: str, delimiter: str) -> list[Transaction]:
    return parse_csv(source, delimiter=delimiter)


def _transactions_to_csv(transactions: Iterable[Transaction]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "description", "amount", "category"])
    for tx in transactions:
        writer.writerow([tx.date.isoformat(), tx.description, str(tx.amount), tx.category or ""])
    return buffer.getvalue()


def _run_summary(args: argparse.Namespace) -> int:
    transactions = _load(args.source, args.delimiter)
    if args.categorise:
        transactions = categorizer_with_defaults().categorize_all(transactions)
    if args.month:
        result = summarise(transactions, month=args.month)
        print(f"Month: {result.month}")
        print(render_summary([result]))
    else:
        print(render_summary(monthly_summaries(transactions)))
    return 0


def _run_list(args: argparse.Namespace) -> int:
    transactions = _load(args.source, args.delimiter)
    categorizer: Categorizer = categorizer_with_defaults()
    transactions = categorizer.categorize_all(transactions)
    if args.category:
        transactions = [tx for tx in transactions if tx.category == args.category]
    for tx in transactions:
        category = f" [{tx.category}]" if tx.category else ""
        print(f"{tx.date.isoformat()}  {tx.amount:>12}  {tx.description}{category}")
    return 0


def _run_categorize(args: argparse.Namespace) -> int:
    transactions = _load(args.source, args.delimiter)
    transactions = categorizer_with_defaults().categorize_all(transactions)
    output = _transactions_to_csv(transactions)
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as handle:
            handle.write(output)
    else:
        sys.stdout.write(output)
    return 0


_COMMANDS = {
    "summary": _run_summary,
    "list": _run_list,
    "categorize": _run_categorize,
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
