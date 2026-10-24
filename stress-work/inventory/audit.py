"""The append-only audit log of stock movements, and rebuilding stock from it.

Every operation that changes on-hand or reserved stock appends exactly one
:class:`Movement` to the log.  Because each movement kind has a fixed effect on
a ``(quantity, reserved)`` pair, the live stock levels are *derivable*: replaying
the whole log from an empty warehouse must reproduce them exactly.  That is what
:func:`replay_totals` does and what :func:`stock_level_drift` checks.

Keeping the log authoritative is what makes it possible to answer "what is
really in the bin?" after a half-applied import, a bad migration or a manual
edit: rebuild from the log and compare.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union

from .errors import AuditLogError
from .models import StockLevel

__all__ = [
    "Movement",
    "AuditLog",
    "STOCK_EFFECTS",
    "movement_delta",
    "replay_totals",
    "stock_level_drift",
]

StockKey = Tuple[str, str]
Totals = Dict[StockKey, Tuple[int, int]]


@dataclass(frozen=True)
class Movement:
    """An immutable audit-log entry describing one change to stock.

    ``units`` is always the quantity the operation was asked to move.  Its
    direction is implied by ``kind`` -- see :data:`STOCK_EFFECTS` -- except for
    ``adjust``, which records the signed difference between the counted and the
    recorded quantity.
    """

    kind: str
    sku_code: str
    location_code: str
    units: int
    reference: Optional[str] = None
    recorded_at: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.recorded_at is None:
            object.__setattr__(self, "recorded_at", datetime.now(timezone.utc))

    @property
    def key(self) -> StockKey:
        """The ``(sku_code, location_code)`` this movement applies to."""
        return (self.sku_code, self.location_code)


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------
#: For each movement kind, the sign applied to ``(quantity, reserved)``.
STOCK_EFFECTS: Dict[str, Tuple[int, int]] = {
    "receive": (1, 0),
    "pick": (-1, 0),
    "reserve": (0, 1),
    "release": (0, -1),
    "transfer-out": (-1, 0),
    "transfer-in": (1, 0),
    "adjust": (1, 0),  # the delta is already signed
    "ship": (-1, -1),
}


def movement_delta(movement: Movement) -> Tuple[int, int]:
    """The ``(quantity, reserved)`` change a movement represents."""
    if not isinstance(movement, Movement):
        raise AuditLogError("only Movement entries can be replayed")
    try:
        quantity_sign, reserved_sign = STOCK_EFFECTS[movement.kind]
    except KeyError as exc:
        raise AuditLogError(
            f"cannot replay unknown movement kind {movement.kind!r}"
        ) from exc
    return quantity_sign * movement.units, reserved_sign * movement.units


def replay_totals(movements: Iterable[Movement]) -> Totals:
    """Replay a movement log into ``{(sku, location): (quantity, reserved)}``.

    Raises :class:`AuditLogError` if the log cannot describe a real warehouse:
    an unknown movement kind, a negative quantity or reservation, or more
    reserved than is on hand at any point during the replay.
    """
    running: Dict[StockKey, List[int]] = {}
    for movement in movements:
        quantity_delta, reserved_delta = movement_delta(movement)
        totals = running.setdefault(movement.key, [0, 0])
        totals[0] += quantity_delta
        totals[1] += reserved_delta
        if totals[0] < 0:
            raise AuditLogError(
                f"audit log drives {movement.sku_code!r} at {movement.location_code!r} "
                f"to a negative quantity ({totals[0]})"
            )
        if totals[1] < 0:
            raise AuditLogError(
                f"audit log drives {movement.sku_code!r} at {movement.location_code!r} "
                f"to a negative reservation ({totals[1]})"
            )
        if totals[1] > totals[0]:
            raise AuditLogError(
                f"audit log reserves more than it holds for {movement.sku_code!r} at "
                f"{movement.location_code!r} ({totals[1]} reserved of {totals[0]})"
            )
    return {key: (totals[0], totals[1]) for key, totals in running.items()}


def stock_level_drift(
    movements: Iterable[Movement], stock_levels: Iterable[StockLevel]
) -> List[str]:
    """Describe every way live records disagree with the replayed log.

    Returns an empty list when the records are exactly what the log implies,
    which is the normal state of a healthy warehouse.  Each problem is a
    human-readable line so a report or CLI can print it directly.
    """
    replayed = replay_totals(movements)
    live: Totals = {
        (record.sku.code, record.location.code): (record.quantity, record.reserved)
        for record in stock_levels
    }

    problems: List[str] = []
    for key in sorted(set(replayed) | set(live)):
        expected = replayed.get(key)
        actual = live.get(key)
        if expected == actual:
            continue
        where = f"{key[0]}@{key[1]}"
        if actual is None:
            problems.append(f"{where}: the log holds {expected[0]} but there is no record")
        elif expected is None:
            problems.append(
                f"{where}: the record holds {actual[0]} but the log never mentions it"
            )
        else:
            problems.append(
                f"{where}: the log implies (quantity={expected[0]}, reserved={expected[1]}) "
                f"but the record holds (quantity={actual[0]}, reserved={actual[1]})"
            )
    return problems


# ---------------------------------------------------------------------------
# The log itself
# ---------------------------------------------------------------------------
class AuditLog(Sequence):
    """An append-only sequence of :class:`Movement` entries.

    Entries may be appended and read, never edited, replaced, reordered or
    removed: every mutating sequence operation raises
    :class:`~inventory.errors.AuditLogError`.

    The single exception is :meth:`rollback_to`, which discards a suffix that
    was never committed.  It exists so a failed transaction can compensate,
    exactly as a database undoes an uncommitted transaction, and it is not a
    way to rewrite committed history.
    """

    __slots__ = ("_entries",)

    def __init__(self, entries: Iterable[Movement] = ()) -> None:
        self._entries: List[Movement] = []
        self.extend(entries)

    # -- growing ---------------------------------------------------------
    def append(self, movement: Movement) -> Movement:
        """Add one entry to the end of the log."""
        if not isinstance(movement, Movement):
            raise AuditLogError(
                f"only Movement entries can be appended, got {type(movement).__name__}"
            )
        self._entries.append(movement)
        return movement

    def extend(self, movements: Iterable[Movement]) -> None:
        """Append every entry of ``movements``, in order."""
        if isinstance(movements, (str, bytes)):
            raise AuditLogError("an audit log can only hold Movement entries")
        for movement in movements:
            self.append(movement)

    def rollback_to(self, length: int) -> None:
        """Discard entries after ``length``, compensating a failed transaction."""
        if isinstance(length, bool) or not isinstance(length, int):
            raise AuditLogError("length must be an integer")
        if not 0 <= length <= len(self._entries):
            raise AuditLogError(
                f"cannot roll back to {length} entries; the log holds {len(self._entries)}"
            )
        del self._entries[length:]

    # -- reading ---------------------------------------------------------
    def entry(self, index: int) -> Movement:
        """The entry at ``index``, raising :class:`AuditLogError` when absent."""
        try:
            return self._entries[index]
        except IndexError as exc:
            raise AuditLogError(
                f"no audit entry at index {index}; the log holds {len(self._entries)}"
            ) from exc

    def entries(self) -> Tuple[Movement, ...]:
        """A snapshot tuple of the entries, safe to keep."""
        return tuple(self._entries)

    def kinds(self) -> Tuple[str, ...]:
        """The kind of every entry, in order."""
        return tuple(movement.kind for movement in self._entries)

    def __getitem__(self, index: Union[int, slice]) -> Union[Movement, Tuple[Movement, ...]]:
        if isinstance(index, slice):
            return tuple(self._entries[index])
        return self._entries[index]

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[Movement]:
        return iter(self._entries)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, AuditLog):
            return self._entries == other._entries
        if isinstance(other, (list, tuple)):
            return self._entries == list(other)
        return NotImplemented

    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"AuditLog({len(self._entries)} entries)"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{len(self._entries)} audit entries"

    # -- refused operations ----------------------------------------------
    def _refuse(self, operation: str) -> None:
        raise AuditLogError(f"the audit log is append-only; {operation} is not allowed")

    def __setitem__(self, index, value) -> None:
        self._refuse("assignment")

    def __delitem__(self, index) -> None:
        self._refuse("deletion")

    def __iadd__(self, other):
        self._refuse("in-place concatenation")

    def insert(self, index, value) -> None:
        self._refuse("insertion")

    def pop(self, index=-1):
        self._refuse("popping")

    def remove(self, value) -> None:
        self._refuse("removal")

    def clear(self) -> None:
        self._refuse("clearing")

    def reverse(self) -> None:
        self._refuse("reordering")

    def sort(self, **kwargs) -> None:
        self._refuse("reordering")
