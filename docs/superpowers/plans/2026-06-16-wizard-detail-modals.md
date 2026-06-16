# Wizard detail modals + trimmed cards — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the wizard's jammed spell cards and over-stuffed race cards with trimmed cards plus book-style zine detail surfaces — a click-to-open modal with a Select button for race/single-class (and multiclass), and inline expanders with a Learn button for spells.

**Architecture:** A pure presentation helper (`aose/web/book.py`) turns `CharClass`/`Race`/`Spell` models into a flat `entry` dict (header stat rows + feature/body markdown). One Jinja macro (`_book_entry.html`) renders that dict identically wherever it appears. The race/class steps render each card's entry into a hidden block that a small vanilla controller (`wizard_cards.js`) injects into one shared zine `.overlay.modal`; the spells step renders the entry inline as an expander. Selection stays client-side and POSTs the same form fields on Next as today.

**Tech Stack:** Python 3 / FastAPI / Jinja2 / Pydantic v2; zine CSS tokens already global via `sheet.css`; vanilla JS (no framework); pytest + FastAPI `TestClient`.

---

## File structure

| File | Responsibility |
|---|---|
| `aose/web/book.py` (create) | Pure model→`entry`-dict builders: `class_entry`, `race_entry`, `spell_entry`, plus small formatting helpers. No engine imports. |
| `tests/test_book.py` (create) | Unit tests for the three entry builders. |
| `aose/web/templates/_book_entry.html` (create) | `book_entry(entry)` macro — header stat block + feature sections / spell body. |
| `aose/web/static/wizard_cards.css` (create) | Zine styling for the book modal, expander, and collapsed-grid states. Wizard-only. |
| `aose/web/static/wizard_cards.js` (create) | One controller: modal open/close, Select/Clear (single + multiclass cap), spell expand + Learn toggle. |
| `aose/web/templates/base.html` (modify) | Add `{% block head %}` and `{% block scripts %}`. |
| `aose/web/templates/wizard.html` (modify) | Load the new css/js; render the shared `#wizard-detail` overlay shell once. |
| `aose/web/wizard.py` (modify) | Attach `entry` + `select_reason` to race/class card dicts; attach `entry` to spell candidates. |
| `aose/web/templates/wizard/race.html` (modify) | Trim card; add hidden detail body + data attrs + Clear button. |
| `aose/web/templates/wizard/class.html` (modify) | Same as race; mark grid `data-multi` + cap when multiclassing. |
| `aose/web/templates/wizard/class_setup.html` (modify) | Spell cards: trimmed, inline expander, Learn button; drop the old per-grid spell toggle script. |
| `tests/test_wizard.py` (modify) | Update/extend assertions for the new markup. |

---

## Task 1: Presentation helper `aose/web/book.py`

**Files:**
- Create: `aose/web/book.py`
- Test: `tests/test_book.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_book.py`:

```python
from pathlib import Path

from aose.data.loader import GameData
from aose.web.book import class_entry, race_entry, spell_entry

DATA_DIR = Path(__file__).parent.parent / "data"


def _data():
    return GameData.load(DATA_DIR)


def _stat(entry, label):
    for s in entry["stats"]:
        if s["label"] == label:
            return s["value"]
    raise AssertionError(f"no stat {label!r} in {[s['label'] for s in entry['stats']]}")


def test_class_entry_has_header_and_features():
    cls = _data().classes["assassin"]
    e = class_entry(cls)
    assert e["kind"] == "class"
    assert e["name"] == "Assassin"
    assert _stat(e, "Prime requisite") == "DEX"
    assert _stat(e, "Hit Dice") == "1d4"
    assert _stat(e, "Maximum level") == "14"
    assert "Leather" in _stat(e, "Armour")
    assert _stat(e, "Weapons") == "Any"
    # Features carry their markdown text verbatim for the macro to render.
    names = [f["name"] for f in e["features"]]
    assert "Combat" in names
    assert any("master of the art" in f["text"].lower() or "masters of the art" in f["text"].lower()
               for f in e["features"])
    assert e["body"] is None


def test_race_entry_trims_to_deltas_and_languages():
    race = _data().races["drow"]
    e = race_entry(race)
    assert e["kind"] == "race"
    assert _stat(e, "Requirements") == "INT 9"
    mods = _stat(e, "Ability modifiers")
    assert "DEX +1" in mods and "CON -1" in mods
    assert "Elvish" in _stat(e, "Languages")
    feat_names = [f["name"] for f in e["features"]]
    assert "Innate Magic" in feat_names


def test_spell_entry_carries_meta_and_body():
    spell = _data().spells["light"]
    e = spell_entry(spell)
    assert e["kind"] == "spell"
    assert _stat(e, "Range") == spell.range
    assert _stat(e, "Duration") == spell.duration
    assert e["features"] == []
    assert e["body"] == spell.description
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_book.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'aose.web.book'`.

- [ ] **Step 3: Write the implementation**

Create `aose/web/book.py`:

