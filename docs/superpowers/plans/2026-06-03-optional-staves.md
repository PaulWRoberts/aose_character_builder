# Optional Staves Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single optional rule that lets spellcasting classes (magic-user, illusionist) wield a mundane staff in combat, gating the staff's equip/proficiency availability behind a `RuleSet` toggle.

**Architecture:** A new `CharClass.optional_weapons_allowed` list holds weapons usable only when the new `RuleSet.optional_staves` flag is on. `allowed_weapon_ids` gains an optional `ruleset` param that unions those weapons in when the flag is set; this single engine change flows to both `equip()` enforcement and the inventory `class_allowed` flag. The flag is registered in the settings page's rule groups, which auto-wires both the settings page and the wizard `/rules` step.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, pytest. Run tests with `.venv\Scripts\python.exe -m pytest`.

---

## File Structure

- `aose/models/ruleset.py` — add `optional_staves: bool = False`.
- `aose/models/character_class.py` — add `optional_weapons_allowed: list[str]`.
- `aose/engine/proficiency.py` — `allowed_weapon_ids` gains `ruleset=None` param.
- `data/classes/magic_user.yaml`, `data/classes/illusionist.yaml` — move `staff` from `weapons_allowed` to `optional_weapons_allowed`.
- `aose/web/routes.py` (2 call sites), `aose/web/wizard.py` (4 call sites) — thread the per-character ruleset into `allowed_weapon_ids`.
- `aose/web/settings_routes.py` — register the rule (label, implemented set, Combat group).
- `tests/test_optional_staves.py` (new) — model + engine + data integration tests.
- `tests/test_weapon_proficiency.py` (modify) — update the two magic-user proficiency tests affected by the data move; add positive rule-on coverage.

---

## Task 1: Model fields

**Files:**
- Modify: `aose/models/ruleset.py`
- Modify: `aose/models/character_class.py`
- Test: `tests/test_optional_staves.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_optional_staves.py`:

```python
"""Optional Staves rule: model fields, engine gating, and data integration."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.models import CharClass, RuleSet

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


def test_ruleset_defaults_optional_staves_off():
    assert RuleSet().optional_staves is False


def test_charclass_optional_weapons_defaults_empty(data):
    # Fighter has no optional weapons in data.
    assert data.classes["fighter"].optional_weapons_allowed == []


def test_charclass_accepts_optional_weapons_list(data):
    cls = data.classes["fighter"].model_copy(
        update={"optional_weapons_allowed": ["staff"]}
    )
    assert cls.optional_weapons_allowed == ["staff"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_optional_staves.py -q`
Expected: FAIL — `RuleSet` has no attribute `optional_staves` / `CharClass` rejects `optional_weapons_allowed` (extra="forbid").

- [ ] **Step 3: Add the RuleSet flag**

In `aose/models/ruleset.py`, after `human_racial_abilities: bool = False` (line ~21) add:

```python
    optional_staves: bool = False
```

- [ ] **Step 4: Add the CharClass field**

In `aose/models/character_class.py`, after the `weapons_allowed: AllowedList` line (line ~46) add:

```python
    # Weapons a class may use in combat ONLY when an optional rule is on.
    # Today this is the staff, gated by RuleSet.optional_staves (the AOSE
    # "Magic-Users/Illusionists and Staves" optional rules). Resolved through
    # the same path as weapons_allowed and unioned in by allowed_weapon_ids.
    optional_weapons_allowed: list[str] = Field(default_factory=list)
```

(`Field` is already imported in this module.)

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_optional_staves.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add aose/models/ruleset.py aose/models/character_class.py tests/test_optional_staves.py
git commit -m "feat: add optional_staves flag and optional_weapons_allowed field"
```

---

## Task 2: Engine gating in `allowed_weapon_ids`

**Files:**
- Modify: `aose/engine/proficiency.py`
- Test: `tests/test_optional_staves.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_optional_staves.py`:

```python
from aose.engine.proficiency import allowed_weapon_ids


