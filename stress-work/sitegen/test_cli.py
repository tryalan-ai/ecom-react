"""Tests for :mod:`sitegen.cli`."""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
