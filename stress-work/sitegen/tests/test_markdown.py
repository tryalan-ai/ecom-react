import unittest

from sitegen.markdown import escape_html, render_inline, render_markdown


class EscapeTests(unittest.TestCase):
    def test_escapes_html_specials(self):
        self.assertEqual(
            escape_html('<a href="x">&'), "&lt;a href=&quot;x&quot;&gt;&amp;"
        )

    def test_ampersand_not_double_escaped_value(self):
        self.assertEqual(escape_html("a&b"), "a&amp;b")


class InlineTests(unittest.TestCase):
    def test_plain_text_is_preserved(self):
        self.assertEqual(render_inline("hello world"), "hello world")

    def test_bold_star(self):
        self.assertEqual(render_inline("**bold**"), "<strong>bold</strong>")

    def test_bold_underscore(self):
        self.assertEqual(render_inline("__bold__"), "<strong>bold</strong>")

    def test_italic_star(self):
        self.assertEqual(render_inline("*it*"), "<em>it</em>")

    def test_italic_underscore(self):
        self.assertEqual(render_inline("_it_"), "<em>it</em>")

    def test_snake_case_not_emphasised(self):
        self.assertEqual(render_inline("some_var_name"), "some_var_name")

    def test_inline_code(self):
        self.assertEqual(render_inline("`x = 1`"), "<code>x = 1</code>")

    def test_inline_code_escapes_html(self):
        self.assertEqual(render_inline("`<b>`"), "<code>&lt;b&gt;</code>")

    def test_link(self):
        self.assertEqual(
            render_inline("[docs](http://e.com)"),
            '<a href="http://e.com">docs</a>',
        )

    def test_link_with_title(self):
        self.assertEqual(
            render_inline('[docs](http://e.com "Home")'),
            '<a href="http://e.com" title="Home">docs</a>',
        )

    def test_link_label_supports_emphasis(self):
        self.assertEqual(
            render_inline("[**b**](u)"), '<a href="u"><strong>b</strong></a>'
        )

    def test_image(self):
        self.assertEqual(
            render_inline("![alt](img.png)"), '<img src="img.png" alt="alt" />'
        )

    def test_image_with_title(self):
        self.assertEqual(
            render_inline('![a](i.png "T")'),
            '<img src="i.png" alt="a" title="T" />',
        )

    def test_autolink(self):
        self.assertEqual(
            render_inline("<https://e.com>"),
            '<a href="https://e.com">https://e.com</a>',
        )

    def test_raw_html_is_escaped(self):
        self.assertEqual(render_inline("<script>x</script>"), "&lt;script&gt;x&lt;/script&gt;")

    def test_ampersand_in_link_url_is_escaped(self):
        self.assertEqual(
            render_inline("[q](http://e.com?a=1&b=2)"),
            '<a href="http://e.com?a=1&amp;b=2">q</a>',
        )


class LinkRewriteTests(unittest.TestCase):
    def test_md_link_rewritten_to_html(self):
        self.assertEqual(render_inline("[a](b.md)"), '<a href="b.html">a</a>')

    def test_markdown_extension_rewritten(self):
        self.assertEqual(render_inline("[a](b.markdown)"), '<a href="b.html">a</a>')

    def test_external_link_not_rewritten(self):
        self.assertEqual(
            render_inline("[a](http://e.com/b.md)"),
            '<a href="http://e.com/b.md">a</a>',
        )

    def test_anchor_not_rewritten(self):
        self.assertEqual(render_inline("[a](#sec)"), '<a href="#sec">a</a>')

    def test_nested_md_link_rewritten(self):
        self.assertEqual(
            render_inline("[a](guide/intro.md)"), '<a href="guide/intro.html">a</a>'
        )


