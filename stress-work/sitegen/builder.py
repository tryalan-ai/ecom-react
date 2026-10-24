"""Site builder: reads Markdown, renders HTML, and writes it to disk.

The builder supports *incremental* builds. It keeps a manifest (a JSON file in
the output directory) mapping each source file to the hash of its contents. On
a rebuild only pages whose content changed are re-rendered; unchanged pages are
skipped. Navigation and the index are rebuilt whenever the set of pages or a
page's navigation-relevant metadata changes.
"""

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field

from .feed import FEED_NAME, render_rss
from .frontmatter import parse_front_matter
from .index import render_index
from .markdown import render_markdown
from .nav import relative_url, render_nav, sort_pages
from .page import Page, derive_title, slug_for
from .template import Template

__all__ = ["BuildResult", "SiteBuilder", "build_site", "DEFAULT_TEMPLATE", "MANIFEST_NAME"]

MANIFEST_NAME = ".sitegen-manifest.json"
MANIFEST_VERSION = 2

DEFAULT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ page.title }} &middot; {{ site.title }}</title>
{% if page.description %}<meta name="description" content="{{ page.description }}">
{% endif %}</head>
<body>
<header class="site-header">
  <a class="site-title" href="{{ home_url }}">{{ site.title }}</a>
</header>
{{{ nav }}}
<main class="content">
{{{ content }}}
</main>
<footer class="site-footer"><p>{{ site.title }}</p></footer>
</body>
</html>
"""

_MARKDOWN_EXTENSIONS = (".md", ".markdown")
MARKDOWN_EXTENSIONS = _MARKDOWN_EXTENSIONS


@dataclass
class BuildResult:
    """What a single :meth:`SiteBuilder.build` call did."""

    output_dir: str
    rendered: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    pages: list = field(default_factory=list)
    manifest_path: str = ""
    full_rebuild: bool = False

    @property
    def written_count(self):
        return len(self.rendered)

    @property
    def skipped_count(self):
        return len(self.skipped)


class SiteBuilder:
    def __init__(
        self,
        source_dir,
        output_dir,
        template=None,
        site_title="Site",
        index_title="Home",
        incremental=True,
        feed=True,
        site_url="",
        feed_limit=50,
    ):
        self.source_dir = os.path.abspath(source_dir)
        self.output_dir = os.path.abspath(output_dir)
        self.template_source = template if template is not None else DEFAULT_TEMPLATE
        self.site_title = site_title
        self.index_title = index_title
        self.incremental = incremental
        self.feed = feed
        self.site_url = site_url
        self.feed_limit = feed_limit
        self.manifest_path = os.path.join(self.output_dir, MANIFEST_NAME)

    # -- source discovery -------------------------------------------------
    def source_files(self):
        """Return markdown source files relative to the source dir (sorted)."""
        found = []
        for root, dirs, files in os.walk(self.source_dir):
            dirs[:] = sorted(
                d
                for d in dirs
                if not d.startswith(".")
                and os.path.abspath(os.path.join(root, d)) != self.output_dir
            )
            for name in files:
                if name.startswith("."):
                    continue
                if name.lower().endswith(_MARKDOWN_EXTENSIONS):
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, self.source_dir).replace(os.sep, "/")
                    found.append(rel)
        return sorted(found)

    def _load_page(self, rel_path):
        full = os.path.join(self.source_dir, rel_path)
        with open(full, "r", encoding="utf-8") as handle:
            raw = handle.read()
        metadata, body = parse_front_matter(raw)
        title = metadata.get("title")
        if not title:
            title = derive_title(body, rel_path)
        page = Page(
            source_path=rel_path,
            slug=slug_for(rel_path),
            title=str(title),
            body=body,
            content_html=render_markdown(body),
            metadata=metadata,
        )
        return page, _content_hash(raw)

    def load_pages(self):
        """Load every page. Returns ``(pages, hashes)``."""
        pages = []
        hashes = {}
        for rel in self.source_files():
            page, digest = self._load_page(rel)
            pages.append(page)
            hashes[rel] = digest
        return pages, hashes

    # -- manifest helpers -------------------------------------------------
    def _load_manifest(self):
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict) or data.get("version") != MANIFEST_VERSION:
            return {}
        return data

    def _config_signature(self):
        payload = "\x00".join(
            [
                self.template_source,
                self.site_title,
                self.index_title,
                str(self.feed),
                self.site_url,
                str(self.feed_limit),
            ]
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _nav_signature(pages):
        digest = hashlib.sha1()
        for page in sort_pages(pages):
            digest.update(
                "\x1f".join(
                    [
                        page.slug,
                        page.title,
                        str(page.in_nav),
                        str(page.order),
                        str(page.draft),
                        page.description,
                    ]
                ).encode("utf-8")
                + b"\n"
            )
        return digest.hexdigest()

    # -- building ---------------------------------------------------------
    def build(self):
        """Build the site, rendering only what changed when incremental."""
        os.makedirs(self.output_dir, exist_ok=True)
        pages, hashes = self.load_pages()
        manifest = self._load_manifest() if self.incremental else {}
        old_pages = manifest.get("pages", {}) if isinstance(manifest, dict) else {}

        config_sig = self._config_signature()
        nav_sig = self._nav_signature(pages)
        config_changed = manifest.get("config") != config_sig
        nav_changed = manifest.get("nav") != nav_sig
        full_rebuild = (
            (not self.incremental)
            or not manifest
            or config_changed
            or nav_changed
        )

        template = Template(self.template_source)
        result = BuildResult(self.output_dir, manifest_path=self.manifest_path)
        result.full_rebuild = full_rebuild
        result.pages = pages
        new_manifest_pages = {}

        for page in pages:
            rel = page.source_path
            digest = hashes[rel]
            prev = old_pages.get(rel)
            out_path = os.path.join(self.output_dir, page.slug)
            unchanged = (
                not full_rebuild
                and prev is not None
                and prev.get("hash") == digest
                and prev.get("slug") == page.slug
                and os.path.exists(out_path)
            )
            if unchanged:
                result.skipped.append(page.slug)
            else:
                html = self._render_page(page, pages, template)
                self._write(out_path, html)
                result.rendered.append(page.slug)
            new_manifest_pages[rel] = {"hash": digest, "slug": page.slug, "output": page.slug}

        # Remove outputs for sources that disappeared.
        for rel, prev in old_pages.items():
            if rel not in new_manifest_pages:
                stale = os.path.join(self.output_dir, prev.get("output", ""))
                if prev.get("output") and os.path.exists(stale):
                    os.remove(stale)
                    result.removed.append(prev.get("output"))

        # Index page (only when the source does not provide its own index.md).
        source_index = any(page.slug == "index.html" for page in pages)
        index_hash = None
        if not source_index:
            index_html_body = render_index(pages, title=self.index_title, site_title=self.site_title)
            index_page = Page(
                source_path="__index__",
                slug="index.html",
                title=self.index_title,
                content_html=index_html_body,
                metadata={"generated": True},
            )
            index_html = self._render_page(index_page, pages, template, current_slug="index.html")
            index_hash = _content_hash(index_html)
            index_out = os.path.join(self.output_dir, "index.html")
            if (
                not full_rebuild
                and manifest.get("index") == index_hash
                and os.path.exists(index_out)
            ):
                result.skipped.append("index.html")
            else:
                self._write(index_out, index_html)
                result.rendered.append("index.html")

        self._copy_assets()

        # RSS feed.
        feed_hash = None
        if self.feed:
            feed_xml = render_rss(
                pages,
                self.site_title,
                site_url=self.site_url,
                limit=self.feed_limit,
            )
            feed_hash = _content_hash(feed_xml)
            feed_out = os.path.join(self.output_dir, FEED_NAME)
            if (
                not full_rebuild
                and manifest.get("feed") == feed_hash
                and os.path.exists(feed_out)
            ):
                result.skipped.append(FEED_NAME)
            else:
                self._write(feed_out, feed_xml)
                result.rendered.append(FEED_NAME)

        new_manifest = {
            "version": MANIFEST_VERSION,
            "config": config_sig,
            "nav": nav_sig,
            "pages": new_manifest_pages,
            "index": index_hash,
            "feed": feed_hash,
        }
        with open(self.manifest_path, "w", encoding="utf-8") as handle:
            json.dump(new_manifest, handle, indent=2, sort_keys=True)
        return result

    def _render_page(self, page, pages, template, current_slug=None):
        slug = current_slug if current_slug is not None else page.slug
        context = {
            "title": page.title,
            "home_url": relative_url(slug, "index.html"),
            "site": {"title": self.site_title, "pages": pages},
            "page": {
                "title": page.title,
                "slug": page.slug,
                "url": page.url,
                "description": page.description,
                "metadata": page.metadata,
            },
            "nav": render_nav(pages, current_slug=slug),
            "content": page.content_html,
            "pages": pages,
        }
        return template.render(context)

    def _write(self, path, text):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def _copy_assets(self):
        """Copy non-markdown files (e.g. CSS) into the output directory."""
        for root, dirs, files in os.walk(self.source_dir):
            dirs[:] = sorted(
                d
                for d in dirs
                if not d.startswith(".")
                and os.path.abspath(os.path.join(root, d)) != self.output_dir
            )
            for name in files:
                if name.startswith(".") or name.lower().endswith(_MARKDOWN_EXTENSIONS):
                    continue
                full = os.path.join(root, name)
                rel = os.path.relpath(full, self.source_dir)
                target = os.path.join(self.output_dir, rel)
                os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
                shutil.copy2(full, target)

    def clean(self):
        """Remove all generated output (including the manifest)."""
        if os.path.isdir(self.output_dir):
            shutil.rmtree(self.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)


def _content_hash(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def build_site(source_dir, output_dir, **kwargs):
    """Convenience wrapper around :class:`SiteBuilder`."""
    return SiteBuilder(source_dir, output_dir, **kwargs).build()
