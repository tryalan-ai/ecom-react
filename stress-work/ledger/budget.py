"""Per-category budgets and over-budget alerts.

A :class:`Budget` is a spend limit for one category. :class:`Budgets` holds a
set of them and can evaluate a list of transactions against the limits,
producing a :class:`BudgetStatus` per budgeted category. Spending is measured as
the magnitude of expenses (negative amounts), so a limit of ``200`` means "no
more than 200 of outflow this period".

Public API
----------
``Budget``              -- a single category limit.
``BudgetStatus``        -- spend vs limit with remaining/overspend helpers.
``Budgets``             -- a collection of budgets with evaluation helpers.
``spend_by_category``   -- positive expense magnitude per category.
``load_budgets``        -- read budgets from a CSV file or text.
``budgets_to_csv``      -- serialise budgets to CSV text.
``render_budget_status`` -- a plain-text status table.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Mapping

from .csv_parser import ParseError, Transaction, parse_amount
from .summary import month_key

CENT = Decimal("0.01")
UNCATEGORISED = "Uncategorised"


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return parse_amount(value)


@dataclass(frozen=True)
class Budget:
    """A spend limit for a single category."""

    category: str
    limit: Decimal

    def __post_init__(self) -> None:
        if not str(self.category).strip():
            raise ValueError("budget category must not be empty")
        limit = _to_decimal(self.limit)
        if limit < 0:
            raise ValueError("budget limit must not be negative")
        object.__setattr__(self, "limit", limit)

    def to_row(self) -> list[str]:
        """Return the ``[category, limit]`` CSV row."""
        return [self.category, str(self.limit)]


@dataclass
class BudgetStatus:
    """Spending against a limit for one category."""

    category: str
    limit: Decimal
    spent: Decimal

    @property
    def remaining(self) -> Decimal:
        """Limit minus spend; negative when over budget."""
        return (self.limit - self.spent).quantize(CENT)

    @property
    def overspend(self) -> Decimal:
        """Amount spent beyond the limit, or zero when within budget."""
        excess = self.spent - self.limit
        return excess.quantize(CENT) if excess > 0 else Decimal("0.00")

    @property
    def is_over(self) -> bool:
        """True when spending exceeds the limit."""
        return self.spent > self.limit

    @property
    def ratio(self) -> Decimal:
        """Spend as a fraction of the limit, rounded to four places."""
        if self.limit == 0:
            return Decimal("0") if self.spent == 0 else Decimal("Infinity")
        return (self.spent / self.limit * Decimal("100")).quantize(Decimal("0.01"))

    def alert(self) -> str:
        """A one-line human-readable alert for this status."""
        if self.is_over:
            return (
                f"OVER BUDGET: {self.category} spent {self.spent} "
                f"of {self.limit} (over by {self.overspend})"
            )
        return f"OK: {self.category} spent {self.spent} of {self.limit} (remaining {self.remaining})"


def spend_by_category(
    transactions: Iterable[Transaction],
    month: str | None = None,
) -> dict[str, Decimal]:
    """Return the positive expense magnitude per category.

    Only expenses (negative amounts) count towards spending; income is ignored.
    When ``month`` is given only transactions in that ``YYYY-MM`` bucket count.
    """
    totals: dict[str, Decimal] = {}
    for tx in transactions:
        if month is not None and month_key(tx.date) != month:
            continue
        if tx.amount >= 0:
            continue
        key = tx.category or UNCATEGORISED
        totals[key] = totals.get(key, Decimal("0")) + (-tx.amount)
    return totals


class Budgets:
    """An ordered collection of :class:`Budget` keyed by category."""

    def __init__(self, budgets: Mapping[str, Any] | Iterable[Budget] | None = None) -> None:
        self._by_category: dict[str, Budget] = {}
        if budgets is None:
            return
        if isinstance(budgets, Mapping):
            for category, limit in budgets.items():
                self.add(Budget(category, _to_decimal(limit)))
        else:
            for budget in budgets:
                self.add(budget)

    def add(self, budget: Budget) -> "Budgets":
        """Add or replace a budget. Returns ``self`` for chaining."""
        self._by_category[budget.category] = budget
        return self

    def __len__(self) -> int:
        return len(self._by_category)

    def __contains__(self, category: object) -> bool:
        return category in self._by_category

    def __iter__(self):
        return iter(self._by_category.values())

    def categories(self) -> list[str]:
        """Return the budgeted categories in insertion order."""
        return list(self._by_category)

    def limit_for(self, category: str) -> Decimal:
        """Return the limit for ``category``, or zero when unbudgeted."""
        budget = self._by_category.get(category)
        return budget.limit if budget else Decimal("0")

    def status_for(self, category: str, spent: Decimal) -> BudgetStatus:
        """Build a :class:`BudgetStatus` for one category."""
        return BudgetStatus(category=category, limit=self.limit_for(category), spent=spent)

    def evaluate(
        self,
        transactions: Iterable[Transaction],
        month: str | None = None,
    ) -> list[BudgetStatus]:
        """Evaluate every budget against ``transactions``.

        Categories appear in budget order; each status carries the spend found
        (zero when nothing was spent in that category).
        """
        spent = spend_by_category(transactions, month=month)
        return [self.status_for(category, spent.get(category, Decimal("0.00"))) for category in self._by_category]

    def alerts(
        self,
        transactions: Iterable[Transaction],
        month: str | None = None,
    ) -> list[BudgetStatus]:
        """Return only the over-budget statuses, worst overspend first."""
        over = [status for status in self.evaluate(transactions, month=month) if status.is_over]
        return sorted(over, key=lambda status: status.overspend, reverse=True)


def load_budgets(source: Any, delimiter: str = ",") -> Budgets:
    """Load budgets from a path, file object or CSV text.

    The CSV must have ``category`` and ``limit`` columns (header aliases such as
    ``name``/``amount`` are not accepted - budgets are explicit).
    """
    if hasattr(source, "read"):
        text = source.read()
        if isinstance(text, bytes):
            text = text.decode("utf-8-sig")
    elif isinstance(source, (bytes, bytearray)):
        text = bytes(source).decode("utf-8-sig")
    elif isinstance(source, str):
        if source == "" or "\n" in source or "\r" in source:
            text = source
        else:
            with open(source, "r", encoding="utf-8-sig", newline="") as handle:
                text = handle.read()
    else:
        raise TypeError(f"unsupported budgets source: {type(source)!r}")

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = [cell.strip().lower() for cell in next(reader)]
    except StopIteration:
        return Budgets()
    if "category" not in header or "limit" not in header:
        raise ParseError("budgets CSV needs 'category' and 'limit' columns")
    category_idx = header.index("category")
    limit_idx = header.index("limit")

    budgets = Budgets()
    for line_no, row in enumerate(reader, start=2):
        if not row or all(not str(cell).strip() for cell in row):
            continue
        try:
            category = row[category_idx].strip()
            limit = parse_amount(row[limit_idx])
        except (IndexError, ParseError) as exc:
            raise ParseError(f"line {line_no}: {exc}") from exc
        budgets.add(Budget(category, limit))
    return budgets


def budgets_to_csv(budgets: Iterable[Budget], delimiter: str = ",") -> str:
    """Serialise budgets to CSV text with a ``category,limit`` header."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter)
    writer.writerow(["category", "limit"])
    for budget in budgets:
        writer.writerow(budget.to_row())
    return buffer.getvalue()


def render_budget_status(statuses: Iterable[BudgetStatus]) -> str:
    """Render budget statuses as an aligned table, flagging overspend."""
    header = ("Category", "Limit", "Spent", "Remaining", "State")
    lines = ["{:<14} {:>10} {:>10} {:>10} {:>6}".format(*header)]
    lines.append("-" * 56)
    for status in statuses:
        state = "OVER" if status.is_over else "ok"
        lines.append(
            "{:<14} {:>10} {:>10} {:>10} {:>6}".format(
                status.category,
                str(status.limit),
                str(status.spent),
                str(status.remaining),
                state,
            )
        )
    return "\n".join(lines)
