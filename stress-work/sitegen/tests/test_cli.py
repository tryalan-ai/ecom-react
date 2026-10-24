import contextlib
import io
import os
import tempfile
import unittest

from sitegen.cli import build_parser, main


class ParserTests(unittest.TestCase):
    def test_build_defaults(self):
        args = build_parser().parse_args(["build", "src"])
        self.assertEqual(args.command, "build")
        self.assertEqual(args.output, "_site")
        self.assertFalse(args.no_incremental)

    def test_watch_default_interval(self):
        args = build_parser().parse_args(["watch", "src"])
        self.assertEqual(args.interval, 2.0)

    def test_sample_defaults(self):
        args = build_parser().parse_args(["sample", "out"])
        self.assertEqual(args.count, 300)
        self.assertEqual(args.seed, 1337)


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = os.path.join(self.tmp.name, "src")
        self.out = os.path.join(self.tmp.name, "out")
        os.makedirs(self.src)

    def write(self, rel, text):
        path = os.path.join(self.src, rel)
        os.makedirs(os.path.dirname(path) or self.src, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def run_cli(self, argv):
        with contextlib.redirect_stdout(io.StringIO()):
            return main(argv)

    def test_build_command(self):
        self.write("a.md", "# A")
        code = self.run_cli(["build", self.src, "-o", self.out, "--title", "T"])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(self.out, "a.html")))

    def test_build_with_template_file(self):
        self.write("a.md", "# A")
        tmpl = os.path.join(self.tmp.name, "t.html")
        with open(tmpl, "w", encoding="utf-8") as handle:
            handle.write("CUSTOM {{{ content }}}")
        self.run_cli(["build", self.src, "-o", self.out, "--template", tmpl])
        with open(os.path.join(self.out, "a.html"), encoding="utf-8") as handle:
            self.assertTrue(handle.read().startswith("CUSTOM "))

    def test_build_no_incremental(self):
        self.write("a.md", "# A")
        self.run_cli(["build", self.src, "-o", self.out])
        code = self.run_cli(["build", self.src, "-o", self.out, "--no-incremental"])
        self.assertEqual(code, 0)

    def test_sample_command(self):
        target = os.path.join(self.tmp.name, "sample")
        code = self.run_cli(["sample", target, "--count", "5", "--seed", "3"])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(target, "index.md")))

    def test_watch_command_bounded(self):
        self.write("a.md", "# A")
        code = self.run_cli(
            ["watch", self.src, "-o", self.out, "--max-polls", "1", "--interval", "2"]
        )
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(self.out, "a.html")))

    def test_build_clean_removes_stale_output(self):
        self.write("a.md", "# A")
        self.run_cli(["build", self.src, "-o", self.out])
        os.remove(os.path.join(self.src, "a.md"))
        self.write("b.md", "# B")
        self.run_cli(["build", self.src, "-o", self.out, "--clean"])
        self.assertFalse(os.path.exists(os.path.join(self.out, "a.html")))
        self.assertTrue(os.path.exists(os.path.join(self.out, "b.html")))


if __name__ == "__main__":
    unittest.main()
