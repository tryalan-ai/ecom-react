"""Rule-based categorisation of bank transactions.

Rules are matched in descending priority order (then in insertion order) and the
first match wins. A rule can constrain the description with a substring, a
regular expression, an exact match or a prefix, and can additionally restrict
the amount direction (income only / expense only) and an amount range.

Public API
----------
``Rule``        -- a single matching rule.
``Categorizer`` -- an ordered collection of rules with a default fallback.
``default_rules`` -- a sensible starter rule set for everyday spending.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from .csv_parser import Transaction

UNCATEGORISED = "Uncategorised"


@dataclass(frozen=True)
class Rule:
    """A single categorisation rule.

    ``match`` is one of ``"contains"``, ``"regex"``, ``"exact"`` or
    ``"startswith"``. ``direction`` may be ``"income"``, ``"expense"`` or
    ``None`` (either). ``min_amount``/``max_amount`` bound the signed amount
    inclusively.
    """

    category: str
    pattern: str = ""
    match: str = "contains"
    direction: str | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    priority: int = 0
    _regex: re.Pattern[str] | None = None

    def __post_init__(self) -> None:
        if self.match not in {"contains", "regex", "exact", "startswith"}:
            raise ValueError(f"unknown match type {self.match!r}")
        if self.direction not in {None, "income", "expense"}:
            raise ValueError(f"unknown direction {self.direction!r}")
        if self.match == "regex" and self.pattern:
            compiled = re.compile(self.pattern, re.IGNORECASE)
            object.__setattr__(self, "_regex", compiled)

    def _text_matches(self, text: str) -> bool:
        if not self.pattern:
            return True
        haystack = text.lower()
        needle = self.pattern.lower()
        if self.match == "contains":
            return needle in haystack
        if self.match == "exact":
            return haystack == needle
        if self.match == "startswith":
            return haystack.startswith(needle)
        assert self._regex is not None
        return bool(self._regex.search(text))

    def matches(self, transaction: Transaction) -> bool:
        """Return True when ``transaction`` satisfies every constraint."""
        if not self._text_matches(transaction.description):
            return False
        if self.direction == "income" and not transaction.is_income():
            return False
        if self.direction == "expense" and not transaction.is_expense():
            return False
        if self.min_amount is not None and transaction.amount < self.min_amount:
            return False
        if self.max_amount is not None and transaction.amount > self.max_amount:
            return False
        return True


class Categorizer:
    """Apply an ordered set of :class:`Rule` objects to transactions."""

    def __init__(self, rules: Iterable[Rule] | None = None, default: str = UNCATEGORISED) -> None:
        self._rules: list[Rule] = list(rules or [])
        self.default = default
        self.rules = self._ordered()

    def _ordered(self) -> list[Rule]:
        # Stable sort keeps insertion order among equal priorities.
        return sorted(self._rules, key=lambda rule: rule.priority, reverse=True)

    def add_rule(self, rule: Rule) -> "Categorizer":
        """Append ``rule`` and re-sort. Returns ``self`` for chaining."""
        self._rules.append(rule)
        self.rules = self._ordered()
        return self

    def matching_rule(self, transaction: Transaction) -> Rule | None:
        """Return the highest-priority matching rule, or None."""
        for rule in self.rules:
            if rule.matches(transaction):
                return rule
        return None

    def categorize(self, transaction: Transaction) -> Transaction:
        """Return ``transaction`` with its category filled in (if unset)."""
        if transaction.category:
            return transaction
        rule = self.matching_rule(transaction)
        return transaction.with_category(rule.category if rule else self.default)

    def categorize_all(self, transactions: Iterable[Transaction]) -> list[Transaction]:
        """Categorise an iterable of transactions, preserving order."""
        return [self.categorize(tx) for tx in transactions]

    def explain(self, transaction: Transaction) -> str:
        """Human-readable explanation of how ``transaction`` was categorised."""
        rule = self.matching_rule(transaction)
        if rule is not None:
            return f"{transaction.description!r} -> {rule.category} (rule: {rule.pattern!r})"
        return f"{transaction.description!r} -> {self.default} (no matching rule)"


def default_rules() -> list[Rule]:
    """Return a starter rule set covering common spending categories."""
    return [
        Rule("Income", pattern=r"salary|payroll|wages|invoice paid", match="regex", direction="income", priority=100),
        Rule("Groceries", pattern=r"tesco|sainsbury|aldi|lidl|whole foods|grocer", match="regex", direction="expense", priority=50),
        Rule("Transport", pattern=r"uber|lyft|trainline|tfl|metro|rail", match="regex", direction="expense", priority=50),
        Rule("Dining", pattern=r"restaurant|cafe|coffee|pizza|mcdonald|starbucks", match="regex", direction="expense", priority=40),
        Rule("Utilities", pattern=r"electric|gas bill|water|broadband|internet provider", match="regex", direction="expense", priority=40),
        Rule("Rent", pattern=r"rent|landlord|letting", match="regex", direction="expense", priority=30),
        Rule("Fees", pattern=r"bank fee|overdraft|interest charge|service charge", match="regex", direction="expense", priority=20),
        Rule("Transfers", pattern=r"transfer|standing order", match="regex", priority=10),
    ]


def categorizer_with_defaults(default: str = UNCATEGORISED) -> Categorizer:
    """Build a :class:`Categorizer` pre-loaded with :func:`default_rules`."""
    return Categorizer(default_rules(), default=default)
