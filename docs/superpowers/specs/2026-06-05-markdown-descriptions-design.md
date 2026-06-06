# Rendered-Markdown descriptions — design

**Date:** 2026-06-05
**Status:** Approved (brainstorming)

## Problem

On the live character sheet, clicking a class/race feature, an item, or a spell
opens a modal whose body is the entity's `description` / feature `text`. These
strings are authored in **Markdown** — pipe tables (e.g. the thief "Thief Skills
Chance of Success" matrix), `**bold**`, blank-line-separated paragraphs, and
`▶` bullet lines. Every render site drops them straight into `<p>{{ text }}</p>`.

Two things break:

1. **Jinja autoescaping** turns Markdown markup into literal characters — `**x**`
   prints with the asterisks, a pipe table prints as raw `| Level | CS | ... |`
   rows.
2. **HTML whitespace collapse** flattens the blank-line paragraph breaks, so
   multi-paragraph descriptions run together on one line.

Result: descriptions are hard to read, nothing is emphasised, and tables are
unusable.

## Goal

Render the Markdown to HTML at every description surface and style the output in
the existing OSR-zine design system, so descriptions read well — bold emphasis,
separated paragraphs, lists, and proper tables.

## Scope

In scope — every place a description / feature text renders:

- **Feature modal** (`sheet.html` → shared `#modal-feature`): class features,
  racial features, magic-item descriptions (all routed through `data-text`).
- **Per-item modals** (`sheet.html` → `modal-item-*`).
- **Per-spell modals** (`sheet.html` → `modal-spell-*`).
- **Inline detail cards** (`_detail_card.html` macro → `DetailCard.description`),
  the in-progress drawer-expander feature. Only the card's *description*
  rendering is touched.

Out of scope:

- Rewriting the YAML data. Markdown stays the authoring format; we render it,
  we don't migrate it.
- The inline-card toggle JS/CSS still mid-implementation in
  `2026-06-05-inline-detail-cards.md` — untouched except for the description
  render inside the shared macro.
- Wizard description surfaces that already read well, and the `DetailCard.stats`
  lines (already pre-formatted plain strings).

## Architecture

The content is our own game data (`data/**.yaml`), authored by us. The app is a
local-only single-user tool with no auth model and no untrusted input, so
emitting trusted HTML from these descriptions carries no XSS exposure. We render
server-side and mark the output safe.

### 1. Dependency

Add `markdown>=3.5` to the **`web`** optional-dependencies group in
`pyproject.toml` (alongside fastapi / uvicorn / jinja2 — it is only needed by the
web render layer). Python-Markdown is the standard, well-tested renderer and
ships a first-party `tables` extension.

### 2. Renderer module — `aose/web/templating.py` (new)

```python
import functools
import markdown as _md
from markupsafe import Markup
from fastapi.templating import Jinja2Templates

@functools.lru_cache(maxsize=None)
def render_markdown(text: str | None) -> Markup:
    if not text:
        return Markup("")
    html = _md.markdown(text, extensions=["tables", "sane_lists"])
    return Markup(html)

def make_templates(directory: str) -> Jinja2Templates:
    templates = Jinja2Templates(directory=directory)
    templates.env.filters["markdown"] = render_markdown
    return templates
```

- `render_markdown` returns `markupsafe.Markup` so Jinja does **not** re-escape
  the rendered HTML.
- `lru_cache` — descriptions are static catalog data; the same string renders
  identically every request. The cache is keyed by the input string.
- `▶` bullet lines are literal text separated by blank lines; Markdown renders
  each as its own `<p>`, which reads fine. No special handling.

### 3. Wire the filter into every template env

`routes.py`, `wizard.py`, and `settings_routes.py` each currently construct their
own `Jinja2Templates(directory=str(TEMPLATES_DIR))`. Each switches to
`make_templates(str(TEMPLATES_DIR))` so the `markdown` filter is available in
every render path. (Three call sites; `TEMPLATES_DIR` stays defined where it is.)

### 4. Template edits

Markdown output already wraps block content in its own `<p>` / `<table>` / `<ul>`,
so the hand-rolled `<p style=...>` wrappers are replaced by a `<div class="prose">`
container to avoid invalid `<p><p>` nesting.

| Site | File | Change |
|---|---|---|
| Per-item modal body | `sheet.html` (~line 9) | `<div class="prose">{{ row.description \| markdown }}</div>` |
| Per-spell modal body | `sheet.html` (~line 565) | `<div class="prose">{{ row.description \| markdown }}</div>` |
| Detail card description | `_detail_card.html` (~line 14) | `<div class="detail-desc prose">{{ card.description \| markdown }}</div>` |
| Feature modal triggers | `sheet.html` (data-text sites) | `data-text="{{ f.text \| markdown }}"` (and `mi.description`, racial `text`) |

### 5. Feature modal — `sheet_overlays.js`

The shared `#modal-feature` is populated by `fill()` from the trigger's
`dataset`. Today `[data-role="text"]` is set via `textContent`. Since the trigger
now passes **pre-rendered HTML** in `data-text` (Jinja escapes it into the
attribute; `el.dataset.text` decodes it back to the HTML string on read), `fill()`
switches that one assignment to `innerHTML`:

```js
panel.querySelectorAll('[data-role="text"]').forEach(el => { if (t.text) el.innerHTML = t.text; });
```

`[data-role="title"]` and `[data-role="ability"]` stay `textContent`. This is the
only behavioral JS change and is scoped to the feature modal's body.

### 6. Styling — `sheet.css`

One `.prose` block added **above** the `LEGACY / SITE-WIDE` banner, using existing
zine tokens only (no new variables):

- `.prose p` — body font, paragraph spacing, last-child margin reset.
- `.prose strong` — bold emphasis.
- `.prose ul`, `.prose ol` — list indentation/spacing.
- `.prose table` — collapsed hairline rules, an inked header row (display font,
  uppercase/tracked), `font-variant-numeric: tabular-nums lining` on cells so
  number columns align. Wide tables (the 8-column thief matrix) get horizontal
  scroll within the modal rather than overflowing it.

## Testing

- `tests/test_markdown_filter.py` — unit tests for `render_markdown`:
  - `**bold**` → contains `<strong>bold</strong>`.
  - a pipe table → contains `<table>` and `<th>`.
  - multi-paragraph input → contains two `<p>` blocks.
  - `None` and `""` → `Markup("")`.
  - return type is `markupsafe.Markup` (so Jinja won't double-escape).
- A template render smoke test (style of existing sheet tests): a thief
  character's "Thief Skills Chance of Success" feature trigger carries a
  `data-text` containing `<table>`; a caster's spell modal body contains `<p>`
  (and `<strong>` where the source uses it).

## Non-goals / invariants preserved

- No YAML data migration. Markdown remains the authoring format.
- Static files stay `no-cache`; CSS/JS edits show on refresh under `--reload`.
- New zine CSS stays above the legacy banner.
- The one-surface-open overlay model and `sheet_overlays.js` control flow are
  unchanged apart from the single `textContent`→`innerHTML` line for the feature
  modal body.
- `@media print` still degrades gracefully — `.prose` is plain block HTML.