class BlockTests(unittest.TestCase):
    def test_h1(self):
        self.assertEqual(render_markdown("# Title"), "<h1>Title</h1>")

    def test_h3(self):
        self.assertEqual(render_markdown("### Sub"), "<h3>Sub</h3>")

    def test_atx_closing_hashes_ignored(self):
        self.assertEqual(render_markdown("## Mid ##"), "<h2>Mid</h2>")

    def test_seven_hashes_is_paragraph(self):
        self.assertEqual(render_markdown("####### x"), "<p>####### x</p>")

    def test_setext_h1(self):
        self.assertEqual(render_markdown("Title\n====="), "<h1>Title</h1>")

    def test_setext_h2(self):
        self.assertEqual(render_markdown("Sub\n---"), "<h2>Sub</h2>")

    def test_paragraph_multiline_joined(self):
        self.assertEqual(render_markdown("a\nb"), "<p>a b</p>")

    def test_two_paragraphs(self):
        self.assertEqual(render_markdown("a\n\nb"), "<p>a</p>\n<p>b</p>")

    def test_horizontal_rule(self):
        self.assertEqual(render_markdown("---"), "<hr />")

    def test_horizontal_rule_stars(self):
        self.assertEqual(render_markdown("***"), "<hr />")

    def test_unordered_list(self):
        self.assertEqual(
            render_markdown("- a\n- b"), "<ul>\n<li>a</li>\n<li>b</li>\n</ul>"
        )

    def test_ordered_list(self):
        self.assertEqual(
            render_markdown("1. a\n2. b"), "<ol>\n<li>a</li>\n<li>b</li>\n</ol>"
        )

    def test_ordered_list_parenthesis(self):
        self.assertEqual(
            render_markdown("1) a\n2) b"), "<ol>\n<li>a</li>\n<li>b</li>\n</ol>"
        )

    def test_nested_unordered_list(self):
        result = render_markdown("- a\n  - b")
        self.assertIn("<li>a", result)
        self.assertIn("<ul>", result)
        self.assertIn("<li>b</li>", result)

    def test_list_item_with_inline_markup(self):
        self.assertEqual(
            render_markdown("- **x**"), "<ul>\n<li><strong>x</strong></li>\n</ul>"
        )

    def test_fenced_code_block(self):
        md = "```\nx = 1\n```"
        self.assertEqual(render_markdown(md), "<pre><code>x = 1</code></pre>")

    def test_fenced_code_block_with_language(self):
        md = '```python\nprint("hi")\n```'
        self.assertEqual(
            render_markdown(md),
            '<pre><code class="language-python">'
            "print(&quot;hi&quot;)</code></pre>",
        )

    def test_fenced_code_escapes_html(self):
        md = "```\n<b>&\n```"
        self.assertEqual(
            render_markdown(md), "<pre><code>&lt;b&gt;&amp;</code></pre>"
        )

    def test_fenced_code_preserves_blank_lines(self):
        md = "```\na\n\nb\n```"
        self.assertEqual(render_markdown(md), "<pre><code>a\n\nb</code></pre>")

    def test_indented_code_block(self):
        self.assertEqual(
            render_markdown("    code here"), "<pre><code>code here</code></pre>"
        )

    def test_blockquote(self):
        self.assertEqual(
            render_markdown("> quoted"), "<blockquote>\n<p>quoted</p>\n</blockquote>"
        )

    def test_blockquote_with_inline(self):
        self.assertEqual(
            render_markdown("> **hi**"),
            "<blockquote>\n<p><strong>hi</strong></p>\n</blockquote>",
        )

    def test_complex_document(self):
        md = (
            "---\ntitle: t\n---\n"  # front matter is not this layer's job
            "# Heading\n\n"
            "Intro with a [link](u).\n\n"
            "- one\n- two\n\n"
            "```js\nlet a = 1;\n```\n"
        )
        # render_markdown receives the body only; feed body manually
        body = "# Heading\n\nIntro with a [link](u).\n\n- one\n- two\n\n```js\nlet a = 1;\n```\n"
        html = render_markdown(body)
        self.assertIn("<h1>Heading</h1>", html)
        self.assertIn('<a href="u">link</a>', html)
        self.assertIn("<li>one</li>", html)
        self.assertIn('<code class="language-js">let a = 1;</code>', html)

    def test_crlf_normalised(self):
        self.assertEqual(render_markdown("a\r\n\r\nb"), "<p>a</p>\n<p>b</p>")


if __name__ == "__main__":
    unittest.main()
