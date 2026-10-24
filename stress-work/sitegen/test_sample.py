"""Tests for :mod:`sitegen.sample`."""

import inspect
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from sitegen.frontmatter import parse_front_matter
from sitegen.sample import DEFAULT_PAGES, DEFAULT_SEED, generate_sample_site
from sitegen.site import build_site, parse_page_text


class GenerateSampleTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_default_is_300_pages(self):
        signature = inspect.signature(generate_sample_site)
        self.assertEqual(signature.parameters["pages"].default, 300)
        self.assertEqual(DEFAULT_PAGES, 300)

    def test_writes_requested_number_of_files(self):
        written = generate_sample_site(self.root / "content", pages=12)
        self.assertEqual(len(written), 12)
        self.assertTrue(all(path.exists() for path in written))

    def test_first_file_is_index(self):
        written = generate_sample_site(self.root / "content", pages=5)
        self.assertEqual(written[0].name, "index.md")

    def test_other_pages_are_grouped_in_sections(self):
        written = generate_sample_site(self.root / "content", pages=60)
        sections = {path.parent.name for path in written if path.name != "index.md"}
        self.assertTrue(any(name.startswith("section-") for name in sections))

    def test_deterministic_for_same_seed(self):
        first = generate_sample_site(self.root / "one", pages=8, seed=7)
        second = generate_sample_site(self.root / "two", pages=8, seed=7)
        for a, b in zip(first, second):
            self.assertEqual(a.read_text(encoding="utf-8"), b.read_text(encoding="utf-8"))

    def test_different_seed_differs(self):
        first = generate_sample_site(self.root / "one", pages=8, seed=1)
        second = generate_sample_site(self.root / "two", pages=8, seed=2)
        texts_a = "\n".join(p.read_text(encoding="utf-8") for p in first)
        texts_b = "\n".join(p.read_text(encoding="utf-8") for p in second)
        self.assertNotEqual(texts_a, texts_b)

    def test_front_matter_present(self):
        written = generate_sample_site(self.root / "content", pages=3)
        text = written[1].read_text(encoding="utf-8")
        page = parse_page_text(text, "section-00/page-001.md")
        self.assertIn("title", page.metadata)
        self.assertIn("weight", page.metadata)
        self.assertIn("date", page.metadata)
        self.assertTrue(page.tags)

    def test_dates_increase(self):
        written = generate_sample_site(self.root / "content", pages=3)
        dates = []
        for path in written:
            text = path.read_text(encoding="utf-8")
            meta, _ = parse_front_matter(text)
            dates.append(meta["date"])
        self.assertEqual(dates, sorted(dates))

    def test_zero_pages_raises(self):
        with self.assertRaises(ValueError):
            generate_sample_site(self.root / "content", pages=0)

    def test_creates_directory_when_missing(self):
        target = self.root / "does" / "not" / "exist"
        write_count = len(generate_sample_site(target, pages=2))
        self.assertEqual(write_count, 2)
        self.assertTrue(target.is_dir())


class SampleBuildTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_default_sample_site_builds_300_pages(self):
        generate_sample_site(self.root / "content", pages=DEFAULT_PAGES)
        result = build_site(str(self.root / "content"), str(self.root / "public"))
        self.assertEqual(len(result.pages), 300)
        self.assertTrue((self.root / "public" / "index.html").exists())

    def test_sample_site_produces_feed_with_all_but_index(self):
        generate_sample_site(self.root / "content", pages=25)
        build_site(
            str(self.root / "content"),
            str(self.root / "public"),
            base_url="https://example.test",
        )
        root = ET.fromstring(
            (self.root / "public" / "feed.xml").read_text(encoding="utf-8")
        )
        items = root.find("channel").findall("item")
        self.assertEqual(len(items), 24)
        self.assertTrue(items[0].findtext("link").startswith("https://example.test/"))

    def test_sample_site_second_build_is_noop(self):
        generate_sample_site(self.root / "content", pages=40)
        build_site(str(self.root / "content"), str(self.root / "public"))
        result = build_site(str(self.root / "content"), str(self.root / "public"))
        self.assertEqual(result.rebuilt, [])
        self.assertEqual(result.written, [])
        self.assertEqual(len(result.skipped), 40)

    def test_sample_site_one_change_rebuilds_one_page(self):
        generate_sample_site(self.root / "content", pages=20)
        build_site(str(self.root / "content"), str(self.root / "public"))

        target = self.root / "content" / "section-00" / "page-001.md"
        target.write_text(
            target.read_text(encoding="utf-8") + "\n\nAn extra paragraph.\n",
            encoding="utf-8",
        )
        result = build_site(str(self.root / "content"), str(self.root / "public"))
        self.assertEqual(result.rebuilt, ["section-00/page-001.md"])
        self.assertEqual(len(result.skipped), 19)

    def test_seed_constant(self):
        self.assertEqual(DEFAULT_SEED, 1234)


if __name__ == "__main__":
    unittest.main()
