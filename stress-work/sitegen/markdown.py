"""A small Markdown-to-HTML renderer written from scratch.

Supported syntax (the subset a docs site needs):

* ATX headings ``# .. ######`` and Setext headings (``===`` / ``---``)
* unordered (``-``, ``*``, ``+``) and ordered (``1.``) lists, incl. nesting
* links ``[text](url)`` and images ``![alt](src "title")``
* inline code ``` `code` ``` and fenced code blocks ```` ```lang ````
* indented (4-space) code blocks
* block quotes ``>``
* horizontal rules
* bold ``**x**`` / ``__x__`` and italic ``*x*`` / ``_x_``
* autolinks ``<https://example.com>``

No third-party libraries are used. Raw HTML in the source is escaped.
"""

import re

__all__ = ["render_markdown", "render_inline", "escape_html", "rewrite_href"]


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w+#.-]*)\s*$")
_HR_RE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
_BLOCKQUOTE_RE = re.compile(r"^\s*>")
_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_SETEXT_H1_RE = re.compile(r"^=+\s*$")
_SETEXT_H2_RE = re.compile(r"^-+\s*$")
_INDENT_CODE_RE = re.compile(r"^(?: {4}|\t)")

_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(\s*([^)\s]+)(?:\s+\"([^\"]*)\")?\s*\)")
_LINK_RE = re.compile(r"\[([^\]]*)\]\(\s*([^)\s]+)(?:\s+\"([^\"]*)\")?\s*\)")
_AUTOLINK_RE = re.compile(r"<(https?://[^>\s]+)>")

_STRONG_STAR_RE = re.compile(r"\*\*(.+?)\*\*")
_STRONG_USCORE_RE = re.compile(r"__(.+?)__")
_EM_STAR_RE = re.compile(r"\*(.+?)\*")
_EM_USCORE_RE = re.compile(r"(?<!\w)_(.+?)_(?!\w)")


def escape_html(text):
    """Escape the characters that are meaningful in HTML text/attributes."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_inline(text):
    """Render inline markdown constructs inside a single block of text."""
    placeholders = []

    def stash(html):
        token = "\x00%d\x00" % len(placeholders)
        placeholders.append(html)
        return token

    # Order matters: code spans are opaque, links may contain inline markup.
    text = _CODE_SPAN_RE.sub(
        lambda m: stash("<code>%s</code>" % escape_html(m.group(1))), text
    )
    text = _IMAGE_RE.sub(
        lambda m: stash(_render_image(m.group(1), m.group(2), m.group(3))), text
    )
    text = _LINK_RE.sub(
        lambda m: stash(_render_link(m.group(1), m.group(2), m.group(3))), text
    )
    text = _AUTOLINK_RE.sub(
        lambda m: stash(
            '<a href="%s">%s</a>' % (escape_html(m.group(1)), escape_html(m.group(1)))
        ),
        text,
    )

    # Everything left is literal text; escape it before adding our own markup.
    text = escape_html(text)

    text = _STRONG_STAR_RE.sub(r"<strong>\1</strong>", text)
    text = _STRONG_USCORE_RE.sub(r"<strong>\1</strong>", text)
    text = _EM_STAR_RE.sub(r"<em>\1</em>", text)
    text = _EM_USCORE_RE.sub(r"<em>\1</em>", text)

    for index, html in enumerate(placeholders):
        text = text.replace("\x00%d\x00" % index, html)
    return text


def rewrite_href(href):
    """Point Markdown links at the generated HTML instead of the source file."""
    if "://" in href or href.startswith(("#", "mailto:", "/")):
        return href
    lowered = href.lower()
    for ext in (".markdown", ".md"):
        if lowered.endswith(ext):
            return href[: -len(ext)] + ".html"
    return href


def _render_image(alt, src, title):
    parts = ['<img src="%s"' % escape_html(src), 'alt="%s"' % escape_html(alt)]
    if title:
        parts.append('title="%s"' % escape_html(title))
    return " ".join(parts) + " />"


def _render_link(label, href, title):
    inner = render_inline(label)
    attrs = ' href="%s"' % escape_html(rewrite_href(href))
    if title:
        attrs += ' title="%s"' % escape_html(title)
    return "<a%s>%s</a>" % (attrs, inner)


def render_markdown(text):
    """Render a full Markdown document to HTML."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    return "\n".join(_render_blocks(lines))


