"""CSV export of summaries, category totals and transactions.

All functions are pure and return CSV text; :func:`write_csv` handles writing
that text to a path or a stream. The functions accept the same inputs as
:func:`ledger.summary.render_summary`, namely either an iterable of summaries or
the mapping returned by :func:`ledger.summary.monthly_summaries`.

Public API
----------
``transactions_to_csv``   -- categorised transactions as CSV.
``summaries_to_csv``      -- monthly summaries as CSV.
``category_totals_to_csv``-- signed totals per category as CSV.
``budget_status_to_csv``  -- budget spend vs limit as CSV.
``write_csv``             -- write CSV text to a path, stream or stdout.
"""

from __future__ import annotations

import csv
import io
import sys
from decimal import Decimal
from typing import Any, Iterable, Mapping

from .budget import BudgetStatus
from .csv_parser import Transaction
from .summary import MonthlySummary


def _rows(summaries: Iterable[MonthlySummary] | Mapping[str, MonthlySummary]) -> list[MonthlySummary]:
    if isinstance(summaries, Mapping):
        return [summaries[key] for key in sorted(summaries)]
    return list(summaries)


def transactions_to_csv(transactions: Iterable[Transaction], delimiter: str = ",") -> str:
    """Return categorised transactions as CSV text."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter)
    writer.writerow(["date", "description", "amount", "category"])
    for tx in transactions:
        writer.writerow([tx.date.isoformat(), tx.description, str(tx.amount), tx.category or ""])
    return buffer.getvalue()


def summaries_to_csv(
    summaries: Iterable[MonthlySummary] | Mapping[str, MonthlySummary],
    delimiter: str = ",",
    include_categories: bool = False,
) -> str:
    """Return monthly summaries as CSV text.

    With ``include_categories`` a further block lists each month's per-category
    signed totals, distinguished by a leading ``category`` column in the header
    block that stays blank on the summary rows.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter)
    writer.writerow(["month", "income", "expenses", "net", "count"])
    rows = _rows(summaries)
    for summary in rows:
        writer.writerow(
            [
                summary.month,
                str(summary.income),
                str(summary.expenses),
                str(summary.net),
                summary.count,
            ]
        )
    if include_categories:
        writer.writerow([])
        writer.writerow(["month", "category", "total"])
        for summary in rows:
            for category in sorted(summary.by_category):
                writer.writerow([summary.month, category, str(summary.by_category[category])])
    return buffer.getvalue()


def category_totals_to_csv(
    totals: Mapping[str, Decimal] | Iterable[tuple[str, Decimal]],
    delimiter: str = ",",
) -> str:
    """Return per-category totals as CSV text."""
    items = totals.items() if isinstance(totals, Mapping) else totals
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter)
    writer.writerow(["category", "total"])
    for category, value in items:
        writer.writerow([category, str(value)])
    return buffer.getvalue()


def budget_status_to_csv(statuses: Iterable[BudgetStatus], delimiter: str = ",") -> str:
    """Return budget statuses as CSV text."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter)
    writer.writerow(["category", "limit", "spent", "remaining", "over", "overspend"])
    for status in statuses:
        writer.writerow(
            [
                status.category,
                str(status.limit),
                str(status.spent),
                str(status.remaining),
                "yes" if status.is_over else "no",
                str(status.overspend),
            ]
        )
    return buffer.getvalue()


def write_csv(text: str, destination: Any = None) -> None:
    """Write ``text`` to a path, a writable file object, or stdout.

    ``destination`` may be ``None``/``"-"`` (stdout), a path string, or an open
    file object.
    """
    if destination is None or destination == "-":
        sys.stdout.write(text)
        return
    if hasattr(destination, "write"):
        destination.write(text)
        return
    with open(destination, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
