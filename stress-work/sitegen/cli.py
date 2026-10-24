"""Command line interface for sitegen."""

import argparse
import sys

from .builder import SiteBuilder
from .sample import DEFAULT_COUNT, generate_sample_site
from .watch import DEFAULT_INTERVAL, Watcher

__all__ = ["main", "build_parser"]


def build_parser():
    parser = argparse.ArgumentParser(
        prog="sitegen",
        description="Generate a static HTML site from a folder of Markdown files.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="build the site once")
    _add_common(build)
    build.add_argument("--no-incremental", action="store_true", help="rebuild every page")
    build.add_argument("--no-feed", action="store_true", help="do not write feed.xml")
    build.add_argument("--clean", action="store_true", help="remove output before building")

    watch = sub.add_parser("watch", help="rebuild whenever a source file changes")
    _add_common(watch)
    watch.add_argument(
        "--interval", type=float, default=DEFAULT_INTERVAL, help="poll interval in seconds"
    )
    watch.add_argument(
        "--max-polls", type=int, default=None, help="stop after N polls (mainly for tests)"
    )

    sample = sub.add_parser("sample", help="generate a synthetic sample site")
    sample.add_argument("target", help="directory to write the sample site into")
    sample.add_argument("--count", type=int, default=DEFAULT_COUNT, help="number of pages")
    sample.add_argument("--seed", type=int, default=1337, help="random seed")

    return parser


def _add_common(parser):
    parser.add_argument("source", help="directory containing Markdown source files")
    parser.add_argument("-o", "--output", default="_site", help="output directory")
    parser.add_argument("--template", default=None, help="path to a template file")
    parser.add_argument("--title", default="Site", help="site title")
    parser.add_argument("--index-title", default="Home", help="index page heading")
    parser.add_argument("--site-url", default="", help="absolute site URL for feeds")


def _read_template(path):
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "sample":
        created = generate_sample_site(args.target, count=args.count, seed=args.seed)
        print("Generated %d files in %s" % (len(created), args.target))
        return 0

    builder = SiteBuilder(
        args.source,
        args.output,
        template=_read_template(getattr(args, "template", None)),
        site_title=args.title,
        index_title=getattr(args, "index_title", "Home"),
        incremental=not getattr(args, "no_incremental", False),
        feed=not getattr(args, "no_feed", False),
        site_url=getattr(args, "site_url", ""),
    )

    if args.command == "build":
        if getattr(args, "clean", False):
            builder.clean()
        result = builder.build()
        print(
            "Wrote %d page(s), skipped %d, removed %d"
            % (result.written_count, result.skipped_count, len(result.removed))
        )
        return 0

    if args.command == "watch":
        watcher = Watcher(
            args.source, args.output, interval=args.interval, builder=builder
        )

        def report(result):
            print(
                "rebuilt: %d written, %d skipped"
                % (result.written_count, result.skipped_count)
            )

        try:
            polls = watcher.run(max_polls=args.max_polls, on_build=report)
        except KeyboardInterrupt:
            print("stopped")
            return 0
        print("watched %d poll(s)" % polls)
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
