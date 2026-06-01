# Wizard Overhaul — Slice 1: Rules Page & Creation Method — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make "character creation method" (Basic vs Advanced) a visible top-level
choice, regroup the rules page (wizard + global settings) to the target layout,
merge the two demihuman optional rules into one `lift_demihuman_restrictions`
flag, and drop the unused `max_hp_at_l1` rule.

**Architecture:** Mostly presentation plus two small `RuleSet` changes. A new
radio section ("Character Creation Method") binds to the existing
`separate_race_class` boolean. The shared `settings_routes.py` data structures
(`RULE_GROUPS`, `RULE_LABELS`, `IMPLEMENTED_RULES`) are rebuilt, and a single
shared Jinja partial renders the method section + rule groups for both the
wizard rules step and the global settings page. The server (`parse_ruleset_from_form`)
is the source of truth: Basic forces `multiclassing` and
`lift_demihuman_restrictions` off regardless of posted values.

**Tech Stack:** Python 3, FastAPI, Jinja2, Pydantic v2, pytest. Vanilla
progressive-enhancement JS (no framework). PowerShell on Windows.

**Test command (run from project root):**
```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```
The trailing `PermissionError` on `pytest-current` is a known Windows-tempdir
quirk in pytest 9; ignore it.

---

## Reference: the AOSE Builder spec source

This plan implements `docs/superpowers/specs/2026-05-31-wizard-rules-creation-method-design.md`.
Out of scope for this slice (handled by later slices): Human Racial Abilities /
Blessed HP (Slice 5), removing `ability_roll_method` / the arrange UI (Slice 2 —
it keeps rendering until then), racial ability modifiers (Slice 3). The app is
not deployed: **no backward-compat migrations** for the data-shape changes.

---

### Task 1: `RuleSet` model — drop `max_hp_at_l1`, merge demihuman flags

**Files:**
- Modify: `aose/models/ruleset.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Update the model test to assert the new flag set**

In `tests/test_models.py`, replace the body of `test_default_ruleset` (currently
asserts `rs.demihuman_level_limits is True`):

```python
def test_default_ruleset():
    rs = RuleSet()
    assert rs.ascending_ac is False
    assert rs.separate_race_class is True
    assert rs.lift_demihuman_restrictions is False
    assert rs.encumbrance == "basic"
    assert rs.ability_roll_method == "3d6_in_order"


def test_ruleset_has_no_removed_flags():
    """max_hp_at_l1 and the two split demihuman flags are gone; extra='forbid'
    means passing them raises rather than silently accepting."""
    import pytest
    from pydantic import ValidationError
    for dead in ("max_hp_at_l1", "demihuman_level_limits", "demihuman_class_restrictions"):
        with pytest.raises(ValidationError):
            RuleSet(**{dead: True})  # type: ignore[arg-type]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models.py::test_default_ruleset tests/test_models.py::test_ruleset_has_no_removed_flags -q`
Expected: FAIL — `RuleSet` still has `demihuman_level_limits`, no `lift_demihuman_restrictions`.

- [ ] **Step 3: Edit the model**

In `aose/models/ruleset.py`, change the field block. Remove `max_hp_at_l1`,
`demihuman_level_limits`, and `demihuman_class_restrictions`; add
`lift_demihuman_restrictions`:

```python
class RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ascending_ac: bool = False
    secondary_skills: bool = False
    weapon_proficiency: bool = False
    multiclassing: bool = False
    reroll_1s_2s_hp_l1: bool = False
    separate_race_class: bool = True
    lift_demihuman_restrictions: bool = False
    variable_weapon_damage: bool = False
    advanced_spell_books: bool = False

    ability_roll_method: AbilityRollMethod = "3d6_in_order"
    encumbrance: EncumbranceMode = "basic"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models.py -q`
Expected: PASS (test_models only — the rest of the suite still references the old
flags and will be fixed in later tasks).

- [ ] **Step 5: Commit**

```powershell
git add aose/models/ruleset.py tests/test_models.py
git commit -m @'
feat(ruleset): merge demihuman flags into lift_demihuman_restrictions, drop max_hp_at_l1

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 2: `settings_routes.py` — labels, implemented set, groups, parser

**Files:**
- Modify: `aose/web/settings_routes.py`
- Test: `tests/test_settings.py` (parser-focused additions below)

This task rebuilds the shared data structures and teaches
`parse_ruleset_from_form` about the creation-method radio plus Basic enforcement.

- [ ] **Step 1: Write failing parser tests**

Add to the end of `tests/test_settings.py`:

```python
# ── Creation method + Basic enforcement (Slice 1) ─────────────────────────

from aose.web.settings_routes import parse_ruleset_from_form


class _Form(dict):
    """Minimal stand-in for a Starlette FormData: supports `in` and `.get`.
    The parser only uses membership tests and `.get`, so a dict suffices."""


def test_parser_advanced_method_sets_separate_race_class_true():
    rs = parse_ruleset_from_form(_Form({"creation_method": "advanced"}))
    assert rs.separate_race_class is True


def test_parser_basic_method_sets_separate_race_class_false():
    rs = parse_ruleset_from_form(_Form({"creation_method": "basic"}))
    assert rs.separate_race_class is False


def test_parser_missing_method_defaults_to_advanced():
    rs = parse_ruleset_from_form(_Form({}))
    assert rs.separate_race_class is True


def test_parser_basic_forces_advanced_only_rules_off():
    """Even if multiclassing / lift_demihuman_restrictions are posted true,
    Basic mode forces them off server-side."""
    rs = parse_ruleset_from_form(_Form({
        "creation_method": "basic",
        "multiclassing": "on",
        "lift_demihuman_restrictions": "on",
    }))
    assert rs.separate_race_class is False
    assert rs.multiclassing is False
    assert rs.lift_demihuman_restrictions is False


def test_parser_advanced_keeps_advanced_only_rules():
    rs = parse_ruleset_from_form(_Form({
        "creation_method": "advanced",
        "multiclassing": "on",
        "lift_demihuman_restrictions": "on",
    }))
    assert rs.multiclassing is True
    assert rs.lift_demihuman_restrictions is True
