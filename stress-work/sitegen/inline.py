"""A small, self-contained inline Markdown parser.

Handles the inline constructs a documentation site needs:

* backslash escapes
* code spans (`` `code` ``)
* emphasis (``*em*``, ``_em_``) and strong (``**strong**``, ``__strong__``)
* links (``[text](url "title")``), images (``![alt](src)``)
* autolinks (``<https://example.com>``)
* hard line breaks (two trailing spaces before a newline)

Everything is parsed by hand rather than with a Markdown library, and all text
is HTML-escaped as it is emitted so the result is safe to embed in a page.
"""

from __future__ import annotations

import re

from .htmlutil import escape_attr, escape_text

_ESCAPABLE = set("\\`*_{}[]()#+-.!>~|\"")

_AUTOLINK_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9+.\-]*://[^<>\s]+)>")
_EMAIL_RE = re.compile(r"<([^<>\s@]+@[^<>\s@]+\.[^<>\s@]+)>")


def render_inline(text):
    """Render a string of inline Markdown to HTML."""
    return _Parser(text).parse()


def strip_markdown(text):
    """Best-effort removal of inline markup, for plain-text titles/excerpts."""
    if text is None:
        return ""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(\*|_)(.*?)\1", r"\2", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _split_destination(destination):
    """Split ``url "optional title"`` into ``(url, title)``.

    Returns ``(None, None)`` when the destination cannot be parsed, which the
    caller treats as "this is not a link".
    """
    destination = destination.strip()
    if not destination:
        return None, None
    if destination.startswith("<"):
        end = destination.find(">")
        if end == -1:
            return None, None
        url = destination[1:end]
        rest = destination[end + 1 :].strip()
    else:
        pieces = destination.split(None, 1)
        url = pieces[0]
        rest = pieces[1].strip() if len(pieces) > 1 else ""
    if not url:
        return None, None
    title = None
    if rest:
        if len(rest) >= 2 and rest[0] == rest[-1] and rest[0] in "\"'":
            title = rest[1:-1]
        else:
            return None, None
    return url, title


class _Parser:
    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.length = len(text)

    # -- public entry point ------------------------------------------------
    def parse(self):
        out = []
        buffer = []

        def flush():
            if buffer:
                out.append(escape_text("".join(buffer)))
                del buffer[:]

        while self.pos < self.length:
            ch = self.text[self.pos]

            if ch == "\\":
                nxt = self.text[self.pos + 1] if self.pos + 1 < self.length else ""
                if nxt in _ESCAPABLE:
                    buffer.append(nxt)
                    self.pos += 2
                    continue
                buffer.append(ch)
                self.pos += 1
                continue

            if ch == "\n":
                trailing = 0
                while buffer and buffer[-1] == " ":
                    buffer.pop()
                    trailing += 1
                if trailing >= 2:
                    flush()
                    out.append("<br>\n")
                else:
                    buffer.append("\n")
                self.pos += 1
                continue

            if ch == "`":
                span = self._try_code_span()
                if span is not None:
                    flush()
                    out.append(span)
                    continue
                buffer.append(ch)
                self.pos += 1
                continue

            if ch == "!" and self.text[self.pos + 1 : self.pos + 2] == "[":
                link = self._try_link(image=True)
                if link is not None:
                    flush()
                    out.append(link)
                    continue
                buffer.append(ch)
                self.pos += 1
                continue

            if ch == "[":
                link = self._try_link(image=False)
                if link is not None:
                    flush()
                    out.append(link)
                    continue
                buffer.append(ch)
                self.pos += 1
                continue

            if ch == "<":
                auto = self._try_autolink()
                if auto is not None:
                    flush()
                    out.append(auto)
                    continue
                buffer.append(ch)
                self.pos += 1
                continue

            if ch in "*_":
                emphasis = self._try_emphasis(ch)
                if emphasis is not None:
                    flush()
                    out.append(emphasis)
                    continue
                buffer.append(ch)
                self.pos += 1
                continue

            buffer.append(ch)
            self.pos += 1

        flush()
        return "".join(out)

    # -- helpers -----------------------------------------------------------
    def _try_code_span(self):
        start = self.pos
        ticks = 0
        while start + ticks < self.length and self.text[start + ticks] == "`":
            ticks += 1
        marker = "`" * ticks
        end = self.text.find(marker, start + ticks)
        if end == -1:
            return None
        code = self.text[start + ticks : end]
        # A single leading/trailing space is stripped, matching Markdown.
        if len(code) >= 2 and code[0] == " " and code[-1] == " ":
            code = code[1:-1]
        self.pos = end + ticks
        return "<code>%s</code>" % escape_text(code)

    def _try_autolink(self):
        rest = self.text[self.pos :]
        match = _AUTOLINK_RE.match(rest)
        if match:
            url = match.group(1)
            self.pos += match.end()
            return '<a href="%s">%s</a>' % (escape_attr(url), escape_text(url))
        match = _EMAIL_RE.match(rest)
        if match:
            email = match.group(1)
            self.pos += match.end()
            return '<a href="mailto:%s">%s</a>' % (
                escape_attr(email),
                escape_text(email),
            )
        return None

    def _try_link(self, image):
        start = self.pos
        cursor = start + (2 if image else 1)
        if cursor > self.length:
            return None

        depth = 0
        index = cursor
        while index < self.length:
            ch = self.text[index]
            if ch == "\\":
                index += 2
                continue
            if ch == "[":
                depth += 1
            elif ch == "]":
                if depth == 0:
                    break
                depth -= 1
            index += 1
        if index >= self.length:
            return None

        label = self.text[cursor:index]
        if self.text[index + 1 : index + 2] != "(":
            return None

        close = index + 2
        paren_depth = 0
        while close < self.length:
            ch = self.text[close]
            if ch == "\\":
                close += 2
                continue
            if ch == "(":
                paren_depth += 1
            elif ch == ")":
                if paren_depth == 0:
                    break
                paren_depth -= 1
            close += 1
        if close >= self.length:
            return None

        url, title = _split_destination(self.text[index + 2 : close])
        if url is None:
            return None

        self.pos = close + 1
        title_attr = ' title="%s"' % escape_attr(title) if title else ""
        if image:
            alt = strip_markdown(label)
            return '<img src="%s" alt="%s"%s>' % (
                escape_attr(url),
                escape_attr(alt),
                title_attr,
            )
        return '<a href="%s"%s>%s</a>' % (
            escape_attr(url),
            title_attr,
            _Parser(label).parse(),
        )

    def _try_emphasis(self, delim):
        start = self.pos
        run = 0
        while start + run < self.length and self.text[start + run] == delim:
            run += 1

        use = 2 if run >= 2 else 1
        marker = delim * use
        after_index = start + use
        if after_index >= self.length or self.text[after_index].isspace():
            return None
        if delim == "_" and start > 0 and self.text[start - 1].isalnum():
            return None

        search = after_index
        close = -1
        while True:
            candidate = self.text.find(marker, search)
            if candidate == -1:
                return None
            if candidate == start:
                search = candidate + use
                continue
            if self.text[candidate - 1].isspace():
                search = candidate + use
                continue
            if delim == "_" and candidate + use < self.length:
                if self.text[candidate + use].isalnum():
                    search = candidate + use
                    continue
            close = candidate
            break

        inner = self.text[after_index:close]
        if not inner.strip():
            return None
        tag = "strong" if use == 2 else "em"
        self.pos = close + use
        return "<%s>%s</%s>" % (tag, _Parser(inner).parse(), tag)