```python
"""Build flat, render-ready detail "entries" for the wizard's book-style
surfaces (modal + spell expander).

Pure presentation: turns a CharClass / Race / Spell model into a dict the
``book_entry`` macro renders. No engine imports, no formatting decisions in
templates. An entry is::

    {
        "kind":  "class" | "race" | "spell",
        "name":  str,
        "stats": [{"label": str, "value": str}, ...],   # the green-box block
        "features": [{"name": str, "text": str}, ...],   # markdown per section
        "body":  str | None,                              # spell description only
    }
"""

from aose.models.character_class import CharClass
from aose.models.race import Race
from aose.models.spell import Spell

_ALIGN = {"law": "Law", "neutral": "Neutral", "chaos": "Chaos"}


def _titlecase(value: str) -> str:
    return value.replace("_", " ").title()


def _fmt_reqs(reqs) -> str:
    return ", ".join(f"{ab.value} {v}" for ab, v in reqs.items()) or "None"


def _fmt_allowed(value) -> str:
    if value == "all":
        return "Any"
    return ", ".join(_titlecase(v) for v in value) or "None"


def _fmt_mods(mods) -> str:
    return ", ".join(f"{ab.value} {d:+d}" for ab, d in mods.items()) or "None"


def class_entry(cls: CharClass) -> dict:
    armour = _fmt_allowed(cls.armor_allowed)
    if cls.shields_allowed and armour != "Any":
        armour = f"{armour}, shields"
    align = ", ".join(_ALIGN[a] for a in cls.allowed_alignments) or "Any"
    stats = [
        {"label": "Requirements", "value": _fmt_reqs(cls.ability_requirements)},
        {"label": "Prime requisite",
         "value": ", ".join(a.value for a in cls.prime_requisites)},
        {"label": "Hit Dice", "value": cls.hit_die},
        {"label": "Maximum level", "value": str(cls.max_level)},
        {"label": "Armour", "value": armour},
        {"label": "Weapons", "value": _fmt_allowed(cls.weapons_allowed)},
        {"label": "Alignment", "value": align},
    ]
    return {
        "kind": "class",
        "name": cls.name,
        "stats": stats,
        "features": [{"name": f.name, "text": f.text} for f in cls.features],
        "body": None,
    }


def race_entry(race: Race) -> dict:
    if race.allowed_classes:
        classes = ", ".join(
            f"{_titlecase(cid)}"
            + (f" {race.class_level_caps[cid]}" if cid in race.class_level_caps else "")
            for cid in race.allowed_classes
        )
    else:
        classes = "Any"
    stats = [
        {"label": "Requirements", "value": _fmt_reqs(race.ability_requirements)},
        {"label": "Ability modifiers", "value": _fmt_mods(race.ability_modifiers)},
        {"label": "Languages",
         "value": ", ".join(_titlecase(l) for l in race.languages) or "None"},
    ]
    if race.infravision:
        stats.append({"label": "Infravision", "value": f"{race.infravision}'"})
    stats.append({"label": "Available classes", "value": classes})
    return {
        "kind": "race",
        "name": race.name,
        "stats": stats,
        "features": [{"name": f.name, "text": f.text} for f in race.features],
        "body": None,
    }


def spell_entry(spell: Spell) -> dict:
    stats = [
        {"label": "Level", "value": str(spell.level)},
        {"label": "Range", "value": spell.range},
        {"label": "Duration", "value": spell.duration},
    ]
    if spell.reversible:
        stats.append({"label": "Reversible",
                      "value": spell.reverse_name or "Yes"})
    return {
        "kind": "spell",
        "name": spell.name,
        "stats": stats,
        "features": [],
        "body": spell.description,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_book.py -q`
Expected: PASS (3 passed). Ignore the trailing `pytest-current` PermissionError (known Windows quirk).

- [ ] **Step 5: Commit**

```bash
git add aose/web/book.py tests/test_book.py
git commit -m "feat(wizard): book entry builders for detail surfaces"
```

---

## Task 2: The `book_entry` macro

**Files:**
- Create: `aose/web/templates/_book_entry.html`
- Test: covered indirectly in Task 4+ via rendered pages (no isolated test here).

- [ ] **Step 1: Write the macro**

Create `aose/web/templates/_book_entry.html`:

```jinja
{# Book-style detail renderer, shared by the wizard race/class modal and the
   spell expander. `entry` is the dict from aose/web/book.py. Markdown text is
   trusted local data. #}
{% macro book_entry(entry) %}
<div class="book-entry">
  {% if entry.stats %}
  <dl class="book-stats">
    {% for s in entry.stats %}
    <div><dt>{{ s.label }}</dt><dd>{{ s.value }}</dd></div>
    {% endfor %}
  </dl>
  {% endif %}
  {% if entry.body %}
  <div class="book-body prose">{{ entry.body | markdown | safe }}</div>
  {% endif %}
  {% for f in entry.features %}
  <section class="book-feature">
    <h4 class="book-feature-head">{{ f.name }}</h4>
    <div class="book-feature-body prose">{{ f.text | markdown | safe }}</div>
  </section>
  {% endfor %}
</div>
{% endmacro %}
```

- [ ] **Step 2: Smoke-check it imports**

Run: `.venv\Scripts\python.exe -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('aose/web/templates')).get_template('_book_entry.html')"`
Expected: no output, exit 0 (template parses).

- [ ] **Step 3: Commit**

