"""Command line entry point for the inventory package.

    python3 -m inventory verify  <database>
    python3 -m inventory rebuild <database>

``verify`` replays the audit log and reports any stock row that disagrees with
it, exiting non-zero when there is drift.  ``rebuild`` rewrites the stock table
from the log, which is the repair for exactly that drift.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .errors import InventoryError
from .storage import SQLiteStore

__all__ = ["main", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m inventory",
        description="Inspect and repair an inventory database using its audit log.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    verify = subcommands.add_parser(
        "verify", help="check that stock levels match the audit log"
    )
    verify.add_argument("database", help="path to the SQLite database")

    rebuild = subcommands.add_parser(
        "rebuild", help="rebuild stock levels by replaying the audit log"
    )
    rebuild.add_argument("database", help="path to the SQLite database")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Run the command.  Returns the process exit code."""
    args = build_parser().parse_args(argv)

    try:
        with SQLiteStore(args.database) as store:
            movements = store.count_movements()

            if args.command == "verify":
                problems = store.stock_level_drift()
                if problems:
                    print(
                        f"stock levels disagree with the audit log "
                        f"({len(problems)} problem(s) over {movements} movement(s)):"
                    )
                    for problem in problems:
                        print(f"  {problem}")
                    print("run `python3 -m inventory rebuild <database>` to repair")
                    return 1
                print(
                    f"stock levels match the audit log "
                    f"({movements} movement(s) replayed)"
                )
                return 0

            rebuilt = store.rebuild_stock_levels()
            print(f"rebuilt {rebuilt} stock record(s) from {movements} movement(s)")
            return 0
    except InventoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised via main()
    sys.exit(main())
