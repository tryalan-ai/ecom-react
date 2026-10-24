"""Tests for :mod:`sitegen.watch`."""

import tempfile
import unittest
from pathlib import Path

from sitegen.watch import DEFAULT_INTERVAL, watch


def no_sleep(_seconds):
    """Never actually wait during tests."""
    return None


class WatchTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src = self.root / "content"
        self.src.mkdir(parents=True, exist_ok=True)
        self.out = self.root / "public"

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, content):
        path = self.src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_default_interval_is_two_seconds(self):
        self.assertEqual(DEFAULT_INTERVAL, 2.0)

    def test_initial_build_happens_once(self):
        self.write("a.md", "# A")
        results = watch(
            str(self.src),
            str(self.out),
            sleep=no_sleep,
            poll_hook=lambda poll: False,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0].pages), 1)
        self.assertTrue((self.out / "a.html").exists())

    def test_no_changes_does_not_rebuild(self):
        self.write("a.md", "# A")
        results = watch(
            str(self.src),
            str(self.out),
            sleep=no_sleep,
            max_polls=3,
        )
        self.assertEqual(len(results), 1)

    def test_added_file_triggers_rebuild(self):
        def hook(poll):
            if poll == 0:
                self.write("b.md", "# B")
                return True
            return False

        results = watch(
            str(self.src),
            str(self.out),
            sleep=no_sleep,
            poll_hook=hook,
            max_polls=5,
        )
        self.assertEqual(len(results), 2)
        self.assertTrue((self.out / "b.html").exists())
        self.assertEqual([p.title for p in results[-1].pages], ["B"])

    def test_modified_file_triggers_rebuild(self):
        self.write("a.md", "# A\n\nshort")

        def hook(poll):
            if poll == 0:
                self.write("a.md", "# A\n\nmuch longer replacement text")
                return True
            return False

        results = watch(
            str(self.src),
            str(self.out),
            sleep=no_sleep,
            poll_hook=hook,
            max_polls=5,
        )
        self.assertEqual(len(results), 2)
        self.assertIn(
            "much longer replacement text",
            (self.out / "a.html").read_text(encoding="utf-8"),
        )

    def test_rebuild_is_incremental(self):
        self.write("a.md", "# A")
        self.write("b.md", "# B")

        def hook(poll):
            if poll == 0:
                self.write("a.md", "# A\n\nextra")
                return True
            return False

        results = watch(
            str(self.src),
            str(self.out),
            sleep=no_sleep,
            poll_hook=hook,
            max_polls=5,
        )
        self.assertEqual(results[-1].rebuilt, ["a.md"])
        self.assertEqual(results[-1].skipped, ["b.md"])

    def test_deleted_file_triggers_rebuild(self):
        self.write("a.md", "# A")
        self.write("b.md", "# B")

        def hook(poll):
            if poll == 0:
                (self.src / "b.md").unlink()
                return True
            return False

        results = watch(
            str(self.src),
            str(self.out),
            sleep=no_sleep,
            poll_hook=hook,
            max_polls=5,
        )
        self.assertEqual(len(results), 2)
        self.assertFalse((self.out / "b.html").exists())

    def test_max_polls_limits_iterations(self):
        self.write("a.md", "# A")
        sleeps = []

        def counting_sleep(seconds):
            sleeps.append(seconds)

        results = watch(
            str(self.src),
            str(self.out),
            sleep=counting_sleep,
            max_polls=2,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(len(sleeps), 2)
        self.assertEqual(sleeps, [DEFAULT_INTERVAL, DEFAULT_INTERVAL])

    def test_poll_hook_stops_loop(self):
        self.write("a.md", "# A")
        seen = []

        def hook(poll):
            seen.append(poll)
            return poll < 2

        results = watch(
            str(self.src),
            str(self.out),
            sleep=no_sleep,
            poll_hook=hook,
            max_polls=100,
        )
        self.assertEqual(seen, [0, 1, 2])
        self.assertEqual(len(results), 1)

    def test_on_build_callback(self):
        self.write("a.md", "# A")
        built = []
        watch(
            str(self.src),
            str(self.out),
            sleep=no_sleep,
            poll_hook=lambda poll: False,
            on_build=built.append,
        )
        self.assertEqual(len(built), 1)
        self.assertEqual(len(built[0].pages), 1)

    def test_passes_build_options_through(self):
        self.write("a.md", "# A")
        template = self.root / "t.html"
        template.write_text("<div>{{{ content }}}</div>", encoding="utf-8")
        results = watch(
            str(self.src),
            str(self.out),
            sleep=no_sleep,
            poll_hook=lambda poll: False,
            template_path=str(template),
            site_title="Watched",
        )
        self.assertTrue(
            (self.out / "a.html").read_text(encoding="utf-8").startswith("<div>")
        )
        self.assertTrue((self.out / "feed.xml").exists())
        self.assertEqual(results[0].pages[0].title, "A")

    def test_missing_source_raises(self):
        from sitegen.site import SiteError

        with self.assertRaises(SiteError):
            watch(
                str(self.root / "missing"),
                str(self.out),
                sleep=no_sleep,
                poll_hook=lambda poll: False,
            )


if __name__ == "__main__":
    unittest.main()
