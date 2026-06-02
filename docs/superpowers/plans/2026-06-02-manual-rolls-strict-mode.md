# Manual Rolls + Strict Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ability-score and starting-gold rolls deliberate player button presses (like HP), add a default-on `strict_mode` rule that locks rolls (off = free re-rolls), let a hopeless ability set re-roll under Strict Mode, and show both Blessed HP sets with the higher bolded.

**Architecture:** A new `RuleSet.strict_mode` flag gates the one-roll lock across abilities/HP/gold. Abilities and gold stop being auto-rolled at draft creation / page load and gain dedicated POST roll routes mirroring the existing `/hp/roll`. Blessed HP keeps both rolled sets on the draft (display-only, never persisted) so the template can bold the winner. All logic lives in the existing `aose/web/wizard.py`, `aose/engine/dice.py`, `aose/web/settings_routes.py`, `aose/models/ruleset.py`, and the wizard Jinja templates.

**Tech Stack:** Python 3, FastAPI, Jinja2, Pydantic v2, pytest. Run the app with `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`; run tests with `.venv\Scripts\python.exe -m pytest tests/ -q`.

**Spec:** `docs/superpowers/specs/2026-06-02-manual-rolls-strict-mode-design.md`

---

## Key design decisions (read before starting)

- **No `rules_done` flag.** The only change `_next_incomplete_step` needs is its
  first line: a draft with no abilities resolves to `"abilities"` (was
  `"rules"`). `/wizard/new` still redirects to `/rules`, and posting `/rules`
  redirects forward to `/abilities` via `_next_incomplete_step`. This keeps the
  existing `test_gate_redirects_to_first_incomplete_step` (expects `/abilities`)
  green.
- **Hopeless = `subpar OR rock_bottom`.** `ability_warnings(...)` already returns
  both (`subpar` = all six ≤ 8; `rock_bottom` = list of abilities equal to 3).
  Under Strict Mode the abilities Roll button stays active when either is truthy.
- **`strict_mode` default `True` + checkbox semantics.** `parse_ruleset_from_form`
  derives bools as `field in form`. The template renders the checkbox `checked`
  when `ruleset['strict_mode']` is true, so an unchecked submit → `False`
  (correct). Test form helpers (`_rules_form`) must include `strict_mode` so they
  keep matching the default; this is done in Task 1.
- **Blessed sets are draft-only.** `draft["hp_blessed_sets"]` is display state;
  `CharacterSpec` has no such field, so it never reaches a saved character.

---

## Task 1: Add the `strict_mode` rule and keep the suite green

**Files:**
- Modify: `aose/models/ruleset.py:9-24`
- Modify: `aose/web/settings_routes.py:17-83` (`RULE_LABELS`, `IMPLEMENTED_RULES`, `RULE_GROUPS`)
- Modify: `tests/test_wizard_class_setup.py:60` (`_rules_form` base dict)
- Modify: `tests/test_wizard_rules_step.py:55` (`_TRUE_DEFAULTS`)
- Test: `tests/test_strict_mode.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_strict_mode.py`:

```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters.drafts import load_draft, save_draft
from aose.models import RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture
def client(tmp_path):
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=tmp_path / "characters",
        drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir,
    )
    c = TestClient(app, follow_redirects=False)
    c._drafts = tmp_path / "drafts"
    return c


def test_strict_mode_defaults_on():
    assert RuleSet().strict_mode is True


def test_strict_mode_no_pending_badge(client):
    r = client.get("/settings")
    assert r.status_code == 200
    assert 'name="strict_mode"' in r.text
    # The strict_mode row must not carry a pending badge.
    idx = r.text.index('name="strict_mode"')
    snippet = r.text[idx:idx + 400]
    assert "pending" not in snippet
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_strict_mode.py -q`
Expected: FAIL — `RuleSet` has no `strict_mode`; settings page has no `name="strict_mode"`.

- [ ] **Step 3: Add the model field**

In `aose/models/ruleset.py`, add to `RuleSet` (after `human_racial_abilities`):

```python
    human_racial_abilities: bool = False
    strict_mode: bool = True
```

- [ ] **Step 4: Wire the settings metadata**

In `aose/web/settings_routes.py`:

Add to `RULE_LABELS`:

```python
    "human_racial_abilities": "Human Racial Abilities",
    "strict_mode": "Strict Mode",
```

Add to `IMPLEMENTED_RULES`:

```python
    "human_racial_abilities",
    "strict_mode",
```

Add a row to the existing `"Character Options"` group in `RULE_GROUPS` (after the `secondary_skills` entry):

```python
        ("strict_mode",
         "Ability scores, hit points, and starting gold are locked after a "
         "single roll (a hopeless ability set may always be re-rolled). Turn "
         "off to allow free re-rolls."),
```

- [ ] **Step 5: Keep existing form helpers matching the new default**

In `tests/test_wizard_class_setup.py`, change the `_rules_form` base dict
(line ~60) to include `strict_mode`:

```python
    data = {"encumbrance": "basic", "creation_method": "advanced",
            "strict_mode": "on"}
```

In `tests/test_wizard_rules_step.py`, change `_TRUE_DEFAULTS` (line ~55):

```python
_TRUE_DEFAULTS = ("strict_mode",)
```

- [ ] **Step 6: Run the new test + the two touched test files**

Run: `.venv\Scripts\python.exe -m pytest tests/test_strict_mode.py tests/test_wizard_class_setup.py tests/test_wizard_rules_step.py tests/test_settings.py -q`
Expected: PASS (the pending-badge guard `test_no_pending_badges_when_all_rules_implemented` still green because `strict_mode` is in `IMPLEMENTED_RULES`).

- [ ] **Step 7: Commit**

```bash
git add aose/models/ruleset.py aose/web/settings_routes.py tests/test_strict_mode.py tests/test_wizard_class_setup.py tests/test_wizard_rules_step.py
git commit -m "feat(rules): add default-on strict_mode rule"
```

---

## Task 2: Blessed HP — engine helper that returns both sets

**Files:**
- Modify: `aose/engine/dice.py:25-50`
- Test: `tests/test_dice.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dice.py`:

```python
def test_roll_blessed_hp_sets_returns_two_complete_sets():
    import random
    from aose.engine.dice import roll_blessed_hp_sets
    probe = random.Random(7)
    a = [probe.randint(1, 8), probe.randint(1, 4)]
    b = [probe.randint(1, 8), probe.randint(1, 4)]
    set_a, set_b = roll_blessed_hp_sets(["1d8", "1d4"], min_die=1,
                                        rng=random.Random(7))
    assert set_a == a
    assert set_b == b


def test_roll_blessed_hp_sets_respects_min_die():
    import random
    from aose.engine.dice import roll_blessed_hp_sets
    set_a, set_b = roll_blessed_hp_sets(["1d8", "1d4"], min_die=3,
                                        rng=random.Random(123))
    assert all(v >= 3 for v in set_a + set_b)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_dice.py -k blessed_hp_sets -q`
Expected: FAIL — `roll_blessed_hp_sets` not defined.

- [ ] **Step 3: Implement the helper and refactor the blessed branch**

In `aose/engine/dice.py`, add `roll_blessed_hp_sets` and have
`roll_first_level_hp` delegate to it (the RNG draw order is unchanged — set A
then set B — so existing `roll_first_level_hp` blessed tests stay valid):

```python
def roll_blessed_hp_sets(
    hit_dice: list[str],
    *,
    min_die: int = 1,
    rng: Optional[random.Random] = None,
) -> tuple[list[int], list[int]]:
    """Roll two complete first-level HP sets (one die per class each) for the
    Human Blessed ability. Returns ``(set_a, set_b)`` in draw order; the caller
    decides which to keep (larger sum, ties keep ``set_a``)."""
    r = rng or random.Random()
    set_a = [roll_hp(hd, r, min_die=min_die) for hd in hit_dice]
    set_b = [roll_hp(hd, r, min_die=min_die) for hd in hit_dice]
    return set_a, set_b
```

Then replace the blessed branch of `roll_first_level_hp` (the lines that build
`set_a`/`set_b` inline) with:

```python
    if not blessed:
        return one_set()
    set_a, set_b = roll_blessed_hp_sets(hit_dice, min_die=min_die, rng=r)
    return set_a if sum(set_a) >= sum(set_b) else set_b
```

(Keep the `one_set()` inner function for the non-blessed path.)

- [ ] **Step 4: Run the dice tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_dice.py tests/test_wizard_class_setup.py -k "hp or blessed or dice" -q`
Expected: PASS (including the existing `test_blessed_*` in `test_wizard_class_setup.py`).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/dice.py tests/test_dice.py
git commit -m "feat(dice): roll_blessed_hp_sets returns both blessed sets"
```

---

## Task 3: Abilities — manual roll backend

**Files:**
- Modify: `aose/web/wizard.py` — `new_wizard` (308-317), `_next_incomplete_step` (220-242), `_apply_rule_changes` (356-360), `get_abilities` (399-413), `post_abilities` (416-424), and a new `post_abilities_roll` route.
- Test: `tests/test_strict_mode.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_strict_mode.py`:

```python
def _new(client):
    r = client.get("/wizard/new")
    return r.headers["location"].split("/")[2]


def _force(client, draft_id, abilities):
    d = load_draft(draft_id, client._drafts)
    d["abilities"] = abilities
    save_draft(draft_id, d, client._drafts)


def test_new_does_not_pre_roll_abilities(client):
    draft_id = _new(client)
    d = load_draft(draft_id, client._drafts)
    assert "abilities" not in d


def test_abilities_roll_route_sets_six_scores(client):
    draft_id = _new(client)
    r = client.post(f"/wizard/{draft_id}/abilities/roll")
    assert r.status_code == 303
    d = load_draft(draft_id, client._drafts)
    assert set(d["abilities"]) == {"STR", "INT", "WIS", "DEX", "CON", "CHA"}


def test_strict_locks_abilities_after_roll(client):
    draft_id = _new(client)
    # Non-hopeless scores so the lock applies.
    _force(client, draft_id, {"STR": 13, "INT": 12, "WIS": 11,
                              "DEX": 10, "CON": 14, "CHA": 9})
    r = client.post(f"/wizard/{draft_id}/abilities/roll")
    assert r.status_code == 400


def test_hopeless_reroll_allowed_in_strict(client):
    draft_id = _new(client)
    # rock_bottom: a single 3 must re-enable the roll even under Strict Mode.
    _force(client, draft_id, {"STR": 3, "INT": 12, "WIS": 11,
                              "DEX": 10, "CON": 14, "CHA": 9})
    r = client.post(f"/wizard/{draft_id}/abilities/roll")
    assert r.status_code == 303


def test_subpar_reroll_allowed_in_strict(client):
    draft_id = _new(client)
    _force(client, draft_id, {"STR": 8, "INT": 8, "WIS": 8,
                              "DEX": 8, "CON": 8, "CHA": 8})
    r = client.post(f"/wizard/{draft_id}/abilities/roll")
    assert r.status_code == 303


def test_non_strict_allows_ability_reroll(client):
    draft_id = _new(client)
    client.post(f"/wizard/{draft_id}/rules",
                data={"encumbrance": "basic", "creation_method": "advanced"})
    _force(client, draft_id, {"STR": 13, "INT": 12, "WIS": 11,
                              "DEX": 10, "CON": 14, "CHA": 9})
    r = client.post(f"/wizard/{draft_id}/abilities/roll")
    assert r.status_code == 303  # strict off (checkbox absent) -> free reroll


def test_ability_reroll_clears_downstream_and_confirmation(client):
    draft_id = _new(client)
    client.post(f"/wizard/{draft_id}/rules",
                data={"encumbrance": "basic", "creation_method": "advanced"})
    _force(client, draft_id, {"STR": 13, "INT": 12, "WIS": 11,
                              "DEX": 10, "CON": 14, "CHA": 9})
    client.post(f"/wizard/{draft_id}/abilities", data={})  # confirm
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/abilities/roll")       # reroll
    d = load_draft(draft_id, client._drafts)
    assert "race_id" not in d
    assert not d.get("abilities_confirmed")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_strict_mode.py -q`
Expected: FAIL — abilities still seeded at `/new`; no `/abilities/roll` route.

- [ ] **Step 3: Stop auto-seeding at draft creation**

In `aose/web/wizard.py` `new_wizard` (308-317), remove the
`_seed_draft_abilities(draft)` call so the body reads:

```python
@router.get("/new")
async def new_wizard(request: Request):
    draft_id = new_draft_id()
    ruleset = load_settings(request.app.state.settings_path)
    # Abilities are rolled by the player on the abilities step, not here.
    draft: dict[str, Any] = {"ruleset": ruleset.model_dump()}
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/rules")
```

- [ ] **Step 4: Route abilities-missing drafts to the abilities step**

In `_next_incomplete_step` (220-242), replace the first two checks:

```python
    if "abilities" not in draft:
        return "rules"
    if not draft.get("abilities_confirmed"):
        return "abilities"
```

with:

```python
    if "abilities" not in draft or not draft.get("abilities_confirmed"):
        return "abilities"
```

- [ ] **Step 5: Simplify the rule-change safety block**

In `_apply_rule_changes` (356-360), replace the re-seed block:

```python
    if "abilities" not in draft:
        # Safety re-seed only — abilities are normally rolled at draft creation.
        _seed_draft_abilities(draft)
        _clear_after_abilities(draft)
        return
```

with a plain early return (nothing downstream exists yet):

```python
    if "abilities" not in draft:
        return
```

- [ ] **Step 6: Add the roll route and a Continue guard; update `get_abilities`**

Add this route (place it just above `get_abilities`):

```python
@router.post("/{draft_id}/abilities/roll")
async def post_abilities_roll(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    if "abilities" in draft:
        warn = ability_warnings(draft["abilities"])
        hopeless = warn["subpar"] or bool(warn["rock_bottom"])
        if _ruleset_of(draft).strict_mode and not hopeless:
            raise HTTPException(400, "Ability scores are already rolled and locked.")
    _clear_after_abilities(draft)          # back-nav reroll: drop stale downstream
    draft.pop("abilities_confirmed", None)
    _seed_draft_abilities(draft)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/abilities")
```

Replace `get_abilities` (399-413) with a version that handles the not-yet-rolled
state and computes `can_reroll`:

```python
@router.get("/{draft_id}/abilities", response_class=HTMLResponse)
async def get_abilities(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    ctx = _base_context(request, draft_id, draft, "abilities")
    rolled = "abilities" in draft
    ctx["abilities_rolled"] = rolled
    if rolled:
        ctx["ability_rows"] = [
            {
                "name": ab.value,
                "score": draft["abilities"][ab.value],
                "modifier": ability_modifier(draft["abilities"][ab.value]),
            }
            for ab in ABILITY_ORDER
        ]
        warn = ability_warnings(draft["abilities"])
        ctx.update(warn)  # subpar, rock_bottom
        hopeless = warn["subpar"] or bool(warn["rock_bottom"])
        ctx["can_reroll"] = (not _ruleset_of(draft).strict_mode) or hopeless
    return templates.TemplateResponse(request, "wizard.html", ctx)
```

Update `post_abilities` (416-424) to guard against confirming an unrolled draft:

```python
@router.post("/{draft_id}/abilities")
async def post_abilities(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    if "abilities" not in draft:
        return _redirect(f"/wizard/{draft_id}/abilities")
    draft["abilities_confirmed"] = True
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")
```

- [ ] **Step 7: Run the abilities backend tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_strict_mode.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add aose/web/wizard.py tests/test_strict_mode.py
git commit -m "feat(wizard): player-rolled abilities with strict lock + hopeless reroll"
```

---

## Task 4: Abilities — template + fix the two stale wizard tests

**Files:**
- Modify: `aose/web/templates/wizard/abilities.html`
- Modify: `tests/test_wizard.py:37-51` (`test_new_creates_draft_with_abilities`, `test_abilities_page_renders`)

- [ ] **Step 1: Write the failing test**

Replace `test_new_creates_draft_with_abilities` and `test_abilities_page_renders`
in `tests/test_wizard.py` with:

```python
def test_new_does_not_pre_roll_abilities(client, tmp_path):
    draft_id = _start_draft(client)
    draft = load_draft(draft_id, tmp_path / "drafts")
    assert "abilities" not in draft


def test_abilities_page_shows_roll_button_before_rolling(client):
    draft_id = _start_draft(client)
    r = client.get(f"/wizard/{draft_id}/abilities")
    assert r.status_code == 200
    assert "Abilities" in r.text
    assert f'/wizard/{draft_id}/abilities/roll' in r.text


def test_abilities_page_shows_scores_after_rolling(client):
    draft_id = _start_draft(client)
    client.post(f"/wizard/{draft_id}/abilities/roll")
    r = client.get(f"/wizard/{draft_id}/abilities")
    assert "Continue" in r.text
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard.py -k abilities -q`
Expected: FAIL — page renders the old always-on score table, not the roll button.

- [ ] **Step 3: Rewrite the template**

Replace the entire contents of `aose/web/templates/wizard/abilities.html` with:

```html
<h2>Step 1: Abilities</h2>

{% if not abilities_rolled %}
<p class="muted">Roll <strong>3d6 in order</strong> for your six ability scores.
   Once rolled they're fixed for this character.</p>
<form method="post" action="/wizard/{{ draft_id }}/abilities/roll" class="inline-form">
    <button type="submit" class="primary">Roll 3d6</button>
</form>
{% else %}
<p class="muted">Rolled 3d6 in order.</p>

{% if subpar %}
<p class="creation-warning">
    <strong>Sub-par character:</strong> all six scores are 8 or lower. The rules
    let you start over &mdash; use <em>Roll again</em> below for a fresh set, or
    proceed as-is.
</p>
{% endif %}
{% if rock_bottom %}
<p class="creation-note">
    {% for name in rock_bottom %}{{ name }} is 3 &mdash; extremely low.{% if not loop.last %} {% endif %}{% endfor %}
    You may use <em>Roll again</em> for a fresh set.
</p>
{% endif %}

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

{% if can_reroll %}
<form method="post" action="/wizard/{{ draft_id }}/abilities/roll" class="inline-form">
    <button type="submit">Roll again</button>
</form>
{% endif %}

<form method="post" action="/wizard/{{ draft_id }}/abilities" class="step-form">
    <button type="submit" class="primary">Continue &rarr;</button>
</form>
{% endif %}
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard.py -k abilities -q`
Expected: PASS.

- [ ] **Step 5: Run the full wizard test file for regressions**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard.py -q`
Expected: All pass except possibly `test_full_wizard_flow_creates_character`
(its equipment/gold step is fixed in Task 5). If it fails only at the
equipment GET/POST, that's expected — note it and continue.

- [ ] **Step 6: Commit**

```bash
git add aose/web/templates/wizard/abilities.html tests/test_wizard.py
git commit -m "feat(wizard): abilities page roll/reroll UI"
```

---

## Task 5: Gold — manual roll backend, template, and test fixes

**Files:**
- Modify: `aose/web/wizard.py` — `get_equipment` (1223-1239) + new `post_equipment_roll_gold` route.
- Modify: `aose/web/templates/wizard/equipment.html`
- Modify: `tests/test_equipment.py` — `_walk_to_equipment` helper (177-198) + `test_equipment_get_seeds_starting_gold`, `test_reroll_gold_route_removed` (208-224)
- Modify: `tests/test_wizard.py:102-106` (gold step of the full-flow test)
- Test: `tests/test_strict_mode.py`

- [ ] **Step 1: Write the failing tests**

First update the existing `_walk_to_equipment` helper (177-198) so its `/rules`
POST keeps Strict Mode on (the current form uses stale field names that would
drop `strict_mode` → False). Add `"strict_mode": "on"` to its rules form dict:

```python
    client.post(f"/wizard/{draft_id}/rules", data={
        "ability_roll_method": "3d6_in_order", "encumbrance": "basic",
        "separate_race_class": "on",
        "demihuman_level_limits": "on",
        "demihuman_class_restrictions": "on",
        "strict_mode": "on",
    })
```

Then replace `test_equipment_get_seeds_starting_gold` and
`test_reroll_gold_route_removed` (208-224) with:

```python
def test_equipment_get_does_not_auto_roll_gold(client):
    draft_id = _walk_to_equipment(client)
    r = client.get(f"/wizard/{draft_id}/equipment")
    assert r.status_code == 200
    draft = load_draft(draft_id, client._drafts_dir)
    assert "gold" not in draft
    assert f"/wizard/{draft_id}/equipment/roll-gold" in r.text


def test_roll_gold_route_sets_and_locks_gold_in_strict(client):
    draft_id = _walk_to_equipment(client)
    r = client.post(f"/wizard/{draft_id}/equipment/roll-gold")
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert 30 <= draft["gold"] <= 180 and draft["gold"] % 10 == 0
    assert draft["gold_locked"] is True
    # Strict default: a second roll is rejected.
    r2 = client.post(f"/wizard/{draft_id}/equipment/roll-gold")
    assert r2.status_code == 400
```

Append a non-strict reroll test to `tests/test_strict_mode.py` (it has its own
end-to-end helper need; drive the draft minimally):

```python
def _drive_to_equipment(client, draft_id, strict=True):
    form = {"encumbrance": "basic", "creation_method": "advanced"}
    if strict:
        form["strict_mode"] = "on"
    client.post(f"/wizard/{draft_id}/rules", data=form)
    _force(client, draft_id, {"STR": 13, "INT": 12, "WIS": 11,
                              "DEX": 13, "CON": 13, "CHA": 12})
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/identity",
                data={"name": "G", "alignment": "law"})


def test_non_strict_gold_reroll_until_purchase(client):
    draft_id = _new(client)
    _drive_to_equipment(client, draft_id, strict=False)
    client.post(f"/wizard/{draft_id}/equipment/roll-gold")
    d = load_draft(draft_id, client._drafts)
    assert d["gold_locked"] is False
    # Non-strict: re-roll allowed while unlocked.
    r = client.post(f"/wizard/{draft_id}/equipment/roll-gold")
    assert r.status_code == 303
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equipment.py -k gold tests/test_strict_mode.py -k gold -q`
Expected: FAIL — GET still auto-rolls; no `/equipment/roll-gold` route.

- [ ] **Step 3: Remove auto-roll, add the roll-gold route**

In `aose/web/wizard.py` `get_equipment` (1223-1239), delete the auto-roll block:

```python
    # First visit: roll starting gold once and lock it immediately.
    if "gold" not in draft:
        draft["gold"] = roll_starting_gold()
        draft.setdefault("inventory", [])
        draft["gold_locked"] = True
        save_draft(draft_id, draft, _drafts_dir(request))
```

so the handler becomes:

```python
@router.get("/{draft_id}/equipment", response_class=HTMLResponse)
async def get_equipment(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "equipment", draft_id)
    if redirect:
        return redirect
    ctx = _base_context(request, draft_id, draft, "equipment")
    ctx.update(_equipment_context(draft, request.app.state.game_data))
    ctx["gold_rolled"] = "gold" in draft
    ctx["target_url_prefix"] = f"/wizard/{draft_id}/equipment"
    return templates.TemplateResponse(request, "wizard.html", ctx)
```

Add the new route just after `get_equipment`:

```python
@router.post("/{draft_id}/equipment/roll-gold")
async def post_equipment_roll_gold(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    if draft.get("gold_locked"):
        raise HTTPException(400, "Starting gold is already rolled and locked.")
    draft["gold"] = roll_starting_gold()
    draft.setdefault("inventory", [])
    # Strict locks immediately; otherwise the first purchase locks it (buy route).
    draft["gold_locked"] = _ruleset_of(draft).strict_mode
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")
```

- [ ] **Step 4: Rewrite the equipment template**

Replace the contents of `aose/web/templates/wizard/equipment.html` with:

```html
<h2>Equipment</h2>

{% if not gold_rolled %}
<p class="muted">Roll your starting gold (<strong>3d6 &times; 10 gp</strong>),
   then buy what you need from the shop.</p>
<form method="post" action="/wizard/{{ draft_id }}/equipment/roll-gold" class="inline-form">
    <button type="submit" class="primary">Roll starting gold</button>
</form>
{% else %}
<p class="muted">
    {% if gold_locked %}Your starting gold is fixed.{% else %}Your starting gold
    can still be re-rolled until you buy something.{% endif %}
    Buy what you need from the shop below.
</p>
{% if not gold_locked %}
<form method="post" action="/wizard/{{ draft_id }}/equipment/roll-gold" class="inline-form">
    <button type="submit">Re-roll gold</button>
</form>
{% endif %}

{% include "_equipment_ui.html" %}

<form method="post" action="/wizard/{{ draft_id }}/equipment" class="step-form">
    <button type="submit" class="primary">Next: Review &rarr;</button>
</form>
{% endif %}
```

- [ ] **Step 5: Fix the full-flow wizard test gold step**

In `tests/test_wizard.py` `test_full_wizard_flow_creates_character`, replace the
gold/equipment lines (102-106):

```python
    # Visit equipment to roll starting gold, then continue to review.
    client.get(f"/wizard/{draft_id}/equipment")  # seeds gold on first GET
    r = client.post(f"/wizard/{draft_id}/equipment")
```

with:

```python
    # Roll starting gold (now a deliberate button press), then continue.
    r = client.post(f"/wizard/{draft_id}/equipment/roll-gold")
    assert r.status_code == 303
    r = client.post(f"/wizard/{draft_id}/equipment")
```

- [ ] **Step 6: Run the touched tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equipment.py tests/test_strict_mode.py tests/test_wizard.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add aose/web/wizard.py aose/web/templates/wizard/equipment.html tests/test_equipment.py tests/test_strict_mode.py tests/test_wizard.py
git commit -m "feat(wizard): player-rolled starting gold with strict lock"
```

---

## Task 6: HP — strict reroll, store both Blessed sets, bold the higher

**Files:**
- Modify: `aose/web/wizard.py` — imports (27), `post_hp_roll` (1072-1097), `_hp_context` (1003-1041).
- Modify: `aose/web/templates/wizard/class_setup.html:1-45` (HP section)
- Modify: `tests/test_wizard_class_setup.py` — `test_blessed_human_hp_uses_two_sets` (268-284)
- Test: `tests/test_strict_mode.py`, `tests/test_wizard_class_setup.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_strict_mode.py`:

```python
def test_non_strict_allows_hp_reroll(client):
    draft_id = _new(client)
    _drive_to_equipment(client, draft_id, strict=False)
    # _drive_to_equipment already rolled HP once; a second roll must be allowed.
    r = client.post(f"/wizard/{draft_id}/hp/roll")
    assert r.status_code == 303
```

Add a `_hp_context` blessed test to `tests/test_wizard_class_setup.py`:

```python
def test_hp_context_exposes_both_blessed_sets(tmp_path):
    from aose.web.wizard import _hp_context
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id, race="human", flag=True)
    client.post(f"/wizard/{draft_id}/hp/roll")
    draft = load_draft(draft_id, client._drafts_dir)
    assert "hp_blessed_sets" in draft
    ctx = _hp_context(draft, GameData.load(DATA_DIR))
    sets = ctx["blessed_sets"]
    assert len(sets) == 2
    # Exactly one set is flagged higher, and it has the >= total.
    higher = [s for s in sets if s["higher"]]
    assert len(higher) == 1
    assert higher[0]["total"] == max(s["total"] for s in sets)
```

Rewrite `test_blessed_human_hp_uses_two_sets` (268-284) to spy on the new
function the route calls for the blessed path:

```python
def test_blessed_human_hp_uses_two_sets(tmp_path, monkeypatch):
    import aose.web.wizard as wiz
    captured = {}
    real = wiz.roll_blessed_hp_sets

    def spy(hit_dice, *, min_die, rng=None):
        captured["called"] = True
        return real(hit_dice, min_die=min_die, rng=rng)

    monkeypatch.setattr(wiz, "roll_blessed_hp_sets", spy)
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id, race="human", flag=True)
    client.post(f"/wizard/{draft_id}/hp/roll")
    assert captured.get("called") is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_strict_mode.py -k hp tests/test_wizard_class_setup.py -k "blessed_sets or uses_two_sets" -q`
Expected: FAIL — `roll_blessed_hp_sets` not imported in wizard; `_hp_context` has
no `blessed_sets`; HP still locks under strict-off.

- [ ] **Step 3: Import the helper**

In `aose/web/wizard.py` line 27, extend the dice import:

```python
from aose.engine.dice import (
    roll_3d6_in_order,
    roll_blessed_hp_sets,
    roll_first_level_hp,
    roll_hp,
)
```

- [ ] **Step 4: Rewrite `post_hp_roll`**

Replace `post_hp_roll` (1072-1097) with a version that honours Strict Mode and
stores both Blessed sets:

```python
@router.post("/{draft_id}/hp/roll")
async def post_hp_roll(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    ruleset = _ruleset_of(draft)
    if _has_hp(draft) and ruleset.strict_mode:
        # Locked after one roll under Strict Mode (like abilities and gold).
        raise HTTPException(400, "Hit points are already rolled and locked.")
    data = request.app.state.game_data
    ids = _class_ids(draft)
    classes = [data.classes[cid] for cid in ids]
    hit_dice = [c.hit_die for c in classes]

    blessed = (draft.get("race_id") == "human" and ruleset.human_racial_abilities)
    min_die = 3 if ruleset.reroll_1s_2s_hp_l1 else 1

    if blessed:
        set_a, set_b = roll_blessed_hp_sets(hit_dice, min_die=min_die)
        rolls = set_a if sum(set_a) >= sum(set_b) else set_b
        draft["hp_blessed_sets"] = [set_a, set_b]
    else:
        rolls = roll_first_level_hp(hit_dice, blessed=False, min_die=min_die)
        draft.pop("hp_blessed_sets", None)

    if len(ids) == 1:
        draft["hp_roll"] = rolls[0]
        draft.pop("hp_rolls", None)
    else:
        draft["hp_rolls"] = rolls
        draft.pop("hp_roll", None)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/class_setup")
```

- [ ] **Step 5: Extend `_hp_context`**

In `_hp_context` (1003-1041), before the `return`, build the blessed-set view
and the reroll flag, then add them to the returned dict:

```python
    blessed_sets = None
    raw_sets = draft.get("hp_blessed_sets")
    if raw_sets and len(raw_sets) == 2:
        totals = [sum(s) for s in raw_sets]
        higher_idx = 0 if totals[0] >= totals[1] else 1
        blessed_sets = [
            {"rolls": s, "total": t, "higher": (i == higher_idx)}
            for i, (s, t) in enumerate(zip(raw_sets, totals))
        ]
```

Add these two keys to the dict that `_hp_context` returns:

```python
        "hp_done": (total is not None),
        "blessed_sets": blessed_sets,
        "can_reroll_hp": not ruleset.strict_mode,
    }
