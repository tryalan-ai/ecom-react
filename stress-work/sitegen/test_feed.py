"""Tests for :mod:`sitegen.feed` and the RSS feed produced by the builder."""

import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from sitegen.feed import (
    feed_pages,
    item_datetime,
    join_url,
    parse_date,
    render_rss,
    rfc822,
)
from sitegen.site import Page, build_site


def make_page(title, url, date=None, excerpt="", metadata=None):
    meta = dict(metadata or {})
    if date is not None:
        meta["date"] = date
    return Page(
        source=url,
        rel=url,
        url=url,
        title=title,
        metadata=meta,
        excerpt=excerpt,
    )


FIXED = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


class ParseDateTests(unittest.TestCase):
    def test_iso_date(self):
        parsed = parse_date("2024-03-04")
        self.assertEqual(parsed.year, 2024)
        self.assertEqual(parsed.month, 3)
        self.assertEqual(parsed.day, 4)

    def test_iso_datetime(self):
        self.assertEqual(parse_date("2024-03-04T05:06:07").hour, 5)

    def test_other_formats(self):
        self.assertIsNotNone(parse_date("2024/03/04"))
        self.assertIsNotNone(parse_date("4 March 2024"))
        self.assertIsNotNone(parse_date("March 4, 2024"))

    def test_datetime_passthrough(self):
        self.assertIs(parse_date(FIXED).tzinfo is not None, True)

    def test_invalid_returns_none(self):
        self.assertIsNone(parse_date("not a date"))
        self.assertIsNone(parse_date(42))


class ItemDatetimeTests(unittest.TestCase):
    def test_uses_front_matter_date(self):
        page = make_page("A", "a.html", date="2024-01-02")
        self.assertEqual(item_datetime(page, FIXED).day, 2)

    def test_falls_back_to_default(self):
        page = make_page("A", "a.html")
        self.assertEqual(item_datetime(page, FIXED), FIXED)


class Rfc822Tests(unittest.TestCase):
    def test_format(self):
        self.assertEqual(rfc822(FIXED), "Sat, 01 Jun 2024 12:00:00 +0000")

    def test_naive_datetime_treated_as_utc(self):
        self.assertTrue(rfc822(datetime(2024, 1, 1)).endswith("+0000"))


class JoinUrlTests(unittest.TestCase):
    def test_no_base_url(self):
        self.assertEqual(join_url("", "a.html"), "a.html")

    def test_with_base_url(self):
        self.assertEqual(
            join_url("https://example.com/docs", "guide/a.html"),
            "https://example.com/docs/guide/a.html",
        )

    def test_base_url_trailing_slash(self):
        self.assertEqual(
            join_url("https://example.com/", "a.html"), "https://example.com/a.html"
        )


class FeedPagesTests(unittest.TestCase):
    def test_index_excluded(self):
        pages = [make_page("Home", "index.html"), make_page("A", "a.html")]
        self.assertEqual([p.title for p in feed_pages(pages)], ["A"])

    def test_feed_false_excluded(self):
        page = make_page("Secret", "s.html", metadata={"feed": False})
        self.assertEqual(feed_pages([page]), [])


class RenderRssTests(unittest.TestCase):
    def setUp(self):
        self.pages = [
            make_page("Home", "index.html"),
            make_page("First", "first.html", date="2024-01-01", excerpt="first post"),
            make_page("Second", "second.html", date="2024-01-02"),
        ]

    def render(self, **kwargs):
        return render_rss(self.pages, "My Site", build_date=FIXED, **kwargs)

    def test_valid_xml(self):
        root = ET.fromstring(self.render())
        self.assertEqual(root.tag, "rss")
        self.assertEqual(root.get("version"), "2.0")

    def test_channel_fields(self):
        channel = ET.fromstring(self.render()).find("channel")
        self.assertEqual(channel.findtext("title"), "My Site")
        self.assertEqual(channel.findtext("link"), "index.html")
        self.assertIn("sitegen", channel.findtext("description"))
        self.assertEqual(
            channel.findtext("lastBuildDate"), "Sat, 01 Jun 2024 12:00:00 +0000"
        )

    def test_item_count_excludes_index(self):
        channel = ET.fromstring(self.render()).find("channel")
        self.assertEqual(len(channel.findall("item")), 2)

    def test_item_fields(self):
        channel = ET.fromstring(self.render()).find("channel")
        first = channel.findall("item")[0]
        self.assertEqual(first.findtext("title"), "First")
        self.assertEqual(first.findtext("link"), "first.html")
        self.assertEqual(first.findtext("guid"), "first.html")
        self.assertIn("2024", first.findtext("pubDate"))

    def test_item_description_from_excerpt(self):
        channel = ET.fromstring(self.render()).find("channel")
        first = channel.findall("item")[0]
        self.assertEqual(first.findtext("description"), "first post")

    def test_base_url_used_in_links(self):
        channel = ET.fromstring(self.render(base_url="https://x.test")).find("channel")
        self.assertEqual(channel.findtext("link"), "https://x.test/index.html")
        self.assertEqual(
            channel.findall("item")[0].findtext("link"), "https://x.test/first.html"
        )

    def test_escaping_of_special_characters(self):
        pages = [make_page("A & B <tag>", "a.html")]
        xml = render_rss(pages, "Site & Co", build_date=FIXED)
        self.assertIn("A &amp; B &lt;tag&gt;", xml)
        self.assertIn("Site &amp; Co", xml)
        ET.fromstring(xml)  # must still parse

    def test_ends_with_newline(self):
        self.assertTrue(self.render().endswith("\n"))