```bash
git add aose/web/templates/_book_entry.html
git commit -m "feat(wizard): book_entry macro"
```

---

## Task 3: Base blocks, wizard asset loading, shared overlay shell

**Files:**
- Modify: `aose/web/templates/base.html`
- Modify: `aose/web/templates/wizard.html`
- Create: `aose/web/static/wizard_cards.css`
- Create: `aose/web/static/wizard_cards.js`

- [ ] **Step 1: Add blocks to `base.html`**

In `aose/web/templates/base.html`, change the `<head>` link line to add a head block right after it:

```jinja
    <link rel="stylesheet" href="/static/sheet.css">
    {% block head %}{% endblock %}
```

And add a scripts block just before `</body>`:

```jinja
    {% block scripts %}{% endblock %}
</body>
```

- [ ] **Step 2: Wire the wizard to the new assets + add the overlay shell**

In `aose/web/templates/wizard.html`, add the blocks. After `{% block title %}…{% endblock %}` add:

```jinja
{% block head %}<link rel="stylesheet" href="/static/wizard_cards.css">{% endblock %}
```

Inside `{% block content %}`, immediately after `<div class="wizard">`, add the shared shell:

```jinja
    <div class="overlay modal" id="wizard-detail" role="dialog" aria-label="Detail">
      <div class="ov-head"><h3 data-role="title">Detail</h3><button class="x" data-close>×</button></div>
      <div class="ov-body" data-role="body"></div>
      <div class="ov-foot">
        <button type="button" class="primary" data-role="select">Select</button>
      </div>
    </div>
```

At the end of `wizard.html`, after `{% endblock %}` of content, add:

```jinja
{% block scripts %}<script src="/static/wizard_cards.js" defer></script>{% endblock %}
```

- [ ] **Step 3: Create the stylesheet**

Create `aose/web/static/wizard_cards.css` (zine tokens are already global from `sheet.css`):

```css
/* Wizard-only zine surfaces: book modal, spell expander, collapsed grids.
   Tokens (--ink/--paper/--display/--body/--gap/...) come from sheet.css. */

/* ---- shared overlay foot (Select button row) ---- */
#wizard-detail .ov-foot {
  display: flex; justify-content: flex-end;
  padding: 10px 16px; border-top: 1px solid var(--hair);
}
#wizard-detail .ov-foot .primary[disabled] { opacity: .5; cursor: not-allowed; }

/* ---- book entry (modal body + spell expander) ---- */
.book-entry { font-family: var(--body); color: var(--ink); }
.book-stats {
  margin: 0 0 12px; padding: 10px 12px;
  background: var(--box-sunk); border: 1px solid var(--hair);
}
.book-stats > div { display: flex; gap: 8px; padding: 2px 0; }
.book-stats dt {
  flex: 0 0 9.5rem; margin: 0; font-family: var(--display);
  text-transform: uppercase; letter-spacing: .06em; font-size: 12px;
  font-weight: 600; color: var(--gray);
}
.book-stats dd { margin: 0; font-size: 14px; }
.book-feature { margin: 12px 0; }
.book-feature-head {
  margin: 0 0 4px; font-family: var(--display);
  text-transform: uppercase; letter-spacing: .06em; font-size: 14px;
  background: var(--ink); color: #f7f5ed; padding: 3px 8px;
}
.book-feature-body { font-size: 14px; line-height: 1.45; }
.book-feature-body table { border-collapse: collapse; margin: 6px 0; font-size: 13px; }
.book-feature-body th, .book-feature-body td {
  border: 1px solid var(--hair); padding: 2px 6px; text-align: left;
}

/* ---- collapsed selection grid ---- */
.card-grid.collapsed .card:not(.selected) { display: none; }
.card .card-clear { display: none; }
.card.selected .card-clear { display: inline-block; }
.card-clear {
  margin-top: 6px; font-family: var(--display); text-transform: uppercase;
  letter-spacing: .06em; font-size: 11px; cursor: pointer;
  background: none; border: 1px solid var(--hair); padding: 2px 8px;
}
.card[data-detail] { cursor: pointer; }

/* ---- spell cards: expander + Learn ---- */
.spell-card .spell-detail { display: none; margin-top: 8px;
  border-top: 1px solid var(--hair); padding-top: 8px; }
.spell-card.expanded .spell-detail { display: block; }
.spell-card .spell-actions { display: flex; gap: 8px; align-items: center; margin-top: 6px; }
.spell-card .spell-meta { font-family: var(--display); font-size: 11px;
  text-transform: uppercase; letter-spacing: .06em; color: var(--gray); }
.btn-learn {
  font-family: var(--display); text-transform: uppercase; letter-spacing: .06em;
  font-size: 11px; cursor: pointer; padding: 3px 10px;
  background: var(--ink); color: #f7f5ed; border: none;
}
.btn-learn[disabled] { opacity: .4; cursor: not-allowed; }
.spell-card.learned .btn-learn { background: var(--stamp); }
```

- [ ] **Step 4: Create the controller skeleton (filled in Tasks 4–6)**

Create `aose/web/static/wizard_cards.js`:

```javascript
/* Wizard card interactions: book modal (race/class), collapse/clear,
   multiclass cap, spell expander + Learn. One delegated controller. */
(function () {
  "use strict";

  const overlay = document.getElementById("wizard-detail");

  /* ---------- overlay open/close ---------- */
  function openOverlay() { if (overlay) overlay.classList.add("on"); }
  function closeOverlay() { if (overlay) overlay.classList.remove("on"); }

  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-close]")) { closeOverlay(); return; }
    if (overlay && overlay.classList.contains("on") &&
        !e.target.closest("#wizard-detail .ov-head, #wizard-detail .ov-body, #wizard-detail .ov-foot")) {
      // scrim click (the overlay backdrop) closes
      if (e.target === overlay) closeOverlay();
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeOverlay();
  });

  /* Detail-modal + selection wiring is added in Task 5 (and reused by race). */
  /* Spell expander + Learn wiring is added in Task 6. */
})();
```

- [ ] **Step 5: Verify the wizard still loads**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard.py -q`
Expected: PASS (existing tests unaffected — blocks are additive). Ignore the `pytest-current` PermissionError.

- [ ] **Step 6: Commit**

```bash
git add aose/web/templates/base.html aose/web/templates/wizard.html aose/web/static/wizard_cards.css aose/web/static/wizard_cards.js
git commit -m "feat(wizard): zine detail overlay shell + asset wiring"
```

---

## Task 4: Race step — view model, trimmed card, hidden body

**Files:**
- Modify: `aose/web/wizard.py` (`get_race`, ~line 614-638)
- Modify: `aose/web/templates/wizard/race.html`
- Test: `tests/test_wizard.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_wizard.py`:

```python
def test_race_card_is_trimmed_and_carries_detail(client, tmp_path):
    draft_id = _start_draft(client)
    _override_abilities(tmp_path, draft_id, {
        "STR": 12, "INT": 12, "WIS": 12, "DEX": 12, "CON": 12, "CHA": 12
    })
    client.post(f"/wizard/{draft_id}/abilities", data={})
    r = client.get(f"/wizard/{draft_id}/race")
    assert r.status_code == 200
    # Trimmed: no Movement line, no "languages" count line.
    assert "Movement:" not in r.text
    assert "languages</div>" not in r.text
    # Book detail body present (hidden) for the modal to inject.
    assert 'class="detail-body"' in r.text
    assert 'data-role="select"' in r.text  # shared shell rendered on the page
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard.py::test_race_card_is_trimmed_and_carries_detail -q`
Expected: FAIL — `Movement:` still present (and `detail-body` missing).

- [ ] **Step 3: Enrich the race view model**

In `aose/web/wizard.py`, add the import near the other local imports at the top of the file (with the `from aose...` imports):

```python
from aose.web.book import class_entry, race_entry, spell_entry
```

In `get_race`, inside the `for race in ...` loop, replace the `races.append({...})` call with one that adds `entry` and `select_reason`:

```python
        meets = _meets_ability_requirements(race.ability_requirements, abilities)
        races.append({
            "id": race.id,
            "name": race.name,
            "infravision": race.infravision,
            "base_movement": race.base_movement,
            "requirements": {ab.value: v for ab, v in race.ability_requirements.items()},
            "languages": race.languages,
            "ability_changes": ability_changes,
            "meets_requirements": meets,
            "selected": draft.get("race_id") == race.id,
            "entry": race_entry(race),
            "select_reason": None if meets else "Ability requirements not met",
        })
```

- [ ] **Step 4: Rewrite `race.html`**

Replace `aose/web/templates/wizard/race.html` with:

```jinja
{% from "_book_entry.html" import book_entry %}
<h2>Choose Race</h2>
<p class="muted">Click a card to read the full entry, then Select. Greyed-out races require ability scores you don't have.</p>

{% include "wizard/_ability_summary.html" %}

<form method="post" action="/wizard/{{ draft_id }}/race" class="step-form">
    <div class="card-grid" data-single>
    {% for race in races %}
        <label class="card {% if not race.meets_requirements %}disabled{% endif %} {% if race.selected %}selected{% endif %}"
               data-detail data-name="{{ race.name }}"
               data-available="{{ 0 if race.select_reason else 1 }}"
               {% if race.select_reason %}data-reason="{{ race.select_reason }}"{% endif %}>
            <input type="radio" name="race_id" value="{{ race.id }}" required
                   {% if not race.meets_requirements %}disabled{% endif %}
                   {% if race.selected %}checked{% endif %}>
            <div class="card-name">{{ race.name }}</div>
            {% if race.requirements %}
            <div class="card-detail">Requires:
                {%- for ab, v in race.requirements.items() %}
                    {{ ab }} {{ v }}+{% if not loop.last %},{% endif %}
                {%- endfor %}
            </div>
            {% endif %}
            {% if race.ability_changes %}
            <div class="card-detail small">
                {%- for ch in race.ability_changes %}
                    {{ ch.name }} {{ '+' if ch.delta > 0 else '' }}{{ ch.delta }}{% if not loop.last %}, {% endif %}
                {%- endfor %}
            </div>
            {% endif %}
            {% if race.infravision %}
            <div class="card-detail">Infravision: {{ race.infravision }}'</div>
            {% endif %}
            <button type="button" class="card-clear">Clear</button>
            <div class="detail-body" hidden>{{ book_entry(race.entry) }}</div>
        </label>
    {% endfor %}
    </div>
    <button type="submit" class="primary">Next: Class &rarr;</button>
