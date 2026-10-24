import unittest

from sitegen.index import render_index
from sitegen.page import Page


def make_page(slug, title, **meta):
    return Page(source_path=slug.replace(".html", ".md"), slug=slug, title=title, metadata=meta)


class RenderIndexTests(unittest.TestCase):
    def test_lists_pages(self):
        html = render_index([make_page("a.html", "Alpha"), make_page("b.html", "Beta")])
        self.assertIn("Alpha", html)
        self.assertIn("Beta", html)

    def test_links_to_pages(self):
        html = render_index([make_page("guide/intro.html", "Intro")])
        self.assertIn('href="guide/intro.html"', html)

    def test_title_rendered(self):
        html = render_index([], title="Docs Home")
        self.assertIn("<h1>Docs Home</h1>", html)

    def test_description_rendered(self):
        page = make_page("a.html", "Alpha", description="About alpha")
        html = render_index([page])
        self.assertIn("About alpha", html)

    def test_drafts_excluded(self):
        html = render_index(
            [make_page("a.html", "Alpha"), make_page("d.html", "Draft", draft=True)]
        )
        self.assertNotIn("Draft", html)

    def test_order_respected(self):
        html = render_index(
            [
                make_page("b.html", "Beta", order=2),
                make_page("a.html", "Alpha", order=1),
            ]
        )
        self.assertLess(html.index("Alpha"), html.index("Beta"))

    def test_custom_template(self):
        html = render_index(
            [make_page("a.html", "A")],
            template="PAGES{% for p in pages %}{{ p.title }}{% endfor %}",
        )
        self.assertEqual(html, "PAGESA")

    def test_titles_escaped(self):
        html = render_index([make_page("a.html", "<script>")])
        self.assertIn("&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()
