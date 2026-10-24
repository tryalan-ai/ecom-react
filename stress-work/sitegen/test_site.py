"""Tests for :mod:`sitegen.site`."""

import os
import tempfile
import unittest
from pathlib import Path

from sitegen.site import (
    Page,
    SiteError,
    build_nav,
    build_site,
    discover_sources,
    excerpt,
    load_page,
    page_url,
    render_index_body,
    render_toc,
    sort_pages,
)


def make_tree(root, files):
    for rel, content in files.items():
        path = Path(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def make_page(title, url, rel=None, blocks=None, tags=None):
    return Page(
        source=rel or url,
        rel=rel or url,
        url=url,
        title=title,
        blocks=blocks if blocks is not None else [],
        tags=tags or [],
    )


class PageUrlTests(unittest.TestCase):
    def test_markdown_to_html(self):
        self.assertEqual(page_url("index.md"), "index.html")
        self.assertEqual(page_url("guide/intro.md"), "guide/intro.html")

    def test_markdown_variant_suffix(self):
        self.assertEqual(page_url("a/b.markdown"), "a/b.html")

    def test_non_markdown_suffix(self):
        self.assertEqual(page_url("page.txt"), "page.txt.html")


class DiscoverTests(unittest.TestCase):
    def test_discovers_and_sorts(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_tree(tmp, {"b.md": "b", "a.md": "a", "sub/c.md": "c", "notes.txt": "x"})
            found = [p.name for p in discover_sources(tmp)]
            self.assertEqual(found, ["a.md", "b.md", "c.md"])

    def test_missing_directory_raises(self):
        with self.assertRaises(SiteError):
            discover_sources(os.path.join(tempfile.gettempdir(), "nope-does-not-exist"))


class LoadPageTests(unittest.TestCase):
    def test_front_matter_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.md"
            path.write_text("---\ntitle: Custom\n---\n# Heading", encoding="utf-8")
            page = load_page(path, tmp)
            self.assertEqual(page.title, "Custom")
            self.assertEqual(page.url, "p.html")

    def test_title_falls_back_to_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.md"
            path.write_text("# From Heading\n\ntext", encoding="utf-8")
            self.assertEqual(load_page(path, tmp).title, "From Heading")

    def test_title_falls_back_to_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "my-cool-page.md"
            path.write_text("no heading here", encoding="utf-8")
            self.assertEqual(load_page(path, tmp).title, "My Cool Page")

    def test_body_html_and_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.md"
            path.write_text("---\ntags: [a, b]\n---\n**bold**", encoding="utf-8")
            page = load_page(path, tmp)
            self.assertEqual(page.tags, ["a", "b"])
            self.assertEqual(page.body_html, "<p><strong>bold</strong></p>")

    def test_headings_collected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.md"
            path.write_text("# A\n\n## B", encoding="utf-8")
            self.assertEqual([h["text"] for h in load_page(path, tmp).headings], ["A", "B"])


class SortTests(unittest.TestCase):
    def test_weight_orders_pages(self):
        heavy = make_page("Heavy", "h.html")
        heavy.metadata = {"weight": 5}
        light = make_page("Light", "l.html")
        light.metadata = {"weight": 1}
        ordered = sort_pages([heavy, light])
        self.assertEqual([p.title for p in ordered], ["Light", "Heavy"])

    def test_unweighted_pages_sort_last(self):
        weighted = make_page("W", "w.html")
        weighted.metadata = {"weight": 1}
        plain = make_page("P", "p.html")
        self.assertEqual([p.title for p in sort_pages([plain, weighted])], ["W", "P"])


class ExcerptTests(unittest.TestCase):
    def test_excerpt_from_first_paragraph(self):
        from sitegen.blocks import parse_blocks

        blocks = parse_blocks("Hello **world** here\n\nsecond")
        self.assertEqual(excerpt(blocks), "Hello world here")

    def test_excerpt_truncates(self):
        from sitegen.blocks import parse_blocks

        blocks = parse_blocks("word " * 100)
        self.assertTrue(excerpt(blocks, limit=20).endswith("\u2026"))

    def test_excerpt_empty_without_paragraph(self):
        from sitegen.blocks import parse_blocks

        self.assertEqual(excerpt(parse_blocks("# Only heading")), "")


class NavTests(unittest.TestCase):
    def test_nav_contains_all_pages(self):
        pages = [make_page("A", "a.html"), make_page("B", "b.html")]
        nav = build_nav(pages, "index.html")
        self.assertIn('<a href="a.html">A</a>', nav)
        self.assertIn('<a href="b.html">B</a>', nav)
        self.assertIn("Home", nav)

    def test_nav_is_relative_from_subdirectory(self):
        pages = [make_page("A", "a.html")]
        nav = build_nav(pages, "guide/intro.html")
        self.assertIn('href="../a.html"', nav)
        self.assertIn('href="../index.html"', nav)

    def test_nav_marks_current_page(self):
        pages = [make_page("A", "a.html")]
        nav = build_nav(pages, "a.html")
        self.assertIn('<li class="active"><a href="a.html">A</a></li>', nav)

    def test_nav_can_omit_home(self):
        nav = build_nav([], "index.html", include_home=False)
        self.assertNotIn("index.html", nav)


class TocTests(unittest.TestCase):
    def test_toc_uses_h2_and_h3(self):
        headings = [
            {"level": 1, "text": "Title", "id": "title"},
            {"level": 2, "text": "Sub", "id": "sub"},
            {"level": 3, "text": "Deep", "id": "deep"},
        ]
        toc = render_toc(headings)
        self.assertIn('href="#sub"', toc)
        self.assertIn('href="#deep"', toc)
        self.assertNotIn("#title", toc)

    def test_toc_empty_without_subsections(self):
        self.assertEqual(render_toc([{"level": 1, "text": "Only", "id": "only"}]), "")


class IndexBodyTests(unittest.TestCase):
    def test_index_lists_titles_and_excerpts(self):
        from sitegen.blocks import parse_blocks

        page = make_page("A", "a.html", blocks=parse_blocks("Summary text"))
        body = render_index_body([page], "index.html")
        self.assertIn('<a href="a.html">A</a>', body)
        self.assertIn("Summary text", body)

    def test_index_links_relative_from_subdir(self):
        page = make_page("A", "a.html")
        body = render_index_body([page], "guide/index.html")
        self.assertIn('href="../a.html"', body)


class BuildSiteTests(unittest.TestCase):
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            out = Path(tmp) / "public"
            make_tree(
                str(src),
                {
                    "index.md": "---\ntitle: Home\n---\n# Welcome\n",
                    "guide/intro.md": "---\ntitle: Intro\nweight: 1\n---\n# Intro\nText\n",
                },
            )
            result = build_site(str(src), str(out), site_title="Docs")

            self.assertTrue((out / "index.html").exists())
            self.assertTrue((out / "guide" / "intro.html").exists())
            self.assertEqual(len(result.pages), 2)

            intro = (out / "guide" / "intro.html").read_text(encoding="utf-8")
            self.assertIn("<title>Intro &middot; Docs</title>", intro)
            self.assertIn("<h1 id=\"intro\">Intro</h1>", intro)
            self.assertIn('href="../index.html"', intro)
            self.assertIn('href="../style.css"', intro)

    def test_explicit_index_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            out = Path(tmp) / "public"
            make_tree(str(src), {"index.md": "---\ntitle: Custom Home\n---\n# Custom\n"})
            build_site(str(src), str(out))
            index = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn("Custom Home", index)
            self.assertIn("Custom", index)

    def test_generated_index_lists_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            out = Path(tmp) / "public"
            make_tree(str(src), {"a.md": "# Alpha\n\nfirst para", "b.md": "# Beta"})
            build_site(str(src), str(out))
            index = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn("Alpha", index)
            self.assertIn("Beta", index)

    def test_drafts_excluded_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            out = Path(tmp) / "public"
            make_tree(str(src), {"a.md": "# A", "secret.md": "---\ndraft: true\n---\n# S"})
            result = build_site(str(src), str(out))
            self.assertEqual([p.title for p in result.pages], ["A"])
            self.assertFalse((out / "secret.html").exists())

    def test_drafts_included_on_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            out = Path(tmp) / "public"
            make_tree(str(src), {"secret.md": "---\ndraft: true\n---\n# S"})
            result = build_site(str(src), str(out), include_drafts=True)
            self.assertEqual(len(result.pages), 1)
            self.assertTrue((out / "secret.html").exists())

    def test_custom_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            out = Path(tmp) / "public"
            template = Path(tmp) / "t.html"
            make_tree(str(src), {"a.md": "# A"})
            template.write_text("<main>{{{ content }}}</main>", encoding="utf-8")
            build_site(str(src), str(out), template_path=str(template))
            html = (out / "a.html").read_text(encoding="utf-8")
            self.assertEqual(html, '<main><h1 id="a">A</h1></main>')

    def test_missing_source_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SiteError):
                build_site(os.path.join(tmp, "missing"), os.path.join(tmp, "out"))

    def test_missing_template_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            make_tree(str(src), {"a.md": "# A"})
            with self.assertRaises(SiteError):
                build_site(str(src), os.path.join(tmp, "out"), template_path=os.path.join(tmp, "no.html"))

    def test_result_written_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            out = Path(tmp) / "public"
            make_tree(str(src), {"a.md": "# A"})
            result = build_site(str(src), str(out))
            self.assertIn(str(out / "a.html"), result.written)
            self.assertIn(str(out / "index.html"), result.written)
            self.assertEqual(result.index_path, str(out / "index.html"))

    def test_nav_ordering_follows_weight(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            out = Path(tmp) / "public"
            make_tree(
                str(src),
                {
                    "z.md": "---\ntitle: First\nweight: 1\n---\n# First",
                    "a.md": "---\ntitle: Second\nweight: 2\n---\n# Second",
                },
            )
            result = build_site(str(src), str(out))
            self.assertEqual([p.title for p in result.pages], ["First", "Second"])


if __name__ == "__main__":
    unittest.main()
