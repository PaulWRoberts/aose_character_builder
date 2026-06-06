# Rendered-Markdown Descriptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the Markdown in feature / spell / item descriptions to HTML at every description surface on the live sheet, styled in the OSR-zine system, so tables, bold, lists, and paragraphs read well instead of printing as raw text.

**Architecture:** Add a server-side Markdown→HTML renderer (`render_markdown`) exposed as a Jinja `markdown` filter via a shared `make_templates()` factory used by all three template environments. Description render sites swap `{{ text }}` for `{{ text | markdown }}` wrapped in a `.prose` container; the shared feature modal pre-renders HTML and `fill()` injects it via `innerHTML`. A `.prose` CSS block styles the output. Content is our own trusted game data (local single-user app, no untrusted input), so emitting safe HTML carries no XSS exposure.

**Tech Stack:** Python 3.11, FastAPI, Jinja2, Pydantic v2, Python-Markdown (`markdown` lib, `tables` + `sane_lists` extensions). Tests via pytest + `fastapi.testclient.TestClient`.

**Spec:** [docs/superpowers/specs/2026-06-05-markdown-descriptions-design.md](../specs/2026-06-05-markdown-descriptions-design.md)

---

## File map

| File | Change |
|---|---|
| `pyproject.toml` | Add `markdown>=3.5` to the `web` optional-dependencies group |
| `aose/web/templating.py` | **New** — `render_markdown()` + `make_templates()` factory |
| `aose/web/routes.py` | Use `make_templates(str(TEMPLATES_DIR))` instead of bare `Jinja2Templates(...)` |
| `aose/web/wizard.py` | Same one-line swap |
| `aose/web/settings_routes.py` | Same one-line swap |
| `aose/web/templates/sheet.html` | Markdown-render item modal, spell modal, and feature-modal `data-text` |
| `aose/web/templates/_detail_card.html` | Markdown-render `card.description` |
| `aose/web/static/sheet_overlays.js` | Feature-modal body: `textContent` → `innerHTML` for `[data-role="text"]` |
| `aose/web/static/sheet.css` | Add `.prose` block; drop `white-space: pre-wrap` from `.detail-desc` |
| `tests/test_markdown_filter.py` | **New** — unit tests for `render_markdown` |
| `tests/test_web.py` | Add render smoke tests (thief skills table modal; spell modal HTML) |

---

### Task 1: Markdown renderer module + dependency

**Files:**
- Modify: `pyproject.toml`
- Create: `aose/web/templating.py`
- Test: `tests/test_markdown_filter.py`

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, find the `web = [...]` block under `[project.optional-dependencies]` and add `"markdown>=3.5",` to the list:

```toml
web = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "jinja2>=3.1",
    "python-multipart",
    "markdown>=3.5",
]
```

- [ ] **Step 2: Install it into the venv**

Run: `.venv\Scripts\python.exe -m pip install "markdown>=3.5"`
Expected: installs `markdown` (and `markupsafe`, already present via Jinja).

- [ ] **Step 3: Write the failing tests**

Create `tests/test_markdown_filter.py`:

```python
from markupsafe import Markup

from aose.web.templating import render_markdown


def test_bold_renders_strong():
    out = render_markdown("This is **bold** text.")
    assert "<strong>bold</strong>" in out


def test_pipe_table_renders_table():
    md = (
        "| Level | CS |\n"
        "|---|---|\n"
        "| 1 | 87 |\n"
        "| 2 | 88 |\n"
    )
    out = render_markdown(md)
    assert "<table>" in out
    assert "<th>Level</th>" in out
    assert "<td>87</td>" in out


def test_blank_line_separates_paragraphs():
    out = render_markdown("First para.\n\nSecond para.")
    assert out.count("<p>") == 2


def test_none_and_empty_render_empty_markup():
    assert render_markdown(None) == Markup("")
    assert render_markdown("") == Markup("")


def test_return_type_is_markup():
    out = render_markdown("plain")
    assert isinstance(out, Markup)
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_markdown_filter.py -q`
Expected: FAIL — `aose.web.templating` does not exist (ModuleNotFoundError).

- [ ] **Step 5: Implement the module**

Create `aose/web/templating.py`:

```python
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
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_markdown_filter.py -q`
Expected: PASS (5 tests).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml aose/web/templating.py tests/test_markdown_filter.py
git commit -m "feat(web): markdown renderer + templates factory with markdown filter"
```

---

### Task 2: Wire the filter into all three template environments

**Files:**
- Modify: `aose/web/routes.py` (~line 96)
- Modify: `aose/web/wizard.py` (~line 108)
- Modify: `aose/web/settings_routes.py` (~line 14)
- Test: `tests/test_web.py` (existing `client` fixture covers render paths)

Each module builds its own module-level `templates = Jinja2Templates(directory=str(TEMPLATES_DIR))`. Swap each for the factory so the `markdown` filter is registered in every env.

- [ ] **Step 1: Update `routes.py`**

In `aose/web/routes.py`, add the import near the other `aose.web` / `aose.sheet` imports (around line 88-89):

```python
from aose.web.templating import make_templates
```

Then replace line ~96:

```python
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
```

with:

```python
templates = make_templates(str(TEMPLATES_DIR))
```

The existing `from fastapi.templating import Jinja2Templates` import can stay (harmless) or be removed if no longer referenced — leave it to minimise diff noise.

- [ ] **Step 2: Update `wizard.py`**

In `aose/web/wizard.py`, add near the top imports:

```python
from aose.web.templating import make_templates
```

Replace line ~108 `templates = Jinja2Templates(directory=str(TEMPLATES_DIR))` with:

```python
templates = make_templates(str(TEMPLATES_DIR))
```

- [ ] **Step 3: Update `settings_routes.py`**

In `aose/web/settings_routes.py`, add near the top imports:

```python
from aose.web.templating import make_templates
```

Replace line ~14 `templates = Jinja2Templates(directory=str(TEMPLATES_DIR))` with:

```python
templates = make_templates(str(TEMPLATES_DIR))
```

- [ ] **Step 4: Verify the filter is live and nothing regressed**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py -q`
Expected: PASS — existing sheet/index/wizard render tests still pass (the filter is registered but not yet used by any template).

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py aose/web/wizard.py aose/web/settings_routes.py
git commit -m "feat(web): register markdown Jinja filter in all template envs"
```

---

### Task 3: Render Markdown in item & spell modals + detail card

**Files:**
- Modify: `aose/web/templates/sheet.html` (item modal ~line 10; spell modal ~line 565)
- Modify: `aose/web/templates/_detail_card.html` (~line 14)
- Test: `tests/test_web.py`

- [ ] **Step 1: Write the failing smoke test**

Append to `tests/test_web.py`:

```python
def test_spell_modal_renders_markdown(tmp_path):
    """A caster's spell modal body renders Markdown as HTML (paragraphs)."""
    from fastapi.testclient import TestClient
    from aose.characters import save_character
    from aose.models import CharacterSpec, ClassEntry
    from aose.web.app import create_app

    characters_dir = tmp_path / "characters"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir, drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir, settings_path=tmp_path / "settings.json",
    )
    spec = CharacterSpec(
        name="Merlin",
        abilities={"STR": 9, "INT": 16, "WIS": 9, "DEX": 12, "CON": 10, "CHA": 9},
        race_id="human",
        classes=[ClassEntry(class_id="magic_user", level=1, hp_rolls=[4],
                            spellbook=["magic_user_charm_person"])],
        alignment="neutral",
    )
    save_character("merlin", spec, characters_dir)
    body = TestClient(app).get("/character/merlin").text
    # Charm Person's description is multi-paragraph Markdown → rendered <p> tags,
    # not raw text dropped into a single <p>.
    assert "modal-spell-magic_user-magic_user_charm_person" in body
    assert "<p>A single human" in body
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_spell_modal_renders_markdown -q`
Expected: FAIL — the description currently renders as escaped text inside one hand-rolled `<p>`, so `<p>A single human` (Markdown's own paragraph tag) is absent.

- [ ] **Step 3: Update the item modal**

In `aose/web/templates/sheet.html`, find line ~10:

```jinja
    {% if row.description %}<p style="font-size:15px;margin:0 0 12px">{{ row.description }}</p>{% endif %}
```

Replace with:

```jinja
    {% if row.description %}<div class="prose">{{ row.description | markdown }}</div>{% endif %}
```

- [ ] **Step 4: Update the spell modal**

In `aose/web/templates/sheet.html`, find line ~565:

```jinja
    <p style="font-size:15px;margin:0 0 12px">{{ row.description }}</p>
```

Replace with:

```jinja
    <div class="prose">{{ row.description | markdown }}</div>
```

- [ ] **Step 5: Update the detail card macro**

In `aose/web/templates/_detail_card.html`, find line ~14:

```jinja
  {% if card.description %}<p class="detail-desc">{{ card.description }}</p>{% endif %}
```

Replace with:

```jinja
  {% if card.description %}<div class="detail-desc prose">{{ card.description | markdown }}</div>{% endif %}
```

- [ ] **Step 6: Run the smoke test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_spell_modal_renders_markdown -q`
Expected: PASS.

