"""Tests for :mod:`sitegen.cli`."""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sitegen.cli import build_parser, main


def make_tree(root, files):
    for rel, content in files.items():
        path = Path(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


class ParserTests(unittest.TestCase):
    def test_build_arguments(self):
        args = build_parser().parse_args(["build", "src", "out", "--title", "Docs"])
        self.assertEqual(args.command, "build")
        self.assertEqual(args.source, "src")
        self.assertEqual(args.output, "out")
        self.assertEqual(args.title, "Docs")
        self.assertFalse(args.drafts)

    def test_default_title(self):
        args = build_parser().parse_args(["build", "src", "out"])
        self.assertEqual(args.title, "sitegen")

    def test_version_exits(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stdout(io.StringIO()):
                build_parser().parse_args(["--version"])


class MainTests(unittest.TestCase):
    def test_no_command_prints_help(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main([])
        self.assertEqual(code, 2)
        self.assertIn("usage:", stderr.getvalue())

    def test_successful_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            out = Path(tmp) / "public"
            make_tree(str(src), {"a.md": "# A"})
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["build", str(src), str(out), "--title", "Docs"])
            self.assertEqual(code, 0)
            self.assertIn("Generated 1 page(s)", stdout.getvalue())
            self.assertTrue((out / "a.html").exists())

    def test_missing_source_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = main(["build", os.path.join(tmp, "nope"), os.path.join(tmp, "out")])
            self.assertEqual(code, 1)
            self.assertIn("error:", stderr.getvalue())

    def test_drafts_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            out = Path(tmp) / "public"
            make_tree(str(src), {"d.md": "---\ndraft: true\n---\n# Draft"})
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(["build", str(src), str(out), "--drafts"])
            self.assertEqual(code, 0)
            self.assertTrue((out / "d.html").exists())

    def test_custom_template_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            out = Path(tmp) / "public"
            template = Path(tmp) / "t.html"
            make_tree(str(src), {"a.md": "# A"})
            template.write_text("<div>{{{ content }}}</div>", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(
                    ["build", str(src), str(out), "--template", str(template)]
                )
            self.assertEqual(code, 0)
            self.assertTrue((out / "a.html").read_text(encoding="utf-8").startswith("<div>"))


class NewParserTests(unittest.TestCase):
    def test_sample_arguments(self):
        args = build_parser().parse_args(["sample", "out", "--pages", "7", "--seed", "3"])
        self.assertEqual(args.command, "sample")
        self.assertEqual(args.directory, "out")
        self.assertEqual(args.pages, 7)
        self.assertEqual(args.seed, 3)

    def test_sample_defaults(self):
        args = build_parser().parse_args(["sample", "out"])
        self.assertEqual(args.pages, 300)
        self.assertEqual(args.seed, 1234)

    def test_incremental_and_feed_flags(self):
        args = build_parser().parse_args(
            ["build", "src", "out", "--no-incremental", "--no-feed", "--base-url", "u"]
        )
        self.assertTrue(args.no_incremental)
        self.assertTrue(args.no_feed)
        self.assertEqual(args.base_url, "u")

    def test_watch_flags(self):
        args = build_parser().parse_args(["build", "src", "out", "--watch", "--interval", "0.5"])
        self.assertTrue(args.watch)
        self.assertEqual(args.interval, 0.5)


class SampleCommandTests(unittest.TestCase):
    def test_sample_command_writes_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "content")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["sample", target, "--pages", "5"])
            self.assertEqual(code, 0)
            self.assertIn("Wrote 5 Markdown file(s)", stdout.getvalue())
            self.assertTrue(os.path.exists(os.path.join(target, "index.md")))


class IncrementalCliTests(unittest.TestCase):
    def test_second_build_reports_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            out = Path(tmp) / "public"
            make_tree(str(src), {"a.md": "# A"})
            with contextlib.redirect_stdout(io.StringIO()):
                main(["build", str(src), str(out)])
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["build", str(src), str(out)])
            self.assertEqual(code, 0)
            self.assertIn("0 rebuilt, 1 unchanged", stdout.getvalue())

    def test_no_incremental_rebuilds(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            out = Path(tmp) / "public"
            make_tree(str(src), {"a.md": "# A"})
            with contextlib.redirect_stdout(io.StringIO()):
                main(["build", str(src), str(out)])
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                main(["build", str(src), str(out), "--no-incremental"])
            self.assertIn("1 rebuilt, 0 unchanged", stdout.getvalue())


class FeedCliTests(unittest.TestCase):
    def test_feed_written_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            out = Path(tmp) / "public"
            make_tree(str(src), {"a.md": "# A"})
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                main(["build", str(src), str(out), "--base-url", "https://x.test"])
            self.assertTrue((out / "feed.xml").exists())
            self.assertIn("feed.xml", stdout.getvalue())
            self.assertIn(
                "https://x.test/a.html",
                (out / "feed.xml").read_text(encoding="utf-8"),
            )

    def test_no_feed_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            out = Path(tmp) / "public"
            make_tree(str(src), {"a.md": "# A"})
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(["build", str(src), str(out), "--no-feed"])
            self.assertEqual(code, 0)
            self.assertFalse((out / "feed.xml").exists())


class WatchCliTests(unittest.TestCase):
    def test_watch_prints_and_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            out = Path(tmp) / "public"
            make_tree(str(src), {"a.md": "# A"})
            stdout = io.StringIO()
            with mock.patch("sitegen.cli.watch", return_value=[]) as patched:
                with contextlib.redirect_stdout(stdout):
                    code = main(["build", str(src), str(out), "--watch", "--interval", "0.1"])
            self.assertEqual(code, 0)
            self.assertIn("Watching", stdout.getvalue())
            patched.assert_called_once()
            self.assertEqual(patched.call_args.kwargs["interval"], 0.1)

    def test_watch_handles_keyboard_interrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            out = Path(tmp) / "public"
            make_tree(str(src), {"a.md": "# A"})
            stdout = io.StringIO()
            with mock.patch("sitegen.cli.watch", side_effect=KeyboardInterrupt):
                with contextlib.redirect_stdout(stdout):
                    code = main(["build", str(src), str(out), "--watch"])
            self.assertEqual(code, 0)
            self.assertIn("Stopped watching", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
