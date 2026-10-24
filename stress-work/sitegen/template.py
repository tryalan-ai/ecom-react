"""A tiny, dependency-free template engine.

Supports variable interpolation, raw interpolation, conditionals and loops:

* ``{{ name }}``   - HTML-escaped interpolation (dotted paths allowed)
* ``{{{ name }}}`` - raw, unescaped interpolation
* ``{% if name %} ... {% else %} ... {% endif %}``
* ``{% for item in items %} ... {% endfor %}``

Inside a loop the variable ``loop`` exposes ``index`` (1-based), ``index0``,
``first`` and ``last``.
"""

import re

from .markdown import escape_html

__all__ = ["Template"]

_TOKEN_RE = re.compile(r"\{\{\{(.*?)\}\}\}|\{\{(.*?)\}\}|\{%(.*?)%\}", re.S)


class Template:
    """A compiled template ready to be rendered with a context dict."""

    def __init__(self, source):
        self.source = source
        self.nodes = _parse(_tokenize(source))

    @classmethod
    def from_string(cls, source):
        return cls(source)

    def render(self, context=None):
        return _render(self.nodes, [dict(context or {})])


def _tokenize(source):
    tokens = []
    pos = 0
    for match in _TOKEN_RE.finditer(source):
        if match.start() > pos:
            tokens.append(("text", source[pos:match.start()]))
        if match.group(1) is not None:
            tokens.append(("raw", match.group(1).strip()))
        elif match.group(2) is not None:
            tokens.append(("var", match.group(2).strip()))
        else:
            tokens.append(("tag", match.group(3).strip()))
        pos = match.end()
    if pos < len(source):
        tokens.append(("text", source[pos:]))
    return tokens


def _parse_block(tokens, pos, stops):
    nodes = []
    while pos < len(tokens):
        kind, value = tokens[pos][0], tokens[pos][1]
        if kind == "tag":
            word = value.split()[0] if value.split() else ""
            if word in stops:
                return nodes, pos
            if word == "if":
                cond = value[2:].strip()
                body, pos = _parse_block(tokens, pos + 1, ("else", "endif"))
                orelse = []
                if pos < len(tokens) and tokens[pos][1].split()[:1] == ["else"]:
                    orelse, pos = _parse_block(tokens, pos + 1, ("endif",))
                pos += 1  # consume endif
                nodes.append(("if", cond, body, orelse))
                continue
            if word == "for":
                spec = value[3:].strip()
                var, sep, expr = spec.partition(" in ")
                if not sep:
                    pos += 1
                    continue
                body, pos = _parse_block(tokens, pos + 1, ("endfor",))
                pos += 1  # consume endfor
                nodes.append(("for", var.strip(), expr.strip(), body))
                continue
            pos += 1  # unknown tag: ignore
            continue
        nodes.append(tokens[pos])
        pos += 1
    return nodes, pos


def _parse(tokens):
    nodes, _ = _parse_block(tokens, 0, ())
    return nodes


def _render(nodes, scopes):
    out = []
    for node in nodes:
        if node[0] == "text":
            out.append(node[1])
        elif node[0] == "var":
            value = _resolve(node[1], scopes)
            out.append("" if value is None else escape_html(_stringify(value)))
        elif node[0] == "raw":
            value = _resolve(node[1], scopes)
            out.append("" if value is None else _stringify(value))
        elif node[0] == "if":
            branch = node[2] if _resolve(node[1], scopes) else node[3]
            out.append(_render(branch, scopes))
        elif node[0] == "for":
            seq = _resolve(node[2], scopes)
            if not seq:
                continue
            seq = list(seq)
            total = len(seq)
            for index, item in enumerate(seq):
                loop = {
                    "index": index + 1,
                    "index0": index,
                    "first": index == 0,
                    "last": index == total - 1,
                }
                local = {node[1]: item, "loop": loop}
                out.append(_render(node[3], [local] + scopes))
    return "".join(out)


def _stringify(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _resolve(name, scopes):
    name = name.strip()
    if not name:
        return None
    parts = name.split(".")
    for scope in scopes:
        if parts[0] in scope:
            value = scope[parts[0]]
            for part in parts[1:]:
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    value = getattr(value, part, None)
                if value is None:
                    break
            return value
    return None
