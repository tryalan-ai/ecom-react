"""Tests for :mod:`sitegen.template`."""

import unittest

from sitegen.template import Template, TemplateError, render_template


class BasicTests(unittest.TestCase):
    def test_plain_text(self):
        self.assertEqual(render_template("hello"), "hello")

    def test_simple_substitution(self):
        self.assertEqual(render_template("Hi {{ name }}!", {"name": "Ada"}), "Hi Ada!")

    def test_missing_variable_is_empty(self):
        self.assertEqual(render_template("[{{ nope }}]", {}), "[]")

    def test_values_are_escaped_by_default(self):
        self.assertEqual(
            render_template("{{ x }}", {"x": "<b>"}),
            "&lt;b&gt;",
        )

    def test_raw_triple_braces(self):
        self.assertEqual(
            render_template("{{{ html }}}", {"html": "<b>bold</b>"}),
            "<b>bold</b>",
        )

    def test_whitespace_inside_braces(self):
        self.assertEqual(render_template("{{  x  }}", {"x": "y"}), "y")

    def test_numbers_and_booleans_stringified(self):
        self.assertEqual(render_template("{{ n }}/{{ b }}", {"n": 3, "b": True}), "3/true")


class DottedLookupTests(unittest.TestCase):
    def test_nested_dict(self):
        self.assertEqual(
            render_template("{{ page.title }}", {"page": {"title": "Home"}}),
            "Home",
        )

    def test_list_index(self):
        self.assertEqual(
            render_template("{{ items.1 }}", {"items": ["a", "b", "c"]}),
            "b",
        )

    def test_missing_nested_key(self):
        self.assertEqual(render_template("{{ a.b.c }}", {"a": {}}), "")

    def test_attribute_lookup_on_object(self):
        class Obj:
            name = "obj"

        self.assertEqual(render_template("{{ o.name }}", {"o": Obj()}), "obj")


class IfTests(unittest.TestCase):
    def test_true_branch(self):
        self.assertEqual(
            render_template("{% if x %}yes{% endif %}", {"x": 1}), "yes"
        )

    def test_false_branch_empty(self):
        self.assertEqual(
            render_template("{% if x %}yes{% endif %}", {"x": ""}), ""
        )

    def test_else_branch(self):
        self.assertEqual(
            render_template("{% if x %}a{% else %}b{% endif %}", {}), "b"
        )

    def test_truthy_empty_list_is_false(self):
        self.assertEqual(
            render_template("{% if xs %}some{% else %}none{% endif %}", {"xs": []}),
            "none",
        )

    def test_nested_if(self):
        template = "{% if a %}A{% if b %}B{% endif %}{% endif %}"
        self.assertEqual(render_template(template, {"a": 1, "b": 1}), "AB")

    def test_unclosed_if_raises(self):
        with self.assertRaises(TemplateError):
            render_template("{% if x %}yes", {"x": 1})


class ForTests(unittest.TestCase):
    def test_loop_over_list_of_strings(self):
        self.assertEqual(
            render_template("{% for x in xs %}{{ x }},{% endfor %}", {"xs": ["a", "b"]}),
            "a,b,",
        )

    def test_loop_over_dicts(self):
        template = "{% for p in pages %}<a>{{ p.title }}</a>{% endfor %}"
        result = render_template(
            template, {"pages": [{"title": "A"}, {"title": "B"}]}
        )
        self.assertEqual(result, "<a>A</a><a>B</a>")

    def test_empty_loop(self):
        self.assertEqual(
            render_template("{% for x in xs %}{{ x }}{% endfor %}", {"xs": []}),
            "",
        )

    def test_loop_variable_does_not_leak(self):
        template = "{% for x in xs %}{{ x }}{% endfor %}{{ x }}"
        self.assertEqual(render_template(template, {"xs": ["a"], "x": "keep"}), "akeep")

    def test_malformed_for_raises(self):
        with self.assertRaises(TemplateError):
            render_template("{% for xs %}x{% endfor %}", {})

    def test_unknown_tag_raises(self):
        with self.assertRaises(TemplateError):
            render_template("{% bogus %}", {})


class TemplateClassTests(unittest.TestCase):
    def test_reusable_template(self):
        template = Template("Hi {{ who }}")
        self.assertEqual(template.render({"who": "A"}), "Hi A")
        self.assertEqual(template.render({"who": "B"}), "Hi B")

    def test_default_context_is_empty(self):
        self.assertEqual(Template("x{{ missing }}").render(), "x")


if __name__ == "__main__":
    unittest.main()
