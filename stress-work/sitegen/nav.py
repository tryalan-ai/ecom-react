"""Navigation rendering shared by every page."""

import posixpath

from .markdown import escape_html

__all__ = ["sort_pages", "relative_url", "render_nav"]


def sort_pages(pages):
    """Order pages by explicit ``order`` then title (case-insensitive)."""
    return sorted(pages, key=lambda p: (p.order, p.title.lower(), p.slug))


def relative_url(from_slug, to_slug):
    """Return a link from the page at ``from_slug`` to the page at ``to_slug``."""
    from_dir = posixpath.dirname(from_slug)
    if not from_dir:
        from_dir = "."
    return posixpath.relpath(to_slug, from_dir)


def render_nav(pages, current_slug=None, css_class="nav"):
    """Render an unordered-list navigation for the site.

    ``current_slug`` marks the active page. Pages with ``nav: false`` in their
    front matter (or drafts) are excluded.
    """
    visible = [page for page in sort_pages(pages) if page.in_nav]
    lines = ['<nav class="%s">' % escape_html(css_class), "<ul>"]
    for page in visible:
        href = relative_url(current_slug, page.url) if current_slug else page.url
        classes = ' class="active"' if current_slug and page.slug == current_slug else ""
        lines.append(
            '<li%s><a href="%s">%s</a></li>'
            % (classes, escape_html(href), escape_html(page.title))
        )
    lines.append("</ul>")
    lines.append("</nav>")
    return "\n".join(lines)
