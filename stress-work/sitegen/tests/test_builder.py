import json
import os
import tempfile
import unittest

from sitegen.builder import MANIFEST_NAME, SiteBuilder, build_site
from sitegen.feed import FEED_NAME


class BuilderTestCase(unittest.TestCase):
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

    def read_out(self, rel):
        with open(os.path.join(self.out, rel), "r", encoding="utf-8") as handle:
            return handle.read()

    def builder(self, **kwargs):
        return SiteBuilder(self.src, self.out, **kwargs)


class BasicBuildTests(BuilderTestCase):
    def test_creates_page_html(self):
        self.write("a.md", "# A\n\nHello")
        self.builder().build()
        self.assertTrue(os.path.exists(os.path.join(self.out, "a.html")))

    def test_renders_heading_and_link(self):
        self.write("a.md", "# Title\n\nSee [b](b.md).")
        self.write("b.md", "# B")
        self.builder().build()
        html = self.read_out("a.html")
        self.assertIn("<h1>Title</h1>", html)
        self.assertIn('<a href="b.html">b</a>', html)

    def test_nav_is_included(self):
        self.write("a.md", "# A")
        self.write("b.md", "# B")
        self.builder().build()
        html = self.read_out("a.html")
        self.assertIn("<nav", html)
        self.assertIn('href="b.html"', html)

    def test_front_matter_title_used(self):
        self.write("a.md", "---\ntitle: Custom\n---\nbody")
        self.builder().build()
        self.assertIn("<title>Custom", self.read_out("a.html"))

    def test_title_from_first_h1(self):
        self.write("a.md", "# Derived Heading\n\nbody")
        self.builder().build()
        self.assertIn("Derived Heading", self.read_out("a.html"))

    def test_title_from_filename_when_no_heading(self):
        self.write("my-page.md", "just body")
        self.builder().build()
        self.assertIn("My Page", self.read_out("my-page.html"))

    def test_nested_slug(self):
        self.write("guide/intro.md", "# Intro")
        self.builder().build()
        self.assertTrue(os.path.exists(os.path.join(self.out, "guide", "intro.html")))

    def test_custom_template_used(self):
        self.write("a.md", "# A")
        self.builder(template="T={{ page.title }}|{{{ content }}}").build()
        self.assertTrue(self.read_out("a.html").startswith("T=A|"))

    def test_generated_index_lists_pages(self):
        self.write("a.md", "# Alpha", )
        self.write("b.md", "# Beta")
        self.builder().build()
        html = self.read_out("index.html")
        self.assertIn("Alpha", html)
        self.assertIn("Beta", html)

    def test_source_index_is_not_overwritten(self):
        self.write("index.md", "# Home From Source\n\ncustom")
        self.write("a.md", "# A")
        self.builder().build()
        html = self.read_out("index.html")
        self.assertIn("Home From Source", html)
        self.assertNotIn("page-list", html)

    def test_assets_copied(self):
        self.write("a.md", "# A")
        self.write("style.css", "body{color:red}")
        self.builder().build()
        self.assertTrue(os.path.exists(os.path.join(self.out, "style.css")))

    def test_draft_pages_are_built_but_excluded_from_nav(self):
        self.write("a.md", "# A")
        self.write("d.md", "---\ntitle: Draft\ndraft: true\n---\n# Draft")
        self.builder().build()
        self.assertIn("Draft", self.read_out("d.html"))
        self.assertNotIn(">Draft</a>", self.read_out("a.html"))

    def test_build_site_function(self):
        self.write("a.md", "# A")
        result = build_site(self.src, self.out)
        self.assertIn("a.html", result.rendered)


class ManifestTests(BuilderTestCase):
    def test_manifest_written(self):
        self.write("a.md", "# A")
        self.builder().build()
        path = os.path.join(self.out, MANIFEST_NAME)
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertIn("pages", data)
        self.assertIn("a.md", data["pages"])

    def test_hash_recorded(self):
        self.write("a.md", "# A")
        self.builder().build()
        with open(os.path.join(self.out, MANIFEST_NAME), encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertTrue(data["pages"]["a.md"]["hash"])


class IncrementalTests(BuilderTestCase):
    def build_two(self):
        self.write("a.md", "# A")
        self.write("b.md", "# B")
        return self.builder()

    def test_first_build_is_full(self):
        result = self.build_two().build()
        self.assertTrue(result.full_rebuild)

    def test_unchanged_pages_are_skipped(self):
        builder = self.build_two()
        builder.build()
        second = builder.build()
        self.assertFalse(second.full_rebuild)
        self.assertIn("a.html", second.skipped)
        self.assertIn("b.html", second.skipped)
        self.assertEqual(second.rendered, [])

    def test_changed_page_only_rerendered(self):
        builder = self.build_two()
        builder.build()
        # Change the body without changing the title, so navigation is stable.
        self.write("a.md", "# A\n\nMore text")
        result = builder.build()
        self.assertIn("a.html", result.rendered)
        self.assertIn("b.html", result.skipped)

    def test_added_page_triggers_nav_rebuild(self):
        builder = self.build_two()
        builder.build()
        self.write("c.md", "# C")
        result = builder.build()
        self.assertTrue(result.full_rebuild)
        self.assertIn("c.html", result.rendered)
        self.assertIn('href="c.html"', self.read_out("a.html"))

    def test_deleted_page_output_removed(self):
        builder = self.build_two()
        builder.build()
        os.remove(os.path.join(self.src, "b.md"))
        result = builder.build()
        self.assertIn("b.html", result.removed)
        self.assertFalse(os.path.exists(os.path.join(self.out, "b.html")))

    def test_non_incremental_rebuilds_all(self):
        builder = self.build_two()
        builder.build()
        builder.incremental = False
        result = builder.build()
        self.assertTrue(result.full_rebuild)
        self.assertIn("a.html", result.rendered)
        self.assertIn("b.html", result.rendered)

    def test_template_change_forces_rebuild(self):
        builder = self.build_two()
        builder.build()
        builder.template_source = "X{{{ content }}}"
        result = builder.build()
        self.assertTrue(result.full_rebuild)

    def test_index_skipped_when_unchanged(self):
        builder = self.build_two()
        builder.build()
        second = builder.build()
        self.assertIn("index.html", second.skipped)

    def test_manifest_survives_across_builders(self):
        self.build_two().build()
        fresh = self.builder()
        result = fresh.build()
        self.assertFalse(result.full_rebuild)
        self.assertEqual(result.rendered, [])


class FeedBuildTests(BuilderTestCase):
    def test_feed_is_generated(self):
        self.write("a.md", "---\ntitle: A\ndate: 2024-01-02\n---\n# A")
        self.builder().build()
        self.assertTrue(os.path.exists(os.path.join(self.out, FEED_NAME)))

    def test_feed_can_be_disabled(self):
        self.write("a.md", "# A")
        self.builder(feed=False).build()
        self.assertFalse(os.path.exists(os.path.join(self.out, FEED_NAME)))

    def test_clean_removes_output(self):
        self.write("a.md", "# A")
        builder = self.builder()
        builder.build()
        builder.clean()
        self.assertFalse(os.path.exists(os.path.join(self.out, "a.html")))


if __name__ == "__main__":
    unittest.main()
