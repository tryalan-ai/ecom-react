import unittest

from sitegen.template import Template


class VariableTests(unittest.TestCase):
    def test_plain_text_passthrough(self):
        self.assertEqual(Template("hello").render({}), "hello")

    def test_variable_substitution(self):
        self.assertEqual(Template("Hi {{ name }}!").render({"name": "Al"}), "Hi Al!")

    def test_missing_variable_is_empty(self):
        self.assertEqual(Template("[{{ nope }}]").render({}), "[]")

    def test_variable_is_html_escaped(self):
        self.assertEqual(
            Template("{{ x }}").render({"x": "<b>&"}), "&lt;b&gt;&amp;"
        )

    def test_raw_variable_not_escaped(self):
        self.assertEqual(
            Template("{{{ x }}}").render({"x": "<b>ok</b>"}), "<b>ok</b>"
        )

    def test_dotted_path_resolution(self):
        tmpl = Template("{{ site.title }}")
        self.assertEqual(tmpl.render({"site": {"title": "Docs"}}), "Docs")

    def test_whitespace_inside_braces(self):
        self.assertEqual(Template("{{name}}").render({"name": "x"}), "x")

    def test_integer_value(self):
        self.assertEqual(Template("{{ n }}").render({"n": 3}), "3")


class ConditionalTests(unittest.TestCase):
    def test_if_true(self):
        tmpl = Template("{% if show %}yes{% endif %}")
        self.assertEqual(tmpl.render({"show": True}), "yes")

    def test_if_false(self):
        tmpl = Template("{% if show %}yes{% endif %}")
        self.assertEqual(tmpl.render({"show": False}), "")

    def test_if_missing_is_false(self):
        tmpl = Template("{% if show %}yes{% endif %}")
        self.assertEqual(tmpl.render({}), "")

    def test_if_else(self):
        tmpl = Template("{% if show %}yes{% else %}no{% endif %}")
        self.assertEqual(tmpl.render({"show": False}), "no")

    def test_if_with_dotted_path(self):
        tmpl = Template("{% if page.draft %}D{% endif %}")
        self.assertEqual(tmpl.render({"page": {"draft": True}}), "D")


class LoopTests(unittest.TestCase):
    def test_for_loop(self):
        tmpl = Template("{% for x in items %}{{ x }},{% endfor %}")
        self.assertEqual(tmpl.render({"items": ["a", "b"]}), "a,b,")

    def test_for_loop_empty(self):
        tmpl = Template("{% for x in items %}{{ x }}{% endfor %}")
        self.assertEqual(tmpl.render({"items": []}), "")

    def test_loop_metadata(self):
        tmpl = Template("{% for x in items %}{{ loop.index }}:{{ x }} {% endfor %}")
        self.assertEqual(tmpl.render({"items": ["a", "b"]}), "1:a 2:b ")

    def test_loop_first_last(self):
        tmpl = Template(
            "{% for x in items %}{% if loop.first %}[{% endif %}{{ x }}"
            "{% if loop.last %}]{% endif %}{% endfor %}"
        )
        self.assertEqual(tmpl.render({"items": ["a", "b"]}), "[ab]")

    def test_nested_loops(self):
        tmpl = Template(
            "{% for row in rows %}{% for c in row %}{{ c }}{% endfor %};{% endfor %}"
        )
        self.assertEqual(
            tmpl.render({"rows": [["a", "b"], ["c"]]}), "ab;c;"
        )

    def test_for_over_dict_items_attribute(self):
        tmpl = Template("{% for p in pages %}{{ p.title }} {% endfor %}")
        ctx = {"pages": [{"title": "A"}, {"title": "B"}]}
        self.assertEqual(tmpl.render(ctx), "A B ")

    def test_unknown_tag_is_ignored(self):
        self.assertEqual(Template("a{% frobnicate %}b").render({}), "ab")


if __name__ == "__main__":
    unittest.main()
