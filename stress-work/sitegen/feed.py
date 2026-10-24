"""RSS 2.0 feed generation (standard library only)."""

import email.utils
from datetime import datetime, timezone

from .markdown import escape_html

__all__ = ["render_rss", "parse_date", "FEED_NAME"]

FEED_NAME = "feed.xml"

_DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%a, %d %b %Y %H:%M:%S %z")


def parse_date(value):
    """Parse a front matter date into an aware UTC datetime, or ``None``."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def _rfc822(dt):
    return email.utils.format_datetime(dt)


def _absolute(site_url, path):
    if not site_url:
        return path
    return site_url.rstrip("/") + "/" + path.lstrip("/")


def render_rss(pages, site_title, site_url="", description="", limit=20, build_date=None):
    """Render an RSS 2.0 document for ``pages``.

    Pages are ordered newest first (by their ``date`` front matter, falling back
    to navigation order) and limited to ``limit`` items. ``build_date`` accepts a
    datetime or an ISO date string; when omitted the newest page date is used so
    that output stays deterministic for tests.
    """
    items = [page for page in pages if not page.draft]

    def sort_key(page):
        dt = parse_date(page.metadata.get("date"))
        return (
            dt is not None,
            dt or datetime.min.replace(tzinfo=timezone.utc),
            page.title.lower(),
        )

    items.sort(key=sort_key)
    items.reverse()
    if limit is not None and limit >= 0:
        items = items[:limit]

    newest = parse_date(build_date)
    if newest is None:
        for page in items:
            dt = parse_date(page.metadata.get("date"))
            if dt is not None:
                newest = dt
                break

    channel_link = _absolute(site_url, "index.html")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        "  <channel>",
        "    <title>%s</title>" % escape_html(site_title),
        "    <link>%s</link>" % escape_html(channel_link),
        "    <description>%s</description>"
        % escape_html(description or site_title),
        "    <language>en</language>",
    ]
    if newest is not None:
        lines.append("    <lastBuildDate>%s</lastBuildDate>" % _rfc822(newest))

    for page in items:
        link = _absolute(site_url, page.url)
        lines.append("    <item>")
        lines.append("      <title>%s</title>" % escape_html(page.title))
        lines.append("      <link>%s</link>" % escape_html(link))
        lines.append("      <guid isPermaLink=\"false\">%s</guid>" % escape_html(link))
        if page.description:
            lines.append(
                "      <description>%s</description>" % escape_html(page.description)
            )
        dt = parse_date(page.metadata.get("date"))
        if dt is not None:
            lines.append("      <pubDate>%s</pubDate>" % _rfc822(dt))
        lines.append("    </item>")

    lines.append("  </channel>")
    lines.append("</rss>")
    return "\n".join(lines) + "\n"
