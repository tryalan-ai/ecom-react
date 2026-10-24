"""A tiny, dependency-free template engine.

Supports just enough for a static site:

* ``{{ name }}`` — insert an escaped value
* ``{{{ name }}}`` — insert a raw (pre-rendered HTML) value
* ``{{ page.title }}`` — dotted lookups into dicts, lists and objects
* ``{% if name %} ... {% else %} ... {% endif %}``
* ``{% for item in items %} ... {% endfor %}``

Escaping is on by default, so template authors have to opt in to injecting
HTML with the triple-brace form.
"""

from __future__ import annotations

import re

from .htmlutil import escape_text

_TOKEN_RE = re.compile(r"(\{\{\{.*?\}\}\}|\{\{.*?\}\}|\{%.*?%\})", re.S)
_FOR_RE = re.compile(r"^(\w+)\s+in\s+(.+)$")


class TemplateError(ValueError):
    """Raised for malformed templates."""


def render_template(source, context=None):
    """Render *source* with *context* and return the resulting string."""
    return Template(source).render(context or {})


class Template:
    def __init__(self, source):
        self.source = source
        self.nodes = _parse_block(_tokenize(source), 0, ())[0]

    def render(self, context=None):
        return _render_nodes(self.nodes, context or {})

    # Convenience so a Template can be used where a string is expected.
    def __str__(self):  # pragma: no cover - trivial
        return self.source


# ---------------------------------------------------------------------------
# Tokenising and parsing
# ---------------------------------------------------------------------------
def _tokenize(source):
    tokens = []
    for part in _TOKEN_RE.split(source):
        if part == "":
            continue
        if part.startswith("{{{"):
            tokens.append(("var", part[3:-3].strip(), True))
        elif part.startswith("{{"):
            tokens.append(("var", part[2:-2].strip(), False))
        elif part.startswith("{%"):
            tokens.append(("tag", part[2:-2].strip()))
        else:
            tokens.append(("text", part))
    return tokens


def _parse_block(tokens, index, stop_tags):
    nodes = []
    while index < len(tokens):
        token = tokens[index]
        if token[0] == "text":
            nodes.append({"type": "text", "value": token[1]})
            index += 1
            continue
        if token[0] == "var":
            nodes.append({"type": "var", "expr": token[1], "raw": token[2]})
            index += 1
            continue

        tag = token[1].strip()
        name = tag.split(None, 1)[0] if tag else ""
        if name in stop_tags:
            return nodes, index

        if name == "if":
            condition = tag[2:].strip()
            body, index = _parse_block(tokens, index + 1, ("else", "endif"))
            alt = []
            if index < len(tokens) and tokens[index][1].strip().split(None, 1)[0] == "else":
                alt, index = _parse_block(tokens, index + 1, ("endif",))
            if index >= len(tokens):
                raise TemplateError("unclosed {% if %}")
            nodes.append({"type": "if", "cond": condition, "body": body, "alt": alt})
            index += 1
            continue

        if name == "for":
            match = _FOR_RE.match(tag[3:].strip())
            if not match:
                raise TemplateError("malformed for tag: {% " + tag + " %}")
            body, index = _parse_block(tokens, index + 1, ("endfor",))
            if index >= len(tokens):
                raise TemplateError("unclosed {% for %}")
            nodes.append(
                {
                    "type": "for",
                    "var": match.group(1),
                    "iter": match.group(2).strip(),
                    "body": body,
                }
            )
            index += 1
            continue

        raise TemplateError("unknown tag: {% " + tag + " %}")

    if stop_tags:
        raise TemplateError("missing closing tag, expected one of %r" % (stop_tags,))
    return nodes, index


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def _render_nodes(nodes, context):
    parts = []
    for node in nodes:
        kind = node["type"]
        if kind == "text":
            parts.append(node["value"])
        elif kind == "var":
            value = _lookup(node["expr"], context)
            text = "" if value is None else _stringify(value)
            parts.append(text if node["raw"] else escape_text(text))
        elif kind == "if":
            branch = node["body"] if _truthy(_lookup(node["cond"], context)) else node["alt"]
            parts.append(_render_nodes(branch, context))
        elif kind == "for":
            items = _lookup(node["iter"], context) or []
            for item in items:
                scope = dict(context)
                scope[node["var"]] = item
                parts.append(_render_nodes(node["body"], scope))
    return "".join(parts)


def _lookup(expr, context):
    expr = expr.strip()
    if expr == "":
        return None
    if len(expr) >= 2 and expr[0] == expr[-1] and expr[0] in "\"'":
        return expr[1:-1]
    if expr == "true":
        return True
    if expr == "false":
        return False

    parts = expr.split(".")
    if parts[0] not in context:
        return None
    value = context[parts[0]]
    for part in parts[1:]:
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, (list, tuple)) and part.lstrip("-").isdigit():
            position = int(part)
            value = value[position] if -len(value) <= position < len(value) else None
        else:
            value = getattr(value, part, None)
        if value is None:
            return None
    return value


def _truthy(value):
    if value is None or value is False:
        return False
    if isinstance(value, (str, list, tuple, dict, set)) and len(value) == 0:
        return False
    return True


def _stringify(value):
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)
