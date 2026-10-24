"""Generation of the site index page."""

from .nav import relative_url, sort_pages
from .template import Template

__all__ = ["render_index", "DEFAULT_INDEX_TEMPLATE"]

DEFAULT_INDEX_TEMPLATE = """<h1>{{ title }}</h1>
<ul class="page-list">
{% for page in pages %}  <li class="page-list__item">
    <a href="{{ page.href }}">{{ page.title }}</a>{% if page.description %} &mdash; <span class="page-list__summary">{{ page.description }}</span>{% endif %}
  </li>
{% endfor %}</ul>
"""


def render_index(pages, title="Home", site_title=None, template=None):
    """Render the index body listing every visible page.

    Drafts are omitted. Links are computed relative to the index page, which
    always lives at the site root.
    """
    visible = [page for page in sort_pages(pages) if not page.draft]
    items = [
        {
            "title": page.title,
            "href": relative_url("index.html", page.url),
            "description": page.description,
        }
        for page in visible
    ]
    source = template if template is not None else DEFAULT_INDEX_TEMPLATE
    return Template(source).render(
        {
            "title": title,
            "site_title": site_title or title,
            "pages": items,
        }
    )