```

Also fix the existing `max_hp_at_l1` references in `tests/test_settings.py`
(these will be removed/replaced in Task 7's settings rework, but they must at
least import-parse). For now, in `test_save_then_load_roundtrip`,
`test_post_settings_persists_to_disk`, and `test_new_character_inherits_active_ruleset`,
replace `max_hp_at_l1=True` / `"max_hp_at_l1": "on"` / asserts on
`spec.ruleset.max_hp_at_l1` with `ascending_ac` equivalents — but this is fully
specified in Task 7. **For this task, only add the new parser tests above.** The
existing `max_hp_at_l1` tests will still fail until Task 7; that is expected and
called out in Step 4.

- [ ] **Step 2: Run the new parser tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py -k parser -q`
Expected: FAIL — `parse_ruleset_from_form` does not yet read `creation_method`.

- [ ] **Step 3: Rebuild the data structures and parser**

In `aose/web/settings_routes.py`:

Replace `RULE_LABELS` with:

```python
RULE_LABELS = {
    "ascending_ac": "Ascending AC",
    "variable_weapon_damage": "Variable Weapon Damage",
    "weapon_proficiency": "Weapon Proficiency",
    "reroll_1s_2s_hp_l1": "Reroll 1s & 2s for HP at L1",
    "lift_demihuman_restrictions": "Lift Demihuman Class & Level Restrictions",
    "secondary_skills": "Secondary Skills",
    "multiclassing": "Multiclassing",
    "advanced_spell_books": "Advanced Spell Books",
}
```

Replace `IMPLEMENTED_RULES` with (drop `max_hp_at_l1` and the two demihuman
entries; drop `separate_race_class` — it is no longer a checkbox; add
`lift_demihuman_restrictions`):

```python
IMPLEMENTED_RULES = {
    "ascending_ac",
    "reroll_1s_2s_hp_l1",
    "secondary_skills",
    "lift_demihuman_restrictions",
    "weapon_proficiency",
    "multiclassing",
    "variable_weapon_damage",
    "advanced_spell_books",
}
```

Replace `RULE_GROUPS` with the regrouped layout (order is firm per the spec):

```python
RULE_GROUPS = [
    ("Advanced Options", [
        ("multiclassing",
         "Demihumans may pursue two or three classes simultaneously, sharing XP."),
        ("lift_demihuman_restrictions",
         "Demihuman races ignore their normal class options and per-class "
         "maximum-level caps."),
    ]),
    ("Character Options", [
        ("weapon_proficiency",
         "Characters are only proficient with specific weapons; non-proficient "
         "attacks suffer −2 to hit."),
        ("secondary_skills",
         "Each character has a secondary skill (a non-adventuring trade)."),
    ]),
    ("Survivability & Logistics", [
        ("reroll_1s_2s_hp_l1",
         "When rolling 1st-level HP, re-roll any result of 1 or 2."),
    ]),
    ("Magic", [
        ("advanced_spell_books",
         "Arcane spell books have no size limit and the number of beginning "
         "spells is set by Intelligence. Off = standard rules: the book holds "
         "exactly the spells the caster can memorise."),
    ]),
    ("Combat", [
        ("variable_weapon_damage",
         "Each weapon rolls its specific damage die instead of the default 1d6."),
        ("ascending_ac",
         "Show armour class as ascending (10 = unarmoured) and use Attack Bonus, "
         "instead of descending (9 = unarmoured) with THAC0."),
    ]),
]
```

