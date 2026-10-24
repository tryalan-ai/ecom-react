import os
import tempfile
import threading
import unittest

from sitegen.builder import SiteBuilder
from sitegen.watch import DEFAULT_INTERVAL, Watcher


class WatcherTestCase(unittest.TestCase):
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
        return path

    def watcher(self, **kwargs):
        return Watcher(self.src, self.out, **kwargs)


class SnapshotTests(WatcherTestCase):
    def test_default_interval_is_two_seconds(self):
        self.assertEqual(DEFAULT_INTERVAL, 2.0)
        self.assertEqual(self.watcher().interval, 2.0)

    def test_snapshot_lists_files(self):
        self.write("a.md", "# A")
        self.write("sub/b.md", "# B")
        state = self.watcher().snapshot()
        self.assertEqual(sorted(state), ["a.md", "sub/b.md"])

    def test_snapshot_ignores_assets(self):
        self.write("a.md", "# A")
        self.write("style.css", "x")
        self.assertEqual(list(self.watcher().snapshot()), ["a.md"])

    def test_snapshot_detects_change(self):
        self.write("a.md", "# A")
        watcher = self.watcher()
        before = watcher.snapshot()
        self.write("a.md", "# A changed")
        self.assertNotEqual(before["a.md"], watcher.snapshot()["a.md"])


class ChangesTests(unittest.TestCase):
    def test_added(self):
        added, modified, removed = Watcher.changes({"a": "1"}, {"a": "1", "b": "1"})
        self.assertEqual((added, modified, removed), (["b"], [], []))

    def test_modified(self):
        added, modified, removed = Watcher.changes({"a": "1"}, {"a": "2"})
        self.assertEqual((added, modified, removed), ([], ["a"], []))

    def test_removed(self):
        added, modified, removed = Watcher.changes({"a": "1"}, {})
        self.assertEqual((added, modified, removed), ([], [], ["a"]))

    def test_unchanged(self):
        self.assertEqual(Watcher.changes({"a": "1"}, {"a": "1"}), ([], [], []))


class RunTests(WatcherTestCase):
    def test_initial_build_happens(self):
        self.write("a.md", "# A")
        self.watcher().run(max_polls=0, sleep=lambda _s: None)
        self.assertTrue(os.path.exists(os.path.join(self.out, "a.html")))

    def test_zero_polls_returns_zero(self):
        self.write("a.md", "# A")
        polls = self.watcher().run(max_polls=0, sleep=lambda _s: None)
        self.assertEqual(polls, 0)

    def test_rebuild_on_change(self):
        self.write("a.md", "# A")
        calls = {"n": 0}

        def fake_sleep(_seconds):
            calls["n"] += 1
            if calls["n"] == 1:
                self.write("b.md", "# B")

        self.watcher().run(max_polls=2, sleep=fake_sleep)
        self.assertTrue(os.path.exists(os.path.join(self.out, "b.html")))

    def test_no_rebuild_when_unchanged(self):
        self.write("a.md", "# A")
        built = []

        def on_build(result):
            built.append(result)

        self.watcher().run(max_polls=3, sleep=lambda _s: None, on_build=on_build)
        # Initial build only; no source changes so no further builds.
        self.assertEqual(len(built), 1)

    def test_stop_event(self):
        self.write("a.md", "# A")
        event = threading.Event()
        event.set()
        polls = self.watcher().run(max_polls=50, sleep=lambda _s: None, stop_event=event)
        self.assertEqual(polls, 0)

    def test_interval_used_by_sleep(self):
        self.write("a.md", "# A")
        seen = []
        self.watcher(interval=2.0).run(max_polls=1, sleep=lambda s: seen.append(s))
        self.assertEqual(seen, [2.0])


class WatcherBuilderTests(WatcherTestCase):
    def test_accepts_prebuilt_builder(self):
        self.write("a.md", "# A")
        builder = SiteBuilder(self.src, self.out, site_title="Custom")
        watcher = Watcher(self.src, self.out, builder=builder)
        watcher.run(max_polls=0, sleep=lambda _s: None)
        with open(os.path.join(self.out, "a.html"), encoding="utf-8") as handle:
            self.assertIn("Custom", handle.read())


if __name__ == "__main__":
    unittest.main()
