"""The in-memory representation of a single page in the site."""

import posixpath
import re
from dataclasses import dataclass, field

__all__ = ["Page", "slug_for", "derive_title"]

_FIRST_H1_RE = re.compile(r"^#\s+(.*?)\s*#*\s*$", re.MULTILINE)


def slug_for(rel_path):
    """Map a source path to its HTML output path.

    ``index.md`` keeps its directory: ``guide/index.md`` -> ``guide/index.html``
    while ``guide/intro.md`` -> ``guide/intro.html``.
    """
    rel = rel_path.replace("\\", "/")
    lower = rel.lower()
    if lower.endswith(".markdown"):
        base = rel[: -len(".markdown")]
    elif lower.endswith(".md"):
        base = rel[:-3]
    else:
        base = rel
    return base + ".html"


def derive_title(body, fallback):
    """Use the first level-1 heading as the title, else a humanised fallback."""
    match = _FIRST_H1_RE.search(body or "")
    if match:
        title = match.group(1).strip()
        if title:
            return title
    stem = posixpath.basename(fallback or "")
    stem = re.sub(r"\.(md|markdown)$", "", stem, flags=re.IGNORECASE)
    stem = stem.replace("-", " ").replace("_", " ").strip()
    return stem.title() if stem else "Untitled"


@dataclass
class Page:
    """A page to be rendered.

    ``source_path`` is the path relative to the source directory (posix style),
    ``slug`` is the path relative to the output directory and ``content_html``
    is the rendered Markdown body.
    """

    source_path: str
    slug: str
    title: str
    body: str = ""
    content_html: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def url(self):
        return self.slug

    @property
    def description(self):
        value = self.metadata.get("description", "")
        return "" if value is None else str(value)

    @property
    def order(self):
        value = self.metadata.get("order")
        if isinstance(value, bool) or value is None:
            return 10_000
        if isinstance(value, (int, float)):
            return value
        try:
            return float(value)
        except (TypeError, ValueError):
            return 10_000

    @property
    def draft(self):
        return bool(self.metadata.get("draft", False))

    @property
    def in_nav(self):
        if self.metadata.get("nav", True) is False:
            return False
        return not self.draft
