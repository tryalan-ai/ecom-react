"""sitegen - a dependency-free static site generator.

Converts a folder of Markdown files (headings, lists, links, code blocks and
YAML-ish front matter) into a static HTML site with a template, navigation and
an index page. Supports incremental builds (content hashing), a synthetic
sample-site generator and a polling ``--watch`` mode.

Everything here uses only the Python standard library.
"""

__version__ = "1.1.0"