def _caster_with_optional_staff(data):
    # A constructed class: dagger allowed, staff optional. Independent of the
    # YAML edits in Task 3 so this test is isolated.
    return data.classes["magic_user"].model_copy(
        update={"weapons_allowed": ["dagger"], "optional_weapons_allowed": ["staff"]}
    )


def test_optional_weapon_excluded_when_ruleset_none(data):
    cls = _caster_with_optional_staff(data)
    allowed = allowed_weapon_ids([cls], data)
    assert "dagger" in allowed
    assert "staff" not in allowed


def test_optional_weapon_excluded_when_rule_off(data):
    cls = _caster_with_optional_staff(data)
    allowed = allowed_weapon_ids([cls], data, RuleSet(optional_staves=False))
    assert "staff" not in allowed


def test_optional_weapon_included_when_rule_on(data):
    cls = _caster_with_optional_staff(data)
    allowed = allowed_weapon_ids([cls], data, RuleSet(optional_staves=True))
    assert "dagger" in allowed
    assert "staff" in allowed


def test_optional_weapon_ignored_for_unrestricted_class(data):
    # A class whose weapons_allowed == "all" stays "all" regardless.
    fighter = data.classes["fighter"].model_copy(
        update={"optional_weapons_allowed": ["staff"]}
    )
    assert allowed_weapon_ids([fighter], data, RuleSet(optional_staves=True)) == "all"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_optional_staves.py -q`
Expected: FAIL — `test_optional_weapon_included_when_rule_on` (staff not unioned), and the rule-on call passes an unexpected 3rd positional arg → `TypeError`.

- [ ] **Step 3: Implement the ruleset param**

In `aose/engine/proficiency.py`, replace the whole `allowed_weapon_ids` function (lines ~182-190):

```python
def allowed_weapon_ids(classes: list[CharClass], data, ruleset=None) -> "set[str] | str":
    weapons = [i for i in data.items.values() if isinstance(i, Weapon)]
    optional_on = bool(ruleset is not None and getattr(ruleset, "optional_staves", False))
    per_class: list["set[str] | str"] = []
    for cls in classes:
        if cls.weapons_allowed == "all":
            per_class.append("all")
            continue
        resolved = _resolve_entries(list(cls.weapons_allowed), weapons)
        if optional_on and cls.optional_weapons_allowed and resolved != "all":
            extra = _resolve_entries(list(cls.optional_weapons_allowed), weapons)
            if extra == "all":
                resolved = "all"
            else:
                resolved = resolved | extra
        per_class.append(resolved)
    return _union(per_class)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_optional_staves.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Run the equip-enforcement suite (no-ruleset callers unaffected)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_enforcement.py -q`
Expected: PASS (existing `allowed_weapon_ids(classes, data)` calls behave exactly as before).

- [ ] **Step 6: Commit**

```bash
git add aose/engine/proficiency.py tests/test_optional_staves.py
git commit -m "feat: union optional weapons into allowed_weapon_ids when rule on"
```

---

## Task 3: Move staff to optional in class data

**Files:**
- Modify: `data/classes/magic_user.yaml`
- Modify: `data/classes/illusionist.yaml`
- Test: `tests/test_optional_staves.py` (data integration), `tests/test_weapon_proficiency.py` (fix affected test)

- [ ] **Step 1: Write the failing data-integration test**

Append to `tests/test_optional_staves.py`:

```python
@pytest.mark.parametrize("class_id", ["magic_user", "illusionist"])
def test_caster_staff_gated_by_real_data(data, class_id):
    cls = data.classes[class_id]
    # Staff is declared as optional, not a default weapon.
    assert "staff" in cls.optional_weapons_allowed
    assert "staff" not in (cls.weapons_allowed if cls.weapons_allowed != "all" else [])

    off = allowed_weapon_ids([cls], data)
    assert "dagger" in off
    assert "staff" not in off

    on = allowed_weapon_ids([cls], data, RuleSet(optional_staves=True))
    assert "staff" in on
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_optional_staves.py -k staff_gated_by_real_data -q`
Expected: FAIL — staff still lives in `weapons_allowed`, `optional_weapons_allowed` is empty.

- [ ] **Step 3: Edit `data/classes/magic_user.yaml`**

Replace the `weapons_allowed` block (lines ~9-11):

```yaml
weapons_allowed:
- dagger
- staff # TODO: confirm optional staff rule
```

with:

```yaml
weapons_allowed:
- dagger
optional_weapons_allowed:
- staff  # AOSE "Magic-Users and Staves" optional rule (RuleSet.optional_staves)
```

- [ ] **Step 4: Edit `data/classes/illusionist.yaml`**

Replace the `weapons_allowed` block (lines ~11-13):

```yaml
weapons_allowed:
- dagger
- staff # TODO: confirm optional staff rule
```

with:

```yaml
weapons_allowed:
- dagger
optional_weapons_allowed:
- staff  # AOSE "Illusionists and Staves" optional rule (RuleSet.optional_staves)
```

- [ ] **Step 5: Run the data-integration test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_optional_staves.py -q`
Expected: PASS (9 passed).