def _render_blocks(lines):
    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        if line.strip() == "":
            i += 1
            continue

        fence = _FENCE_RE.match(line)
        if fence:
            html, i = _render_fenced_code(lines, i)
            out.append(html)
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            content = render_inline(heading.group(2).strip())
            out.append("<h%d>%s</h%d>" % (level, content, level))
            i += 1
            continue

        if line.strip() and i + 1 < n:
            if _SETEXT_H1_RE.match(lines[i + 1]) and not _is_block_start(line):
                out.append("<h1>%s</h1>" % render_inline(line.strip()))
                i += 2
                continue
            if (
                _SETEXT_H2_RE.match(lines[i + 1])
                and not _LIST_RE.match(line)
                and not _is_block_start(line)
            ):
                out.append("<h2>%s</h2>" % render_inline(line.strip()))
                i += 2
                continue

        if _SETEXT_H1_RE.match(line):
            # An orphan '===' line: render a rule rather than swallow it.
            out.append("<hr />")
            i += 1
            continue

        if _HR_RE.match(line):
            out.append("<hr />")
            i += 1
            continue

        if _BLOCKQUOTE_RE.match(line):
            html, i = _render_blockquote(lines, i)
            out.append(html)
            continue

        if _LIST_RE.match(line):
            html, i = _render_list(lines, i)
            out.append(html)
            continue

        if _INDENT_CODE_RE.match(line):
            html, i = _render_indented_code(lines, i)
            out.append(html)
            continue

        html, i = _render_paragraph(lines, i)
        out.append(html)

    return out


def _render_paragraph(lines, i):
    parts = []
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.strip() == "":
            break
        if parts and _is_block_start(line):
            break
        if parts and _SETEXT_H1_RE.match(line):
            break
        parts.append(line.strip())
        i += 1
    return "<p>%s</p>" % render_inline(" ".join(parts)), i


def _render_fenced_code(lines, i):
    match = _FENCE_RE.match(lines[i])
    fence = match.group(1)
    lang = match.group(2)
    marker = fence[0]
    i += 1
    code = []
    n = len(lines)
    close_re = re.compile(r"^\s*" + re.escape(marker) + r"{" + str(len(fence)) + r",}\s*$")
    while i < n and not close_re.match(lines[i]):
        code.append(lines[i])
        i += 1
    if i < n:
        i += 1  # consume the closing fence
    return _code_block_html(code, lang), i


def _render_indented_code(lines, i):
    code = []
    n = len(lines)
    while i < n and (lines[i].strip() == "" or _INDENT_CODE_RE.match(lines[i])):
        if lines[i].startswith("\t"):
            code.append(lines[i][1:])
        elif lines[i].startswith("    "):
            code.append(lines[i][4:])
        else:
            code.append(lines[i].strip())
        i += 1
    while code and code[-1] == "":
        code.pop()
    return _code_block_html(code, ""), i


def _code_block_html(code_lines, lang):
    body = escape_html("\n".join(code_lines))
    if lang:
        return '<pre><code class="language-%s">%s</code></pre>' % (
            escape_html(lang),
            body,
        )
    return "<pre><code>%s</code></pre>" % body


def _render_blockquote(lines, i):
    quoted = []
    n = len(lines)
    while i < n and _BLOCKQUOTE_RE.match(lines[i]):
        quoted.append(re.sub(r"^\s*>\s?", "", lines[i]))
        i += 1
    inner = render_markdown("\n".join(quoted))
    return "<blockquote>\n%s\n</blockquote>" % inner, i


def _render_list(lines, i):
    first = _LIST_RE.match(lines[i])
    base_indent = len(first.group(1))
    ordered = first.group(2)[0].isdigit()
    items = []
    n = len(lines)

    while i < n:
        match = _LIST_RE.match(lines[i])
        if not match or len(match.group(1)) != base_indent:
            break
        if match.group(2)[0].isdigit() != ordered:
            break

        item_lines = [match.group(3)]
        i += 1
        while i < n:
            line = lines[i]
            if line.strip() == "":
                if i + 1 < n and _indent_of(lines[i + 1]) > base_indent:
                    item_lines.append("")
                    i += 1
                    continue
                break
            inner_match = _LIST_RE.match(line)
            if inner_match and len(inner_match.group(1)) == base_indent:
                break
            if _indent_of(line) > base_indent:
                dedent = base_indent + 2
                item_lines.append(line[dedent:] if len(line) >= dedent else "")
                i += 1
            else:
                break
        items.append(item_lines)

    tag = "ol" if ordered else "ul"
    html = ["<%s>" % tag]
    for item_lines in items:
        inner = render_markdown("\n".join(item_lines))
        html.append("<li>%s</li>" % _unwrap_paragraph(inner))
    html.append("</%s>" % tag)
    return "\n".join(html), i


def _unwrap_paragraph(html):
    """Tight lists omit the paragraph wrapper around simple item text."""
    if html.startswith("<p>"):
        end = html.find("</p>")
        if end != -1:
            rest = html[end + 4:]
            if rest == "":
                return html[3:end]
            if rest.startswith("\n"):
                return html[3:end] + rest
    return html


def _indent_of(line):
    stripped = line.lstrip(" ")
    return len(line) - len(stripped)


def _is_block_start(line):
    if line.strip() == "":
        return True
    if _FENCE_RE.match(line):
        return True
    if _HEADING_RE.match(line):
        return True
    if _HR_RE.match(line):
        return True
    if _BLOCKQUOTE_RE.match(line):
        return True
    if _LIST_RE.match(line):
        return True
    if _INDENT_CODE_RE.match(line):
        return True
    return False
