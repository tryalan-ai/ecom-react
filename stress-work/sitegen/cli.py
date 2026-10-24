"""Command-line interface for sitegen.

Usage::

    python3 -m sitegen build CONTENT_DIR OUTPUT_DIR [options]
    python3 -m sitegen sample DIR [--pages N] [--seed S]

The CLI is intentionally thin: it parses arguments, calls into
:mod:`sitegen.site` and :mod:`sitegen.sample`, and reports what happened.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .sample import DEFAULT_PAGES, DEFAULT_SEED, generate_sample_site
from .site import SiteError, build_site
from .watch import DEFAULT_INTERVAL, watch


def build_parser():
    parser = argparse.ArgumentParser(
        prog="sitegen",
        description="Generate a static HTML site from a folder of Markdown files.",
    )
    parser.add_argument("--version", action="version", version="sitegen " + __version__)
    subparsers = parser.add_subparsers(dest="command")

    build = subparsers.add_parser("build", help="build the site")
    build.add_argument("source", help="folder containing Markdown files")
    build.add_argument("output", help="folder to write HTML into")
    build.add_argument("--template", default=None, help="path to an HTML template file")
    build.add_argument("--title", default="sitegen", help="site title")
    build.add_argument(
        "--drafts",
        action="store_true",
        help="also include pages marked 'draft: true'",
    )
    build.add_argument(
        "--no-incremental",
        action="store_true",
        help="rebuild every page instead of only changed ones",
    )
    build.add_argument(
        "--watch",
        action="store_true",
        help="keep running and rebuild when source files change",
    )
    build.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help="poll interval in seconds for --watch (default: %(default)s)",
    )
    build.add_argument(
        "--base-url",
        default="",
        help="absolute site URL used for links in the RSS feed",
    )
    build.add_argument(
        "--no-feed",
        action="store_true",
        help="do not write the RSS feed (feed.xml)",
    )

    sample = subparsers.add_parser(
        "sample", help="generate a synthetic Markdown site"
    )
    sample.add_argument("directory", help="folder to write Markdown files into")
    sample.add_argument(
        "--pages",
        type=int,
        default=DEFAULT_PAGES,
        help="number of pages to generate (default: %(default)s)",
    )
    sample.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="random seed for deterministic content (default: %(default)s)",
    )
    return parser


def _summary(result):
    summary = "Generated %d page(s) into %s (%d rebuilt, %d unchanged, %d removed)" % (
        len(result.pages),
        result.output_dir,
        len(result.rebuilt),
        len(result.skipped),
        len(result.removed),
    )
    if result.feed_path:
        summary += "; feed: %s" % result.feed_path
    return summary


def _run_build(args):
    options = {
        "template_path": args.template,
        "site_title": args.title,
        "include_drafts": args.drafts,
        "incremental": not args.no_incremental,
        "base_url": args.base_url,
        "feed": not args.no_feed,
    }

    if args.watch:
        print(
            "Watching %s every %gs (press Ctrl-C to stop)"
            % (args.source, args.interval)
        )
        try:
            watch(
                args.source,
                args.output,
                interval=args.interval,
                on_build=lambda result: print(_summary(result)),
                **options
            )
        except (KeyboardInterrupt, SiteError) as error:
            if isinstance(error, SiteError):
                print("error: %s" % error, file=sys.stderr)
                return 1
            print("\nStopped watching.")
        return 0

    try:
        result = build_site(args.source, args.output, **options)
    except SiteError as error:
        print("error: %s" % error, file=sys.stderr)
        return 1

    print(_summary(result))
    return 0


def _run_sample(args):
    paths = generate_sample_site(args.directory, pages=args.pages, seed=args.seed)
    print("Wrote %d Markdown file(s) to %s" % (len(paths), args.directory))
    return 0


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "build":
        return _run_build(args)
    if args.command == "sample":
        return _run_sample(args)

    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
