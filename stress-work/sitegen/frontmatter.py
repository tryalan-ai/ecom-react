"""Parsing for the simple YAML-ish front matter used by sitegen documents.

A document may begin with an optional block delimited by ``---`` lines::

    ---
    title: Getting Started
    weight: 2
    tags: [guide, intro]
    draft: false
    ---

    The rest of the file is Markdown.

Only the small subset of YAML that a documentation site needs is supported:
``key: value`` pairs with scalar, list and quoted values. Nested mappings,
anchors and multi-line values are deliberately out of scope.
"""

from __future__ import annotations

import re

DELIMITER = "---"
_INT_RE = re.compile(r"-?\d+")


def _split_top_level(value):
    """Split *value* on commas that are not inside quotes."""
    parts = []
    current = []
    quote = None
    for ch in value:
        if quote is not None:
            current.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            current.append(ch)
        elif ch == ",":
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip() != "" or len(parts) == 1]


def parse_value(value):
    """Coerce a raw front-matter value into a bool, int, list or string."""
    value = value.strip()
    if value == "":
        return ""
    if value[0] in "[(" and value[-1] in "])":
        inner = value[1:-1].strip()
        if inner == "":
            return []
        return [parse_value(part) for part in _split_top_level(inner)]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in ("null", "~"):
        return None
    if _INT_RE.fullmatch(value):
        return int(value)
    return value


def parse_metadata(text):
    """Parse the body of a front-matter block into a dictionary."""
    meta = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = parse_value(value)
    return meta


def parse_front_matter(text):
    """Split *text* into ``(metadata, body)``.

    If there is no front matter, or the opening ``---`` is never closed, the
    whole input is returned as the body and the metadata is empty.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != DELIMITER:
        return {}, text

    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == DELIMITER:
            end = index
            break
    if end is None:
        return {}, text

    meta = parse_metadata("\n".join(lines[1:end]))
    body = "\n".join(lines[end + 1 :])
    return meta, body



def split_list(value):
    """Normalise a metadata value into a list of strings.

    Accepts an already-parsed list, a comma-separated string, or a single
    value, so templates never have to care which form the author used.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(value)]