- [ ] **Step 6: Fix the now-stale wizard picker test**

The wizard proficiency picker does not yet thread the ruleset (that lands in Task 4), so with the rule off by default the staff no longer appears for a magic-user. Update `tests/test_weapon_proficiency.py::test_magic_user_picker_shows_one_slot_filtered`:

Replace:

```python
    assert "Dagger" in r.text
    assert "Staff" in r.text
    assert "Sword" not in r.text
```

with:

```python
    assert "Dagger" in r.text
    # Staff is combat-optional; not offered unless the optional_staves rule is on.
    assert "Staff" not in r.text
    assert "Sword" not in r.text
```

- [ ] **Step 7: Run the affected proficiency test file**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_proficiency.py -q`
Expected: PASS. (`test_post_wrong_count_rejected` still returns 400 — staff is now disallowed — and remains green.)

- [ ] **Step 8: Commit**

```bash
git add data/classes/magic_user.yaml data/classes/illusionist.yaml tests/test_optional_staves.py tests/test_weapon_proficiency.py
git commit -m "feat: gate magic-user/illusionist staff behind optional_staves rule"
```

---

## Task 4: Thread the ruleset into the call sites

**Files:**
- Modify: `aose/web/routes.py` (2 call sites)
- Modify: `aose/web/wizard.py` (4 call sites)
- Test: `tests/test_weapon_proficiency.py` (add rule-on coverage)

- [ ] **Step 1: Write the failing wizard rule-on test**

In `tests/test_weapon_proficiency.py`, update the `_start_magic_user` helper to optionally enable the rule. Replace the helper (lines ~189-199):

```python
def _start_magic_user(client, optional_staves=False):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 10, "INT": 15, "WIS": 11, "DEX": 13, "CON": 12, "CHA": 10}
    if optional_staves:
        draft.setdefault("ruleset", {})["optional_staves"] = True
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "magic_user"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    return draft_id
```

Then add two new tests after `test_magic_user_picker_shows_one_slot_filtered`:

```python
def test_magic_user_picker_shows_staff_when_rule_on(client):
    draft_id = _start_magic_user(client, optional_staves=True)
    r = client.get(f"/wizard/{draft_id}/class_setup")
    assert r.status_code == 200
    assert "Staff" in r.text