</form>
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard.py::test_race_card_is_trimmed_and_carries_detail -q`
Expected: PASS.

- [ ] **Step 6: Run the full wizard suite (no regressions in POST flow)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard.py -q`
Expected: PASS — the radio name/value are unchanged, so `POST /race` still works.

- [ ] **Step 7: Commit**

```bash
git add aose/web/wizard.py aose/web/templates/wizard/race.html tests/test_wizard.py
git commit -m "feat(wizard): trimmed race cards + book detail body"
```

---

## Task 5: Class step + the modal/Select/Clear controller (incl. multiclass)

**Files:**
- Modify: `aose/web/wizard.py` (`get_class`, the `classes.append({...})` ~line 724-735)
- Modify: `aose/web/templates/wizard/class.html`
- Modify: `aose/web/static/wizard_cards.js`
- Test: `tests/test_wizard.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_wizard.py`:

```python
def test_class_card_carries_detail_and_reason(client, tmp_path):
    draft_id = _start_draft(client)
    _override_abilities(tmp_path, draft_id, {
        "STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10
    })
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    r = client.get(f"/wizard/{draft_id}/class")
    assert r.status_code == 200
    assert 'class="detail-body"' in r.text
    # A class Dwarf can't take (e.g. magic_user) carries a select reason.
    assert "Not available to Dwarf" in r.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard.py::test_class_card_carries_detail_and_reason -q`
Expected: FAIL — no `detail-body`.

- [ ] **Step 3: Enrich the class view model**

In `aose/web/wizard.py` `get_class`, replace the `classes.append({...})` block with one adding `entry` and `select_reason`:

```python
        if not allowed_by_race:
            reason = f"Not available to {race_name}"
        elif not meets_abilities:
            reason = "Ability requirements not met"
        else:
            reason = None
        classes.append({
            "id": cls.id,
            "name": cls.name,
            "hit_die": cls.hit_die,
            "prime_requisites": [a.value for a in cls.prime_requisites],
            "level_cap": level_cap,
            "race_locked": cls.race_locked,
            "allowed_by_race": allowed_by_race,
            "meets_abilities": meets_abilities,
            "available": allowed_by_race and meets_abilities,
            "selected": cls.id in _class_ids(draft),
            "entry": class_entry(cls),
            "select_reason": reason,
        })
```

- [ ] **Step 4: Rewrite `class.html`**

Replace `aose/web/templates/wizard/class.html` with:

```jinja
{% from "_book_entry.html" import book_entry %}
<h2>{% if race_as_class_mode %}Choose Class &amp; Race{% else %}Choose Class{% endif %}</h2>
{% if race_as_class_mode %}
<p class="muted">Race-as-Class mode is active &mdash; demihumans are full classes.
   Picking one (e.g. <em>Dwarf</em>) sets both class and race in one step.</p>
{% else %}
<p class="muted">Filtered by your race ({{ race_name }}) and ability scores. Click a card to read the entry, then Select.</p>
{% endif %}

{% if multiclass_enabled %}
<p class="hint">Multi-classing is on: pick up to {{ max_classes }} classes. The character
   tracks XP and level separately per class and uses the best benefits of each.
   Picking a single class is still fine.</p>
{% endif %}

{% include "wizard/_ability_summary.html" %}

<form method="post" action="/wizard/{{ draft_id }}/class" class="step-form">
    <div class="card-grid"
         {% if multiclass_enabled %}data-multi data-cap="{{ max_classes }}"{% else %}data-single{% endif %}>
    {% for cls in classes %}
        <label class="card {% if not cls.available %}disabled{% endif %} {% if cls.selected %}selected{% endif %}"
               data-detail data-name="{{ cls.name }}"
               data-available="{{ 0 if cls.select_reason else 1 }}"
               {% if cls.select_reason %}data-reason="{{ cls.select_reason }}"{% endif %}>
            <input type="{% if multiclass_enabled %}checkbox{% else %}radio{% endif %}"
                   name="class_id" value="{{ cls.id }}"
                   {% if not multiclass_enabled %}required{% endif %}
                   {% if not cls.available %}disabled{% endif %}
                   {% if cls.selected %}checked{% endif %}>
            <div class="card-name">
                {{ cls.name }}
                {% if cls.race_locked %}
                <span class="rule-pending" title="Race-as-class entry — selecting this also locks your race.">demihuman</span>
                {% endif %}
            </div>
            <div class="card-detail">HD: {{ cls.hit_die }}</div>
            <div class="card-detail">Prime: {{ cls.prime_requisites | join(", ") }}</div>
            {% if cls.level_cap %}
            <div class="card-detail">{{ race_name }} max level: {{ cls.level_cap }}</div>
            {% endif %}
            <button type="button" class="card-clear">Clear</button>
            <div class="detail-body" hidden>{{ book_entry(cls.entry) }}</div>
        </label>
    {% endfor %}
    </div>

    <button type="submit" class="primary">Next: Adjustments &rarr;</button>
</form>
```

- [ ] **Step 5: Implement the modal/Select/Clear controller**

