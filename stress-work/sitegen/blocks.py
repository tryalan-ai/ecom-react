"""Hand-written block-level Markdown parser and HTML renderer.

The parser turns Markdown text into a small list-of-dicts AST, and the renderer
turns that AST back into HTML. Keeping the two apart makes the parser easy to
test without string-matching HTML, and lets the site builder walk the AST (for
things like a table of contents).

Supported blocks: ATX headings, paragraphs, fenced and indented code blocks,
unordered/ordered (including nested) lists, blockquotes and thematic breaks.
"""

from __future__ import annotations

import re

from .htmlutil import escape_attr, escape_text, slugify
from .inline import render_inline, strip_markdown

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})\s*([^`]*)$")
_HR_RE = re.compile(r"^\s{0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")
_ULIST_RE = re.compile(r"^(\s*)([-*+])\s+(.*)$")
_OLIST_RE = re.compile(r"^(\s*)(\d{1,9})[.)]\s+(.*)$")
_QUOTE_RE = re.compile(r"^\s{0,3}>\s?(.*)$")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def parse_blocks(text):
    """Parse *text* into a list of block nodes."""
    blocks, _ = _parse_blocks(text.split("\n"), {})
    return blocks


def _parse_blocks(lines, used_ids):
    blocks = []
    index = 0
    total = len(lines)
    while index < total:
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        fence = _FENCE_RE.match(line)
        if fence:
            code, lang, index = _read_fence(lines, index, fence)
            blocks.append({"type": "code", "lang": lang, "text": code})
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            text = _strip_closing_hashes(heading.group(2))
            blocks.append(
                {
                    "type": "heading",
                    "level": len(heading.group(1)),
                    "text": text,
                    "id": _unique_slug(text, used_ids),
                }
            )
            index += 1
            continue

        if _HR_RE.match(line):
            blocks.append({"type": "hr"})
            index += 1
            continue

        if _list_item_match(line):
            node, index = _parse_list(lines, index, used_ids)
            blocks.append(node)
            continue

        if _QUOTE_RE.match(line):
            node, index = _parse_blockquote(lines, index, used_ids)
            blocks.append(node)
            continue

        if line.startswith("    ") or line.startswith("\t"):
            node, index = _parse_indented_code(lines, index)
            blocks.append(node)
            continue

        node, index = _parse_paragraph(lines, index)
        blocks.append(node)
    return blocks, index


def _parse_paragraph(lines, start):
    index = start
    total = len(lines)
    buffer = []
    while index < total:
        line = lines[index]
        if not line.strip():
            break
        if buffer and _starts_block(line):
            break
        buffer.append(line.lstrip())
        index += 1
    return {"type": "paragraph", "text": "\n".join(buffer).strip()}, index


def _parse_indented_code(lines, start):
    index = start
    total = len(lines)
    body = []
    while index < total:
        line = lines[index]
        if line.startswith("    "):
            body.append(line[4:])
        elif line.startswith("\t"):
            body.append(line[1:])
        elif not line.strip():
            body.append("")
        else:
            break
        index += 1
    while body and not body[-1].strip():
        body.pop()
    return {"type": "code", "lang": "", "text": "\n".join(body)}, index


def _parse_blockquote(lines, start, used_ids):
    index = start
    total = len(lines)
    inner = []
    while index < total:
        line = lines[index]
        match = _QUOTE_RE.match(line)
        if match:
            inner.append(match.group(1))
            index += 1
            continue
        if not line.strip():
            if index + 1 < total and _QUOTE_RE.match(lines[index + 1]):
                inner.append("")
                index += 1
                continue
            break
        if inner and not _starts_block(line):
            inner.append(line)
            index += 1
            continue
        break
    children, _ = _parse_blocks(inner, used_ids)
    return {"type": "blockquote", "children": children}, index


def _parse_list(lines, start, used_ids):
    first = _list_item_match(lines[start])
    ordered = first["ordered"]
    base_indent = first["indent"]
    start_number = first["number"]

    items = []
    loose = False
    index = start
    total = len(lines)
    current = None
    content_indent = 0

    while index < total:
        line = lines[index]
        if not line.strip():
            ahead = index
            while ahead < total and not lines[ahead].strip():
                ahead += 1
            if ahead < total:
                nxt = _list_item_match(lines[ahead])
                if nxt and nxt["indent"] == base_indent and nxt["ordered"] == ordered:
                    loose = True
                    index = ahead
                    continue
                if _indent(lines[ahead]) > base_indent and current is not None:
                    current.append("")
                    loose = True
                    index = ahead
                    continue
            break

        match = _list_item_match(line)
        if match and match["indent"] == base_indent and match["ordered"] == ordered:
            current = [match["text"]]
            items.append(current)
            content_indent = base_indent + len(match["marker"]) + 1
            index += 1
            continue

        if _indent(line) > base_indent and current is not None:
            strip_count = min(content_indent, _indent(line))
            current.append(line[strip_count:])
            index += 1
            continue

        break

    parsed_items = []
    for item_lines in items:
        blocks, _ = _parse_blocks(item_lines, used_ids)
        parsed_items.append(blocks)
        if len(blocks) > 1:
            loose = True

    node = {
        "type": "list",
        "ordered": ordered,
        "start": start_number,
        "items": parsed_items,
        "loose": loose,
    }
    return node, index


def _read_fence(lines, start, match):
    fence = match.group(1)
    char = fence[0]
    min_len = len(fence)
    info = match.group(2).strip()
    lang = info.split()[0] if info else ""
    index = start + 1
    total = len(lines)
    body = []
    while index < total:
        line = lines[index]
        stripped = line.strip()
        if stripped and set(stripped) == {char} and len(stripped) >= min_len:
            index += 1
            break
        body.append(line)
        index += 1
    return "\n".join(body), lang, index


# ---------------------------------------------------------------------------
# Small parsing helpers
# ---------------------------------------------------------------------------
def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _list_item_match(line):
    unordered = _ULIST_RE.match(line)
    if unordered:
        return {
            "indent": len(unordered.group(1)),
            "marker": unordered.group(2),
            "text": unordered.group(3),
            "ordered": False,
            "number": 1,
        }
    ordered = _OLIST_RE.match(line)
    if ordered:
        return {
            "indent": len(ordered.group(1)),
            "marker": ordered.group(2) + ".",
            "text": ordered.group(3),
            "ordered": True,
            "number": int(ordered.group(2)),
        }
    return None


def _starts_block(line):
    return bool(
        _HEADING_RE.match(line)
        or _FENCE_RE.match(line)
        or _HR_RE.match(line)
        or _QUOTE_RE.match(line)
        or _list_item_match(line)
    )


def _strip_closing_hashes(text):
    text = text.strip()
    return re.sub(r"\s+#+\s*$", "", text)


def _unique_slug(text, used):
    base = slugify(strip_markdown(text)) or "section"
    seen = used.get(base, 0)
    used[base] = seen + 1
    return base if seen == 0 else "%s-%d" % (base, seen)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render_blocks(blocks):
    """Render a list of block nodes to an HTML string."""
    return "\n".join(render_block(node) for node in blocks)


def render_block(node):
    kind = node["type"]
    if kind == "heading":
        level = node["level"]
        return '<h%d id="%s">%s</h%d>' % (
            level,
            escape_attr(node.get("id", "")),
            render_inline(node["text"]),
            level,
        )
    if kind == "paragraph":
        return "<p>%s</p>" % render_inline(node["text"])
    if kind == "code":
        lang = node.get("lang", "")
        attr = ' class="language-%s"' % escape_attr(lang) if lang else ""
        return "<pre><code%s>%s</code></pre>" % (attr, escape_text(node["text"]))
    if kind == "hr":
        return "<hr>"
    if kind == "blockquote":
        body = render_blocks(node["children"])
        return "<blockquote>\n%s\n</blockquote>" % body
    if kind == "list":
        return _render_list(node)
    raise ValueError("unknown block type: %r" % (kind,))


def _render_list(node):
    tag = "ol" if node["ordered"] else "ul"
    attr = ""
    if node["ordered"] and node["start"] != 1:
        attr = ' start="%d"' % node["start"]
    parts = ["<%s%s>" % (tag, attr)]
    for item in node["items"]:
        parts.append(_render_item(item, node["loose"]))
    parts.append("</%s>" % tag)
    return "\n".join(parts)


def _render_item(blocks, loose):
    if not blocks:
        return "<li></li>"
    if not loose and len(blocks) == 1 and blocks[0]["type"] == "paragraph":
        return "<li>%s</li>" % render_inline(blocks[0]["text"])
    return "<li>\n%s\n</li>" % render_blocks(blocks)


def collect_headings(blocks):
    """Return ``[{"level", "text", "id"}]`` for every heading, in order."""
    found = []
    for node in blocks:
        if node["type"] == "heading":
            found.append(
                {"level": node["level"], "text": node["text"], "id": node["id"]}
            )
        elif node["type"] == "blockquote":
            found.extend(collect_headings(node["children"]))
    return found


def extract_title(blocks):
    """Return the plain text of the first heading, or ``None``."""
    for node in blocks:
        if node["type"] == "heading":
            return strip_markdown(node["text"])
    return None