- [ ] **Step 7: Run the full web test file**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add aose/web/templates/sheet.html aose/web/templates/_detail_card.html tests/test_web.py
git commit -m "feat(sheet): render Markdown in item/spell modals and detail cards"
```

---

### Task 4: Render Markdown in the shared feature modal

**Files:**
- Modify: `aose/web/templates/sheet.html` (feature triggers ~lines 148, 154, 174, 325)
- Modify: `aose/web/static/sheet_overlays.js` (the `fill()` function, ~line 11)
- Test: `tests/test_web.py`

The feature modal (`#modal-feature`) is shared; triggers pass the body text via `data-text`, and `fill()` assigns it with `textContent`. We pre-render the Markdown into `data-text` (Jinja escapes it into the attribute; `el.dataset.text` decodes it back on read) and switch the body assignment to `innerHTML`.

- [ ] **Step 1: Write the failing smoke test**

Append to `tests/test_web.py`:

```python
def test_feature_modal_renders_table_markdown(tmp_path):
    """The thief 'Thief Skills' feature carries rendered <table> HTML in data-text."""
    from fastapi.testclient import TestClient
    from aose.characters import save_character
    from aose.models import CharacterSpec, ClassEntry
    from aose.web.app import create_app

    characters_dir = tmp_path / "characters"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir, drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir, settings_path=tmp_path / "settings.json",
    )
    spec = CharacterSpec(
        name="Sneak",
        abilities={"STR": 9, "INT": 10, "WIS": 9, "DEX": 14, "CON": 10, "CHA": 9},
        race_id="human",
        classes=[ClassEntry(class_id="thief", level=1, hp_rolls=[4])],
        alignment="neutral",
    )
    save_character("sneak", spec, characters_dir)
    body = TestClient(app).get("/character/sneak").text
    # The pipe table is rendered to HTML and escaped into the data-text attribute,
    # so the escaped opening tag appears in the markup.
    assert "&lt;table&gt;" in body
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_feature_modal_renders_table_markdown -q`
Expected: FAIL — `data-text` currently holds the raw Markdown table (escaped pipes), no `<table>`.

- [ ] **Step 3: Markdown-render the feature `data-text` attributes**

In `aose/web/templates/sheet.html`, update the four feature-trigger `data-text` attributes to pipe through the filter:

Line ~148 (race features):

```jinja
            <li class="info" data-modal="modal-feature" data-title="{{ f.name }}" data-text="{{ f.text | markdown }}">
```

Line ~154 (class features):

```jinja
            <li class="info" data-modal="modal-feature" data-title="{{ f.name }}" data-text="{{ f.text | markdown }}">
```

Line ~174 (weapon-proficiency chips) — this body is a plain interpolated sentence, not authored Markdown. Wrap it so the output is still HTML for the `innerHTML` path:

```jinja
                    data-text="{{ (('Weapon specialisation: +1 to hit and +1 damage with the ' ~ w.name ~ '.') if w.specialised else 'Proficient — no non-proficiency penalty.') | markdown }}">
```

Line ~325 (worn magic items):

```jinja
            <li class="info" data-modal="modal-feature" data-title="{{ mi.name }}" data-text="{{ (mi.description or '') | markdown }}">
```

- [ ] **Step 4: Switch the feature-modal body to `innerHTML`**

In `aose/web/static/sheet_overlays.js`, find the `fill()` function (~lines 9-13). Replace the `[data-role="text"]` line:

```js
    panel.querySelectorAll('[data-role="text"]').forEach(el => { if (t.text) el.textContent = t.text; });
```

with:

```js
    panel.querySelectorAll('[data-role="text"]').forEach(el => { if (t.text) el.innerHTML = t.text; });
```

Leave the `[data-role="title"]` and `[data-role="ability"]` lines as `textContent`.

- [ ] **Step 5: Run the smoke test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_feature_modal_renders_table_markdown -q`
Expected: PASS.

- [ ] **Step 6: Run the full web test file**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add aose/web/templates/sheet.html aose/web/static/sheet_overlays.js tests/test_web.py
git commit -m "feat(sheet): render Markdown in the shared feature modal (innerHTML body)"
```

---

### Task 5: `.prose` styling

**Files:**
- Modify: `aose/web/static/sheet.css` (add `.prose` block above the `LEGACY / SITE-WIDE` banner ~line 325; fix `.detail-desc` ~line 321)

No new tests — this is presentational. Verified visually in Task 6.

- [ ] **Step 1: Drop the obsolete `pre-wrap` on `.detail-desc`**

In `aose/web/static/sheet.css`, find line ~321:

```css
.detail-desc { margin: 0; font-size: 13px; white-space: pre-wrap; color: var(--ink-2); }
```

Replace with (the body is now real block HTML, not whitespace-significant text):

