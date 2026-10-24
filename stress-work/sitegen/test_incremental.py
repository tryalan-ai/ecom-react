"""Tests for incremental builds and the build manifest in :mod:`sitegen.site`."""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from sitegen.site import (
    MANIFEST_NAME,
    MANIFEST_VERSION,
    build_site,
    content_hash,
    load_manifest,
    manifest_path,
    save_manifest,
)


def make_tree(root, files):
    for rel, content in files.items():
        path = Path(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


class HashTests(unittest.TestCase):
    def test_hash_is_stable(self):
        self.assertEqual(content_hash("abc"), content_hash("abc"))

    def test_hash_changes_with_content(self):
        self.assertNotEqual(content_hash("abc"), content_hash("abd"))


class ManifestIoTests(unittest.TestCase):
    def test_missing_manifest_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load_manifest(tmp))

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = {"version": MANIFEST_VERSION, "pages": {}, "nav_key": "x"}
            path = save_manifest(tmp, data)
            self.assertEqual(path, str(manifest_path(tmp)))
            self.assertEqual(load_manifest(tmp), data)

    def test_corrupt_manifest_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / MANIFEST_NAME).write_text("{not json", encoding="utf-8")
            self.assertIsNone(load_manifest(tmp))

    def test_wrong_version_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / MANIFEST_NAME).write_text(
                json.dumps({"version": 999, "pages": {}}), encoding="utf-8"
            )
            self.assertIsNone(load_manifest(tmp))

    def test_missing_pages_key_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / MANIFEST_NAME).write_text(
                json.dumps({"version": MANIFEST_VERSION}), encoding="utf-8"
            )
            self.assertIsNone(load_manifest(tmp))


class IncrementalBuildTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src = self.root / "content"
        self.out = self.root / "public"

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, content):
        path = self.src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_first_build_writes_everything(self):
        self.write("a.md", "# A\n\nalpha")
        self.write("b.md", "# B\n\nbeta")
        result = build_site(str(self.src), str(self.out))
        self.assertCountEqual(result.rebuilt, ["a.md", "b.md"])
        self.assertEqual(result.skipped, [])
        self.assertTrue(result.forced)
        self.assertTrue((self.out / MANIFEST_NAME).exists())

    def test_second_build_without_changes_skips_all(self):
        self.write("a.md", "# A\n\nalpha")
        self.write("b.md", "# B\n\nbeta")
        build_site(str(self.src), str(self.out))

        first = (self.out / "a.html").read_text(encoding="utf-8")
        result = build_site(str(self.src), str(self.out))
        self.assertEqual(result.rebuilt, [])
        self.assertEqual(result.skipped, ["a.md", "b.md"])
        self.assertFalse(result.forced)
        self.assertEqual((self.out / "a.html").read_text(encoding="utf-8"), first)

    def test_changed_file_only_rebuilds_that_page(self):
        self.write("a.md", "# A\n\nalpha")
        self.write("b.md", "# B\n\nbeta")
        build_site(str(self.src), str(self.out))

        time.sleep(0.01)
        self.write("a.md", "# A\n\nchanged text")
        result = build_site(str(self.src), str(self.out))

        self.assertEqual(result.rebuilt, ["a.md"])
        self.assertEqual(result.skipped, ["b.md"])
        body = (self.out / "a.html").read_text(encoding="utf-8")
        self.assertIn("changed text", body)

    def test_new_file_forces_rebuild_for_navigation(self):
        self.write("a.md", "# A\n\nalpha")
        build_site(str(self.src), str(self.out))

        self.write("b.md", "# B\n\nbeta")
        result = build_site(str(self.src), str(self.out))

        self.assertTrue(result.forced)
        self.assertIn("b.md", result.rebuilt)
        self.assertIn(
            'href="b.html"', (self.out / "a.html").read_text(encoding="utf-8")
        )

    def test_deleted_file_removes_output(self):
        self.write("a.md", "# A")
        self.write("gone.md", "# Gone")
        build_site(str(self.src), str(self.out))
        self.assertTrue((self.out / "gone.html").exists())

        (self.src / "gone.md").unlink()
        result = build_site(str(self.src), str(self.out))

        self.assertIn(str(self.out / "gone.html"), result.removed)
        self.assertFalse((self.out / "gone.html").exists())

    def test_renamed_file_removes_old_output(self):
        self.write("old.md", "# Old")
        build_site(str(self.src), str(self.out))
        self.assertTrue((self.out / "old.html").exists())

        (self.src / "old.md").rename(self.src / "new.md")
        result = build_site(str(self.src), str(self.out))

        self.assertFalse((self.out / "old.html").exists())
        self.assertTrue((self.out / "new.html").exists())
        self.assertIn(str(self.out / "old.html"), result.removed)

    def test_template_change_forces_full_rebuild(self):
        self.write("a.md", "# A")
        self.write("b.md", "# B")
        template = self.root / "t.html"
        template.write_text("<main>{{{ content }}}</main>", encoding="utf-8")
        build_site(str(self.src), str(self.out), template_path=str(template))

        template.write_text("<article>{{{ content }}}</article>", encoding="utf-8")
        result = build_site(str(self.src), str(self.out), template_path=str(template))

        self.assertTrue(result.forced)
        self.assertCountEqual(result.rebuilt, ["a.md", "b.md"])
        self.assertIn(
            "<article>", (self.out / "a.html").read_text(encoding="utf-8")
        )

    def test_site_title_change_forces_full_rebuild(self):
        self.write("a.md", "# A")
        self.write("b.md", "# B")
        build_site(str(self.src), str(self.out), site_title="One")
        result = build_site(str(self.src), str(self.out), site_title="Two")
        self.assertTrue(result.forced)
        self.assertEqual(len(result.rebuilt), 2)

    def test_no_incremental_forces_full_rebuild(self):
        self.write("a.md", "# A")
        self.write("b.md", "# B")
        build_site(str(self.src), str(self.out))
        result = build_site(str(self.src), str(self.out), incremental=False)
        self.assertTrue(result.forced)
        self.assertCountEqual(result.rebuilt, ["a.md", "b.md"])
        self.assertEqual(result.skipped, [])

    def test_missing_output_is_rewritten(self):
        self.write("a.md", "# A")
        self.write("b.md", "# B")
        build_site(str(self.src), str(self.out))
        (self.out / "a.html").unlink()

        result = build_site(str(self.src), str(self.out))

        self.assertIn("a.md", result.rebuilt)
        self.assertEqual(result.skipped, ["b.md"])
        self.assertTrue((self.out / "a.html").exists())

    def test_corrupt_manifest_triggers_full_rebuild(self):
        self.write("a.md", "# A")
        build_site(str(self.src), str(self.out))
        (self.out / MANIFEST_NAME).write_text("broken", encoding="utf-8")
        result = build_site(str(self.src), str(self.out))
        self.assertTrue(result.forced)
        self.assertEqual(result.rebuilt, ["a.md"])

    def test_cached_pages_have_no_parsed_body(self):
        self.write("a.md", "# A\n\nalpha")
        self.write("b.md", "# B\n\nbeta")
        build_site(str(self.src), str(self.out))
        result = build_site(str(self.src), str(self.out))
        cached = {page.rel: page for page in result.pages}
        self.assertTrue(cached["a.md"].from_cache)
        self.assertEqual(cached["a.md"].body_html, "")
        self.assertEqual(cached["a.md"].title, "A")
        self.assertEqual(cached["a.md"].excerpt, "alpha")

    def test_index_rebuilt_when_excerpt_changes(self):
        self.write("a.md", "# A\n\nfirst trailer")
        build_site(str(self.src), str(self.out))
        index_before = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn("first trailer", index_before)

        self.write("a.md", "# A\n\nsecond trailer")
        build_site(str(self.src), str(self.out))
        self.assertIn(
            "second trailer", (self.out / "index.html").read_text(encoding="utf-8")
        )

    def test_index_not_rewritten_when_nothing_changes(self):
        self.write("a.md", "# A\n\nalpha")
        build_site(str(self.src), str(self.out))
        result = build_site(str(self.src), str(self.out))
        self.assertEqual(result.written, [])

    def test_drafts_respected_across_builds(self):
        self.write("a.md", "# A")
        self.write("d.md", "---\ndraft: true\n---\n# D")
        result = build_site(str(self.src), str(self.out))
        self.assertFalse((self.out / "d.html").exists())
        self.assertEqual(result.rebuilt, ["a.md"])

        result = build_site(str(self.src), str(self.out), include_drafts=True)
        self.assertIn("d.md", result.rebuilt)
        self.assertTrue((self.out / "d.html").exists())

    def test_empty_source_directory(self):
        self.src.mkdir(parents=True, exist_ok=True)
        result = build_site(str(self.src), str(self.out))
        self.assertEqual(result.pages, [])
        self.assertTrue((self.out / "index.html").exists())

    def test_manifest_records_every_page(self):
        self.write("a.md", "# A")
        self.write("sub/b.md", "# B")
        build_site(str(self.src), str(self.out))
        manifest = load_manifest(str(self.out))
        self.assertCountEqual(manifest["pages"].keys(), ["a.md", "sub/b.md"])
        self.assertEqual(manifest["pages"]["sub/b.md"]["url"], "sub/b.html")


class RelativePathTests(unittest.TestCase):
    def test_manifest_path_is_inside_output(self):
        self.assertEqual(
            manifest_path("/tmp/site"), Path("/tmp/site") / MANIFEST_NAME
        )


if __name__ == "__main__":
    unittest.main()
