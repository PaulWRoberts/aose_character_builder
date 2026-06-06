"""Markdown rendering for description surfaces + a Jinja templates factory.

Game-data descriptions (spells, items, class/race features) are authored in
Markdown.  We render them to HTML server-side and expose the renderer as a
Jinja ``markdown`` filter.  Content is our own trusted YAML data (local
single-user app, no untrusted input), so emitting safe HTML is fine.
"""
import functools

import markdown as _md
from fastapi.templating import Jinja2Templates
from markupsafe import Markup


@functools.lru_cache(maxsize=None)
def render_markdown(text: str | None) -> Markup:
    """Render a Markdown string to safe HTML.

    Returns an empty ``Markup`` for ``None``/empty input.  Cached because
    descriptions are static catalog data — the same string renders identically
    on every request.
    """
    if not text:
        return Markup("")
    html = _md.markdown(text, extensions=["tables", "sane_lists"])
    return Markup(html)


def make_templates(directory: str) -> Jinja2Templates:
    """Build a ``Jinja2Templates`` with the ``markdown`` filter registered."""
    templates = Jinja2Templates(directory=directory)
    templates.env.filters["markdown"] = render_markdown
    return templates