```css
.detail-desc { margin: 0; font-size: 13px; color: var(--ink-2); }
```

- [ ] **Step 2: Add the `.prose` block**

In `aose/web/static/sheet.css`, immediately **above** the `LEGACY / SITE-WIDE` banner comment (~line 325), insert:

```css
/* Rendered-Markdown prose (feature / spell / item descriptions). Zine tokens only. */
.prose { font-size: 14px; line-height: 1.5; color: var(--ink); }
.prose > :first-child { margin-top: 0; }
.prose > :last-child { margin-bottom: 0; }
.prose p { margin: 0 0 10px; }
.prose strong { font-weight: 700; }
.prose em { font-style: italic; }
.prose ul, .prose ol { margin: 0 0 10px; padding-left: 20px; }
.prose li { margin: 2px 0; }
.prose table {
  border-collapse: collapse;
  margin: 4px 0 12px;
  font-size: 13px;
  font-variant-numeric: tabular-nums lining;
}
.prose th, .prose td {
  border: 1px solid var(--hair);
  padding: 3px 8px;
  text-align: center;
}
.prose th {
  font-family: var(--display);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-size: 11px;
  background: var(--ink);
  color: #f7f5ed;  /* same light text the zine inked bars (.bar, .ident) use */
}
/* Wide tables (e.g. the 8-column thief-skills matrix) scroll instead of
   overflowing a fixed-width modal. */
.prose { overflow-x: auto; }
```

(Token reference: `--ink` #18160f, `--hair` #cdc8b6, `--display` Oswald, `--ink-2` #3a362c are all defined in the `:root` block; inked bars use the literal `#f7f5ed` for light text, so the header row matches them.)

- [ ] **Step 3: Commit**

```bash
git add aose/web/static/sheet.css
git commit -m "style(sheet): .prose styling for rendered-Markdown descriptions"
```

---

### Task 6: Verification + manual smoke

**Files:** none (verification only)

- [ ] **Step 1: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing pytest-current PermissionError on Windows).

- [ ] **Step 2: Start the dev server**

Run: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
Expected: server up on http://127.0.0.1:8000.

- [ ] **Step 3: Manual smoke checklist**

Open a character sheet and verify:
- A **class/race feature** modal (e.g. a thief's "Thief Skills Chance of Success") shows a real bordered table with an inked header row, not raw pipes.
- A multi-paragraph **spell** modal (e.g. Charm Person) shows separated paragraphs, not one run-on line.
- An **item** modal description with emphasis shows **bold** rendered.
- Existing modal controls (cast/restore/clear, buy/equip, close ×) still work — the feature modal's `innerHTML` body did not break the overlay buttons.
- A wide table in a modal scrolls horizontally rather than overflowing the panel.

- [ ] **Step 4: Confirm static assets refresh**

Hard-refresh the browser (static is served `no-cache`); confirm the CSS/JS changes are live without a server restart.

- [ ] **Step 5: Final commit (if any verification fixups were needed)**

```bash
git add -A
git commit -m "fix(sheet): markdown description rendering verification fixups"
```

(Skip if nothing changed.)

---

## Self-review against the spec

**Spec coverage**

- ✅ Dependency `markdown>=3.5` in `web` group — Task 1.
- ✅ `render_markdown` (Markup, lru_cache, tables+sane_lists, None/empty handling) — Task 1.
- ✅ `make_templates` factory wired into routes/wizard/settings — Task 2.
- ✅ Item modal, spell modal, detail-card description rendered — Task 3.
- ✅ Feature modal (class/race features, magic-item descriptions) rendered + `innerHTML` switch — Task 4.
- ✅ `.prose` zine CSS above legacy banner; `.detail-desc` pre-wrap removed — Task 5.
- ✅ Unit tests (bold, table, paragraphs, None/empty, Markup type) — Task 1.
- ✅ Render smoke tests (spell paragraphs, thief table in feature modal) — Tasks 3, 4.
- ✅ Non-goals respected: no YAML migration; one-surface overlay model untouched except the single body-assignment line; new CSS above legacy banner.

**Placeholder scan:** None. The only conditional instruction is the `--paper` token fallback in Task 5 Step 2, which gives an explicit resolution procedure (inspect `:root`).

**Type consistency:** `render_markdown(text) -> Markup` and `make_templates(directory: str) -> Jinja2Templates` are used identically across Tasks 1, 2, 3, 4. The `markdown` filter name matches between registration (Task 1/2) and every `| markdown` use (Tasks 3, 4). Modal id `modal-spell-magic_user-magic_user_charm_person` in the Task 3 test matches the existing `modal-spell-{class_id}-{spell_id}-{n|r}` template pattern.