Reorder `CHOICE_GROUPS` so `encumbrance` renders before `ability_roll_method`
(per the spec's firm render order). Replace `CHOICE_GROUPS` with:

```python
CHOICE_GROUPS = [
    ("encumbrance", "Encumbrance", [
        ("none", "None — ignore encumbrance entirely"),
        ("basic", "Basic — track only armour and significant loads"),
        ("detailed", "Detailed — track item-by-item weight in coins"),
    ]),
    ("ability_roll_method", "Ability Score Method", [
        ("3d6_in_order", "3d6 in order — traditional and most deadly"),
        ("3d6_arrange", "3d6, arrange to taste"),
        ("4d6_drop_lowest", "4d6, drop the lowest"),
    ]),
]
```

The constant `ADVANCED_OPTIONS_GROUP` lets the template attach the disabling
hook by a known name; add it just below `RULE_GROUPS`:

```python
# Name of the rule group whose inputs are disabled when Basic is selected.
ADVANCED_OPTIONS_GROUP = "Advanced Options"
```

Replace `parse_ruleset_from_form` with:

```python
def parse_ruleset_from_form(form) -> RuleSet:
    """Build a :class:`RuleSet` from the toggle/radio form fields used by the
    settings page AND the wizard's per-character rules step.

    ``creation_method`` (a radio with values ``"advanced"`` / ``"basic"``) is
    the single source for ``separate_race_class``: Advanced ⇒ True. When Basic
    is chosen the Advanced-only rules (``multiclassing`` and
    ``lift_demihuman_restrictions``) are forced off regardless of what was
    posted. Unknown radio choices are silently dropped so the RuleSet defaults
    take over."""
    bool_field_names = {
        field for _, fields in RULE_GROUPS for field, _ in fields
    }
    bools = {field: field in form for field in bool_field_names}

    # Creation method radio → separate_race_class (default Advanced when absent).
    advanced = form.get("creation_method") != "basic"
    bools["separate_race_class"] = advanced
    if not advanced:
        bools["multiclassing"] = False
        bools["lift_demihuman_restrictions"] = False

    choices = {}
    for field, _label, options in CHOICE_GROUPS:
        chosen = form.get(field)
        valid_values = [v for v, _ in options]
        if chosen in valid_values:
            choices[field] = chosen

    return RuleSet(**bools, **choices)
```

Finally, pass the new constant into the settings template context. In
`get_settings`, add `"advanced_options_group": ADVANCED_OPTIONS_GROUP` to the
context dict:

```python
        {
            "ruleset": ruleset,
            "rule_groups": RULE_GROUPS,
            "choice_groups": CHOICE_GROUPS,
            "rule_labels": RULE_LABELS,
            "implemented_rules": IMPLEMENTED_RULES,
            "implemented_choice_groups": IMPLEMENTED_CHOICE_GROUPS,
            "advanced_options_group": ADVANCED_OPTIONS_GROUP,
            "saved": saved,
        },
```

- [ ] **Step 4: Run the parser tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py -k parser -q`
Expected: PASS (all 5 parser tests).

Note: other `test_settings.py` tests that still reference `max_hp_at_l1` will
fail here — that is expected and fixed in Task 7. Do not fix them now.

- [ ] **Step 5: Commit**

```powershell
git add aose/web/settings_routes.py tests/test_settings.py
git commit -m @'
feat(rules): regroup rule data + creation-method parsing with Basic enforcement

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 3: Shared Jinja partial + method section + disabling JS

**Files:**
- Create: `aose/web/templates/_ruleset_fields.html`
- Modify: `aose/web/templates/settings.html`
- Modify: `aose/web/templates/wizard/rules.html`
- Modify: `aose/web/wizard.py` (pass `advanced_options_group` into the rules-step context)
- Modify: `aose/web/static/sheet.css` (greyed-out style)

- [ ] **Step 1: Create the shared partial**

Create `aose/web/templates/_ruleset_fields.html` with the method section, the
rule-group loop (marking the Advanced Options fieldset), the choice-group loop,
and the disabling JS. It relies on `ruleset`, `rule_groups`, `choice_groups`,
`rule_labels`, `implemented_rules`, `implemented_choice_groups`, and
`advanced_options_group` being in the context (both pages supply these):

```html
{# Shared ruleset form body: creation-method radio + rule groups + choice
   groups + the progressive-enhancement JS that greys out Advanced-only rules
   when Basic is selected. Included by settings.html and wizard/rules.html
   inside their own <form>. #}

<fieldset class="rule-group creation-method">
    <legend>Character Creation Method</legend>
    <div class="radio-stack">
        <label class="radio-card {% if ruleset['separate_race_class'] %}selected{% endif %}">
            <input type="radio" name="creation_method" value="advanced" data-creation-method
                   {% if ruleset['separate_race_class'] %}checked{% endif %}>
            <span class="radio-label">Advanced</span>
            <span class="rule-desc">Choose race and class separately. Advanced
                optional rules become available.</span>
        </label>
        <label class="radio-card {% if not ruleset['separate_race_class'] %}selected{% endif %}">
            <input type="radio" name="creation_method" value="basic" data-creation-method
                   {% if not ruleset['separate_race_class'] %}checked{% endif %}>
            <span class="radio-label">Basic</span>
            <span class="rule-desc">Choose a class; the class determines race. No
                separate race step. Multi-class and lifting demihuman restrictions
                are unavailable.</span>
        </label>
    </div>
</fieldset>

{% for group_name, fields in rule_groups %}
<fieldset class="rule-group"{% if group_name == advanced_options_group %} data-advanced-only{% endif %}>
    <legend>{{ group_name }}</legend>
    {% for field, desc in fields %}
    <label class="rule">
        <input type="checkbox" name="{{ field }}"
               {% if ruleset[field] %}checked{% endif %}>
        <span class="rule-body">
            <span class="rule-name">
                {{ rule_labels[field] }}
                {% if field not in implemented_rules %}
                <span class="rule-pending" title="Saved with the character, but builder/sheet behaviour for this rule is not yet implemented.">pending</span>
                {% endif %}
            </span>
            <span class="rule-desc">{{ desc }}</span>
        </span>
    </label>
    {% endfor %}
</fieldset>
{% endfor %}

{% for field, label, options in choice_groups %}
<fieldset class="rule-group">
    <legend>{{ label }}
        {% if field not in implemented_choice_groups %}
        <span class="rule-pending" title="Saved with the character, but builder behaviour for this choice is not yet implemented.">pending</span>
        {% endif %}
    </legend>
    <div class="radio-stack">
        {% for value, opt_label in options %}
        <label class="radio-card {% if ruleset[field] == value %}selected{% endif %}">
            <input type="radio" name="{{ field }}" value="{{ value }}"
                   {% if ruleset[field] == value %}checked{% endif %}>
            <span class="radio-label">{{ opt_label }}</span>
        </label>
        {% endfor %}
    </div>
</fieldset>
{% endfor %}

<script>
(function () {
    var radios = document.querySelectorAll('[data-creation-method]');
    var advancedInputs = document.querySelectorAll('[data-advanced-only] input');
    function sync() {
        var basic = document.querySelector('[data-creation-method][value="basic"]');
        var disable = !!(basic && basic.checked);
        advancedInputs.forEach(function (el) {
            el.disabled = disable;
            var row = el.closest('.rule');
            if (row) { row.classList.toggle('rule-disabled', disable); }
        });
    }
    radios.forEach(function (r) { r.addEventListener('change', sync); });
    sync();
})();
</script>
```

- [ ] **Step 2: Point both templates at the partial**

In `aose/web/templates/settings.html`, replace the two `{% for ... %}` fieldset
loops (the `rule_groups` loop and the `choice_groups` loop, lines ~23–61) with a
single include. The surrounding `<form method="post" action="/settings" ...>`,
the intro text, the flash, and the form-actions buttons stay. The form body
becomes:

```html
    <form method="post" action="/settings" class="settings-form">

        {% include "_ruleset_fields.html" %}

        <div class="form-actions">
            <button type="submit" class="button primary">Save Settings</button>
            <a href="/" class="button">Cancel</a>
        </div>

    </form>
```

In `aose/web/templates/wizard/rules.html`, replace the two `{% for ... %}`
fieldset loops (lines ~14–52) with the include. Keep the `<h2>`, the two intro
`<p>` blocks, the `<form method="post" action="/wizard/{{ draft_id }}/rules" ...>`
wrapper, and the form-actions button. The form body becomes:

```html
<form method="post" action="/wizard/{{ draft_id }}/rules" class="settings-form step-form">

    {% include "_ruleset_fields.html" %}

    <div class="form-actions">
        <button type="submit" class="primary">
            {% if draft.abilities is defined %}Save Rules &rarr;{% else %}Continue: Roll Abilities &rarr;{% endif %}
        </button>
    </div>
</form>
```

- [ ] **Step 3: Pass `advanced_options_group` into the wizard rules context**

In `aose/web/wizard.py`, update the import from `settings_routes` to add
`ADVANCED_OPTIONS_GROUP`:

```python
from aose.web.settings_routes import (
    ADVANCED_OPTIONS_GROUP,
    CHOICE_GROUPS,
    IMPLEMENTED_CHOICE_GROUPS,
    IMPLEMENTED_RULES,
    RULE_GROUPS,
    RULE_LABELS,
    parse_ruleset_from_form,
)
```

In `get_rules`, add the key to the context update:

```python
    ctx.update({
        "ruleset": ruleset.model_dump(),
        "rule_groups": RULE_GROUPS,
        "choice_groups": CHOICE_GROUPS,
        "rule_labels": RULE_LABELS,
        "implemented_rules": IMPLEMENTED_RULES,
        "implemented_choice_groups": IMPLEMENTED_CHOICE_GROUPS,
        "advanced_options_group": ADVANCED_OPTIONS_GROUP,
    })
```

- [ ] **Step 4: Add the greyed-out style**

Append to `aose/web/static/sheet.css`:

```css
/* Advanced-only rules greyed out when Basic creation method is selected. */
.rule-disabled { opacity: 0.45; }
```

- [ ] **Step 5: Smoke-test both pages render**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py -k "renders or get_rules or renders_every" -q`
Expected: the rendering tests that don't assert on `max_hp_at_l1` pass
(`test_get_settings_renders`). Some matrix tests still reference removed flags
and are fixed in Task 7. If unsure, run a manual render check instead:

```powershell
.venv\Scripts\python.exe -c @'
from pathlib import Path
from fastapi.testclient import TestClient
from aose.web.app import create_app
import tempfile
d = Path(tempfile.mkdtemp())
(d / "examples").mkdir()
app = create_app(data_dir=Path("data"), characters_dir=d/"c", drafts_dir=d/"dr",
                 examples_dir=d/"examples", settings_path=d/"s.json")
c = TestClient(app, follow_redirects=False)
r = c.get("/settings")
assert r.status_code == 200, r.status_code
assert "Character Creation Method" in r.text
assert "data-advanced-only" in r.text
assert "data-creation-method" in r.text
print("settings OK")
loc = c.get("/wizard/new").headers["location"]
did = loc.split("/")[2]
r = c.get(f"/wizard/{did}/rules")
assert r.status_code == 200
assert "Character Creation Method" in r.text
assert "data-advanced-only" in r.text
print("rules OK")
'@
```
Expected: prints `settings OK` then `rules OK`.

- [ ] **Step 6: Commit**

```powershell
git add aose/web/templates/_ruleset_fields.html aose/web/templates/settings.html aose/web/templates/wizard/rules.html aose/web/wizard.py aose/web/static/sheet.css
git commit -m @'
feat(rules-ui): creation-method section + shared partial + Basic-disabling JS

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 4: Engine + wizard gating renames (demihuman → lift)

**Files:**
- Modify: `aose/engine/leveling.py:65`
- Modify: `aose/web/wizard.py` (`_class_allowed_for_race`, class-step level cap)
- Test: `tests/test_demihuman_rules.py` (rewritten in this task)
- Test: `tests/test_leveling.py` (two constructor sites)

- [ ] **Step 1: Rewrite the demihuman-rules test for the merged flag**

Replace the whole of `tests/test_demihuman_rules.py` with the version below. It
swaps `RuleSet(demihuman_class_restrictions=False)` / `demihuman_level_limits`
for the single `lift_demihuman_restrictions=True`, and collapses the two old
"snapshot" assertions into one. Key inversions: old `demihuman_*=True` (default)
≡ new `lift_demihuman_restrictions=False`; old `demihuman_*=False` ≡ new
`lift_demihuman_restrictions=True`.

```python
"""Tests for the merged lift_demihuman_restrictions rule (class restrictions
+ level caps lifted together)."""
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, load_draft, save_draft, save_settings
from aose.data.loader import GameData
from aose.models import CharacterSpec, ClassEntry, Race, RuleSet
from aose.sheet.view import _xp_to_next
from aose.web.app import create_app
from aose.web.wizard import _class_allowed_for_race

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture
def client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    settings_path = tmp_path / "settings.json"
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._settings_path = settings_path
    client._drafts_dir = drafts_dir
    client._characters_dir = characters_dir
    return client


# ── Helper: _class_allowed_for_race ────────────────────────────────────────

def _restrictive_race(allowed: list[str]) -> Race:
    return Race(id="x", name="X", allowed_classes=allowed)


def _open_race() -> Race:
    return Race(id="x", name="X", allowed_classes=[])  # human-style


def test_helper_blocks_unlisted_class_when_restrictions_apply():
    race = _restrictive_race(["fighter"])
    assert _class_allowed_for_race("magic_user", race, RuleSet()) is False


def test_helper_allows_listed_class_when_restrictions_apply():
    race = _restrictive_race(["fighter"])
    assert _class_allowed_for_race("fighter", race, RuleSet()) is True


def test_helper_allows_anything_when_restrictions_lifted():
    race = _restrictive_race(["fighter"])
    rs = RuleSet(lift_demihuman_restrictions=True)
    assert _class_allowed_for_race("magic_user", race, rs) is True
    assert _class_allowed_for_race("anything_at_all", race, rs) is True


def test_helper_treats_empty_allowed_as_unrestricted():
    race = _open_race()
    assert _class_allowed_for_race("anything", race, RuleSet()) is True


# ── Wizard: level-cap display ──────────────────────────────────────────────

def _start_through_race(client, race_id="dwarf"):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": race_id})
    return draft_id


def test_class_page_shows_dwarf_cap_by_default(client):
    draft_id = _start_through_race(client)
    r = client.get(f"/wizard/{draft_id}/class")
    # Dwarf caps Fighter at 9
    assert "max level: 9" in r.text


def test_class_page_hides_cap_when_lifted(client):
    save_settings(client._settings_path, RuleSet(lift_demihuman_restrictions=True))
    draft_id = _start_through_race(client)
    r = client.get(f"/wizard/{draft_id}/class")
    assert "max level" not in r.text


# ── Wizard: class restrictions enforcement ────────────────────────────────

def test_class_card_marked_unavailable_when_restricted(client):
    """All data has only 'fighter', which Dwarf allows.  Patch a synthetic
    class into game_data to exercise the rejection path."""
    from aose.models.character_class import CharClass, ClassLevelData

    fake = CharClass(
        id="magic_user",
        name="Magic-User",
        prime_requisites=[],
        max_level=14,
        hit_die="1d4",
        weapons_allowed=[],
        armor_allowed=[],
        shields_allowed=False,
        progression={
            1: ClassLevelData(
                xp_required=0, thac0=19, hit_dice="1d4",
                saves={"death": 13, "wands": 14, "paralysis": 13, "breath": 16, "spells": 15},
            ),
        },
    )
    original = client.app.state.game_data
    patched_classes = dict(original.classes)
    patched_classes["magic_user"] = fake
    client.app.state.game_data = replace(original, classes=patched_classes)
    try:
        draft_id = _start_through_race(client)  # dwarf
        # Dwarf doesn't allow magic_user → POST should 400
        r = client.post(f"/wizard/{draft_id}/class", data={"class_id": "magic_user"})
        assert r.status_code == 400

        # Now lift restrictions and try again
        save_settings(client._settings_path, RuleSet(lift_demihuman_restrictions=True))
        draft_id = _start_through_race(client)
        r = client.post(f"/wizard/{draft_id}/class", data={"class_id": "magic_user"})
        assert r.status_code == 303
    finally:
        client.app.state.game_data = original


# ── Sheet: _xp_to_next respects the rule ──────────────────────────────────

def _dwarf_fighter(level: int, ruleset: RuleSet, hp_rolls: list[int] | None = None) -> CharacterSpec:
    return CharacterSpec(
        name="Thorin",
        abilities={"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10},
        race_id="dwarf",
        classes=[ClassEntry(
            class_id="fighter",
            level=level,
            hp_rolls=hp_rolls or [8] * level,
        )],
        alignment="law",
        ruleset=ruleset,
    )


def test_xp_to_next_at_l1_unaffected_by_either_rule_setting():
    """L1 → L2 is far below any cap, so both settings yield the same result."""
    data = GameData.load(DATA_DIR)
    on = _dwarf_fighter(1, RuleSet(lift_demihuman_restrictions=False))
    off = _dwarf_fighter(1, RuleSet(lift_demihuman_restrictions=True))
    assert _xp_to_next(on, data) == _xp_to_next(off, data) == (2, 2000)


def test_xp_to_next_returns_none_at_race_cap_by_default(tmp_path):
    """Synthetic race that caps fighter at L2 — at L2 we should see no next."""
    data = GameData.load(DATA_DIR)
    patched_race = data.races["dwarf"].model_copy(update={
        "class_level_caps": {"fighter": 2},
    })
    data = replace(data, races={**data.races, "dwarf": patched_race})

    spec = _dwarf_fighter(2, RuleSet(lift_demihuman_restrictions=False))
    assert _xp_to_next(spec, data) == (None, None)


def test_xp_to_next_ignores_race_cap_when_lifted():
    data = GameData.load(DATA_DIR)
    patched_race = data.races["dwarf"].model_copy(update={
        "class_level_caps": {"fighter": 2},
    })
    data = replace(data, races={**data.races, "dwarf": patched_race})

    spec = _dwarf_fighter(2, RuleSet(lift_demihuman_restrictions=True))
    # With limits lifted, the race cap is ignored — class progression gives L3 = 4000 XP
    assert _xp_to_next(spec, data) == (3, 4000)


def test_xp_to_next_still_bounded_by_class_max_when_lifted():
    """Even with limits lifted, the class's own max_level still applies."""
    data = GameData.load(DATA_DIR)
    patched_cls = data.classes["fighter"].model_copy(update={"max_level": 3})
    data = replace(data, classes={**data.classes, "fighter": patched_cls})

    spec = _dwarf_fighter(3, RuleSet(lift_demihuman_restrictions=True))
    assert _xp_to_next(spec, data) == (None, None)


# ── End-to-end: settings → character snapshot ─────────────────────────────

def test_character_snapshots_lift_rule_choice(client):
    save_settings(client._settings_path, RuleSet(lift_demihuman_restrictions=True))
    draft_id = _start_through_race(client)
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    spec = load_character(char_id, client._characters_dir)
    assert spec.ruleset.lift_demihuman_restrictions is True
```

- [ ] **Step 2: Fix the two `RuleSet` constructor sites in `tests/test_leveling.py`**

In `tests/test_leveling.py`, lines ~131 and ~140, the level-cap behaviour is now
keyed on the inverted flag. Change:

```python
                 ruleset=RuleSet(demihuman_level_limits=True))
```
to
```python
                 ruleset=RuleSet(lift_demihuman_restrictions=False))
```
and
```python
                 ruleset=RuleSet(demihuman_level_limits=False))
```
to
```python
                 ruleset=RuleSet(lift_demihuman_restrictions=True))
```

- [ ] **Step 3: Run the tests to verify they fail (engine not yet renamed)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_demihuman_rules.py tests/test_leveling.py -q`
Expected: FAIL — `leveling.py` and `wizard.py` still read the old flags, so the
lift behaviour is inverted/broken.

- [ ] **Step 4: Rename the flag reads in the engine and wizard**

In `aose/engine/leveling.py`, `_effective_max_level` (~line 65), change:

```python
    if spec.ruleset.demihuman_level_limits:
```
to
```python
    if not spec.ruleset.lift_demihuman_restrictions:
```

In `aose/web/wizard.py`, `_class_allowed_for_race` (~line 504), update the
docstring and the guard:

```python
def _class_allowed_for_race(class_id: str, race, ruleset: RuleSet) -> bool:
    """Return whether a race may pick a class, given the active ruleset.

    With ``lift_demihuman_restrictions`` on, any race may pick any class.
    Otherwise an empty ``allowed_classes`` is treated as "no restriction"
    (the human-style default), and a populated list is enforced.
    """
    if ruleset.lift_demihuman_restrictions:
        return True
    if not race.allowed_classes:
        return True
    return class_id in race.allowed_classes
```

In `aose/web/wizard.py`, `get_class` (~line 548), change the level-cap lookup:

```python
            level_cap = (
                race.class_level_caps.get(cls.id)
                if not ruleset.lift_demihuman_restrictions
                else None
            )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_demihuman_rules.py tests/test_leveling.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add aose/engine/leveling.py aose/web/wizard.py tests/test_demihuman_rules.py tests/test_leveling.py
git commit -m @'
feat(demihuman): gate class restrictions + level caps on lift_demihuman_restrictions

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 5: HP step — drop `max_hp_at_l1` everywhere; remove `take_max`

**Files:**
- Modify: `aose/web/wizard.py` (`_apply_rule_changes`, `get_hp`, `post_hp_roll`)
- Modify: `aose/web/templates/wizard/hp.html`
- Modify: `aose/engine/dice.py` (`roll_hp` — remove the now-dead `take_max`)
- Test: `tests/test_dice.py` (remove the take_max tests)
- Test: `tests/test_multiclassing.py` (remove the max-HP autofill test)

- [ ] **Step 1: Remove the `take_max` tests in `tests/test_dice.py`**

Delete the three tests under the `# ── roll_hp: max_hp_at_l1 ──` heading
(`test_roll_hp_take_max_d8`, `test_roll_hp_take_max_d6`,
`test_roll_hp_take_max_does_not_consume_rng`) and the heading comment line
itself. Leave the reroll-1s/2s tests below intact.

- [ ] **Step 2: Remove the max-HP autofill test in `tests/test_multiclassing.py`**

Delete `test_max_hp_rule_autofills_max_rolls_for_each_class` (the test at
~line 244 that constructs `RuleSet(multiclassing=True, max_hp_at_l1=True)` and
asserts `draft["hp_rolls"] == [8, 4]`).

- [ ] **Step 3: Edit `_apply_rule_changes` in `aose/web/wizard.py`**

Replace the body from the docstring's HP bullet through the multiclass clear.
Drop the `max_hp_at_l1` condition, keep the reroll clear, and add the defensive
`lift_demihuman_restrictions` clear. The function becomes:

```python
def _apply_rule_changes(draft: dict[str, Any], old_rs: RuleSet, new_rs: RuleSet) -> None:
    """Save the new ruleset on the draft and apply targeted clears for any
    rule changes that would invalidate downstream choices.

    Cascading clears (most disruptive first):

    * ability_roll_method change OR abilities not yet rolled  → re-seed
      abilities + clear everything from race down.
    * separate_race_class toggle → clear race + class + below (the race-as-class
      flow restructures both steps).
    * lift_demihuman_restrictions toggle → clear class + below (mirrors a race
      change, so an on→off flip can't leave a now-illegal class/level pick).
    * reroll_1s_2s_hp_l1 change → clear hp_roll(s) only.
    * weapon_proficiency change → clear proficiencies only.
    * multiclassing turned OFF while a combo is picked → clear class + below.
    """
    draft["ruleset"] = new_rs.model_dump()

    if (new_rs.ability_roll_method != old_rs.ability_roll_method
            or "abilities" not in draft):
        _seed_draft_abilities(draft, new_rs)
        _clear_after_abilities(draft)
        return

    if new_rs.separate_race_class != old_rs.separate_race_class:
        _clear_after_abilities(draft)
        return

    if new_rs.lift_demihuman_restrictions != old_rs.lift_demihuman_restrictions:
        _clear_after_race(draft)

    if new_rs.reroll_1s_2s_hp_l1 != old_rs.reroll_1s_2s_hp_l1:
        draft.pop("hp_roll", None)
        draft.pop("hp_rolls", None)

    if new_rs.weapon_proficiency != old_rs.weapon_proficiency:
        draft.pop("proficiencies", None)

    if not new_rs.multiclassing and "class_ids" in draft:
        _clear_after_race(draft)
```

- [ ] **Step 4: Edit `get_hp` in `aose/web/wizard.py`**

Remove the `max_hp_at_l1` auto-fill block (the `if ruleset.max_hp_at_l1:` block,
~lines 869–876) entirely. Then remove the `"max_hp_rule"` key from the context
dict (~line 908). The context update becomes:

```python
    ctx = _base_context(request, draft_id, draft, "hp")
    ctx.update({
        "is_multi": is_multi,
        "class_name": " / ".join(c.name for c in classes),
        "hit_die": classes[0].hit_die,  # single-class template uses this
        "con_mod": con_mod,
        "rolls": rolls_for_template,
        "total_hp": total,
        "reroll_rule": ruleset.reroll_1s_2s_hp_l1,
        "ready": (total is not None),
    })
    return templates.TemplateResponse(request, "wizard.html", ctx)
```

- [ ] **Step 5: Edit `post_hp_roll` in `aose/web/wizard.py`**

Remove the `take_max` computation and the `take_max=` arguments. The roll calls
become reroll-only:

```python
@router.post("/{draft_id}/hp/roll")
async def post_hp_roll(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    ruleset = _ruleset_of(draft)
    ids = _class_ids(draft)
    classes = [data.classes[cid] for cid in ids]

    min_die = 3 if ruleset.reroll_1s_2s_hp_l1 else 1

    if len(ids) == 1:
        draft["hp_roll"] = roll_hp(classes[0].hit_die, min_die=min_die)
        draft.pop("hp_rolls", None)
    else:
        draft["hp_rolls"] = [
            roll_hp(c.hit_die, min_die=min_die) for c in classes
        ]
        draft.pop("hp_roll", None)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/hp")
```

- [ ] **Step 6: Edit `aose/web/templates/wizard/hp.html`**

Remove the `max_hp_rule` branch and always show the Roll button. Replace the
banner block (lines ~13–18) with just the reroll banner:

```html
{% if reroll_rule %}
<p class="rule-active"><strong>Reroll 1s &amp; 2s at L1</strong> is active &mdash; any 1 or 2 on a hit die is rerolled.</p>
{% endif %}
```

Replace the conditional roll-button block (lines ~41–45) with an unconditional
one:

```html
<form method="post" action="/wizard/{{ draft_id }}/hp/roll" class="inline-form">
    <button type="submit">{% if ready %}Re-roll{% else %}Roll HP{% endif %}</button>
</form>
```

- [ ] **Step 7: Remove `take_max` from `aose/engine/dice.py`**

`take_max` now has no callers. Simplify `roll_hp`:

```python
def roll_hp(
    hit_die: str,
    rng: Optional[random.Random] = None,
    *,
    min_die: int = 1,
) -> int:
    """Roll first-level HP from a hit die, with an optional re-roll house rule.

    min_die > 1 -> any single-die result below ``min_die`` is re-rolled until it
                   lands at or above it ("re-roll 1s & 2s" uses 3). Silently
                   treated as 1 if the die can't reach ``min_die``.
    """
    m = _NDS_RE.match(hit_die)
    if not m:
        raise ValueError(f"Invalid dice notation: {hit_die!r}")
    n, s = int(m.group(1)), int(m.group(2))

    effective_min = min_die if min_die <= s else 1
    r = rng or random.Random()
    total = 0
    for _ in range(n):
        v = r.randint(1, s)
        while v < effective_min:
            v = r.randint(1, s)
        total += v
    return total
```

- [ ] **Step 8: Run the affected tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_dice.py tests/test_multiclassing.py -q`
Expected: PASS (the take_max + max-HP tests are gone; reroll/normal-roll tests
still pass).

- [ ] **Step 9: Commit**

```powershell
git add aose/web/wizard.py aose/web/templates/wizard/hp.html aose/engine/dice.py tests/test_dice.py tests/test_multiclassing.py
git commit -m @'
feat(hp): drop max_hp_at_l1 rule; HP at L1 is always rolled (reroll optional)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 6: Sheet rules-summary label map

**Files:**
- Modify: `aose/sheet/view.py` (`OPTIONAL_RULE_LABELS`)

- [ ] **Step 1: Edit `OPTIONAL_RULE_LABELS`**

In `aose/sheet/view.py` (~line 33), drop `max_hp_at_l1` and add the merged
label. The dict becomes:

```python
OPTIONAL_RULE_LABELS = {
    "ascending_ac": "Ascending AC",
    "secondary_skills": "Secondary Skills",
    "weapon_proficiency": "Weapon Proficiency",
    "multiclassing": "Multiclassing",
    "reroll_1s_2s_hp_l1": "Reroll 1s & 2s for HP at L1",
    "lift_demihuman_restrictions": "Lift Demihuman Class & Level Restrictions",
    "variable_weapon_damage": "Variable Weapon Damage",
}
```

`active_optional_rules` (~line 354) iterates this dict via `getattr(rs, field)`,
so dropping the dead key and adding the live one is all that's needed — the
sheet now lists "Lift Demihuman …" only when the character has it on.

- [ ] **Step 2: Verify the sheet view imports cleanly**

Run: `.venv\Scripts\python.exe -c "import aose.sheet.view; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```powershell
git add aose/sheet/view.py
git commit -m @'
feat(sheet): rules summary lists lift_demihuman_restrictions, drops max-HP label

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 7: Update remaining tests + example; add new behaviour tests

**Files:**
- Modify: `examples/thorin.json`
- Modify: `tests/test_settings.py` (purge `max_hp_at_l1`; add Basic-enforcement + pending-badge guards)
- Modify: `tests/test_wizard_rules_step.py` (form helper + toggling tests; add mid-wizard lift clear)

- [ ] **Step 1: Fix the example character ruleset**

In `examples/thorin.json`, the `ruleset` object carries removed keys. Because
`RuleSet` uses `extra="forbid"`, they must be deleted (lift defaults to False, so
no replacement key is needed). Change the `ruleset` block to:

```json
  "ruleset": {
    "ascending_ac": false,
    "secondary_skills": false,
    "weapon_proficiency": false,
    "multiclassing": false,
    "reroll_1s_2s_hp_l1": false,
    "separate_race_class": true,
    "variable_weapon_damage": false,
    "ability_roll_method": "3d6_in_order",
    "encumbrance": "basic"
  }
```

- [ ] **Step 2: Purge `max_hp_at_l1` from `tests/test_settings.py` and add guards**

Make these edits in `tests/test_settings.py`:

(a) In `test_save_then_load_roundtrip`, replace the `max_hp_at_l1` usage:
```python
def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(path, RuleSet(ascending_ac=True, reroll_1s_2s_hp_l1=True))
    rs = load_settings(path)
    assert rs.ascending_ac is True
    assert rs.reroll_1s_2s_hp_l1 is True
```

(b) In `test_post_settings_persists_to_disk`, swap the posted `max_hp_at_l1` for
`reroll_1s_2s_hp_l1` and update the assertion:
```python
def test_post_settings_persists_to_disk(client):
    r = client.post("/settings", data={
        "ascending_ac": "on",
        "reroll_1s_2s_hp_l1": "on",
        "ability_roll_method": "3d6_arrange",
        "encumbrance": "detailed",
    })
    assert r.status_code == 303
    assert r.headers["location"] == "/settings?saved=1"

    rs = load_settings(client._settings_path)
    assert rs.ascending_ac is True
    assert rs.reroll_1s_2s_hp_l1 is True
    assert rs.ability_roll_method == "3d6_arrange"
    assert rs.encumbrance == "detailed"
    assert rs.weapon_proficiency is False
```

(c) In `test_new_character_inherits_active_ruleset`, swap the flag:
```python
def test_new_character_inherits_active_ruleset(client, tmp_path):
    save_settings(client._settings_path, RuleSet(ascending_ac=True, reroll_1s_2s_hp_l1=True))
    char_id = _run_wizard_to_completion(client, tmp_path / "drafts")
    spec = load_character(char_id, tmp_path / "characters")
    assert spec.ruleset.ascending_ac is True
    assert spec.ruleset.reroll_1s_2s_hp_l1 is True
```

(d) Delete the entire `# ── Max HP at L1 ──` section: the helper
`_start_draft_with` is shared with the reroll tests below it, so **keep**
`_start_draft_with`, but delete the three `test_max_hp_rule_*` tests
(`test_max_hp_rule_auto_fills_on_get`, `test_max_hp_rule_hides_roll_button`,
`test_max_hp_rule_persists_to_character`).

(e) Add a Basic-enforcement end-to-end test and confirm the pending-badge guard
still holds (the existing `test_no_pending_badges_when_all_rules_implemented`
needs no change — it asserts the absence of the badge, which our new
`IMPLEMENTED_RULES` preserves). Append:

```python
def test_settings_page_shows_creation_method(client):
    r = client.get("/settings")
    assert "Character Creation Method" in r.text
    assert 'value="basic"' in r.text
    assert 'value="advanced"' in r.text


def test_post_settings_basic_forces_advanced_rules_off(client):
    """Posting Basic with multiclassing + lift checked still persists them off."""
    client.post("/settings", data={
        "creation_method": "basic",
        "multiclassing": "on",
        "lift_demihuman_restrictions": "on",
    })
    rs = load_settings(client._settings_path)
    assert rs.separate_race_class is False
    assert rs.multiclassing is False
    assert rs.lift_demihuman_restrictions is False
```

- [ ] **Step 3: Update `tests/test_wizard_rules_step.py` form helper + tests**

(a) Replace `_TRUE_DEFAULTS` and `_rules_form` so the form models the new shape
(creation-method radio instead of `separate_race_class`/demihuman checkboxes):

```python
# Bool rules that ship True in RuleSet() and ARE rendered as checkboxes.  The
# creation method (separate_race_class) is now a radio, handled separately.
_TRUE_DEFAULTS = ()


def _rules_form(**overrides):
    """Build form data for POST /wizard/{id}/rules matching RuleSet() defaults.
    Pass ``rule="on"`` to enable a bool, ``rule=None`` to drop it, or override
    ``creation_method`` ("advanced"/"basic") and the radio choices directly."""
    data = {
        "ability_roll_method": "3d6_in_order",
        "encumbrance": "basic",
        "creation_method": "advanced",
    }
    for r in _TRUE_DEFAULTS:
        data[r] = "on"
    for k, v in overrides.items():
        if v is None:
            data.pop(k, None)
        else:
            data[k] = v
    return data
```

(b) In `test_get_rules_renders_every_bool_toggle`, the asserted field list still
references `max_hp_at_l1` and `separate_race_class` (now a radio, not a
checkbox). Update it to the live checkboxes plus a creation-method check:

```python
def test_get_rules_renders_every_bool_toggle(client):
    draft_id = _start(client)
    r = client.get(f"/wizard/{draft_id}/rules")
    for field in ("ascending_ac", "weapon_proficiency", "secondary_skills",
                  "multiclassing", "lift_demihuman_restrictions"):
        assert f'name="{field}"' in r.text, f"missing toggle for {field}"
    # Creation method is a radio, not a checkbox
    assert 'name="creation_method"' in r.text
```

(c) In `test_get_rules_prefills_from_settings`, `max_hp_at_l1=True` is gone.
Swap for a still-present rule:

```python
def test_get_rules_prefills_from_settings(tmp_path):
    """The settings.json defaults flow into a fresh draft."""
    client = _make_client(tmp_path, RuleSet(ascending_ac=True, multiclassing=True))
    draft_id = _start(client)
    r = client.get(f"/wizard/{draft_id}/rules")
    idx = r.text.index('name="ascending_ac"')
    snippet = r.text[idx - 10:idx + 80]
    assert "checked" in snippet
```

(d) `test_toggling_separate_race_class_clears_race_and_class` must drive the
radio. Replace its final POST + assertions:

```python
    # Switch to Basic (separate_race_class off)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(creation_method="basic"))
    draft = load_draft(draft_id, client._drafts_dir)
    assert "race_id" not in draft
    assert "class_id" not in draft
```

(e) Replace `test_toggling_max_hp_rule_clears_hp_only` with a reroll-rule
version (the reroll toggle is the remaining HP rule that clears hp only):

```python
def test_toggling_reroll_hp_rule_clears_hp_only(client):
    draft_id = _start(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form())
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "T"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    assert "hp_roll" in load_draft(draft_id, client._drafts_dir)

    # Toggle reroll_1s_2s_hp_l1 on
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(reroll_1s_2s_hp_l1="on"))
    draft = load_draft(draft_id, client._drafts_dir)
    assert "hp_roll" not in draft  # cleared so HP step re-rolls under new rule
    assert draft.get("race_id") == "dwarf"
    assert draft.get("class_id") == "fighter"
    assert draft.get("alignment") == "law"
```

(f) Add two new tests at the end of the file — Basic forces flags off via the
wizard, and changing lift mid-wizard clears class + downstream:

```python
def test_basic_method_via_wizard_forces_advanced_rules_off(client):
    draft_id = _start(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(
        creation_method="basic", multiclassing="on", lift_demihuman_restrictions="on",
    ))
    rs = load_draft(draft_id, client._drafts_dir)["ruleset"]
    assert rs["separate_race_class"] is False
    assert rs["multiclassing"] is False
    assert rs["lift_demihuman_restrictions"] is False


def test_changing_lift_demihuman_clears_class_and_downstream(client):
    draft_id = _start(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form())
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "T"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    assert "class_id" in load_draft(draft_id, client._drafts_dir)

    # Flip lift_demihuman_restrictions on — class + downstream must clear, race stays
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(lift_demihuman_restrictions="on"))
    draft = load_draft(draft_id, client._drafts_dir)
    assert "class_id" not in draft
    assert draft.get("race_id") == "dwarf"  # race survives (mirrors a race change clear)
```

- [ ] **Step 4: Run the two updated test files**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py tests/test_wizard_rules_step.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add examples/thorin.json tests/test_settings.py tests/test_wizard_rules_step.py
git commit -m @'
test(rules): cover creation-method + lift_demihuman; drop max-HP tests; fix example

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 8: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all tests pass (ignore the trailing `pytest-current` `PermissionError`
Windows quirk). If `tests/test_equip_attacks.py`, `tests/test_equipment.py`,
`tests/test_containers.py`, or `tests/test_magic_items.py` fail: they post the
removed keys (`demihuman_level_limits`, `demihuman_class_restrictions`,
`separate_race_class`) as wizard form data. Those keys are now ignored by the
parser (Advanced is the default when `creation_method` is absent), so the posts
should still succeed and leave `separate_race_class=True`. If any of these fail,
remove the three stale keys from their `/rules` form dicts and add
`"creation_method": "advanced"` — do not change their assertions.

- [ ] **Step 2: Manual render check of both rules surfaces**

Reuse the smoke-test snippet from Task 3, Step 5; additionally confirm Basic
greying works without JS by asserting the server enforcement holds (already
covered by `test_post_settings_basic_forces_advanced_rules_off` and
`test_basic_method_via_wizard_forces_advanced_rules_off`).

- [ ] **Step 3: Update CLAUDE.md "Optional rules" note (optional, low priority)**

If the suite is green, optionally add a one-line note under the project's
"Current state" or wiring section that `max_hp_at_l1` was removed and the two
demihuman flags merged into `lift_demihuman_restrictions`, with Basic/Advanced
now a creation-method radio over `separate_race_class`. Keep it terse.

- [ ] **Step 4: Final commit (if any docs changed)**

```powershell
git add CLAUDE.md
git commit -m @'
docs: note demihuman flag merge + creation-method radio (wizard slice 1)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

## Self-Review (author checklist — completed during planning)

**Spec coverage:**
- §1 RuleSet model (remove max_hp_at_l1, merge demihuman → lift, keep separate_race_class) → Task 1. ✔
- §2 Rules-page presentation (method section, regrouped RULE_GROUPS, render order) → Tasks 2 + 3. ✔
- §3 Gating behaviour (display greying via JS; server forces Basic) → Task 2 (parser) + Task 3 (JS/`data-advanced-only`). ✔
- §4 Engine/wizard touch-points: leveling.py rename → Task 4; `_class_allowed_for_race` + level-cap → Task 4; HP step + `_apply_rule_changes` + `take_max` drop → Task 5; sheet view label → Task 6. ✔
- §5 settings_routes (labels, implemented, groups, parser) → Task 2. ✔
- §6 Tests (updated files + 4 new tests) → Tasks 1, 2, 4, 5, 7. New tests: Basic forces flags off (Task 2 parser + Task 7 e2e ×2); lift lifts both restriction+caps (Task 4); mid-wizard lift clear (Task 7); pending-badge guard preserved (Task 7 Step 2e). ✔

**Placeholder scan:** No TBD/"handle edge cases"/"similar to" — every code step
shows full code. ✔

**Type/name consistency:** New field `lift_demihuman_restrictions` (snake_case)
used identically across model, parser, engine, wizard, sheet, templates, tests.
Form radio name `creation_method` with values `advanced`/`basic` consistent
between partial, parser, and tests. Context key `advanced_options_group` matches
the constant `ADVANCED_OPTIONS_GROUP` and the partial's `group_name ==
advanced_options_group` comparison. ✔
