"""A tiny YAML-ish front matter parser (standard library only).

Front matter is an optional block at the very top of a Markdown file delimited
by ``---`` fences::

    ---
    title: Hello
    order: 2
    tags: [intro, demo]
    draft: false
    ---

    # Body starts here

The parser intentionally supports a small, predictable subset of YAML: scalars
(strings, quoted strings, ints, floats, booleans, null) and inline lists.
Anything it does not understand is kept as a plain string so that content is
never silently lost.
"""

import re

_FENCE = re.compile(r"^---\s*$")


def parse_front_matter(text):
    """Split ``text`` into ``(metadata, body)``.

    If the text does not begin with a complete front matter block the metadata
    is an empty dict and the body is the original text unchanged.
    """
    if text.startswith("\ufeff"):
        text = text[1:]

    lines = text.split("\n")
    if not lines or not _FENCE.match(lines[0].strip()):
        return {}, text

    meta = {}
    i = 1
    while i < len(lines):
        line = lines[i]
        if _FENCE.match(line.strip()):
            body = "\n".join(lines[i + 1:])
            return meta, body
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue
        key, _, raw = line.partition(":")
        meta[key.strip()] = parse_value(raw.strip())
        i += 1

    # Unterminated block: not valid front matter, treat the whole text as body.
    return {}, text


def parse_value(raw):
    """Parse a single scalar or inline-list value."""
    raw = raw.strip()
    if raw == "":
        return ""

    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        return _unquote(raw)

    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if inner == "":
            return []
        return [parse_value(part.strip()) for part in _split_list(inner)]

    lowered = raw.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    if lowered in ("null", "~"):
        return None

    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass

    return raw


def _unquote(raw):
    inner = raw[1:-1]
    # Handle the common escapes without pulling in a full YAML parser.
    inner = inner.replace('\\"', '"').replace("\\'", "'")
    inner = inner.replace("\\n", "\n").replace("\\t", "\t")
    return inner


def _split_list(value):
    """Split a comma separated list, respecting quoted segments."""
    parts = []
    buf = []
    quote = None
    for ch in value:
        if quote is not None:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts
