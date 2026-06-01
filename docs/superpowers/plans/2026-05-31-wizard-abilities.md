# Wizard Overhaul — Slice 2: Abilities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lock ability generation to 3d6-in-order (removing the `ability_roll_method` rule, the 4d6 roller, arrange mode, the settings radio, and the reroll route) and add two non-blocking creation warnings (sub-par character, rock-bottom score) surfaced on the abilities page.

**Architecture:** A new pure helper `ability_warnings()` in `aose/engine/ability_mods.py` derives warnings from a score map; the wizard's `get_abilities` route passes them into the existing `wizard/abilities.html` partial. All alternate-roll-method plumbing is deleted across the model, dice engine, wizard routes, settings routes, template, seed data, and tests. Abilities are rolled once at draft creation and are immutable thereafter.

**Tech Stack:** Python 3, FastAPI, Pydantic v2, Jinja2, pytest. No JS framework. Windows / PowerShell.

**Spec:** `docs/superpowers/specs/2026-05-31-wizard-abilities-design.md`

**Conventions:**
- Run tests with: `.venv\Scripts\python.exe -m pytest tests/ -q`
- Run the app with: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
- The trailing `PermissionError` on `pytest-current` is a known Windows-tempdir quirk in pytest 9 — ignore it.
- `ABILITY_ORDER` (STR, INT, WIS, DEX, CON, CHA) in `aose/web/wizard.py` is correct and unchanged.

**Sequencing rationale (keep the suite green between commits):**
- **Task 1** adds the engine helper — fully independent.
- **Task 2** removes all *usage* of alternate methods (reroll route, arrange UI, 4d6 path) but leaves the `ability_roll_method` field on `RuleSet` with its default. The settings page still renders it; its tests still pass. Everything is green at the end of Task 2.
- **Task 3** removes the now-unused `RuleSet.ability_roll_method` field, the 4d6 dice roller, the settings choice-group, the seed-data key, and the remaining tests that referenced them.

**Note — files deliberately NOT touched:** `tests/test_equipment.py:183`, `tests/test_containers.py:597`, `tests/test_equip_attacks.py:383`, and `tests/test_magic_items.py:921` each pass `"ability_roll_method": "3d6_in_order"` as **POST form data** to `/rules`. `parse_ruleset_from_form` only reads fields it knows about, so a leftover form key is silently ignored — these do not error and need no edit.

---

## Task 1: `ability_warnings` engine helper

**Files:**
- Modify: `aose/engine/ability_mods.py`
- Test: `tests/test_ability_warnings.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_ability_warnings.py`:

```python
"""Tests for the pure creation-warning helper used by the abilities step."""
from aose.engine.ability_mods import ability_warnings


def test_all_scores_eight_or_lower_is_subpar():
    scores = {"STR": 8, "INT": 7, "WIS": 6, "DEX": 8, "CON": 5, "CHA": 4}
    result = ability_warnings(scores)
    assert result["subpar"] is True
    assert result["rock_bottom"] == []


def test_one_high_score_is_not_subpar():
    scores = {"STR": 8, "INT": 7, "WIS": 6, "DEX": 9, "CON": 5, "CHA": 4}
    result = ability_warnings(scores)
    assert result["subpar"] is False


def test_rock_bottom_lists_each_three():
    scores = {"STR": 3, "INT": 11, "WIS": 12, "DEX": 3, "CON": 14, "CHA": 10}
    result = ability_warnings(scores)
    assert result["rock_bottom"] == ["STR", "DEX"]


def test_normal_spread_has_no_warnings():
    scores = {"STR": 12, "INT": 11, "WIS": 9, "DEX": 13, "CON": 14, "CHA": 10}
    result = ability_warnings(scores)
    assert result["subpar"] is False
    assert result["rock_bottom"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ability_warnings.py -q`
Expected: FAIL with `ImportError: cannot import name 'ability_warnings'`

- [ ] **Step 3: Add the helper**

Append to `aose/engine/ability_mods.py` (after `prime_requisite_xp_multiplier`):

```python


def ability_warnings(abilities: dict[str, int]) -> dict:
    """Non-blocking creation warnings derived purely from ability scores.

    * ``subpar``      — True when *all six* scores are 8 or lower (the AOSE
                        "may start over" condition).
    * ``rock_bottom`` — the names of any abilities that rolled exactly 3.

    Both are advisory only; nothing here blocks character creation.
    """
    subpar = all(v <= 8 for v in abilities.values())
    rock_bottom = [name for name, v in abilities.items() if v == 3]
    return {"subpar": subpar, "rock_bottom": rock_bottom}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ability_warnings.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```powershell
git add aose/engine/ability_mods.py tests/test_ability_warnings.py
git commit -m @'
feat(abilities): add ability_warnings creation-warning helper

Pure helper deriving the sub-par flag (all six scores <= 8) and the
rock-bottom list (any ability == 3) from a score map. Used next by the
wizard abilities step.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

## Task 2: Lock the wizard to 3d6 — backend, template, CSS

This task removes every *use* of alternate roll methods while leaving the
`RuleSet.ability_roll_method` field in place (default `"3d6_in_order"`), so the
settings page and its tests stay green. The page becomes a static read-only
score table plus the name field, with the two warning banners.

**Files:**
- Modify: `aose/web/wizard.py`
- Modify: `aose/web/templates/wizard/abilities.html`
- Modify: `aose/web/static/sheet.css`
- Modify: `tests/test_wizard.py`
- Modify: `tests/test_wizard_back_nav.py`
- Modify: `tests/test_wizard_rules_step.py`
- Modify: `tests/test_choice_rules.py`
- Test: `tests/test_ability_warnings.py` (extend with page-render tests)

### Backend changes to `aose/web/wizard.py`

- [ ] **Step 1: Update imports**

Change the dice import (line ~21) from:

```python
from aose.engine.dice import roll_3d6_in_order, roll_4d6_drop_lowest_in_order, roll_hp
```

to:

```python
from aose.engine.dice import roll_3d6_in_order, roll_hp
```

Change the ability_mods import (line ~19) from:

```python
from aose.engine.ability_mods import ability_modifier
```

to:

```python
from aose.engine.ability_mods import ability_modifier, ability_warnings
```

- [ ] **Step 2: Replace `_roll_ability_values` + `_seed_draft_abilities`**

Delete the entire `_roll_ability_values` function (lines ~275-283) and replace
the `_seed_draft_abilities` function (lines ~286-294) so the two together become
just:

```python
def _seed_draft_abilities(draft: dict[str, Any]) -> None:
    """Roll 3d6 in order and store the six scores on the draft.

    Abilities are always 3d6 down the line — there are no alternate methods,
    and the roll is locked once the draft exists.
    """
    values = roll_3d6_in_order()
    draft["abilities"] = dict(zip([a.value for a in ABILITY_ORDER], values))
```

- [ ] **Step 3: Update `new_wizard`**

In `new_wizard` (lines ~297-309), simplify the seeding block. Replace:

```python
    draft: dict[str, Any] = {"ruleset": ruleset.model_dump()}
    _seed_draft_abilities(draft, ruleset)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/rules")
```

with:

```python
    draft: dict[str, Any] = {"ruleset": ruleset.model_dump()}
    _seed_draft_abilities(draft)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/rules")
```

Also delete the now-stale comment immediately above (the block beginning
`# Seed abilities up-front using the *default* method.` through
`# working unchanged.`) and replace it with:

```python
    # Abilities are rolled once here and locked. The rules step never changes
    # them — _apply_rule_changes only re-seeds if the draft somehow lacks them.
```

- [ ] **Step 4: Update `_apply_rule_changes` first branch**

In `_apply_rule_changes` (lines ~349-353), replace:

```python
    if (new_rs.ability_roll_method != old_rs.ability_roll_method
            or "abilities" not in draft):
        _seed_draft_abilities(draft, new_rs)
        _clear_after_abilities(draft)
        return
```

with:

```python
    if "abilities" not in draft:
        # Safety re-seed only — abilities are normally rolled at draft creation.
        _seed_draft_abilities(draft)
        _clear_after_abilities(draft)
        return
```

Also update the docstring bullet inside `_apply_rule_changes` — replace the line:

```python
    * ability_roll_method change OR abilities not yet rolled  → re-seed
      abilities + clear everything from race down.
```

with:

```python
    * abilities not yet rolled (safety) → re-seed abilities + clear from race down.
```

- [ ] **Step 5: Delete `_METHOD_LABELS`**

Delete the entire `_METHOD_LABELS` dict (lines ~384-388).

- [ ] **Step 6: Simplify `get_abilities`**

Replace the whole `get_abilities` function (lines ~391-409) with:

```python
@router.get("/{draft_id}/abilities", response_class=HTMLResponse)
async def get_abilities(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    ability_rows = [
        {
            "name": ab.value,
            "score": draft["abilities"][ab.value],
            "modifier": ability_modifier(draft["abilities"][ab.value]),
        }
        for ab in ABILITY_ORDER
    ]
    ctx = _base_context(request, draft_id, draft, "abilities")
    ctx["ability_rows"] = ability_rows
    ctx.update(ability_warnings(draft["abilities"]))  # subpar, rock_bottom
    return templates.TemplateResponse(request, "wizard.html", ctx)
```

- [ ] **Step 7: Delete the reroll route**

Delete the entire `post_reroll` route (lines ~412-421):

```python
@router.post("/{draft_id}/reroll")
async def post_reroll(request: Request, draft_id: str):
    ...
    return _redirect(f"/wizard/{draft_id}/abilities")
```

- [ ] **Step 8: Simplify `post_abilities`**

Replace the whole `post_abilities` function (lines ~424-460) with:

```python
@router.post("/{draft_id}/abilities")
async def post_abilities(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    form = await request.form()
    name = (form.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Name required")
    draft["name"] = name
    save_draft(draft_id, draft, _drafts_dir(request))
    # Route via _next_incomplete_step so race-as-class drafts skip /race.
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")
```

### Template + CSS

- [ ] **Step 9: Rewrite `wizard/abilities.html`**

Replace the entire contents of `aose/web/templates/wizard/abilities.html` with:

```html
<h2>Step 1: Abilities &amp; Name</h2>
<p class="muted">Rolled 3d6 in order — these scores are fixed for this character.</p>

{% if subpar %}
<p class="creation-warning">
    <strong>Sub-par character:</strong> all six scores are 8 or lower. The rules
    let you start over — use <em>Cancel</em> to abandon this character and begin a
    new one if you'd like a fresh set of rolls. You may also proceed as-is.
</p>
{% endif %}
{% if rock_bottom %}
<p class="creation-note">
    {% for name in rock_bottom %}{{ name }} is 3 — extremely low.{% if not loop.last %} {% endif %}{% endfor %}
</p>
{% endif %}

<form method="post" action="/wizard/{{ draft_id }}/abilities" class="step-form">
    <table class="abilities-roll">
        <thead><tr><th>Ability</th><th>Score</th><th>Mod</th></tr></thead>
        <tbody>
        {% for ab in ability_rows %}
            <tr>
                <td>{{ ab.name }}</td>
                <td class="num">{{ ab.score }}</td>
                <td class="num">{{ "%+d"|format(ab.modifier) }}</td>
            </tr>
        {% endfor %}
        </tbody>
    </table>

    <label class="field">
        <span>Character Name</span>
        <input type="text" name="name" required value="{{ draft.name or '' }}" autofocus>
    </label>

    <button type="submit" class="primary">Next: Choose Race &rarr;</button>
</form>
```

- [ ] **Step 10: Add warning-banner CSS**

Append to `aose/web/static/sheet.css` (after the `.rule-active` block, ~line 562):

```css

.creation-warning {
    background: #f4e4e0;
    border: 1px solid #a04040;
    padding: 8px 12px;
    margin: 12px 0;
    font-size: 13px;
    color: #5a1a1a;
    max-width: 500px;
}

.creation-note {
    color: #a04040;
    font-size: 13px;
    margin: 8px 0;
}
```

### Test updates (remove dead behavior, add new coverage)

- [ ] **Step 11: Fix `tests/test_wizard.py`**

In `test_abilities_page_renders` (lines ~44-49), replace:

```python
def test_abilities_page_renders(client):
    draft_id = _start_draft(client)
    r = client.get(f"/wizard/{draft_id}/abilities")
    assert r.status_code == 200
    assert "Abilities" in r.text
    assert "Re-roll" in r.text
```

with:

```python
def test_abilities_page_renders(client):
    draft_id = _start_draft(client)
    r = client.get(f"/wizard/{draft_id}/abilities")
    assert r.status_code == 200
    assert "Abilities" in r.text
    # Reroll affordance is gone — abilities are locked at draft creation.
    assert "Re-roll" not in r.text
```

Delete `test_reroll_changes_abilities` entirely (lines ~52-61).

- [ ] **Step 12: Fix `tests/test_wizard_back_nav.py`**

Delete `test_reroll_clears_race_and_below` entirely (lines ~192-212, the
function and its docstring).

- [ ] **Step 13: Fix `tests/test_wizard_rules_step.py`**

In `_rules_form` (lines ~58-66), remove the `ability_roll_method` entry so the
defaults dict becomes:

```python
    data = {
        "encumbrance": "basic",
        "creation_method": "advanced",
    }
```

In `test_get_rules_renders_choice_radios` (lines ~107-113), remove the two
`ability_roll_method` assertions so it reads:

```python
def test_get_rules_renders_choice_radios(client):
    draft_id = _start(client)
    r = client.get(f"/wizard/{draft_id}/rules")
    assert 'name="encumbrance"' in r.text
    assert 'value="detailed"' in r.text
```

Delete `test_changing_ability_method_rerolls_and_clears` entirely (lines
~145-166) and the section comment above it (`# ── Cascading clears:
ability_roll_method change ──`).

Delete `test_arrange_mode_via_rules_step_seeds_pool` entirely (lines ~169-175).

- [ ] **Step 14: Fix `tests/test_choice_rules.py`**

Delete the whole "Ability roll method" section — every test from
`test_new_wizard_uses_3d6_in_order_by_default` through
`test_non_arrange_post_abilities_works_without_score_fields` (lines ~81-196),
including the `# === Ability roll method ===` banner comment.

Add this replacement immediately after the Encumbrance section (so the file
still has a minimal abilities sanity check):

```python
# ════════════════════════════════════════════════════════════════════════════
# Abilities are always 3d6 in order (no method choice)
# ════════════════════════════════════════════════════════════════════════════

def test_new_wizard_rolls_3d6_in_order(tmp_path):
    client = _make_client(tmp_path, RuleSet())
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    assert set(draft["abilities"]) == {"STR", "INT", "WIS", "DEX", "CON", "CHA"}
    for v in draft["abilities"].values():
        assert 3 <= v <= 18
    # No arrange pool is ever seeded.
    assert "abilities_pool" not in draft


def test_abilities_form_only_needs_name(tmp_path):
    client = _make_client(tmp_path, RuleSet())
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    r = client.post(f"/wizard/{draft_id}/abilities", data={"name": "Whatever"})
    assert r.status_code == 303
```

Then update the final settings test `test_choice_group_pending_badge_hidden_when_implemented`
(lines ~203-209) — its premise (an "Ability Score Method" group exists) is going
away in Task 3, so rewrite it now to assert the *encumbrance* group instead:

```python
def test_choice_group_pending_badge_hidden_when_implemented(tmp_path):
    client = _make_client(tmp_path, RuleSet())
    r = client.get("/settings")
    # The Encumbrance group is implemented — no "pending" badge near its legend.
    idx = r.text.index('Encumbrance')
    snippet = r.text[idx:idx + 400]
    assert ">pending<" not in snippet
```

- [ ] **Step 15: Add page-render warning tests**

Append to `tests/test_ability_warnings.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from aose.characters import load_draft, save_draft, save_settings
from aose.models import RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def _make_client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True)
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, RuleSet())
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._drafts_dir = drafts_dir
    return client


def _new_draft_with_abilities(client, abilities):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = abilities
    save_draft(draft_id, draft, client._drafts_dir)
    return draft_id


def test_abilities_page_shows_subpar_banner(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft_with_abilities(
        client, {"STR": 8, "INT": 7, "WIS": 6, "DEX": 8, "CON": 5, "CHA": 4})
    r = client.get(f"/wizard/{draft_id}/abilities")
    assert "Sub-par character" in r.text


def test_abilities_page_hides_subpar_banner_for_normal_spread(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft_with_abilities(
        client, {"STR": 12, "INT": 11, "WIS": 9, "DEX": 13, "CON": 14, "CHA": 10})
    r = client.get(f"/wizard/{draft_id}/abilities")
    assert "Sub-par character" not in r.text


def test_abilities_page_shows_rock_bottom_note(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft_with_abilities(
        client, {"STR": 3, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10})
    r = client.get(f"/wizard/{draft_id}/abilities")
    assert "STR is 3 — extremely low." in r.text


def test_reroll_route_is_gone(tmp_path):
    client = _make_client(tmp_path)
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    r = client.post(f"/wizard/{draft_id}/reroll")
    assert r.status_code in (404, 405)
```

- [ ] **Step 16: Run the full suite to verify green**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (no failures; the `ability_roll_method` field still exists on
`RuleSet`, so the settings tests untouched in this task still pass). Ignore the
trailing `pytest-current` PermissionError.

- [ ] **Step 17: Commit**

```powershell
git add aose/web/wizard.py aose/web/templates/wizard/abilities.html aose/web/static/sheet.css tests/test_wizard.py tests/test_wizard_back_nav.py tests/test_wizard_rules_step.py tests/test_choice_rules.py tests/test_ability_warnings.py
git commit -m @'
feat(abilities): lock wizard to 3d6 in order + creation warnings

Remove the reroll route, arrange-mode UI/validation, 4d6 path, and method
labels from the wizard. The abilities page is now a static score table plus
the name field, with non-blocking sub-par and rock-bottom warning banners.
Drop the dead behavior tests; add warning-render + reroll-gone tests.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

## Task 3: Remove the `ability_roll_method` field & 4d6 roller

With all usage gone, delete the field from `RuleSet`, the settings choice-group,
the 4d6 dice roller, the seed-data key, and the remaining tests that referenced
them.

**Files:**
- Modify: `aose/models/ruleset.py`
- Modify: `aose/web/settings_routes.py`
- Modify: `aose/engine/dice.py`
- Modify: `examples/thorin.json`
- Modify: `tests/test_models.py`
- Modify: `tests/test_settings.py`
- Modify: `tests/test_dice.py`

- [ ] **Step 1: Update `tests/test_models.py` (test-first for the model change)**

In `test_default_ruleset` (lines ~7-13), delete the line:

```python
    assert rs.ability_roll_method == "3d6_in_order"
```

In `test_ruleset_has_no_removed_flags` (lines ~16-21), add `"ability_roll_method"`
to the `dead` tuple so it reads:

```python
def test_ruleset_has_no_removed_flags():
    """max_hp_at_l1, the two split demihuman flags, and ability_roll_method are
    gone; extra='forbid' means passing them raises rather than silently
    accepting."""
    for dead in ("max_hp_at_l1", "demihuman_level_limits",
                 "demihuman_class_restrictions", "ability_roll_method"):
        with pytest.raises(ValidationError):
            RuleSet(**{dead: True})  # type: ignore[arg-type]
```

- [ ] **Step 2: Run those tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models.py -q`
Expected: FAIL — `test_ruleset_has_no_removed_flags` fails because
`RuleSet(ability_roll_method=True)` is still accepted (field still exists).

- [ ] **Step 3: Remove the field from `RuleSet`**

In `aose/models/ruleset.py`, delete the `AbilityRollMethod` type alias (line ~6):

```python
AbilityRollMethod = Literal["3d6_in_order", "3d6_arrange", "4d6_drop_lowest"]
```

and delete the field (line ~23):

```python
    ability_roll_method: AbilityRollMethod = "3d6_in_order"
```

The file's remaining `EncumbranceMode` alias and `encumbrance` field stay. After
the edit the top of the file reads:

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict


EncumbranceMode = Literal["none", "basic", "detailed"]
```

- [ ] **Step 4: Run model tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models.py -q`
Expected: PASS

- [ ] **Step 5: Remove the settings choice-group**

In `aose/web/settings_routes.py`:

Change `IMPLEMENTED_CHOICE_GROUPS` (line ~43) from:

```python
IMPLEMENTED_CHOICE_GROUPS = {"ability_roll_method", "encumbrance"}
```

to:

```python
IMPLEMENTED_CHOICE_GROUPS = {"encumbrance"}
```

Remove the `ability_roll_method` tuple from `CHOICE_GROUPS` (lines ~88-92) so the
list contains only the `encumbrance` group:

```python
CHOICE_GROUPS = [
    ("encumbrance", "Encumbrance", [
        ("none", "None — ignore encumbrance entirely"),
        ("basic", "Basic — track only armour and significant loads"),
        ("detailed", "Detailed — track item-by-item weight in coins"),
    ]),
]
```

(`parse_ruleset_from_form` derives choice fields from `CHOICE_GROUPS`, so it needs
no separate edit.)

- [ ] **Step 6: Update `tests/test_settings.py`**

In `test_post_settings_persists_to_disk` (lines ~114-129), remove the
`ability_roll_method` form key and its assertion. The body becomes:

```python
def test_post_settings_persists_to_disk(client):
    r = client.post("/settings", data={
        "ascending_ac": "on",
        "reroll_1s_2s_hp_l1": "on",
        "encumbrance": "detailed",
    })
    assert r.status_code == 303
    assert r.headers["location"] == "/settings?saved=1"

    rs = load_settings(client._settings_path)
    assert rs.ascending_ac is True
    assert rs.reroll_1s_2s_hp_l1 is True
    assert rs.encumbrance == "detailed"
    assert rs.weapon_proficiency is False
```

Rewrite `test_post_settings_ignores_invalid_radio_choice` (lines ~139-144) to use
the surviving `encumbrance` choice group:

```python
def test_post_settings_ignores_invalid_radio_choice(client):
    r = client.post("/settings", data={"encumbrance": "made_up_mode"})
    assert r.status_code == 303
    rs = load_settings(client._settings_path)
    # Falls back to the default since the choice was invalid.
    assert rs.encumbrance == "basic"
```

- [ ] **Step 7: Remove the 4d6 roller from `dice.py`**

In `aose/engine/dice.py`, delete the entire `roll_4d6_drop_lowest_in_order`
function (lines ~25-34). `roll_3d6_in_order` and `roll_hp` remain.

- [ ] **Step 8: Update `tests/test_dice.py`**

Change the import (lines ~5-10) to drop `roll_4d6_drop_lowest_in_order`:

```python
from aose.engine.dice import (
    roll,
    roll_3d6_in_order,
    roll_hp,
)
```

Delete the three 4d6 tests at the bottom (lines ~84-105):
`test_4d6_drop_lowest_returns_six_values_in_3_to_18`,
`test_4d6_drop_lowest_deterministic_with_seed`, and
`test_4d6_drop_lowest_shifted_higher_than_3d6_on_average` (including the
`# ── 4d6-drop-lowest in order ──` banner comment).

- [ ] **Step 9: Remove the key from `examples/thorin.json`**

In `examples/thorin.json`, delete the `ability_roll_method` line inside
`ruleset` (line ~34). Because `RuleSet` uses `extra="forbid"`, leaving it would
make the example fail to load. The `ruleset` block becomes:

```json
  "ruleset": {
    "ascending_ac": false,
    "secondary_skills": false,
    "weapon_proficiency": false,
    "multiclassing": false,
    "reroll_1s_2s_hp_l1": false,
    "separate_race_class": true,
    "variable_weapon_damage": false,
    "encumbrance": "basic"
  }
```

- [ ] **Step 10: Run the full suite to verify green**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (no failures). Ignore the trailing `pytest-current`
PermissionError.

- [ ] **Step 11: Commit**

```powershell
git add aose/models/ruleset.py aose/web/settings_routes.py aose/engine/dice.py examples/thorin.json tests/test_models.py tests/test_settings.py tests/test_dice.py
git commit -m @'
refactor(rules): drop ability_roll_method field and 4d6 roller

Remove the now-unused ability_roll_method RuleSet field + type alias, the
settings Ability Score Method choice group, the roll_4d6_drop_lowest_in_order
dice helper, and the example seed key. Abilities are always 3d6 in order.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task / Step |
|---|---|
| Remove `ability_roll_method` field + `AbilityRollMethod` alias | Task 3, Steps 3 |
| Remove `roll_4d6_drop_lowest_in_order` | Task 3, Step 7 |
| `_seed_draft_abilities` → roll 3d6, store, drop pool | Task 2, Step 2 |
| `new_wizard` still seeds once at creation | Task 2, Step 3 |
| `_apply_rule_changes` first branch → `if "abilities" not in draft` | Task 2, Step 4 |
| `get_abilities` drops arrange/pool/method_label, adds warnings | Task 2, Steps 6 |
| `post_abilities` only reads/stores name | Task 2, Step 8 |
| Remove `post_reroll` route | Task 2, Step 7 |
| Remove `ability_roll_method` from `CHOICE_GROUPS` + `IMPLEMENTED_CHOICE_GROUPS` | Task 3, Step 5 |
| `abilities.html`: static table, name, Next, warnings; title "Abilities & Name" | Task 2, Step 9 |
| Remove `_METHOD_LABELS` | Task 2, Step 5 |
| Engine helper `ability_warnings` (subpar all ≤8; rock_bottom == 3) | Task 1 |
| Warnings computed on render, not persisted | Task 2, Step 6 (`ctx.update`, no `save_draft`) |
| Sub-par banner + rock-bottom note, neither blocks Next | Task 2, Step 9 |
| Remove 4d6 test in `test_dice.py` | Task 3, Step 8 |
| Remove `ability_roll_method` cases in `test_choice_rules.py` + `test_settings.py` | Task 2 Step 14 / Task 3 Step 6 |
| Remove arrange assertions in `test_wizard.py` / rules-step | Task 2, Steps 11, 13 |
| Remove reroll-route test in `test_wizard.py` / `test_wizard_back_nav.py` | Task 2, Steps 11, 12 |
| Remove field from `test_models.py` + `examples/thorin.json` | Task 3, Steps 1, 9 |
| Add `ability_warnings` unit tests | Task 1, Step 1 |
| Add abilities-page banner/note render tests | Task 2, Step 15 |
| Add reroll route 404/405 test | Task 2, Step 15 |
| Settings/rules pages render with no ability-method group / arrange UI | Task 2 Step 14 (choice-rules) + Task 3 Step 5 |

All spec requirements map to a task. Out-of-scope items (name move → Slice 6;
review aggregation → Slice 8) are correctly not implemented here; the
`ability_warnings` helper is the reusable hook Slice 8 will consume.

**Type consistency:** `_seed_draft_abilities(draft)` is one-arg everywhere
(definition Task 2 Step 2; calls in `new_wizard` Step 3 and `_apply_rule_changes`
Step 4). `ability_warnings(abilities) -> {"subpar", "rock_bottom"}` matches its
consumers in `get_abilities` (`ctx.update(...)`) and the template (`subpar`,
`rock_bottom`). Banner strings in the template ("Sub-par character", "STR is 3 —
extremely low.") match the page-render test assertions in Task 2 Step 15.

**Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to" placeholders;
every code step shows complete content.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-31-wizard-abilities.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