```

- [ ] **Step 6: Update the Class Setup HP template**

In `aose/web/templates/wizard/class_setup.html`, inside the Hit Points
`<section>`: after the existing `{% if rolls %}…{% endif %}` HP display block
(ends ~line 36) and before the `{% if not hp_done %}` roll form, insert the
both-sets display:

```html
    {% if blessed_sets %}
    <div class="blessed-sets">
        <p class="muted small">Blessed &mdash; rolled twice, keeping the better:</p>
        {% for s in blessed_sets %}
        <div class="stat-row">
            <span>Set {{ loop.index }} ({{ s.rolls|join(', ') }}){% if s.higher %} &mdash; kept{% endif %}</span>
            <span class="stat-big">{% if s.higher %}<strong>{{ s.total }}</strong>{% else %}{{ s.total }}{% endif %}</span>
        </div>
        {% endfor %}
    </div>
    {% endif %}
```

Then replace the roll/locked block (`{% if not hp_done %}…{% else %}…{% endif %}`,
lines ~38-44) with a three-way branch:

```html
    {% if not hp_done %}
    <form method="post" action="/wizard/{{ draft_id }}/hp/roll" class="inline-form">
        <button type="submit">Roll HP</button>
    </form>
    {% elif can_reroll_hp %}
    <form method="post" action="/wizard/{{ draft_id }}/hp/roll" class="inline-form">
        <button type="submit">Re-roll HP</button>
    </form>
    {% else %}
    <p class="muted small">Hit points are locked. To re-roll, cancel and start over.</p>
    {% endif %}
```

- [ ] **Step 7: Run the touched tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_strict_mode.py tests/test_wizard_class_setup.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add aose/web/wizard.py aose/web/templates/wizard/class_setup.html tests/test_strict_mode.py tests/test_wizard_class_setup.py
git commit -m "feat(wizard): strict-aware HP reroll and dual blessed-set display"
```

---

## Task 7: Full-suite verification and stragglers

**Files:**
- Possibly modify: any remaining test that assumed auto-rolled abilities/gold.

- [ ] **Step 1: Run the entire suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: All pass. (Ignore the trailing `PermissionError` on `pytest-current` —
known Windows tempdir quirk per CLAUDE.md.)

- [ ] **Step 2: Triage any failures**

For each failure, the cause is almost certainly one of:
  - A test drove a fresh draft through the wizard relying on abilities being
    auto-rolled at `/new` — fix by injecting abilities via `save_draft` (the
    `_set_abilities`/`_force` pattern) or `POST /abilities/roll` before
    `POST /abilities`.
  - A test relied on gold auto-rolling on the equipment GET — fix by
    `POST /wizard/{id}/equipment/roll-gold` first.
  - A test POSTed `/rules` with a form lacking `strict_mode` and then asserted a
    roll lock — add `strict_mode="on"` to that form.
Apply the minimal fix and re-run.

- [ ] **Step 3: Manual smoke test (optional but recommended)**

Run the app: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
Walk: New Character → Rules (leave Strict Mode on) → Abilities shows only a Roll
button → roll → Continue → … → Class Setup rolls HP once (locked) → Equipment
shows a Roll-gold button → roll → shop appears. Then repeat with Strict Mode off
and confirm Roll-again / Re-roll HP / Re-roll gold buttons appear. With Human
Racial Abilities on (Advanced + lift restrictions), confirm both HP sets show
and the higher total is bold.

- [ ] **Step 4: Update CLAUDE.md "Current state" note**

Add a short bullet under the current-state section of `CLAUDE.md` describing the
manual rolls + `strict_mode` rule and the draft-only `hp_blessed_sets`. Keep it
to a few lines, matching the existing style.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "test+docs: finalize manual rolls + strict mode"
```

---

## Self-Review notes

- **Spec coverage:** strict_mode rule (Task 1), Blessed both-sets engine (Task 2)
  + storage/display (Task 6), manual abilities w/ hopeless reroll (Tasks 3-4),
  manual gold (Task 5), HP strict reroll (Task 6), draft-only blessed sets
  (Task 6 — `hp_blessed_sets` never on `CharacterSpec`). All spec sections map
  to a task.
- **Hopeless condition** is `subpar or bool(rock_bottom)` consistently in the
  roll route (Task 3 Step 6) and `get_abilities` (Task 3 Step 6).
- **Function names** consistent: `roll_blessed_hp_sets` (defined Task 2, imported
  + called Task 6), `post_abilities_roll`, `post_equipment_roll_gold`.
- **Checkbox default:** `strict_mode` rendered `checked` via the shared
  `_ruleset_fields.html` loop (no template edit needed); test form helpers
  updated in Task 1 to keep parity.
