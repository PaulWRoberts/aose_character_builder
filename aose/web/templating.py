"""Markdown rendering for description surfaces + a Jinja templates factory.

Game-data descriptions (spells, items, class/race features) are authored in
Markdown.  We render them to HTML server-side and expose the renderer as a
Jinja ``markdown`` filter.  Content is our own trusted YAML data (local
single-user app, no untrusted input), so emitting safe HTML is fine.
"""
import functools

import markdown as _md
from fastapi.templating import Jinja2Templates


@functools.lru_cache(maxsize=None)
def render_markdown(text: str | None) -> str:
    """Render a Markdown string to HTML.

    Returns a plain ``str`` (not ``Markup``) so Jinja's autoescaping works
    correctly in both contexts:

    - Block content: ``{{ desc | markdown | safe }}`` — the ``safe`` filter
      opts in to rendering the tags as HTML.
    - Attribute values: ``{{ desc | markdown }}`` — Jinja escapes ``<`` →
      ``&lt;`` so the rendered HTML is safely embedded as an attribute string.

    Returns ``""`` for ``None``/empty input.  Cached because descriptions are
    static catalog data — the same string renders identically on every request.
    """
    if not text:
        return ""
    return _md.markdown(text, extensions=["tables", "sane_lists"])


def make_templates(directory: str) -> Jinja2Templates:
    """Build a ``Jinja2Templates`` with the ``markdown`` filter registered."""
    templates = Jinja2Templates(directory=directory)
    templates.env.filters["markdown"] = render_markdown
    return templates
