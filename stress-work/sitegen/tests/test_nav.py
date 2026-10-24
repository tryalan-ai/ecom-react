import unittest

from sitegen.nav import relative_url, render_nav, sort_pages
from sitegen.page import Page


def make_page(slug, title, **meta):
    return Page(source_path=slug.replace(".html", ".md"), slug=slug, title=title, metadata=meta)


class RelativeUrlTests(unittest.TestCase):
    def test_same_directory(self):
        self.assertEqual(relative_url("a.html", "b.html"), "b.html")

    def test_from_root_into_subdir(self):
        self.assertEqual(relative_url("index.html", "guide/intro.html"), "guide/intro.html")

    def test_from_subdir_to_root(self):
        self.assertEqual(relative_url("guide/intro.html", "index.html"), "../index.html")

    def test_sibling_subdirs(self):
        self.assertEqual(relative_url("a/x.html", "b/y.html"), "../b/y.html")

    def test_same_page(self):
        self.assertEqual(relative_url("a/x.html", "a/x.html"), "x.html")


class SortPagesTests(unittest.TestCase):
    def test_order_then_title(self):
        pages = [
            make_page("b.html", "Beta", order=2),
            make_page("a.html", "Alpha", order=1),
            make_page("c.html", "Gamma", order=2),
        ]
        titles = [p.title for p in sort_pages(pages)]
        self.assertEqual(titles, ["Alpha", "Beta", "Gamma"])

    def test_missing_order_sorts_last(self):
        pages = [make_page("n.html", "NoOrder"), make_page("o.html", "Order", order=1)]
        self.assertEqual([p.title for p in sort_pages(pages)], ["Order", "NoOrder"])


class RenderNavTests(unittest.TestCase):
    def test_basic_structure(self):
        html = render_nav([make_page("a.html", "A")])
        self.assertIn('<nav class="nav">', html)
        self.assertIn('<a href="a.html">A</a>', html)
        self.assertIn("</nav>", html)

    def test_active_page_marked(self):
        html = render_nav(
            [make_page("a.html", "A"), make_page("b.html", "B")], current_slug="a.html"
        )
        self.assertIn('<li class="active"><a href="a.html">A</a></li>', html)

    def test_relative_href_from_subdir(self):
        pages = [make_page("index.html", "Home"), make_page("guide/x.html", "X")]
        html = render_nav(pages, current_slug="guide/x.html")
        self.assertIn('href="../index.html"', html)

    def test_pages_with_nav_false_excluded(self):
        pages = [make_page("a.html", "A"), make_page("b.html", "B", nav=False)]
        html = render_nav(pages)
        self.assertIn("A</a>", html)
        self.assertNotIn("B</a>", html)

    def test_drafts_excluded(self):
        pages = [make_page("a.html", "A"), make_page("d.html", "D", draft=True)]
        html = render_nav(pages)
        self.assertNotIn("D</a>", html)

    def test_titles_are_escaped(self):
        html = render_nav([make_page("a.html", "<b>Evil</b>")])
        self.assertIn("&lt;b&gt;Evil&lt;/b&gt;", html)

    def test_empty_nav(self):
        html = render_nav([])
        self.assertIn("<nav", html)
        self.assertIn("</nav>", html)


if __name__ == "__main__":
    unittest.main()
