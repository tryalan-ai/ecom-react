"""Tests for :mod:`sitegen.inline`."""

import unittest

from sitegen.inline import render_inline, strip_markdown


class PlainTextTests(unittest.TestCase):
    def test_plain_text_passthrough(self):
        self.assertEqual(render_inline("hello world"), "hello world")

    def test_special_characters_escaped(self):
        self.assertEqual(render_inline("a < b & c > d"), "a &lt; b &amp; c &gt; d")

    def test_backslash_escape(self):
        self.assertEqual(render_inline(r"\*not emphasis\*"), "*not emphasis*")

    def test_backslash_before_normal_char_kept(self):
        self.assertEqual(render_inline(r"\a"), r"\a")


class CodeSpanTests(unittest.TestCase):
    def test_simple_code_span(self):
        self.assertEqual(render_inline("`code`"), "<code>code</code>")

    def test_code_span_is_escaped(self):
        self.assertEqual(render_inline("`a < b`"), "<code>a &lt; b</code>")

    def test_code_span_protects_emphasis(self):
        self.assertEqual(render_inline("`*x*`"), "<code>*x*</code>")

    def test_double_backtick_span(self):
        self.assertEqual(render_inline("``a`b``"), "<code>a`b</code>")

    def test_unmatched_backtick_is_literal(self):
        self.assertEqual(render_inline("a ` b"), "a ` b")


class EmphasisTests(unittest.TestCase):
    def test_strong_asterisks(self):
        self.assertEqual(render_inline("**bold**"), "<strong>bold</strong>")

    def test_strong_underscores(self):
        self.assertEqual(render_inline("__bold__"), "<strong>bold</strong>")

    def test_emphasis_asterisk(self):
        self.assertEqual(render_inline("*em*"), "<em>em</em>")

    def test_emphasis_underscore(self):
        self.assertEqual(render_inline("_em_"), "<em>em</em>")

    def test_intraword_underscore_not_emphasis(self):
        self.assertEqual(render_inline("snake_case_name"), "snake_case_name")

    def test_asterisks_with_spaces_are_literal(self):
        self.assertEqual(render_inline("a * b * c"), "a * b * c")

    def test_nested_strong_and_em(self):
        self.assertEqual(
            render_inline("**bold _and em_**"),
            "<strong>bold <em>and em</em></strong>",
        )

    def test_emphasis_inside_link_text(self):
        self.assertEqual(
            render_inline("[*hi*](https://x.test)"),
            '<a href="https://x.test"><em>hi</em></a>',
        )


class LinkTests(unittest.TestCase):
    def test_simple_link(self):
        self.assertEqual(
            render_inline("[Alan](https://alan.app)"),
            '<a href="https://alan.app">Alan</a>',
        )

    def test_link_with_title(self):
        self.assertEqual(
            render_inline('[x](https://a.test "Tip")'),
            '<a href="https://a.test" title="Tip">x</a>',
        )

    def test_link_angle_destination(self):
        self.assertEqual(
            render_inline("[x](<https://a.test/b c>)"),
            '<a href="https://a.test/b c">x</a>',
        )

    def test_link_url_attribute_escaped(self):
        self.assertEqual(
            render_inline('[x](https://a.test/?a=1&b=2)'),
            '<a href="https://a.test/?a=1&amp;b=2">x</a>',
        )

    def test_text_with_brackets_not_a_link(self):
        self.assertEqual(render_inline("[not a link]"), "[not a link]")

    def test_image(self):
        self.assertEqual(
            render_inline("![alt text](/img/a.png)"),
            '<img src="/img/a.png" alt="alt text">',
        )

    def test_image_with_title(self):
        self.assertEqual(
            render_inline('![a](/i.png "cap")'),
            '<img src="/i.png" alt="a" title="cap">',
        )

    def test_autolink(self):
        self.assertEqual(
            render_inline("<https://example.com>"),
            '<a href="https://example.com">https://example.com</a>',
        )

    def test_email_autolink(self):
        self.assertEqual(
            render_inline("<a@b.com>"),
            '<a href="mailto:a@b.com">a@b.com</a>',
        )


class LineBreakTests(unittest.TestCase):
    def test_soft_break_preserved(self):
        self.assertEqual(render_inline("a\nb"), "a\nb")

    def test_hard_break_two_spaces(self):
        self.assertEqual(render_inline("a  \nb"), "a<br>\nb")


class StripMarkdownTests(unittest.TestCase):
    def test_strip_emphasis_and_code(self):
        self.assertEqual(strip_markdown("**bold** and `code`"), "bold and code")

    def test_strip_link_keeps_text(self):
        self.assertEqual(strip_markdown("see [docs](/docs)"), "see docs")


if __name__ == "__main__":
    unittest.main()
