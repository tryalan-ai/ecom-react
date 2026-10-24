import unittest

from sitegen.frontmatter import parse_front_matter, parse_value


class ParseValueTests(unittest.TestCase):
    def test_plain_string(self):
        self.assertEqual(parse_value("hello world"), "hello world")

    def test_double_quoted_string(self):
        self.assertEqual(parse_value('"hello world"'), "hello world")

    def test_single_quoted_string(self):
        self.assertEqual(parse_value("'hi'"), "hi")

    def test_integer(self):
        self.assertEqual(parse_value("42"), 42)

    def test_negative_integer(self):
        self.assertEqual(parse_value("-7"), -7)

    def test_float(self):
        self.assertEqual(parse_value("3.5"), 3.5)

    def test_booleans(self):
        self.assertIs(parse_value("true"), True)
        self.assertIs(parse_value("false"), False)

    def test_null(self):
        self.assertIsNone(parse_value("null"))
        self.assertIsNone(parse_value("~"))

    def test_inline_list_of_strings(self):
        self.assertEqual(parse_value("[a, b, c]"), ["a", "b", "c"])

    def test_inline_list_mixed_types(self):
        self.assertEqual(parse_value("[1, true, x]"), [1, True, "x"])

    def test_empty_inline_list(self):
        self.assertEqual(parse_value("[]"), [])

    def test_quoted_list_items_keep_commas(self):
        self.assertEqual(parse_value('["a,b", c]'), ["a,b", "c"])

    def test_date_like_value_stays_string(self):
        self.assertEqual(parse_value("2024-01-31"), "2024-01-31")


class ParseFrontMatterTests(unittest.TestCase):
    def test_no_front_matter(self):
        meta, body = parse_front_matter("# Title\n\nBody")
        self.assertEqual(meta, {})
        self.assertEqual(body, "# Title\n\nBody")

    def test_basic_front_matter(self):
        text = "---\ntitle: Hello\norder: 2\n---\n# Body"
        meta, body = parse_front_matter(text)
        self.assertEqual(meta, {"title": "Hello", "order": 2})
        self.assertEqual(body, "# Body")

    def test_body_preserves_blank_lines(self):
        text = "---\ntitle: T\n---\n\nline1\n\nline2"
        _, body = parse_front_matter(text)
        self.assertEqual(body, "\nline1\n\nline2")

    def test_front_matter_with_list_and_bool(self):
        text = "---\ntags: [a, b]\ndraft: false\n---\nbody"
        meta, _ = parse_front_matter(text)
        self.assertEqual(meta["tags"], ["a", "b"])
        self.assertIs(meta["draft"], False)

    def test_unterminated_front_matter_is_body(self):
        text = "---\ntitle: Broken\n# no closing fence"
        meta, body = parse_front_matter(text)
        self.assertEqual(meta, {})
        self.assertEqual(body, text)

    def test_bom_is_stripped(self):
        text = "\ufeff---\ntitle: T\n---\nbody"
        meta, body = parse_front_matter(text)
        self.assertEqual(meta, {"title": "T"})
        self.assertEqual(body, "body")

    def test_comment_lines_are_ignored(self):
        text = "---\n# a comment\ntitle: T\n---\nbody"
        meta, _ = parse_front_matter(text)
        self.assertEqual(meta, {"title": "T"})

    def test_empty_front_matter(self):
        meta, body = parse_front_matter("---\n---\nbody")
        self.assertEqual(meta, {})
        self.assertEqual(body, "body")

    def test_colon_inside_value(self):
        text = "---\nurl: http://example.com/x\n---\nbody"
        meta, _ = parse_front_matter(text)
        self.assertEqual(meta["url"], "http://example.com/x")


if __name__ == "__main__":
    unittest.main()
