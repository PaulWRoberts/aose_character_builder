# Other Possessions + Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two sheet-only free-text fields to a character — a list of discrete "other possessions" entries (untracked implied items like "a bronze key") and a single open-ended notes block.

**Architecture:** Two new fields on `CharacterSpec` (`other_possessions: list[str]`, `notes: str`). A tiny pure engine module (`aose/engine/possessions.py`) owns the possessions add/remove mutators (mirrors `valuables.py`). Three FastAPI routes mutate-and-save. The sheet view copies both fields straight through; `sheet.html` (interactive) and `sheet_print.html` (read-only) render them. No derivations, no weight, no value.

**Tech Stack:** Python, FastAPI, Pydantic v2, Jinja2, pytest.

---

### Task 1: Model fields on `CharacterSpec`

**Files:**
- Modify: `aose/models/character.py` (add two fields to `CharacterSpec`, around line 191–199, after `secondary_skill`)
- Test: `tests/test_possessions.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_possessions.py`:

```python
"""Other-possessions + notes: model defaults and engine mutators."""
import pytest

from aose.models import CharacterSpec, ClassEntry


def _fighter(**kw):
    return CharacterSpec(
        name="Bran",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral", **kw,
    )


def test_new_fields_default_empty():
    spec = _fighter()
    assert spec.other_possessions == []
    assert spec.notes == ""


def test_fields_round_trip():
    spec = _fighter(other_possessions=["a bronze key"], notes="hello")
    reloaded = CharacterSpec.model_validate(spec.model_dump())
    assert reloaded.other_possessions == ["a bronze key"]
    assert reloaded.notes == "hello"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_possessions.py -q`
Expected: FAIL — `ValidationError`/`extra="forbid"` rejects `other_possessions` / `notes`.

- [ ] **Step 3: Add the fields**

In `aose/models/character.py`, inside `CharacterSpec`, immediately after the `secondary_skill: str | None = None` line, add:

```python
    # Free-text "other possessions" — discrete entries, each an implied item the
    # DM handed out ("a bronze key"). Untracked: no weight, value, or encumbrance.
    other_possessions: list[str] = Field(default_factory=list)
    # Open-ended scratch notes, unrelated to inventory.
    notes: str = ""
```

