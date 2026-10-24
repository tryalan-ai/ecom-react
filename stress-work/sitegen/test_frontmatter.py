"""Tests for :mod:`sitegen.frontmatter`."""

import unittest

from sitegen.frontmatter import (
    parse_front_matter,
    parse_metadata,
    parse_value,
    split_list,
)


class ParseValueTests(unittest.TestCase):
    def test_empty_value_is_empty_string(self):
        self.assertEqual(parse_value("   "), "")

    def test_plain_string(self):
        self.assertEqual(parse_value("Getting Started"), "Getting Started")

    def test_quoted_string_strips_quotes(self):
        self.assertEqual(parse_value('"quoted value"'), "quoted value")

    def test_single_quoted_string(self):
        self.assertEqual(parse_value("'single'"), "single")

    def test_integer(self):
        self.assertEqual(parse_value("42"), 42)
        self.assertEqual(parse_value("-7"), -7)

    def test_booleans(self):
        self.assertIs(parse_value("true"), True)
        self.assertIs(parse_value("False"), False)

    def test_bracketed_list(self):
        self.assertEqual(parse_value("[a, b, c]"), ["a", "b", "c"])

    def test_empty_list(self):
        self.assertEqual(parse_value("[]"), [])

    def test_list_keeps_quoted_commas(self):
        self.assertEqual(parse_value('["a,b", c]'), ["a,b", "c"])

    def test_numbers_stay_strings_inside_lists(self):
        self.assertEqual(parse_value("[1, 2]"), [1, 2])


class ParseMetadataTests(unittest.TestCase):
    def test_simple_pairs(self):
        meta = parse_metadata("title: Home\nweight: 3")
        self.assertEqual(meta, {"title": "Home", "weight": 3})

    def test_comments_and_blanks_ignored(self):
        meta = parse_metadata("# a comment\n\nname: x")
        self.assertEqual(meta, {"name": "x"})

    def test_line_without_colon_ignored(self):
        self.assertEqual(parse_metadata("just a line"), {})

    def test_value_containing_colon(self):
        meta = parse_metadata("url: https://example.com/a")
        self.assertEqual(meta["url"], "https://example.com/a")


class ParseFrontMatterTests(unittest.TestCase):
    def test_no_front_matter(self):
        meta, body = parse_front_matter("# Title\n\ntext")
        self.assertEqual(meta, {})
        self.assertEqual(body, "# Title\n\ntext")

    def test_basic_front_matter(self):
        text = "---\ntitle: Hello\nweight: 1\n---\nBody here"
        meta, body = parse_front_matter(text)
        self.assertEqual(meta["title"], "Hello")
        self.assertEqual(meta["weight"], 1)
        self.assertEqual(body, "Body here")

    def test_body_preserves_leading_blank_line(self):
        text = "---\ntitle: x\n---\n\n# Heading\n"
        meta, body = parse_front_matter(text)
        self.assertEqual(body, "\n# Heading\n")

    def test_unterminated_front_matter_is_treated_as_body(self):
        text = "---\ntitle: x\nno close"
        meta, body = parse_front_matter(text)
        self.assertEqual(meta, {})
        self.assertEqual(body, text)

    def test_empty_front_matter(self):
        meta, body = parse_front_matter("---\n---\nhello")
        self.assertEqual(meta, {})
        self.assertEqual(body, "hello")

    def test_front_matter_must_be_first_line(self):
        text = "\n---\ntitle: x\n---\nbody"
        meta, body = parse_front_matter(text)
        self.assertEqual(meta, {})
        self.assertEqual(body, text)


class SplitListTests(unittest.TestCase):
    def test_list_passthrough(self):
        self.assertEqual(split_list(["a", "b"]), ["a", "b"])

    def test_csv_string(self):
        self.assertEqual(split_list("a, b ,c"), ["a", "b", "c"])

    def test_single_string(self):
        self.assertEqual(split_list("solo"), ["solo"])

    def test_none(self):
        self.assertEqual(split_list(None), [])


if __name__ == "__main__":
    unittest.main()