In `aose/web/static/wizard_cards.js`, replace the comment `/* Detail-modal + selection wiring is added in Task 5 ... */` with:

```javascript
  /* ---------- detail modal + selection ---------- */
  let activeCard = null;

  function gridOf(card) { return card.closest(".card-grid"); }
  function inputOf(card) { return card.querySelector('input[name="race_id"], input[name="class_id"]'); }

  function applySingleCollapse(grid, card) {
    grid.querySelectorAll(".card").forEach(c => c.classList.toggle("selected", c === card));
    grid.classList.add("collapsed");
    if (window.csValidate) window.csValidate();
  }

  function clearSingle(grid) {
    grid.querySelectorAll(".card").forEach(c => {
      c.classList.remove("selected");
      const i = inputOf(c); if (i) i.checked = false;
    });
    grid.classList.remove("collapsed");
    if (window.csValidate) window.csValidate();
  }

  function multiCount(grid) {
    return grid.querySelectorAll('input[name="class_id"]:checked').length;
  }

  function refreshMulti(grid) {
    const cap = parseInt(grid.dataset.cap || "0", 10);
    const atCap = multiCount(grid) >= cap;
    grid.querySelectorAll(".card").forEach(c => {
      const i = inputOf(c);
      c.classList.toggle("selected", !!(i && i.checked));
    });
    grid.classList.toggle("collapsed", atCap);
    if (window.csValidate) window.csValidate();
  }

  function selectCard(card) {
    const grid = gridOf(card);
    const input = inputOf(card);
    if (!input) return;
    if (grid.hasAttribute("data-multi")) {
      input.checked = true;
      refreshMulti(grid);
    } else {
      input.checked = true;
      applySingleCollapse(grid, card);
    }
  }

  function openDetail(card) {
    activeCard = card;
    overlay.querySelector('[data-role="title"]').textContent = card.dataset.name || "Detail";
    overlay.querySelector('[data-role="body"]').innerHTML =
      card.querySelector(".detail-body").innerHTML;
    const selectBtn = overlay.querySelector('[data-role="select"]');
    if (card.dataset.available === "0") {
      selectBtn.disabled = true;
      selectBtn.textContent = card.dataset.reason || "Unavailable";
    } else {
      selectBtn.disabled = false;
      selectBtn.textContent = "Select";
    }
    openOverlay();
  }

  document.addEventListener("click", function (e) {
    // Clear button on a card.
    const clearBtn = e.target.closest(".card-clear");
    if (clearBtn) {
      e.preventDefault();
      const grid = gridOf(clearBtn.closest(".card"));
      if (grid.hasAttribute("data-multi")) {
        const i = inputOf(clearBtn.closest(".card")); if (i) i.checked = false;
        refreshMulti(grid);
      } else {
        clearSingle(grid);
      }
      return;
    }
    // Select button inside the overlay.
    if (e.target.closest('#wizard-detail [data-role="select"]')) {
      if (activeCard && activeCard.dataset.available !== "0") selectCard(activeCard);
      closeOverlay();
      return;
    }
    // Card click → open detail (ignore clicks on the raw input/clear button).
    const card = e.target.closest(".card[data-detail]");
    if (card && !e.target.closest("input, .card-clear")) {
      e.preventDefault();
      openDetail(card);
    }
  });
```

- [ ] **Step 6: Run the class test + full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard.py -q`
Expected: PASS — `POST /class` still receives `class_id` from the same inputs.

- [ ] **Step 7: Preview-verify the interaction**

Start the app and confirm in the browser preview: clicking a race card opens the zine modal with the book entry; Select collapses the grid and reveals Clear; Clear restores the grid; a disabled class shows the modal with a disabled, reason-labelled Select.

Run: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
Then use the preview tools (preview_start → navigate the wizard → preview_click the card → preview_snapshot) to confirm, and preview_console_logs for errors.

- [ ] **Step 8: Commit**

```bash
git add aose/web/wizard.py aose/web/templates/wizard/class.html aose/web/static/wizard_cards.js tests/test_wizard.py
git commit -m "feat(wizard): book modal + Select/Clear for class & race (incl. multiclass cap)"
```

---

## Task 6: Spells step — trimmed cards, expander, Learn

**Files:**
- Modify: `aose/web/wizard.py` (`_caster_entries`, the two candidate-dict builders ~line 1549-1570)
- Modify: `aose/web/templates/wizard/class_setup.html` (the `{% if show_spells %}` section + its inline script)
- Modify: `aose/web/static/wizard_cards.js`
- Test: `tests/test_wizard.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_wizard.py`:

```python
def _to_spells_step(client, tmp_path, draft_id):
    _override_abilities(tmp_path, draft_id, {
        "STR": 10, "INT": 16, "WIS": 10, "DEX": 12, "CON": 12, "CHA": 10
    })
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "magic_user"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    return client.get(f"/wizard/{draft_id}/class_setup")  # spells live on this step


