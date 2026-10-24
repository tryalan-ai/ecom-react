"""Tests for :mod:`sitegen.blocks`."""

import unittest

from sitegen.blocks import (
    collect_headings,
    extract_title,
    parse_blocks,
    render_block,
    render_blocks,
)


def types(blocks):
    return [node["type"] for node in blocks]


class HeadingTests(unittest.TestCase):
    def test_level_and_text(self):
        (node,) = parse_blocks("# Hello")
        self.assertEqual(node["type"], "heading")
        self.assertEqual(node["level"], 1)
        self.assertEqual(node["text"], "Hello")

    def test_levels_two_through_six(self):
        for level in range(2, 7):
            (node,) = parse_blocks("#" * level + " Title")
            self.assertEqual(node["level"], level)

    def test_seven_hashes_is_paragraph(self):
        blocks = parse_blocks("####### nope")
        self.assertEqual(types(blocks), ["paragraph"])

    def test_closing_hashes_stripped(self):
        (node,) = parse_blocks("## Title ##")
        self.assertEqual(node["text"], "Title")

    def test_heading_id_slug(self):
        (node,) = parse_blocks("# Hello, World!")
        self.assertEqual(node["id"], "hello-world")

    def test_duplicate_heading_ids_are_unique(self):
        blocks = parse_blocks("# Same\n\n# Same")
        self.assertEqual(blocks[0]["id"], "same")
        self.assertEqual(blocks[1]["id"], "same-1")

    def test_hash_without_space_is_paragraph(self):
        self.assertEqual(types(parse_blocks("#nope")), ["paragraph"])

    def test_render_heading(self):
        self.assertEqual(render_blocks(parse_blocks("## Hi")),
                         '<h2 id="hi">Hi</h2>')


class ParagraphTests(unittest.TestCase):
    def test_single_paragraph(self):
        blocks = parse_blocks("one line")
        self.assertEqual(types(blocks), ["paragraph"])
        self.assertEqual(render_blocks(blocks), "<p>one line</p>")

    def test_multiline_paragraph_joined(self):
        blocks = parse_blocks("first\nsecond")
        self.assertEqual(blocks[0]["text"], "first\nsecond")

    def test_two_paragraphs_split_on_blank_line(self):
        blocks = parse_blocks("a\n\nb")
        self.assertEqual(types(blocks), ["paragraph", "paragraph"])

    def test_paragraph_with_inline_markup(self):
        blocks = parse_blocks("hello **world**")
        self.assertEqual(render_blocks(blocks), "<p>hello <strong>world</strong></p>")


class CodeBlockTests(unittest.TestCase):
    def test_fenced_code_with_language(self):
        markdown = "```python\nprint('x')\n```"
        (node,) = parse_blocks(markdown)
        self.assertEqual(node["type"], "code")
        self.assertEqual(node["lang"], "python")
        self.assertEqual(node["text"], "print('x')")

    def test_fenced_code_without_language(self):
        (node,) = parse_blocks("```\nplain\n```")
        self.assertEqual(node["lang"], "")

    def test_fenced_code_multiline(self):
        (node,) = parse_blocks("```\na\nb\n```")
        self.assertEqual(node["text"], "a\nb")

    def test_fence_markers_escaped_when_rendered(self):
        html = render_blocks(parse_blocks("```\n<tag> & done\n```"))
        self.assertIn("<pre><code>&lt;tag&gt; &amp; done</code></pre>", html)

    def test_fenced_code_language_class(self):
        html = render_blocks(parse_blocks("```js\ncode\n```"))
        self.assertIn('<code class="language-js">', html)

    def test_tilde_fence(self):
        (node,) = parse_blocks("~~~\nbody\n~~~")
        self.assertEqual(node["type"], "code")

    def test_indented_code_block(self):
        (node,) = parse_blocks("    indented\n    code")
        self.assertEqual(node["type"], "code")
        self.assertEqual(node["text"], "indented\ncode")

    def test_unclosed_fence_consumes_to_end(self):
        (node,) = parse_blocks("```\nno close")
        self.assertEqual(node["text"], "no close")


