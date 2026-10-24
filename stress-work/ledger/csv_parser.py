"""Parsing of CSV bank transaction exports.

The parser is deliberately tolerant about the many shapes a bank export can
take: it recognises common header aliases, single signed ``amount`` columns as
well as split ``debit``/``credit`` columns, several date layouts and amounts
written with currency symbols, thousands separators or accounting parentheses
(e.g. ``(12.34)`` meaning ``-12.34``).

Public API
----------
``parse_amount``      -- turn a raw string into a :class:`decimal.Decimal`.
``parse_date``        -- turn a raw string into a :class:`datetime.date`.
``Transaction``       -- immutable record for a single movement.
``parse_csv``         -- parse a path, file object or string into transactions.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping


class ParseError(ValueError):
    """Raised when a row cannot be turned into a :class:`Transaction`."""


# Date layouts that are tried in order when no explicit format is supplied.
DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%m/%d/%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%Y%m%d",
)

# Header aliases. Keys are the canonical field names used internally.
_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("date", "transaction date", "posted", "posted date", "value date", "booking date"),
    "description": ("description", "details", "narrative", "memo", "payee", "reference", "transaction"),
    "amount": ("amount", "value", "transaction amount", "net amount"),
    "debit": ("debit", "withdrawal", "money out", "paid out", "out"),
    "credit": ("credit", "deposit", "money in", "paid in", "in"),
    "category": ("category", "type", "classification"),
}

_CURRENCY_RE = re.compile(r"[^\d.,()+\-]")
_NUMBER_RE = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})*(?:\.\d+)?$|^[+-]?\d+(?:\.\d+)?$")


def _normalise_header(name: str) -> str:
    """Lower-case and collapse a header cell so aliases match reliably."""
    return re.sub(r"\s+", " ", str(name).strip().lower().replace("_", " "))


def parse_amount(raw: Any) -> Decimal:
    """Parse a raw amount string into a :class:`~decimal.Decimal`.

    Handles currency symbols, thousands separators, a leading ``+`` and
    accounting parentheses that denote a negative value. An empty value is an
    error; a lone sign such as ``-`` is treated as zero.
    """
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, (int, float)):
        return Decimal(str(raw))
    if raw is None:
        raise ParseError("amount is missing")
    text = str(raw).strip()
    if text == "":
        raise ParseError("amount is empty")
    if text in {"-", "+"}:
        return Decimal("0")

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()

    text = text.replace("\u00a0", "").replace(" ", "")
    text = _CURRENCY_RE.sub("", text)
    if text.endswith("-"):  # trailing minus, e.g. "12.34-"
        negative = True
        text = text[:-1]
    if text.startswith("-"):
        negative = True
        text = text[1:]
    text = text.lstrip("+")
    text = text.replace(",", "")
    if text == "" or not re.fullmatch(r"\d+(?:\.\d+)?", text):
        raise ParseError(f"cannot parse amount {raw!r}")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - guarded by regex
        raise ParseError(f"cannot parse amount {raw!r}") from exc
    return -value if negative else value


def parse_date(raw: Any, date_format: str | None = None) -> date:
    """Parse a raw value into a :class:`datetime.date`.

    ``date_format`` pins a single :func:`datetime.strptime` layout; otherwise
    the :data:`DATE_FORMATS` candidates are tried in order.
    """
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if raw is None:
        raise ParseError("date is missing")
    text = str(raw).strip()
    if text == "":
        raise ParseError("date is empty")
    formats = (date_format,) if date_format else DATE_FORMATS
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ParseError(f"cannot parse date {raw!r}")


@dataclass(frozen=True)
class Transaction:
    """A single bank movement.

    ``amount`` is signed: positive is money in, negative is money out.
    """

    date: date
    description: str
    amount: Decimal
    category: str | None = None
    raw: Mapping[str, str] = field(default_factory=dict, compare=False, repr=False)

    def is_income(self) -> bool:
        """True when the movement is money coming in."""
        return self.amount > 0

    def is_expense(self) -> bool:
        """True when the movement is money going out."""
        return self.amount < 0

    def with_category(self, category: str | None) -> "Transaction":
        """Return a copy of this transaction carrying ``category``."""
        return replace(self, category=category)


def _read_source(source: Any) -> str:
    if hasattr(source, "read"):
        data = source.read()
        return data.decode("utf-8-sig") if isinstance(data, bytes) else data
    if isinstance(source, (bytes, bytearray)):
        return bytes(source).decode("utf-8-sig")
    if isinstance(source, str):
        # A string containing newlines (or empty) is treated as raw CSV text.
        if source == "" or "\n" in source or "\r" in source:
            return source
        with open(source, "r", encoding="utf-8-sig", newline="") as handle:
            return handle.read()
    raise TypeError(f"unsupported CSV source: {type(source)!r}")


def _resolve_columns(
    header: list[str],
    column_map: Mapping[str, str] | None,
) -> dict[str, str]:
    """Map canonical fields to the actual header names present in the file."""
    normalised = {_normalise_header(name): name for name in header}
    resolved: dict[str, str] = {}
    explicit = {k: v for k, v in (column_map or {}).items()}
    for field_name, aliases in _ALIASES.items():
        if field_name in explicit:
            target = explicit[field_name]
            if target not in header and _normalise_header(target) not in normalised:
                raise ParseError(f"column {target!r} requested for {field_name!r} is absent")
            resolved[field_name] = normalised.get(_normalise_header(target), target)
            continue
        for alias in aliases:
            if alias in normalised:
                resolved[field_name] = normalised[alias]
                break
    # Explicit mappings for fields without built-in aliases.
    for field_name, target in explicit.items():
        if field_name not in resolved:
            resolved[field_name] = normalised.get(_normalise_header(target), target)
    return resolved


def _amount_from_row(row: Mapping[str, str], columns: Mapping[str, str]) -> Decimal:
    if "amount" in columns:
        raw = row.get(columns["amount"], "")
        if str(raw).strip():
            return parse_amount(raw)
    debit = credit = None
    if "debit" in columns:
        raw = str(row.get(columns["debit"], "")).strip()
        if raw:
            debit = abs(parse_amount(raw))
    if "credit" in columns:
        raw = str(row.get(columns["credit"], "")).strip()
        if raw:
            credit = abs(parse_amount(raw))
    if debit is None and credit is None:
        raise ParseError("row has neither amount nor debit/credit values")
    if debit is not None:
        return -debit
    return credit if credit is not None else Decimal("0")


def parse_csv(
    source: Any,
    *,
    delimiter: str = ",",
    column_map: Mapping[str, str] | None = None,
    date_format: str | None = None,
    skip_invalid: bool = False,
) -> list[Transaction]:
    """Parse a CSV bank export into a list of :class:`Transaction` objects.

    ``source`` may be a filesystem path, an open file object, ``bytes`` or a
    string of CSV text. Rows that cannot be parsed raise :class:`ParseError`
    unless ``skip_invalid`` is true, in which case they are dropped.
    """
    text = _read_source(source)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration:
        return []
    header = [cell.strip() for cell in header]
    columns = _resolve_columns(header, column_map)
    if "date" not in columns:
        raise ParseError("no date column found")
    if "amount" not in columns and "debit" not in columns and "credit" not in columns:
        raise ParseError("no amount, debit or credit column found")

    transactions: list[Transaction] = []
    for line_no, row in enumerate(reader, start=2):
        if not row or all(not str(cell).strip() for cell in row):
            continue
        record = {header[i]: (row[i] if i < len(row) else "") for i in range(len(header))}
        try:
            tx_date = parse_date(record.get(columns["date"], ""), date_format)
            amount = _amount_from_row(record, columns)
            description = ""
            if "description" in columns:
                description = str(record.get(columns["description"], "")).strip()
            category = None
            if "category" in columns:
                category = str(record.get(columns["category"], "")).strip() or None
            transactions.append(
                Transaction(
                    date=tx_date,
                    description=description,
                    amount=amount,
                    category=category,
                    raw=record,
                )
            )
        except ParseError as exc:
            if skip_invalid:
                continue
            raise ParseError(f"line {line_no}: {exc}") from exc
    return transactions


def total(transactions: Iterable[Transaction]) -> Decimal:
    """Sum the signed amounts of ``transactions``."""
    return sum((tx.amount for tx in transactions), Decimal("0"))


def load(source: Any, **kwargs: Any) -> list[Transaction]:
    """Alias for :func:`parse_csv`, kept for readability at call sites."""
    return parse_csv(source, **kwargs)