def test_spell_cards_have_learn_and_expander_not_jammed(client, tmp_path):
    draft_id = _start_draft(client)
    r = _to_spells_step(client, tmp_path, draft_id)
    assert r.status_code == 200
    # Learn button + expander body present.
    assert "btn-learn" in r.text
    assert "spell-detail" in r.text
    # The card no longer dumps the full description inline as a card-detail.
    assert 'class="card-detail small">{{' not in r.text  # sanity: no raw template
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard.py::test_spell_cards_have_learn_and_expander_not_jammed -q`
Expected: FAIL — `btn-learn` absent.

- [ ] **Step 3: Enrich spell candidate dicts**

In `aose/web/wizard.py` `_caster_entries`, add `"entry": spell_entry(s)` to **both** candidate builders (the cantrip list comprehension and the main `candidates` list). For the cantrips block:

```python
            cantrip_candidates = [
                {"id": s.id, "name": s.name, "level": s.level,
                 "description": s.description,
                 "entry": spell_entry(s),
                 "selected": s.id in books.get(cid, [])}
                for s in sorted(
                    (sp for sp in data.spells.values()
                     if sp.level == 0 and set(sp.spell_lists) & enabled_lists
                     and sp.id not in hide),
                    key=lambda sp: sp.name,
                )
            ]
```

And the main candidates inside `rows.append({...})`:

```python
            "candidates": [{"id": s.id, "name": s.name, "level": s.level,
                            "description": s.description,
                            "entry": spell_entry(s),
                            "selected": s.id in books.get(cid, [])}
                           for s in candidates],
