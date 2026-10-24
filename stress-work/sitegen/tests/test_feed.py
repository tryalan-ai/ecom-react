import os
import tempfile
import unittest
from datetime import datetime, timezone

from sitegen.feed import parse_date, render_rss
from sitegen.page import Page


def make_page(slug, title, date=None, description="", **meta):
    if date is not None:
        meta["date"] = date
    if description:
        meta["description"] = description
    return Page(source_path=slug.replace(".html", ".md"), slug=slug, title=title, metadata=meta)


class ParseDateTests(unittest.TestCase):
    def test_iso_date(self):
        self.assertEqual(
            parse_date("2024-01-02"), datetime(2024, 1, 2, tzinfo=timezone.utc)
        )

    def test_iso_datetime(self):
        self.assertEqual(
            parse_date("2024-01-02T03:04:05"),
            datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        )

    def test_invalid_returns_none(self):
        self.assertIsNone(parse_date("not a date"))

    def test_none_returns_none(self):
        self.assertIsNone(parse_date(None))

    def test_empty_returns_none(self):
        self.assertIsNone(parse_date(""))


class RenderRssTests(unittest.TestCase):
    def test_well_formed_header(self):
        xml = render_rss([make_page("a.html", "A")], "My Site", site_url="http://e.com")
        self.assertTrue(xml.startswith('<?xml version="1.0" encoding="UTF-8"?>'))
        self.assertIn('<rss version="2.0">', xml)
        self.assertIn("<channel>", xml)
        self.assertIn("</channel>", xml)
        self.assertTrue(xml.rstrip().endswith("</rss>"))

    def test_channel_metadata(self):
        xml = render_rss([], "Docs", site_url="http://e.com", description="A site")
        self.assertIn("<title>Docs</title>", xml)
        self.assertIn("<link>http://e.com/index.html</link>", xml)
        self.assertIn("<description>A site</description>", xml)

    def test_items_include_title_and_link(self):
        page = make_page("guide/intro.html", "Intro")
        xml = render_rss([page], "S", site_url="http://e.com")
        self.assertIn("<title>Intro</title>", xml)
        self.assertIn("<link>http://e.com/guide/intro.html</link>", xml)

    def test_relative_link_without_site_url(self):
        xml = render_rss([make_page("a.html", "A")], "S")
        self.assertIn("<link>a.html</link>", xml)

    def test_newest_first_ordering(self):
        old = make_page("old.html", "Old", date="2024-01-01")
        new = make_page("new.html", "New", date="2024-06-01")
        xml = render_rss([old, new], "S")
        self.assertLess(xml.index(">New<"), xml.index(">Old<"))

    def test_limit_applied(self):
        pages = [make_page("p%d.html" % i, "P%d" % i, date="2024-01-%02d" % (i + 1)) for i in range(5)]
        xml = render_rss(pages, "S", limit=2)
        self.assertEqual(xml.count("<item>"), 2)

    def test_pubdate_present(self):
        xml = render_rss([make_page("a.html", "A", date="2024-01-02")], "S")
        self.assertIn("<pubDate>", xml)
        self.assertIn("02 Jan 2024", xml)

    def test_last_build_date_uses_newest_page(self):
        pages = [
            make_page("a.html", "A", date="2024-01-01"),
            make_page("b.html", "B", date="2024-02-01"),
        ]
        xml = render_rss(pages, "S")
        self.assertIn("<lastBuildDate>", xml)
        self.assertIn("01 Feb 2024", xml)

    def test_drafts_excluded(self):
        pages = [make_page("a.html", "A"), make_page("d.html", "HiddenDraft", draft=True)]
        xml = render_rss(pages, "S")
        self.assertNotIn("HiddenDraft", xml)

    def test_title_escaped(self):
        xml = render_rss([make_page("a.html", "A & B <c>")], "S")
        self.assertIn("A &amp; B &lt;c&gt;", xml)

    def test_description_escaped(self):
        xml = render_rss([make_page("a.html", "A", description="x & y")], "S")
        self.assertIn("<description>x &amp; y</description>", xml)

    def test_guid_present(self):
        xml = render_rss([make_page("a.html", "A")], "S", site_url="http://e.com")
        self.assertIn('<guid isPermaLink="false">http://e.com/a.html</guid>', xml)

    def test_deterministic(self):
        pages = [make_page("a.html", "A", date="2024-01-01")]
        self.assertEqual(render_rss(pages, "S"), render_rss(pages, "S"))


class FeedIntegrationTests(unittest.TestCase):
    def test_sample_feed_written(self):
        from sitegen.sample import generate_sample_site
        from sitegen.builder import SiteBuilder

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        src = os.path.join(tmp.name, "src")
        out = os.path.join(tmp.name, "out")
        generate_sample_site(src, count=5)
        SiteBuilder(src, out, site_title="Sample", site_url="http://e.com").build()
        with open(os.path.join(out, "feed.xml"), encoding="utf-8") as handle:
            xml = handle.read()
        self.assertIn("<rss", xml)
        self.assertIn("<item>", xml)
        self.assertIn("http://e.com/", xml)


if __name__ == "__main__":
    unittest.main()
