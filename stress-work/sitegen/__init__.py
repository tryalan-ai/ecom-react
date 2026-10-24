"""sitegen: a small static-site generator written from scratch.

This package converts a folder of Markdown files into a static HTML site.
It intentionally depends only on the Python standard library and implements
Markdown parsing, templating and site assembly itself.

The public surface is intentionally small::

    from sitegen.site import build_site
    build_site("content", "public")

Individual pieces are also importable for testing:

    from sitegen.frontmatter import parse_front_matter
    from sitegen.inline import render_inline
    from sitegen.blocks import parse_blocks, render_blocks
    from sitegen.template import render_template
"""

__all__ = [
    "frontmatter",
    "htmlutil",
    "inline",
    "blocks",
    "template",
    "site",
    "sample",
    "watch",
    "cli",
]

__version__ = "1.1.0"