```

- [ ] **Step 4: Rewrite the Spells section of `class_setup.html`**

In `aose/web/templates/wizard/class_setup.html`, add the macro import at the very top of the file (line 1):

```jinja
{% from "_book_entry.html" import book_entry %}
```

Replace the entire `{% if show_spells %} … {% endif %}` block (lines ~134-204, both the divine `<ul>` path and the arcane/mental `card-grid` paths, and the trailing `<script>`) with:

```jinja
{# ── Spells ─────────────────────────────────────────────────────────────── #}
{% if show_spells %}
<section class="class-setup-section">
    <h3>Spells</h3>
    <input type="hidden" name="section" value="spells">
    {% for c in caster_classes %}
    <div class="spell-class">
        <h4>{{ c.class_name }}</h4>
        {% if c.caster_type == "divine" %}
        <p>{{ c.class_name }} casters know <strong>every spell</strong> on their list
           that they are high enough level to cast. Click a spell to read it.</p>
        <div class="card-grid">
            {% for s in c.candidates %}
            <div class="card spell-card" data-spell>
                <div class="card-name">{{ s.name }} <span class="spell-meta">L{{ s.level }}</span></div>
                <div class="spell-detail">{{ book_entry(s.entry) }}</div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <p>Choose <strong>{{ c.required }}</strong> starting spell(s) for your spell
           book{% if c.advanced %} (Advanced Spell Book rules: determined by Intelligence){% else %} (the spells you can memorise at this level){% endif %}. Click a card to read it; press Learn to add it.</p>
        <div class="card-grid spell-grid" data-required="{{ c.required }}">
            {% for s in c.candidates %}
            <div class="card spell-card {% if s.selected %}learned selected{% endif %}" data-spell>
                <input type="checkbox" name="spell_{{ c.class_id }}" value="{{ s.id }}"
                       class="spell-checkbox" hidden {% if s.selected %}checked{% endif %}>
                <div class="card-name">{{ s.name }} <span class="spell-meta">L{{ s.level }}</span></div>
                <div class="spell-actions">
                    <button type="button" class="btn-learn">{{ "Forget" if s.selected else "Learn" }}</button>
                </div>
                <div class="spell-detail">{{ book_entry(s.entry) }}</div>
            </div>
            {% endfor %}
        </div>
        <p class="muted spell-counter">Pick exactly {{ c.required }}.</p>
        {% if c.cantrip_required %}
        <h5 style="margin-top:10px">Cantrips</h5>
        <p>Choose <strong>{{ c.cantrip_required }}</strong> cantrip(s) (level-0 spells) for your spell book.</p>
        <div class="card-grid spell-grid" data-required="{{ c.cantrip_required }}">
            {% for s in c.cantrip_candidates %}
            <div class="card spell-card {% if s.selected %}learned selected{% endif %}" data-spell>
                <input type="checkbox" name="cantrip_{{ c.class_id }}" value="{{ s.id }}"
                       class="spell-checkbox" hidden {% if s.selected %}checked{% endif %}>
                <div class="card-name">{{ s.name }} <span class="spell-meta">L{{ s.level }}</span></div>
                <div class="spell-actions">
                    <button type="button" class="btn-learn">{{ "Forget" if s.selected else "Learn" }}</button>
                </div>
                <div class="spell-detail">{{ book_entry(s.entry) }}</div>
            </div>
            {% endfor %}
        </div>
        <p class="muted spell-counter">Pick exactly {{ c.cantrip_required }}.</p>
        {% endif %}
        {% endif %}
    </div>
    {% endfor %}
</section>
{% endif %}
```

(The old inline `<script>` that managed `.spell-class .card-grid[data-required]` is removed — `wizard_cards.js` owns this now. `csValidate` in the footer script still counts `.spell-checkbox:checked`, which the Learn toggle keeps accurate.)

- [ ] **Step 5: Implement the spell controller**

In `aose/web/static/wizard_cards.js`, replace the comment `/* Spell expander + Learn wiring is added in Task 6. */` with:

```javascript
  /* ---------- spell expander + Learn ---------- */
  function refreshSpellGrid(grid) {
    const required = parseInt(grid.dataset.required, 10);
    const cards = Array.from(grid.querySelectorAll(".spell-card"));
    const learned = cards.filter(c => c.querySelector(".spell-checkbox").checked).length;
    cards.forEach(card => {
      const box = card.querySelector(".spell-checkbox");
      const btn = card.querySelector(".btn-learn");
      card.classList.toggle("learned", box.checked);
      card.classList.toggle("selected", box.checked);
      btn.textContent = box.checked ? "Forget" : "Learn";
      btn.disabled = !box.checked && learned >= required;
    });
    const counter = grid.parentElement.querySelector(".spell-counter");
    if (counter) counter.textContent = "Picked " + learned + " of " + required + ".";
    if (window.csValidate) window.csValidate();
  }

  document.addEventListener("click", function (e) {
    // Learn / Forget toggle.
    const learn = e.target.closest(".btn-learn");
    if (learn) {
      e.preventDefault();
      const card = learn.closest(".spell-card");
      const box = card.querySelector(".spell-checkbox");
      const grid = card.closest(".spell-grid");
      const required = parseInt(grid.dataset.required, 10);
      const learned = grid.querySelectorAll(".spell-checkbox:checked").length;
      if (!box.checked && learned >= required) return;  // cap reached
      box.checked = !box.checked;
      refreshSpellGrid(grid);
      return;
    }
    // Expand/collapse the card (ignore clicks on the Learn button).
    const spellCard = e.target.closest(".spell-card[data-spell]");
    if (spellCard && !e.target.closest(".btn-learn, input")) {
      spellCard.classList.toggle("expanded");
    }
  });

  document.querySelectorAll(".spell-grid[data-required]").forEach(refreshSpellGrid);
```

- [ ] **Step 6: Run the spell test + full wizard suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard.py -q`
Expected: PASS — `spell_{cid}` / `cantrip_{cid}` checkbox names are unchanged, so `_apply_spells` still reads them on POST.

- [ ] **Step 7: Preview-verify**

With the app running, on a magic-user draft's class-setup step: confirm spell cards show name + `L1`, a Learn button, and expand to the book text on body click (multiple open at once); learning N disables the rest; Forget re-enables. Check preview_console_logs for errors.

- [ ] **Step 8: Commit**

```bash
git add aose/web/wizard.py aose/web/templates/wizard/class_setup.html aose/web/static/wizard_cards.js tests/test_wizard.py
git commit -m "feat(wizard): spell cards become expanders with Learn toggle"
```

---

## Task 7: Full sweep + docs

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/ARCHITECTURE.md` (wizard section)
- Test: full suite

- [ ] **Step 1: Run the complete test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing `pytest-current` PermissionError — known Windows quirk).

- [ ] **Step 2: Update the changelog**

Add a one-line row to the top of `docs/CHANGELOG.md`:

```markdown
| 2026-06-16 | Wizard book-style detail modals + trimmed race/spell cards | main | 2026-06-16-wizard-detail-modals |
```

(Match the existing column shape in that file; adjust if columns differ.)

- [ ] **Step 3: Update the architecture wizard section**

In `docs/ARCHITECTURE.md`, in the wizard subsystem section, edit in place to note: race/class cards open a shared zine `#wizard-detail` overlay whose body is built by `aose/web/book.py` + the `_book_entry.html` macro (modal Select drives client-side selection; Clear restores the grid; multiclass collapses at the cap); the spells step renders the same `book_entry` inline as per-card expanders with a Learn toggle. Controller: `aose/web/static/wizard_cards.js`; styles: `wizard_cards.css` (zine tokens reused, wizard-only).

- [ ] **Step 4: Commit**

```bash
git add docs/CHANGELOG.md docs/ARCHITECTURE.md
git commit -m "docs: wizard detail modals landed"
```

---

## Self-review notes

- **Spec coverage:** card trimming (Tasks 4, 6) · `book_entry` macro (Task 2) · race/single-class modal+Select+collapse+Clear (Tasks 4, 5) · disabled read-only modal (Task 5) · multiclass collapse-at-cap (Task 5) · spell expander + Learn + cap + divine read-only (Task 6) · plumbing/asset wiring + view-model enrichment (Tasks 1, 3) · tests (each task) · docs (Task 7). All spec components map to a task.
- **POST compatibility:** radio/checkbox `name`/`value` are unchanged in every step, so existing `post_race`/`post_class`/`_apply_spells` keep working — guarded by re-running the full `test_wizard.py` after each UI task.
- **JS behaviour** (collapse, expander, Learn cap) has no pytest harness in this repo; it is verified via the preview tools (Tasks 5, 6 step "Preview-verify").
- **Type consistency:** `entry` dict shape (`kind`/`name`/`stats`/`features`/`body`) is defined in Task 1 and consumed unchanged by the macro (Task 2) and all call sites (Tasks 4–6). Controller helpers (`selectCard`, `clearSingle`, `refreshMulti`, `refreshSpellGrid`) are each defined once.
