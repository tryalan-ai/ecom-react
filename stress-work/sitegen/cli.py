"""Command-line interface for sitegen.

Usage::

    python3 -m sitegen build CONTENT_DIR OUTPUT_DIR [--template T] [--title NAME]

The CLI is intentionally thin: it parses arguments, calls
:func:`sitegen.site.build_site` and reports what happened.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .site import SiteError, build_site


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
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "build":
        parser.print_help(sys.stderr)
        return 2

    try:
        result = build_site(
            args.source,
            args.output,
            template_path=args.template,
            site_title=args.title,
            include_drafts=args.drafts,
        )
    except SiteError as error:
        print("error: %s" % error, file=sys.stderr)
        return 1

    print("Generated %d page(s) into %s" % (len(result.pages), result.output_dir))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