(`Field` is already imported at the top of the file.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_possessions.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/models/character.py tests/test_possessions.py
git commit -m "feat: add other_possessions + notes fields to CharacterSpec"
```

---

### Task 2: Engine module `aose/engine/possessions.py`

**Files:**
- Create: `aose/engine/possessions.py`
- Test: `tests/test_possessions.py` (append engine tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_possessions.py`:

```python
from aose.engine import possessions
from aose.engine.possessions import PossessionError


def test_add_possession_appends_trimmed():
    assert possessions.add_possession([], "  a bronze key  ") == ["a bronze key"]


def test_add_possession_skips_empty():
    assert possessions.add_possession(["x"], "   ") == ["x"]


def test_add_possession_allows_duplicates():
    assert possessions.add_possession(["key"], "key") == ["key", "key"]


def test_add_possession_returns_new_list():
    original = ["x"]
    result = possessions.add_possession(original, "y")
    assert original == ["x"]            # not mutated in place
    assert result == ["x", "y"]


def test_remove_possession_by_index():
    assert possessions.remove_possession(["a", "b", "c"], 1) == ["a", "c"]


def test_remove_possession_bad_index_raises():
    with pytest.raises(PossessionError):
        possessions.remove_possession(["a"], 5)
    with pytest.raises(PossessionError):
        possessions.remove_possession(["a"], -1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_possessions.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aose.engine.possessions'`.

- [ ] **Step 3: Create the engine module**

Create `aose/engine/possessions.py`:

```python
"""Other possessions — the cycle-free core for free-text "implied item" entries.

Each entry is a plain untracked string ("a bronze key"); no weight, value, or
encumbrance.  Mutators return new lists (no in-place mutation) and raise
``PossessionError`` on bad input; routes map it to HTTP 400.  Imports nothing
from the codebase; nothing imports it back.
"""
from __future__ import annotations


class PossessionError(ValueError):
    """Invalid other-possessions mutation (routes map to HTTP 400)."""


def add_possession(items: list[str], text: str) -> list[str]:
    """Return a new list with ``text`` (trimmed) appended.  Empty or
    whitespace-only input is ignored (the list is returned unchanged)."""
    text = text.strip()
    if not text:
        return list(items)
    return [*items, text]


def remove_possession(items: list[str], index: int) -> list[str]:
    """Return a new list with the entry at ``index`` removed.  An out-of-range
    index raises ``PossessionError``."""
    if index < 0 or index >= len(items):
        raise PossessionError(f"no possession at index {index}")
    return [*items[:index], *items[index + 1:]]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_possessions.py -q`
Expected: PASS (all possession tests pass).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/possessions.py tests/test_possessions.py
git commit -m "feat: add possessions engine (add/remove free-text entries)"
```

---

### Task 3: Routes

**Files:**
- Modify: `aose/web/routes.py` (add 3 routes; add `from aose.engine import possessions as possessions_engine` and `from aose.engine.possessions import PossessionError` near the other engine imports around line 77–78)
- Test: `tests/test_possessions_routes.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_possessions_routes.py`:

```python
"""HTTP route tests for other-possessions + notes sheet actions."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character
from aose.models import CharacterSpec, ClassEntry
from aose.web.app import create_app

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    app = create_app(
        data_dir=DATA_DIR, characters_dir=characters_dir, drafts_dir=drafts_dir,
        examples_dir=examples_dir, settings_path=tmp_path / "settings.json",
    )
    c = TestClient(app, follow_redirects=False)
    c._characters_dir = characters_dir
    return c


def _save_fighter(client):
    spec = CharacterSpec(
        name="Bran",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
    )
    save_character("bran", spec, client._characters_dir)
    return spec


def test_possession_add_route(client):
    _save_fighter(client)
    r = client.post("/character/bran/possessions/add",
                    data={"text": "a bronze key"})
    assert r.status_code == 303
    spec = load_character("bran", client._characters_dir)
    assert spec.other_possessions == ["a bronze key"]


def test_possession_add_blank_is_noop(client):
    _save_fighter(client)
    client.post("/character/bran/possessions/add", data={"text": "   "})
    spec = load_character("bran", client._characters_dir)
    assert spec.other_possessions == []


def test_possession_remove_route(client):
    _save_fighter(client)
    client.post("/character/bran/possessions/add", data={"text": "key"})
    client.post("/character/bran/possessions/add", data={"text": "map"})
    client.post("/character/bran/possessions/remove", data={"index": 0})
    spec = load_character("bran", client._characters_dir)
    assert spec.other_possessions == ["map"]


def test_possession_remove_bad_index_400(client):
    _save_fighter(client)
    r = client.post("/character/bran/possessions/remove", data={"index": 9})
    assert r.status_code == 400


def test_notes_set_route(client):
    _save_fighter(client)
    r = client.post("/character/bran/notes/set",
                    data={"notes": "met a talking owl"})
    assert r.status_code == 303
    spec = load_character("bran", client._characters_dir)
    assert spec.notes == "met a talking owl"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_possessions_routes.py -q`
Expected: FAIL — 404/405 (routes do not exist yet).

- [ ] **Step 3: Add the engine import**

In `aose/web/routes.py`, near the existing `from aose.engine import valuables as valuables_engine` / `from aose.engine.valuables import ValuableError` lines (around 77–78), add:

```python
from aose.engine import possessions as possessions_engine
from aose.engine.possessions import PossessionError
```

- [ ] **Step 4: Add the three routes**

In `aose/web/routes.py`, after the jewellery routes (after the `sheet_jewellery_remove` handler, near line 1130), add:

```python
@router.post("/character/{character_id}/possessions/add")
async def sheet_possession_add(request: Request, character_id: str,
                               text: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    spec.other_possessions = possessions_engine.add_possession(
        spec.other_possessions, text)
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/possessions/remove")
async def sheet_possession_remove(request: Request, character_id: str,
                                  index: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.other_possessions = possessions_engine.remove_possession(
            spec.other_possessions, index)
    except PossessionError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/notes/set")
async def sheet_notes_set(request: Request, character_id: str,
                          notes: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    spec.notes = notes
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

(`Request`, `Form`, `HTTPException`, `RedirectResponse`, `_load_spec_or_404`, and `save_character` are all already imported/defined in this module — confirmed by the existing gem/jewellery routes.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_possessions_routes.py -q`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add aose/web/routes.py tests/test_possessions_routes.py
git commit -m "feat: add possessions add/remove + notes set routes"
```

---

### Task 4: Sheet view passthrough

**Files:**
- Modify: `aose/sheet/view.py` — add two fields to `CharacterSheet` (after `valuables`, around line 265–266) and populate them in the `build_sheet(...)` return (after `valuables=valuables_view(spec)`, around line 853)
- Test: `tests/test_possessions.py` (append a build_sheet test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_possessions.py`:

```python
from pathlib import Path

from aose.data.loader import GameData
from aose.sheet.view import build_sheet

DATA_DIR = Path(__file__).parent.parent / "data"


def test_build_sheet_passes_through_fields():
    data = GameData.load(DATA_DIR)
    spec = _fighter(other_possessions=["a bronze key"], notes="scratch")
    sheet = build_sheet(spec, data)
    assert sheet.other_possessions == ["a bronze key"]
    assert sheet.notes == "scratch"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_possessions.py::test_build_sheet_passes_through_fields -q`
Expected: FAIL — `CharacterSheet` has no `other_possessions` / `notes` attribute.

- [ ] **Step 3: Add the fields to `CharacterSheet`**

In `aose/sheet/view.py`, inside the `CharacterSheet` model, after the `valuables: ValuablesView = Field(...)` block (around line 266), add:

```python
    other_possessions: list[str] = Field(default_factory=list)
    notes: str = ""
```

- [ ] **Step 4: Populate them in `build_sheet`**

In `aose/sheet/view.py`, in the `CharacterSheet(...)` constructor call inside `build_sheet`, after the `valuables=valuables_view(spec),` line (around line 853), add:

```python
        other_possessions=list(spec.other_possessions),
        notes=spec.notes,
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_possessions.py::test_build_sheet_passes_through_fields -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/sheet/view.py tests/test_possessions.py
git commit -m "feat: surface other_possessions + notes on CharacterSheet"
```

---

### Task 5: Templates (interactive + print)

**Files:**
- Modify: `aose/web/templates/sheet.html` — add an Other Possessions + Notes section after the Gems & Jewellery `</section>` (after line 712)
- Modify: `aose/web/templates/sheet_print.html` — add read-only blocks after the Equipment `</section>` (after line 189)

- [ ] **Step 1: Add the interactive section to `sheet.html`**

In `aose/web/templates/sheet.html`, immediately after the Gems & Jewellery section's closing `</section>` (line 712, before the Rest section), insert:

```html
            <section class="section">
                <h2>Other Possessions</h2>
                {% for item in sheet.other_possessions %}
                <div class="valuable">
                    {{ item }}
                    <form method="post" class="no-print inline"
                          action="/character/{{ character_id }}/possessions/remove">
                        <input type="hidden" name="index" value="{{ loop.index0 }}">
                        <button type="submit" class="link-button">drop</button>
                    </form>
                </div>
                {% else %}
                <p class="small muted">No other possessions.</p>
                {% endfor %}

                <form method="post" class="no-print"
                      action="/character/{{ character_id }}/possessions/add">
                    <label>Add an item:
                        <input type="text" name="text" placeholder="e.g. a bronze key">
                    </label>
                    <button type="submit" class="primary">Add</button>
                </form>
            </section>

            <section class="section">
                <h2>Notes</h2>
                {% if sheet.notes %}
                <p style="white-space: pre-wrap;">{{ sheet.notes }}</p>
                {% endif %}
                <form method="post" class="no-print"
                      action="/character/{{ character_id }}/notes/set">
                    <textarea name="notes" rows="6" style="width:100%;"
                              placeholder="Free-text notes…">{{ sheet.notes }}</textarea>
                    <button type="submit" class="primary">Save notes</button>
                </form>
            </section>
```

- [ ] **Step 2: Verify the interactive page renders**

Run: `.venv\Scripts\python.exe -m pytest tests/test_possessions_routes.py -q`
Then manually confirm rendering with a quick smoke check:

Run:
```
.venv\Scripts\python.exe -c "from pathlib import Path; from fastapi.testclient import TestClient; from aose.characters import save_character; from aose.models import CharacterSpec, ClassEntry; from aose.web.app import create_app; import tempfile, os; d=Path(tempfile.mkdtemp()); cd=d/'c'; (d/'ex').mkdir(); app=create_app(data_dir=Path('data'), characters_dir=cd, drafts_dir=d/'dr', examples_dir=d/'ex', settings_path=d/'s.json'); s=CharacterSpec(name='Bran', abilities={'STR':10,'INT':10,'WIS':10,'DEX':10,'CON':10,'CHA':10}, race_id='human', classes=[ClassEntry(class_id='fighter', level=1, hp_rolls=[8])], alignment='neutral', other_possessions=['a bronze key'], notes='hi'); save_character('bran', s, cd); c=TestClient(app); r=c.get('/character/bran'); print(r.status_code); assert 'Other Possessions' in r.text; assert 'a bronze key' in r.text; assert 'Notes' in r.text; print('OK')"
```
Expected: prints `200` then `OK`.

- [ ] **Step 3: Add the read-only print blocks to `sheet_print.html`**

In `aose/web/templates/sheet_print.html`, after the Equipment section's closing `</section>` (line 189, before the Magic Items block), insert:

```html
    {% if sheet.other_possessions %}
    <section class="section">
        <h2>Other Possessions</h2>
        <ul>
            {% for item in sheet.other_possessions %}
            <li>{{ item }}</li>
            {% endfor %}
        </ul>
    </section>
    {% endif %}

    {% if sheet.notes %}
    <section class="section">
        <h2>Notes</h2>
        <p style="white-space: pre-wrap;">{{ sheet.notes }}</p>
    </section>
    {% endif %}
```

- [ ] **Step 4: Verify the print page renders**

Run:
```
.venv\Scripts\python.exe -c "from pathlib import Path; from fastapi.testclient import TestClient; from aose.characters import save_character; from aose.models import CharacterSpec, ClassEntry; from aose.web.app import create_app; import tempfile; d=Path(tempfile.mkdtemp()); cd=d/'c'; (d/'ex').mkdir(); app=create_app(data_dir=Path('data'), characters_dir=cd, drafts_dir=d/'dr', examples_dir=d/'ex', settings_path=d/'s.json'); s=CharacterSpec(name='Bran', abilities={'STR':10,'INT':10,'WIS':10,'DEX':10,'CON':10,'CHA':10}, race_id='human', classes=[ClassEntry(class_id='fighter', level=1, hp_rolls=[8])], alignment='neutral', other_possessions=['a bronze key'], notes='hi'); save_character('bran', s, cd); c=TestClient(app); r=c.get('/character/bran/print'); print(r.status_code); assert 'Other Possessions' in r.text; assert 'a bronze key' in r.text; print('OK')"
```
Expected: prints `200` then `OK`.
(If the print route path differs, find it with `grep -n "/print" aose/web/routes.py` and adjust the URL.)

- [ ] **Step 5: Commit**

```bash
git add aose/web/templates/sheet.html aose/web/templates/sheet_print.html
git commit -m "feat: render other possessions + notes on sheet and print view"
```

---

### Task 6: Full suite + final commit

**Files:** none (verification only)

- [ ] **Step 1: Run the whole test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all tests pass (existing count + the new possessions tests). The trailing `pytest-current` PermissionError on Windows is a known quirk — ignore it.

- [ ] **Step 2: If anything fails, fix it before proceeding**

Use superpowers:systematic-debugging for any failure. Do not claim completion until the suite is green.

- [ ] **Step 3: Final sanity commit (only if uncommitted changes remain)**

```bash
git status
# commit any stragglers, otherwise nothing to do
```

---

## Self-Review Notes

- **Spec coverage:** model fields (Task 1), engine with raise-on-bad-index (Task 2), all three routes (Task 3), sheet view passthrough (Task 4), interactive + print templates (Task 5), tests throughout. All spec sections covered.
- **Type consistency:** `other_possessions: list[str]` and `notes: str` used identically across model, view, and templates. Engine funcs `add_possession(items, text)` / `remove_possession(items, index)` and `PossessionError` referenced consistently in tests and routes.
- **No placeholders:** every code/test step contains complete content.