class ListTests(unittest.TestCase):
    def test_unordered_list(self):
        node = parse_blocks("- a\n- b")[0]
        self.assertEqual(node["type"], "list")
        self.assertFalse(node["ordered"])
        self.assertEqual(len(node["items"]), 2)

    def test_star_and_plus_markers(self):
        for marker in "-*+":
            node = parse_blocks("%s a\n%s b" % (marker, marker))[0]
            self.assertEqual(len(node["items"]), 2)

    def test_ordered_list_start(self):
        node = parse_blocks("3. three\n4. four")[0]
        self.assertTrue(node["ordered"])
        self.assertEqual(node["start"], 3)

    def test_ordered_paren_marker(self):
        node = parse_blocks("1) a\n2) b")[0]
        self.assertTrue(node["ordered"])

    def test_tight_list_render(self):
        html = render_blocks(parse_blocks("- a\n- b"))
        self.assertEqual(html, "<ul>\n<li>a</li>\n<li>b</li>\n</ul>")

    def test_ordered_list_render_start(self):
        html = render_blocks(parse_blocks("3. c"))
        self.assertIn('<ol start="3">', html)

    def test_nested_list_stays_in_item(self):
        node = parse_blocks("- outer\n  - inner")[0]
        outer_item = node["items"][0]
        self.assertEqual(outer_item[0]["type"], "paragraph")
        self.assertEqual(outer_item[1]["type"], "list")

    def test_loose_list_wraps_paragraphs(self):
        html = render_blocks(parse_blocks("- a\n\n- b"))
        self.assertIn("<li>\n<p>a</p>\n</li>", html)

    def test_list_item_with_inline_code(self):
        html = render_blocks(parse_blocks("- use `pip` here"))
        self.assertIn("<li>use <code>pip</code> here</li>", html)


class BlockquoteTests(unittest.TestCase):
    def test_simple_blockquote(self):
        (node,) = parse_blocks("> quoted text")
        self.assertEqual(node["type"], "blockquote")
        self.assertEqual(node["children"][0]["text"], "quoted text")

    def test_blockquote_render(self):
        html = render_blocks(parse_blocks("> hi"))
        self.assertEqual(html, "<blockquote>\n<p>hi</p>\n</blockquote>")

    def test_blockquote_multiline(self):
        node = parse_blocks("> one\n> two")[0]
        self.assertEqual(len(node["children"]), 1)
        self.assertEqual(node["children"][0]["text"], "one\ntwo")


class ThematicBreakTests(unittest.TestCase):
    def test_dashes(self):
        self.assertEqual(types(parse_blocks("---")), ["hr"])

    def test_asterisks_and_underscores(self):
        self.assertEqual(types(parse_blocks("***")), ["hr"])
        self.assertEqual(types(parse_blocks("___")), ["hr"])

    def test_render_hr(self):
        self.assertEqual(render_blocks(parse_blocks("---")), "<hr>")


class DocumentTests(unittest.TestCase):
    def test_mixed_document(self):
        markdown = (
            "# Title\n\n"
            "Intro paragraph.\n\n"
            "## Section\n\n"
            "- one\n- two\n\n"
            "```py\ncode\n```"
        )
        blocks = parse_blocks(markdown)
        self.assertEqual(
            types(blocks),
            ["heading", "paragraph", "heading", "list", "code"],
        )

    def test_collect_headings(self):
        blocks = parse_blocks("# A\n\ntext\n\n## B")
        headings = collect_headings(blocks)
        self.assertEqual([h["text"] for h in headings], ["A", "B"])
        self.assertEqual([h["level"] for h in headings], [1, 2])

    def test_extract_title(self):
        self.assertEqual(extract_title(parse_blocks("# My Page\n\ntext")), "My Page")

    def test_extract_title_none_without_heading(self):
        self.assertIsNone(extract_title(parse_blocks("just text")))

    def test_unknown_block_type_raises(self):
        with self.assertRaises(ValueError):
            render_block({"type": "nope"})


if __name__ == "__main__":
    unittest.main()
