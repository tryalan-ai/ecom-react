"""Small HTML helpers shared by the Markdown and site layers."""

from __future__ import annotations

import re

_ESCAPE_TEXT = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
}

_ESCAPE_ATTR = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
}

_ESCAPE_RE = re.compile(r"[&<>]")
_ESCAPE_ATTR_RE = re.compile(r'[&<>"]')


def escape_text(text):
    """Escape ``&``, ``<`` and ``>`` so *text* is safe inside an HTML element."""
    return _ESCAPE_RE.sub(lambda m: _ESCAPE_TEXT[m.group(0)], text)


def escape_attr(value):
    """Escape a value for use inside a double-quoted HTML attribute."""
    return _ESCAPE_ATTR_RE.sub(lambda m: _ESCAPE_ATTR[m.group(0)], str(value))


def slugify(text):
    """Turn a heading into a stable, URL-friendly anchor.

    ``"Hello, World!"`` becomes ``"hello-world"``. Runs of characters that are
    not letters, digits or hyphens collapse into a single hyphen, so the result
    is safe to use as an ``id`` and in a fragment URL.
    """
    lowered = text.strip().lower()
    # Drop any HTML tags that may already be embedded in the heading text.
    lowered = re.sub(r"<[^>]+>", "", lowered)
    lowered = re.sub(r"[^\w\s-]", "", lowered, flags=re.UNICODE)
    lowered = re.sub(r"[\s_]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
    return lowered


def rel_url(target, current):
    """Return *target* expressed relatively from *current*'s directory.

    Both paths are POSIX-style and relative to the site root. ``current`` is the
    file the link is written into (for example ``"guide/intro.html"``), so
    ``rel_url("index.html", "guide/intro.html")`` yields ``"../index.html"``.
    """
    target = target.lstrip("/")
    current_dir = current.rsplit("/", 1)[0] if "/" in current else ""
    from_parts = [p for p in current_dir.split("/") if p]
    to_parts = [p for p in target.split("/") if p]

    common = 0
    while (
        common < len(from_parts)
        and common < len(to_parts)
        and from_parts[common] == to_parts[common]
    ):
        common += 1

    up = [".."] * (len(from_parts) - common)
    rest = to_parts[common:]
    result = "/".join(up + rest)
    return result or "."
