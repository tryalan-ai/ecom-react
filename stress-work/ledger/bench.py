"""Benchmark harness for the :mod:`ledger` package.

Generates a large synthetic bank statement and times the parse + summary
pipeline over it. Run directly::

    python -m ledger.bench                       # 2,000,000 rows (default)
    python -m ledger.bench --count 100000        # smaller quick run
    python -m ledger.bench --skip-generate       # reuse /tmp/ledger-bench.csv
    python -m ledger.bench --profile             # cProfile the pipeline

The generated file is written to ``/tmp/ledger-bench.csv`` by default and has
the columns ``date,description,amount``. Everything uses the standard library
only.
"""

from __future__ import annotations

import argparse
import cProfile
import io
import os
import pstats
import random
import time
from datetime import date, timedelta
from typing import Callable, Sequence, TypeVar

from .csv_parser import parse_csv
from .summary import monthly_summaries

DEFAULT_PATH = "/tmp/ledger-bench.csv"
DEFAULT_COUNT = 2_000_000

_DESCRIPTIONS = (
    "Salary January",
    "Tesco groceries",
    "Starbucks coffee",
    "Uber trip",
    "Trainline ticket",
    "Electricity bill",
    "Rent payment",
    "Amazon order",
    "Restaurant dinner",
    "Bank fee",
    "Transfer to savings",
    "Dividend payout",
)

T = TypeVar("T")


def generate(path: str, count: int, seed: int = 7, days: int = 730) -> None:
    """Write ``count`` synthetic transactions to ``path`` as CSV.

    Dates are spread over ``days`` from 2020-01-01 and amounts are a mix of
    salary-sized income and everyday expenses, deterministically seeded.
    """
    rng = random.Random(seed)
    start = date(2020, 1, 1)
    chunk: list[str] = []
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write("date,description,amount\n")
        for _ in range(count):
            day = start + timedelta(days=rng.randrange(days))
            description = _DESCRIPTIONS[rng.randrange(len(_DESCRIPTIONS))]
            if description in ("Salary January", "Dividend payout"):
                amount = f"{rng.uniform(1500, 3000):.2f}"
            else:
                amount = f"-{rng.uniform(1, 200):.2f}"
            chunk.append(f"{day.isoformat()},{description},{amount}\n")
            if len(chunk) >= 100_000:
                handle.write("".join(chunk))
                chunk.clear()
        if chunk:
            handle.write("".join(chunk))


def _timed(label: str, fn: Callable[[], T]) -> tuple[T, float]:
    start = time.perf_counter()
    result = fn()
    elapsed = time.perf_counter() - start
    print(f"{label:<28} {elapsed:8.3f} s")
    return result, elapsed


def run(path: str, count: int, do_profile: bool = False) -> dict[str, float]:
    """Time parsing and summarising ``path``; return the timings in seconds."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    size_mb = os.path.getsize(path) / (1024 * 1024)

    print(f"file: {path} ({size_mb:.1f} MiB, target {count:,} rows)")
    timings: dict[str, float] = {}

    if do_profile:
        profiler = cProfile.Profile()
        profiler.enable()
        transactions, parse_s = _timed("parse_csv", lambda: parse_csv(path))
        summaries, summary_s = _timed(
            "monthly_summaries", lambda: monthly_summaries(transactions)
        )
        profiler.disable()
        timings["parse"] = parse_s
        timings["summary"] = summary_s
        timings["total"] = parse_s + summary_s
        print()
        print("cProfile: top functions by cumulative time")
        stream = io.StringIO()
        pstats.Stats(profiler, stream=stream).sort_stats("cumulative").print_stats(15)
        print(stream.getvalue())
    else:
        transactions, parse_s = _timed("parse_csv", lambda: parse_csv(path))
        summaries, summary_s = _timed("monthly_summaries", lambda: monthly_summaries(transactions))
        timings["parse"] = parse_s
        timings["summary"] = summary_s
        timings["total"] = parse_s + summary_s

    print()
    print(f"transactions parsed: {len(transactions):,}")
    print(f"months summarised:   {len(summaries):,}")
    print(f"TOTAL:               {timings['total']:.3f} s")
    return timings


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``python -m ledger.bench``."""
    parser = argparse.ArgumentParser(prog="ledger-bench", description=__doc__)
    parser.add_argument("--path", default=DEFAULT_PATH, help=f"CSV path (default: {DEFAULT_PATH})")
    parser.add_argument(
        "--count", type=int, default=DEFAULT_COUNT, help=f"rows to generate (default: {DEFAULT_COUNT:,})"
    )
    parser.add_argument("--seed", type=int, default=7, help="generation seed")
    parser.add_argument("--skip-generate", action="store_true", help="reuse an existing CSV file")
    parser.add_argument("--profile", action="store_true", help="run under cProfile")
    args = parser.parse_args(argv)

    if not args.skip_generate:
        _, gen_s = _timed("generate", lambda: generate(args.path, args.count, seed=args.seed))
        print()

    timings = run(args.path, args.count, do_profile=args.profile)
    return 0 if timings["total"] >= 0 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