class FeedBuildTests(unittest.TestCase):
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

    def test_build_writes_feed(self):
        self.write("a.md", "---\ndate: 2024-02-03\n---\n# A")
        result = build_site(str(self.src), str(self.out))
        self.assertTrue((self.out / "feed.xml").exists())
        self.assertEqual(result.feed_path, str(self.out / "feed.xml"))
        self.assertIn(str(self.out / "feed.xml"), result.written)

    def test_feed_is_valid_xml_with_items(self):
        self.write("a.md", "# A\n\nalpha summary")
        self.write("b.md", "# B")
        build_site(str(self.src), str(self.out))
        root = ET.fromstring((self.out / "feed.xml").read_text(encoding="utf-8"))
        channel = root.find("channel")
        self.assertEqual(len(channel.findall("item")), 2)

    def test_no_feed_flag(self):
        self.write("a.md", "# A")
        result = build_site(str(self.src), str(self.out), feed=False)
        self.assertFalse((self.out / "feed.xml").exists())
        self.assertEqual(result.feed_path, "")

    def test_feed_skipped_when_unchanged(self):
        self.write("a.md", "# A\n\nalpha")
        build_site(str(self.src), str(self.out))
        first = (self.out / "feed.xml").read_text(encoding="utf-8")
        result = build_site(str(self.src), str(self.out))
        self.assertNotIn(str(self.out / "feed.xml"), result.written)
        self.assertEqual(
            (self.out / "feed.xml").read_text(encoding="utf-8"), first
        )

    def test_feed_rebuilt_when_a_page_changes(self):
        self.write("a.md", "# A\n\nfirst summary")
        build_site(str(self.src), str(self.out))
        self.assertIn(
            "first summary", (self.out / "feed.xml").read_text(encoding="utf-8")
        )

        self.write("a.md", "# A\n\nsecond summary")
        build_site(str(self.src), str(self.out))
        self.assertIn(
            "second summary", (self.out / "feed.xml").read_text(encoding="utf-8")
        )

    def test_feed_rewritten_when_base_url_changes(self):
        self.write("a.md", "# A")
        build_site(str(self.src), str(self.out))
        result = build_site(str(self.src), str(self.out), base_url="https://x.test")
        self.assertIn(str(self.out / "feed.xml"), result.written)
        self.assertIn(
            "https://x.test/a.html",
            (self.out / "feed.xml").read_text(encoding="utf-8"),
        )

    def test_template_links_to_feed(self):
        self.write("a.md", "# A")
        build_site(str(self.src), str(self.out))
        html = (self.out / "a.html").read_text(encoding="utf-8")
        self.assertIn('type="application/rss+xml"', html)
        self.assertIn('href="feed.xml"', html)

    def test_nested_page_links_to_feed_relatively(self):
        self.write("sub/a.md", "# A")
        build_site(str(self.src), str(self.out))
        html = (self.out / "sub" / "a.html").read_text(encoding="utf-8")
        self.assertIn('href="../feed.xml"', html)

    def test_generated_index_includes_feed_link(self):
        self.write("a.md", "# A")
        build_site(str(self.src), str(self.out))
        html = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn("feed.xml", html)


if __name__ == "__main__":
    unittest.main()
