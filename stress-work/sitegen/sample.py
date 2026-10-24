"""Generate a synthetic Markdown site for demos, benchmarks and stress tests.

``generate_sample_site`` writes a deterministic tree of Markdown files (300 by
default) that exercises every feature the generator supports. Given the same
``seed`` the output is byte-for-byte identical, which makes it safe to use in
tests and reproducible in bug reports.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

from .htmlutil import rel_url
from .site import page_url

DEFAULT_PAGES = 300
DEFAULT_SEED = 1234
DEFAULT_START_DATE = date(2024, 1, 1)

_TAGS = ["intro", "guide", "reference", "howto", "api", "faq"]
_NOUNS = [
    "parser",
    "renderer",
    "template",
    "builder",
    "manifest",
    "watcher",
    "index",
    "navigation",
]


def _page_markdown(rng, index, total, own_url, target_url, back_url):
    """Return the Markdown body for one synthetic page."""
    if index == 0:
        title = "Home"
    else:
        title = "Sample Page %03d" % index

    tags = sorted(rng.sample(_TAGS, 2))
    noun = rng.choice(_NOUNS)
    forward = rel_url(target_url, own_url)
    home = rel_url(back_url, own_url)
    published = (DEFAULT_START_DATE + timedelta(days=index)).isoformat()

    lines = [
        "---",
        "title: %s" % title,
        "weight: %d" % index,
        "date: %s" % published,
        "tags: [%s]" % ", ".join(tags),
        "---",
        "",
        "# %s" % title,
        "",
        "This is synthetic page %d of %d. It exists so the generator can be"
        % (index, total),
        "exercised against a realistically sized tree of Markdown without any",
        "hand-written fixtures.",
        "",
        "## Details",
        "",
        "The page mentions the **%s** and uses `inline code` in a sentence." % noun,
        "Continue to [the next page](%s)." % forward,
        "",
        "## Checklist",
        "",
        "1. Parse the %s" % noun,
        "2. Render the template",
        "3. Write the output file",
        "",
        "- deterministic content",
        "- nested list support",
        "  - deeper level",
        "  - another sibling",
        "",
        "```python",
        "def %s(page):" % noun,
        "    return page.title",
        "```",
        "",
        "> Everything on this page is generated; edit the generator, not the output.",
        "",
        "---",
        "",
        "Back to [the index](%s)." % home,
        "",
    ]
    return "\n".join(lines)


def _relative_paths(pages):
    """Return the relative source paths for a site of *pages* pages."""
    section_count = max(1, pages // 25)
    rels = []
    for index in range(pages):
        if index == 0:
            rels.append("index.md")
        else:
            section = (index - 1) % section_count
            rels.append("section-%02d/page-%03d.md" % (section, index))
    return rels


def generate_sample_site(directory, pages=DEFAULT_PAGES, seed=DEFAULT_SEED):
    """Write *pages* synthetic Markdown files under *directory*.

    Returns the list of written paths. The first page is always ``index.md``;
    the rest are grouped into ``section-NN/`` subdirectories.
    """
    if pages < 1:
        raise ValueError("pages must be at least 1")

    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    rels = _relative_paths(pages)
    urls = [page_url(rel) for rel in rels]

    written = []
    for index, rel in enumerate(rels):
        target = (index + 1) % pages
        text = _page_markdown(rng, index, pages, urls[index], urls[target], urls[0])
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written
