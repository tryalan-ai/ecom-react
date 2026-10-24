import os
import tempfile
import unittest

from sitegen.frontmatter import parse_front_matter
from sitegen.sample import DEFAULT_COUNT, SAMPLE_SECTIONS, generate_sample_site


class SampleGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = os.path.join(self.tmp.name, "sample")

    def test_default_count_constant(self):
        self.assertEqual(DEFAULT_COUNT, 300)

    def test_generates_300_by_default(self):
        created = generate_sample_site(self.target)
        self.assertEqual(len(created), 300)
        md = [p for p in created if p.endswith(".md")]
        self.assertEqual(len(md), 300)

    def test_generates_requested_count(self):
        created = generate_sample_site(self.target, count=12)
        self.assertEqual(len(created), 12)

    def test_index_is_first_page(self):
        created = generate_sample_site(self.target, count=5)
        self.assertIn("index.md", created)

    def test_zero_count_creates_nothing(self):
        created = generate_sample_site(self.target, count=0)
        self.assertEqual(created, [])

    def test_deterministic_output(self):
        first = os.path.join(self.tmp.name, "a")
        second = os.path.join(self.tmp.name, "b")
        generate_sample_site(first, count=10, seed=42)
        generate_sample_site(second, count=10, seed=42)
        for rel in ("index.md", "guides/page-001.md"):
            with open(os.path.join(first, rel), encoding="utf-8") as fh:
                one = fh.read()
            with open(os.path.join(second, rel), encoding="utf-8") as fh:
                two = fh.read()
            self.assertEqual(one, two)

    def test_different_seed_differs(self):
        first = os.path.join(self.tmp.name, "a")
        second = os.path.join(self.tmp.name, "b")
        generate_sample_site(first, count=6, seed=1)
        generate_sample_site(second, count=6, seed=2)
        with open(os.path.join(first, "guides/page-001.md"), encoding="utf-8") as fh:
            one = fh.read()
        with open(os.path.join(second, "guides/page-001.md"), encoding="utf-8") as fh:
            two = fh.read()
        self.assertNotEqual(one, two)

    def test_front_matter_has_date_and_title(self):
        generate_sample_site(self.target, count=3)
        with open(os.path.join(self.target, "guides/page-001.md"), encoding="utf-8") as fh:
            meta, body = parse_front_matter(fh.read())
        self.assertIn("title", meta)
        self.assertIn("date", meta)
        self.assertTrue(body.strip().startswith("#"))

    def test_sections_used(self):
        created = generate_sample_site(self.target, count=60)
        for section in SAMPLE_SECTIONS:
            self.assertTrue(
                any(p.startswith(section + "/") for p in created),
                "section %s missing" % section,
            )

    def test_body_contains_markdown_features(self):
        generate_sample_site(self.target, count=3)
        with open(os.path.join(self.target, "guides/page-001.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("## Highlights", text)
        self.assertIn("- Point 1", text)
        self.assertIn("```python", text)
        self.assertIn("](../index.md)", text)


if __name__ == "__main__":
    unittest.main()
