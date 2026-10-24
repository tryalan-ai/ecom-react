"""Monthly aggregation and reporting of transactions.

The functions here turn a flat list of :class:`~ledger.csv_parser.Transaction`
objects into per-month totals, per-category breakdowns and a printable table.

Public API
----------
``month_key``         -- ``date`` -> ``"YYYY-MM"``.
``MonthlySummary``    -- totals for one month.
``monthly_summaries`` -- ``dict`` month-key -> :class:`MonthlySummary`.
``category_totals``   -- signed totals per category.
``render_summary``    -- a plain-text table for a set of summaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable, Mapping

from .csv_parser import Transaction

CENT = Decimal("0.01")


def month_key(value: date) -> str:
    """Return the ``"YYYY-MM"`` bucket key for a date."""
    return f"{value.year:04d}-{value.month:02d}"


def _quantise(value: Decimal) -> Decimal:
    return value.quantize(CENT)


@dataclass
class MonthlySummary:
    """Aggregated figures for a single calendar month.

    ``expenses`` is stored as a positive magnitude while ``net`` keeps the
    signed convention of the underlying transactions.
    """

    month: str
    income: Decimal = Decimal("0")
    expenses: Decimal = Decimal("0")
    count: int = 0
    by_category: dict[str, Decimal] = field(default_factory=dict)

    @property
    def net(self) -> Decimal:
        """Income minus expenses, signed."""
        return _quantise(self.income - self.expenses)

    @property
    def savings_rate(self) -> Decimal:
        """Net as a fraction of income; zero when there is no income."""
        if self.income == 0:
            return Decimal("0")
        return (self.net / self.income).quantize(Decimal("0.0001"))

    def add(self, transaction: Transaction) -> None:
        """Fold one transaction into the running totals."""
        self.count += 1
        if transaction.amount >= 0:
            self.income += transaction.amount
        else:
            self.expenses += -transaction.amount
        if transaction.category:
            self.by_category[transaction.category] = (
                self.by_category.get(transaction.category, Decimal("0")) + transaction.amount
            )


def monthly_summaries(transactions: Iterable[Transaction]) -> dict[str, MonthlySummary]:
    """Group transactions by month, returning summaries ordered by month."""
    buckets: dict[str, MonthlySummary] = {}
    for tx in transactions:
        key = month_key(tx.date)
        summary = buckets.get(key)
        if summary is None:
            summary = MonthlySummary(month=key)
            buckets[key] = summary
        summary.add(tx)
    return {key: buckets[key] for key in sorted(buckets)}


def summarise(transactions: Iterable[Transaction], month: str | None = None) -> MonthlySummary:
    """Return a single :class:`MonthlySummary`, optionally for one month.

    With ``month=None`` every transaction is folded into one summary whose
    ``month`` field is ``"all"``.
    """
    if month is None:
        summary = MonthlySummary(month="all")
        for tx in transactions:
            summary.add(tx)
        return summary
    summary = MonthlySummary(month=month)
    for tx in transactions:
        if month_key(tx.date) == month:
            summary.add(tx)
    return summary


def category_totals(transactions: Iterable[Transaction]) -> dict[str, Decimal]:
    """Signed total per category, ordered by descending absolute value."""
    totals: dict[str, Decimal] = {}
    for tx in transactions:
        key = tx.category or "Uncategorised"
        totals[key] = totals.get(key, Decimal("0")) + tx.amount
    return dict(sorted(totals.items(), key=lambda item: abs(item[1]), reverse=True))


def render_summary(summaries: Iterable[MonthlySummary] | Mapping[str, MonthlySummary]) -> str:
    """Render summaries as an aligned plain-text table.

    Accepts either an iterable of :class:`MonthlySummary` or the mapping
    returned by :func:`monthly_summaries` (whose values are rendered in
    month order).
    """
    if isinstance(summaries, Mapping):
        rows = [summaries[key] for key in sorted(summaries)]
    else:
        rows = list(summaries)
    header = ("Month", "Income", "Expenses", "Net", "Txns")
    lines = ["{:<9} {:>12} {:>12} {:>12} {:>6}".format(*header)]
    lines.append("-" * 55)
    for summary in rows:
        lines.append(
            "{:<9} {:>12} {:>12} {:>12} {:>6}".format(
                summary.month,
                str(_quantise(summary.income)),
                str(_quantise(summary.expenses)),
                str(summary.net),
                summary.count,
            )
        )
    return "\n".join(lines)