def test_magic_user_can_take_staff_proficiency_when_rule_on(client):
    draft_id = _start_magic_user(client, optional_staves=True)
    r = client.post(f"/wizard/{draft_id}/proficiencies", data={"weapon": ["staff"]})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["proficiencies"]["weapons"] == ["staff"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_proficiency.py -k "staff_when_rule_on or take_staff_proficiency" -q`
Expected: FAIL — the proficiency picker/post still ignore the ruleset, so staff is excluded even with the rule on (GET lacks "Staff"; POST returns 400).

- [ ] **Step 3: Thread ruleset in `aose/web/wizard.py`**

The module already has `_ruleset_of(draft)`. Update the four call sites:

In `_proficiency_context` (line ~1033):

```python
    allowed = allowed_weapon_ids(classes, data, _ruleset_of(draft))
```

In `post_proficiencies` (line ~1079):

```python
    allowed = allowed_weapon_ids(classes, data, _ruleset_of(draft))
```

In `_equipment_context` (line ~1367), inside the `inventory_view(...)` call:

```python
            allowed_weapons=allowed_weapon_ids(classes, game_data, _ruleset_of(draft)),
```

In `post_equipment_equip` (line ~1479), inside the `_equip(...)` call:

```python
            allowed_weapons=allowed_weapon_ids(classes, data, _ruleset_of(draft)),
```

- [ ] **Step 4: Thread ruleset in `aose/web/routes.py`**

Both sheet-side call sites have `spec` in scope (`spec.ruleset`).

In the character sheet view (line ~155), inside `shop_inventory_view(...)`:

```python
                allowed_weapons=allowed_weapon_ids(classes, game_data, spec.ruleset),
```

In `equipment_equip` (line ~414), inside `_equip(...)`:

```python
            allowed_weapons=allowed_weapon_ids(classes, data, spec.ruleset),
```

- [ ] **Step 5: Run the new + affected tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_proficiency.py -q`
Expected: PASS (rule-off tests unchanged; rule-on tests now green).

- [ ] **Step 6: Commit**

```bash
git add aose/web/wizard.py aose/web/routes.py tests/test_weapon_proficiency.py
git commit -m "feat: thread per-character ruleset into weapon-allowance call sites"
```

---

## Task 5: Register the rule on the settings/rules page

**Files:**
- Modify: `aose/web/settings_routes.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_settings.py` (it already has a `client` fixture):

```python
import re


def test_optional_staves_toggle_rendered(client):
    r = client.get("/settings")
    assert r.status_code == 200
    assert "Spellcasters and Staves" in r.text


def test_optional_staves_round_trips(client):
    # Post the settings form with the toggle on; reload and confirm it persisted.
    r = client.post("/settings", data={"optional_staves": "on"})
    assert r.status_code == 303
    r2 = client.get("/settings")
    # Precise: the optional_staves checkbox itself is rendered checked. (A bare
    # `"checked" in text` would be always-true since other rules default on.)
    assert re.search(
        r'name="optional_staves"[^>]*\bchecked\b', r2.text, re.DOTALL
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py -k optional_staves -q`
Expected: FAIL — the label "Spellcasters and Staves" is not rendered (rule not in `RULE_GROUPS`).

- [ ] **Step 3: Add the label**

In `aose/web/settings_routes.py`, add to `RULE_LABELS` (after `"strict_mode": "Strict Mode",`):

```python
    "optional_staves": "Spellcasters and Staves",
```

- [ ] **Step 4: Mark the rule implemented**

In `IMPLEMENTED_RULES`, add `"optional_staves",` (e.g. after `"strict_mode",`).

- [ ] **Step 5: Add to the Combat rule group**

In `RULE_GROUPS`, in the `("Combat", [ ... ])` tuple, add as a new entry:

```python
        ("optional_staves",
         "Magic-users and illusionists may wield a staff in combat."),
```

- [ ] **Step 6: Run the settings tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py -q`
Expected: PASS — including `test_no_pending_badges_when_all_rules_implemented` (the new rule is registered as implemented).

- [ ] **Step 7: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the known trailing `pytest-current` PermissionError on Windows).

- [ ] **Step 8: Commit**

```bash
git add aose/web/settings_routes.py tests/test_settings.py
git commit -m "feat: register optional_staves rule on the settings/rules page"
```

---

## Self-Review Notes

- **Spec coverage:** data model (Task 1), engine gating (Task 2), data edits (Task 3), 6-call-site wiring (Task 4), settings registration incl. no-pending guard (Task 5). All spec sections covered.
- **Out of scope (confirmed not implemented):** no cascading clear on toggle-off; magic staves/rods/wands untouched; descriptive `..._and_staves_optional_rule` class features left as-is.
- **Type consistency:** `allowed_weapon_ids(classes, data, ruleset=None)` signature is used identically in every threaded call site; `optional_weapons_allowed` / `optional_staves` names match across model, engine, data, and settings.
- **Affected existing tests handled inline:** `test_magic_user_picker_shows_one_slot_filtered` updated in Task 3; `test_post_wrong_count_rejected` stays green (staff now disallowed → still 400).
