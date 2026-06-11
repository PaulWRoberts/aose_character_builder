# Interactive Wizard Rolls & Class-Setup Consolidation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make rolled features and the secondary skill require a deliberate Roll press (even in Strict Mode), collapse Class Setup into a single save-and-advance, and cap selection inputs client-side.

**Architecture:** Wizard is FastAPI + Jinja2 over a JSON *draft* dict. Each roll already has its own POST route (`/abilities/roll`, `/hp/roll`, `/equipment/roll-gold`) that mutates the draft and redirects back to the step. We add the same shape for features (`/feature-choices/roll`, per-table) and the secondary skill (`/identity/skill-roll`). The Class Setup "Next" button (`POST /{id}/hp`) becomes a consolidated advance handler that, gated by hidden `section` markers in the form, validates and saves proficiencies/spells/feature-overrides before advancing — leaving the standalone `/proficiencies`, `/spells`, `/feature-choices` routes intact for backward compatibility.

**Tech Stack:** Python 3, FastAPI, Pydantic v2, Jinja2, vanilla JS, pytest + `fastapi.testclient`.

**Run tests:** `.venv\Scripts\python.exe -m pytest tests/ -q` (the trailing `pytest-current` PermissionError on Windows is a known pytest-9 quirk — ignore it). Run a single file with e.g. `.venv\Scripts\python.exe -m pytest tests/test_wizard_feature_choices.py -q`.

---

## Background facts the engineer needs

- **Draft storage** lives in `aose/web/wizard.py`. Helpers: `_load(request, draft_id)`, `save_draft(draft_id, draft, _drafts_dir(request))`, `_ruleset_of(draft)`, `_class_ids(draft)`, `_active_choice_groups(draft, data)`.
- **Feature choices** are CC3 roll tables. Engine: `aose/engine/feature_choices.py` — `roll_choice(group)` returns `group.pick` distinct option ids; `validate_choice(group, chosen)` raises `ChoiceError`. Every group in `data/` currently has `roll_dice` set (mutations, draconic bloodline, fiendish gifts/appearance) — there are no pure-pick groups.
- **Secondary skill** engine: `aose/engine/secondary_skills.py` — `roll(entries)` returns `list[str]` (one trade, or two for the roll-twice outcome); `selectable_names(entries)` lists hand-pickable trades.
- **Completion gating:** `_class_setup_complete(draft)` and `_identity_complete(draft)` drive `_next_incomplete_step`, which both `_gate` (forward bounce) and the step POST handlers use. The Class Setup template disables "Next" via a `ready` context flag.
- **Draft → spec:** `_draft_to_spec` reads `draft["spellbooks"]`, `draft.get("proficiencies")`, `draft.get("feature_choices")`, `draft.get("secondary_skill")`. None of those shapes change. `feature_choices_done` and `spells_done` are *gate flags only*, never read by `_draft_to_spec`.
- **Templates:** `aose/web/templates/wizard/class_setup.html` and `.../identity.html`.

---

## Task 1: Feature choices — roll-first, per-table

**Files:**
- Modify: `aose/web/wizard.py` (`_feature_choices_context`, `_class_setup_complete`, `get_class_setup`, `post_feature_choices`, `_clear_after_*`; add `_feature_choices_complete`, `post_feature_choice_roll`)
- Modify: `aose/web/templates/wizard/class_setup.html` (Features section + Next gating)
- Test: `tests/test_wizard_feature_choices.py` (rewrite)

- [ ] **Step 1: Rewrite the test file to the roll-first contract**

Replace the entire contents of `tests/test_wizard_feature_choices.py` with:

```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_draft, save_draft
from aose.models import RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def _client(tmp_path):
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=tmp_path / "characters",
        drafts_dir=tmp_path / "drafts",
        examples_dir=tmp_path / "examples",
        settings_path=tmp_path / "settings.json",
        seed_from_examples=False,
    )
    return TestClient(app, follow_redirects=False), tmp_path / "drafts"


def _seed_mutoid_draft(drafts_dir, strict=True):
    """A race-as-class Mutoid draft at class_setup, HP already rolled."""
    draft = {
        "ruleset": RuleSet(separate_race_class=False, weapon_proficiency=False,
                           strict_mode=strict, secondary_skills=False).model_dump(),
        "abilities": {"STR": 10, "INT": 10, "WIS": 10, "DEX": 12, "CON": 10, "CHA": 10},
        "abilities_confirmed": True,
        "race_id": "mutoid",
        "class_id": "mutoid",
        "ability_adjustments": {},
        "hp_roll": 4,
    }
    save_draft("d1", draft, drafts_dir)
    return "d1"


def test_strict_does_not_autoroll(tmp_path):
    client, drafts_dir = _client(tmp_path)
    draft_id = _seed_mutoid_draft(drafts_dir, strict=True)
    r = client.get(f"/wizard/{draft_id}/class_setup")
    assert r.status_code == 200
    draft = load_draft(draft_id, drafts_dir)
    assert "feature_choices" not in draft or "mutations" not in draft.get("feature_choices", {})
    # The page offers a Roll button for the table.
    assert "feature-choices/roll" in r.text


def test_roll_route_populates_group(tmp_path):
    client, drafts_dir = _client(tmp_path)
    draft_id = _seed_mutoid_draft(drafts_dir, strict=True)
    r = client.post(f"/wizard/{draft_id}/feature-choices/roll",
                    data={"group_id": "mutations"})
    assert r.status_code in (200, 303)
    draft = load_draft(draft_id, drafts_dir)
    assert len(draft["feature_choices"]["mutations"]) == 2
    assert len(set(draft["feature_choices"]["mutations"])) == 2


def test_strict_locks_after_roll(tmp_path):
    client, drafts_dir = _client(tmp_path)
    draft_id = _seed_mutoid_draft(drafts_dir, strict=True)
    client.post(f"/wizard/{draft_id}/feature-choices/roll", data={"group_id": "mutations"})
    first = load_draft(draft_id, drafts_dir)["feature_choices"]["mutations"]
    # Re-roll refused in strict mode.
    r = client.post(f"/wizard/{draft_id}/feature-choices/roll", data={"group_id": "mutations"})
    assert r.status_code == 400
    assert load_draft(draft_id, drafts_dir)["feature_choices"]["mutations"] == first


def test_non_strict_reroll_allowed(tmp_path):
    client, drafts_dir = _client(tmp_path)
    draft_id = _seed_mutoid_draft(drafts_dir, strict=False)
    client.post(f"/wizard/{draft_id}/feature-choices/roll", data={"group_id": "mutations"})
    before = load_draft(draft_id, drafts_dir)["feature_choices"]["mutations"]
    for _ in range(20):
        client.post(f"/wizard/{draft_id}/feature-choices/roll", data={"group_id": "mutations"})
        after = load_draft(draft_id, drafts_dir)["feature_choices"]["mutations"]
        if after != before:
            return
    pytest.fail("Re-roll never changed the mutation set after 20 tries")


def test_non_strict_manual_override_persists(tmp_path):
    client, drafts_dir = _client(tmp_path)
    draft_id = _seed_mutoid_draft(drafts_dir, strict=False)
    client.post(f"/wizard/{draft_id}/feature-choices/roll", data={"group_id": "mutations"})
    r = client.post(f"/wizard/{draft_id}/feature-choices",
                    data={"choice_mutations": ["scales", "clawed_hand"]})
    assert r.status_code in (200, 303)
    draft = load_draft(draft_id, drafts_dir)
    assert set(draft["feature_choices"]["mutations"]) == {"scales", "clawed_hand"}


def test_roll_route_rejects_unknown_group(tmp_path):
    client, drafts_dir = _client(tmp_path)
    draft_id = _seed_mutoid_draft(drafts_dir, strict=True)
    r = client.post(f"/wizard/{draft_id}/feature-choices/roll", data={"group_id": "bogus"})
    assert r.status_code == 400


def test_strict_manual_save_still_rejected(tmp_path):
    client, drafts_dir = _client(tmp_path)
    draft_id = _seed_mutoid_draft(drafts_dir, strict=True)
    r = client.post(f"/wizard/{draft_id}/feature-choices",
                    data={"choice_mutations": ["scales", "clawed_hand"]})
    assert r.status_code == 400
```

- [ ] **Step 2: Run the test file to watch it fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_feature_choices.py -q`
Expected: failures — `test_strict_does_not_autoroll` fails (auto-roll still happens / no Roll button), `test_roll_route_*` fail with 404/405 (route missing).

- [ ] **Step 3: Add the completion helper and roll route in `wizard.py`**

Add `_feature_choices_complete` directly after `_active_choice_groups` (currently ends ~line 1152):

```python
def _feature_choices_complete(draft: dict[str, Any], data) -> bool:
    """Every active feature-choice group has a rolled (or overridden) entry."""
    groups = _active_choice_groups(draft, data)
    chosen = draft.get("feature_choices", {})
    return all(g.id in chosen for g in groups)
```

Add the per-table roll route immediately after `post_feature_choices` (currently ends ~line 1291):

```python
@router.post("/{draft_id}/feature-choices/roll")
async def post_feature_choice_roll(request: Request, draft_id: str):
    """Roll a single feature-choice table. First roll allowed in every mode;
    Strict Mode refuses a re-roll once the group is set (mirrors HP/gold)."""
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    form = await request.form()
    group_id = form.get("group_id")
    groups = {g.id: g for g in _active_choice_groups(draft, data)}
    if group_id not in groups:
        raise HTTPException(400, f"Unknown feature group '{group_id}'")
    chosen = dict(draft.get("feature_choices", {}))
    if _ruleset_of(draft).strict_mode and group_id in chosen:
        raise HTTPException(400, "Feature is already rolled and locked (Strict Mode).")
    chosen[group_id] = roll_choice(groups[group_id])
    draft["feature_choices"] = chosen
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/class_setup")
```

- [ ] **Step 4: Remove the Strict auto-roll and retire `feature_choices_done`**

In `_feature_choices_context` (currently ~lines 1155-1188) delete the Strict auto-roll block so the function only *reads* state:

```python
def _feature_choices_context(draft: dict[str, Any], data) -> dict:
    """Render rows for the Features section. Rolling is an explicit player
    action (see post_feature_choice_roll); nothing is auto-rolled here."""
    groups = _active_choice_groups(draft, data)
    rs = _ruleset_of(draft)
    chosen_map = dict(draft.get("feature_choices", {}))

    rows = []
    for g in groups:
        chosen = set(chosen_map.get(g.id, []))
        rows.append({
            "id": g.id, "name": g.name, "text": g.text, "pick": g.pick,
            "cosmetic": g.cosmetic, "roll_dice": g.roll_dice,
            "rolled": g.id in chosen_map,
            "options": [
                {"id": o.id, "name": o.name, "text": o.text,
                 "selected": o.id in chosen}
                for o in g.options
            ],
        })
    return {
        "feature_groups": rows,
        "feature_choices_locked": rs.strict_mode,
        "has_feature_choices": bool(groups),
    }
```

In `_class_setup_complete` (currently ~line 235) replace the feature line:

```python
    if draft.get("_has_feature_choices") and not _feature_choices_complete(draft, data):
        return False
```

…but `_class_setup_complete` has no `data` parameter today. Change its signature to `_class_setup_complete(draft, data)` and update **both** call sites: `_next_incomplete_step` (pass `request.app.state.game_data` — see Step 6) and `get_class_setup` (`ctx["ready"]` line ~1384).

In `post_feature_choices` (currently ~lines 1272-1291) make the manual save **merge** and drop the done flag:

```python
@router.post("/{draft_id}/feature-choices")
async def post_feature_choices(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    if _ruleset_of(draft).strict_mode:
        raise HTTPException(400, "Feature choices are locked in Strict Mode.")
    form = await request.form()
    _apply_feature_overrides(draft, form, data)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/class_setup")
```

Add the merge helper just above `post_feature_choices`:

```python
def _apply_feature_overrides(draft: dict[str, Any], form, data) -> None:
    """Validate & merge submitted feature picks (non-strict manual override).
    Only groups present in the form are touched; others keep their rolled value."""
    groups = {g.id: g for g in _active_choice_groups(draft, data)}
    chosen_map = dict(draft.get("feature_choices", {}))
    for gid, g in groups.items():
        field = form.getlist(f"choice_{gid}")
        if not field:
            continue  # group not on this submission — leave as-is
        picked = list(dict.fromkeys(field))
        try:
            validate_choice(g, picked)
        except ChoiceError as e:
            raise HTTPException(400, str(e))
        chosen_map[gid] = picked
    draft["feature_choices"] = chosen_map
```

Remove `"feature_choices_done"` from the three `_clear_after_*` helpers (lines ~202, ~210, ~219 — keep `"feature_choices"` and `"_has_feature_choices"`). In `get_class_setup`, delete the now-dead block that saved the draft after a Strict auto-roll (currently ~lines 1380-1383: the `ctx["features_done"]` line and the `if choice_ctx["has_feature_choices"] and _ruleset_of(draft).strict_mode: save_draft(...)` block).

- [ ] **Step 5: Update the Features section + Next gating in `class_setup.html`**

Replace the entire `{# ── Feature Choices (CC3) ── #}` section (currently lines 189-245) with:

```html
{# ── Feature Choices (CC3) ──────────────────────────────────────────────── #}
{% if has_feature_choices %}
<section class="class-setup-section">
    <h3>Features</h3>
    {% for g in feature_groups %}
    <div class="feature-group" data-required="{{ g.pick }}">
        <h4>{{ g.name }}{% if g.cosmetic %} <span class="muted small">(cosmetic)</span>{% endif %}</h4>
        {% if g.text %}<p class="muted small">{{ g.text }}</p>{% endif %}

        {% if not g.rolled %}
        <p class="muted small">Roll <strong>{{ g.pick }}</strong> on the {{ g.roll_dice }} table.</p>
        <form method="post" action="/wizard/{{ draft_id }}/feature-choices/roll" class="inline-form">
            <input type="hidden" name="group_id" value="{{ g.id }}">
            <button type="submit">Roll {{ g.roll_dice or "" }}</button>
        </form>
        {% elif feature_choices_locked %}
        <ul>
            {% for o in g.options if o.selected %}
            <li><strong>{{ o.name }}</strong>{% if o.text %} — <span class="muted small">{{ o.text }}</span>{% endif %}</li>
            {% endfor %}
        </ul>
        {% else %}
        {# Non-strict: rolled, with re-roll + manual override. Checkboxes live in the
           consolidated Next form below; the re-roll button is its own little form. #}
        <div class="card-grid" data-required="{{ g.pick }}">
            {% for o in g.options %}
            <label class="card {% if o.selected %}selected{% endif %}">
                <input type="checkbox" form="class-setup-form" name="choice_{{ g.id }}"
                       value="{{ o.id }}" class="choice-checkbox"
                       {% if o.selected %}checked{% endif %}>
                <div class="card-name">{{ o.name }}</div>
                {% if o.text %}<div class="card-detail small">{{ o.text }}</div>{% endif %}
            </label>
            {% endfor %}
        </div>
        <form method="post" action="/wizard/{{ draft_id }}/feature-choices/roll" class="inline-form">
            <input type="hidden" name="group_id" value="{{ g.id }}">
            <button type="submit">Re-roll {{ g.roll_dice or "" }}</button>
        </form>
        {% endif %}
    </div>
    {% endfor %}
    <script>
        (function () {
            document.querySelectorAll('.feature-group .card-grid[data-required]').forEach(function (grid) {
                const required = parseInt(grid.dataset.required, 10);
                const boxes = Array.from(grid.querySelectorAll('.choice-checkbox'));
                function update() {
                    const checked = boxes.filter(b => b.checked).length;
                    boxes.forEach(function (b) {
                        b.disabled = !b.checked && checked >= required;
                        b.closest('.card').classList.toggle('selected', b.checked);
                    });
                    if (window.csValidate) { window.csValidate(); }
                }
                boxes.forEach(b => b.addEventListener('change', update));
                update();
            });
        })();
    </script>
</section>
{% endif %}
```

> The override checkboxes use `form="class-setup-form"` so they submit with the consolidated Next form (Task 3 gives that form its `id`). Until Task 3 lands the form id, these checkboxes simply have no owning form — harmless for Task 1's tests, which post `/feature-choices` directly.

- [ ] **Step 6: Fix the `_class_setup_complete` call sites**

`_next_incomplete_step` (line ~264) calls `_class_setup_complete(draft)`. It has no `data` in scope. Thread `data` through: change `_next_incomplete_step(draft)` to `_next_incomplete_step(draft, data)` and pass `request.app.state.game_data` at every call site. There are several (`_base_context`, `_gate`, `_strict_back_gate`, and the step POST handlers). Search: `grep -n "_next_incomplete_step(" aose/web/wizard.py` and update each — the `request` (hence `data`) is in scope at all of them. In `_base_context`, `_gate`, `_strict_back_gate`, add a `data` parameter and pass it down from their callers (all of which are route handlers holding `request`).

> This is mechanical but touches ~12 call sites. Do it in one pass, then run the full suite.

- [ ] **Step 7: Run the feature tests, then the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_feature_choices.py -q`
Expected: PASS.

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the `pytest-current` PermissionError). If `test_wizard_class_setup` or `test_strict_mode` assert the old auto-roll, fix those assertions to the roll-first contract (search for `feature_choices_done` and Strict auto-roll expectations).

- [ ] **Step 8: Commit**

```bash
git add aose/web/wizard.py aose/web/templates/wizard/class_setup.html tests/test_wizard_feature_choices.py
git commit -m "feat(wizard): roll-first per-table feature choices

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Secondary skill — roll-first

**Files:**
- Modify: `aose/web/wizard.py` (`get_identity`, `post_identity`; rename `post_identity_skill_reroll` → `post_identity_skill_roll`)
- Modify: `aose/web/templates/wizard/identity.html`
- Test: `tests/test_wizard_identity.py`, `tests/test_secondary_skills.py`

- [ ] **Step 1: Update the identity tests to roll-first**

In `tests/test_wizard_identity.py`, replace `test_identity_shows_and_autorolls_skill_when_rule_on` (lines ~167-178) with:

```python
def test_identity_shows_roll_button_and_does_not_autoroll(tmp_path):
    client = _make_client(tmp_path, RuleSet(secondary_skills=True))
    draft_id = _drive_to_identity(client)
    r = client.get(f"/wizard/{draft_id}/identity")
    assert "Secondary Skill" in r.text
    assert "identity/skill-roll" in r.text
    draft = load_draft(draft_id, client._drafts_dir)
    assert "secondary_skill" not in draft  # nothing rolled until pressed


def test_identity_skill_roll_populates(tmp_path):
    from aose.data.loader import GameData
    from aose.engine.secondary_skills import selectable_names
    client = _make_client(tmp_path, RuleSet(secondary_skills=True))
    draft_id = _drive_to_identity(client)
    client.get(f"/wizard/{draft_id}/identity")
    r = client.post(f"/wizard/{draft_id}/identity/skill-roll")
    assert r.status_code in (200, 303)
    rolled = load_draft(draft_id, client._drafts_dir)["secondary_skill"]
    valid = selectable_names(GameData.load(DATA_DIR).secondary_skills)
    assert isinstance(rolled, list) and all(s in valid for s in rolled)


def test_identity_skill_strict_locks_after_roll(tmp_path):
    client = _make_client(tmp_path, RuleSet(secondary_skills=True, strict_mode=True))
    draft_id = _drive_to_identity(client)
    client.post(f"/wizard/{draft_id}/identity/skill-roll")
    locked = load_draft(draft_id, client._drafts_dir)["secondary_skill"]
    r = client.post(f"/wizard/{draft_id}/identity/skill-roll")
    assert r.status_code == 400
    assert load_draft(draft_id, client._drafts_dir)["secondary_skill"] == locked


def test_identity_advance_requires_rolled_skill(tmp_path):
    client = _make_client(tmp_path, RuleSet(secondary_skills=True))
    draft_id = _drive_to_identity(client)
    client.get(f"/wizard/{draft_id}/identity")
    r = client.post(f"/wizard/{draft_id}/identity",
                    data={"name": "X", "alignment": "law"})
    assert r.status_code == 400  # skill not rolled yet
```

Update the existing `test_identity_skill_reroll_changes_value` (line ~181) to post to the new route:

```python
def test_identity_skill_reroll_changes_value(tmp_path):
    client = _make_client(tmp_path, RuleSet(secondary_skills=True, strict_mode=False))
    draft_id = _drive_to_identity(client)
    client.get(f"/wizard/{draft_id}/identity")
    client.post(f"/wizard/{draft_id}/identity/skill-roll")  # first roll
    before = load_draft(draft_id, client._drafts_dir)["secondary_skill"]
    for _ in range(20):
        client.post(f"/wizard/{draft_id}/identity/skill-roll")
        after = load_draft(draft_id, client._drafts_dir)["secondary_skill"]
        if after != before:
            return
    pytest.fail("Re-roll never changed the skill after 20 tries")
```

Update `test_identity_requires_skill_when_rule_on` (line ~195) and `test_class_change_clears_alignment_keeps_name_and_skill` (line ~209): both currently rely on the GET auto-roll. Add an explicit `client.post(f"/wizard/{draft_id}/identity/skill-roll")` after the `client.get(...)` so a skill exists before the asserted action.

- [ ] **Step 2: Update `test_secondary_skills.py` wizard tests**

In `tests/test_secondary_skills.py`, the wizard-driving tests assume the GET auto-rolls (e.g. lines ~188, ~194, ~203-205, ~215-218, ~261-276, ~329). For each, insert an explicit `client.post(f"/wizard/{draft_id}/identity/skill-roll")` after the identity GET, and change the reroll route from `/identity/skill-reroll` to `/identity/skill-roll`. The test at ~188 (`assert "secondary_skill" not in draft`) should now assert that after a GET *without* a roll the key is absent — keep it as-is but ensure no roll precedes it.

> Read the file first and adjust each driver; the contract is: GET no longer rolls, `skill-roll` rolls, strict refuses a second roll.

- [ ] **Step 3: Run the tests to watch them fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_identity.py tests/test_secondary_skills.py -q`
Expected: failures referencing the missing `skill-roll` route and the GET still auto-rolling.

- [ ] **Step 4: Implement the route + handler changes in `wizard.py`**

Replace the auto-roll block in `get_identity` (currently lines ~1040-1055) with:

```python
    ctx["show_skill"] = rs.secondary_skills
    if rs.secondary_skills:
        skills = _available_skills(request)
        if not skills:
            raise HTTPException(
                500,
                "Secondary Skills rule is active but data/secondary_skills.yaml is empty.",
            )
        ctx["skills"] = skills
        ctx["skill_locked"] = rs.strict_mode
        ctx["skill_rolled"] = "secondary_skill" in draft
        ctx["current_skills"] = draft.get("secondary_skill") or []
```

Rename `post_identity_skill_reroll` → `post_identity_skill_roll`, change its route to `/identity/skill-roll`, and add the Strict lock at the top (keep the existing name/alignment/language preservation):

```python
@router.post("/{draft_id}/identity/skill-roll")
async def post_identity_skill_roll(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    rs = _ruleset_of(draft)
    if rs.strict_mode and "secondary_skill" in draft:
        raise HTTPException(400, "Secondary skill is locked in Strict Mode.")
    form = await request.form()

    name = (form.get("name") or "").strip()
    if name:
        draft["name"] = name

    data = request.app.state.game_data
    alignment = form.get("alignment")
    allowed = {o["id"] for o in _identity_alignment_options(draft, data)}
    if alignment in allowed:
        draft["alignment"] = alignment

    chosen_languages = list(dict.fromkeys(form.getlist("language")))
    if chosen_languages:
        draft["languages"] = chosen_languages

    skill = _roll_skill(request)
    if skill is None:
        raise HTTPException(500, "No secondary skills configured.")
    draft["secondary_skill"] = skill
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/identity")
```

In `post_identity`, replace the `rs.secondary_skills` block (currently ~lines 1105-1115) so an un-rolled skill blocks advance in both modes:

```python
    if rs.secondary_skills:
        if "secondary_skill" not in draft:
            raise HTTPException(400, "Roll your secondary skill first.")
        if not rs.strict_mode:
            submitted = form.get("secondary_skill")
            if submitted:
                if submitted not in _available_skills(request):
                    raise HTTPException(400, f"Unknown skill: {submitted!r}")
                draft["secondary_skill"] = [submitted]  # manual collapses to one
```

- [ ] **Step 5: Update `identity.html` skill section**

Replace the `{% if show_skill %}` fieldset (lines ~22-48) with:

```html
    {% if show_skill %}
    <fieldset class="wfield">
        <legend>Secondary Skill</legend>
        {% if not skill_rolled %}
        <p class="muted">A humble trade from before adventuring — roll for it.</p>
        <button type="submit" formaction="/wizard/{{ draft_id }}/identity/skill-roll"
                formnovalidate>Roll skill</button>
        {% elif skill_locked %}
        <p class="muted">A humble trade rolled at character creation (Strict Mode — locked).</p>
        <p style="margin:0">{{ current_skills | join(", ") if current_skills else "—" }}</p>
        {% else %}
        <p class="muted">A humble trade from before adventuring — re-roll, or choose one instead.</p>
        <p style="margin:0 0 6px"><strong>Rolled:</strong>
           {{ current_skills | join(", ") if current_skills else "—" }}</p>
        <div class="skill-row">
            <label class="wfield">
                <span>Or choose a skill</span>
                <select name="secondary_skill">
                    <option value="">— keep rolled —</option>
                    {% for s in skills %}
                    <option value="{{ s }}"
                        {% if current_skills | length == 1 and s == current_skills[0] %}selected{% endif %}>{{ s }}</option>
                    {% endfor %}
                </select>
            </label>
            <button type="submit" formaction="/wizard/{{ draft_id }}/identity/skill-roll"
                    formnovalidate>Re-roll skill</button>
        </div>
        {% endif %}
    </fieldset>
    {% endif %}
```

Disable the final "Next: Equipment" submit until the skill is rolled. Change the last button (line ~76) to:

```html
    <button type="submit" class="primary"
            {% if show_skill and not skill_rolled %}disabled{% endif %}>Next: Equipment &rarr;</button>
```

- [ ] **Step 6: Run the tests, then the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_identity.py tests/test_secondary_skills.py -q`
Expected: PASS.

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS. Fix any other test that drove the old `/identity/skill-reroll` route (search `skill-reroll`).

- [ ] **Step 7: Commit**

```bash
git add aose/web/wizard.py aose/web/templates/wizard/identity.html tests/test_wizard_identity.py tests/test_secondary_skills.py
git commit -m "feat(wizard): roll-first secondary skill

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Class Setup — single save-and-advance

**Files:**
- Modify: `aose/web/wizard.py` (extract `_apply_proficiencies`/`_apply_spells`; consolidated `post_hp`; `rolls_ready` in `get_class_setup`)
- Modify: `aose/web/templates/wizard/class_setup.html` (single form, hidden `section` markers, remove per-section Save buttons, Next gating)
- Test: `tests/test_wizard_class_setup.py` (add consolidated-advance tests)

- [ ] **Step 1: Write failing tests for the consolidated advance**

Append to `tests/test_wizard_class_setup.py` (it already has `_make_client`, `_new_draft`, `_set_abilities`, `_rules_form`, `_GOOD`, `_drive_to_class_setup` — reuse them):

```python
def test_consolidated_next_saves_all_sections(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(weapon_proficiency="on"))
    _set_abilities(client, draft_id, dict(_GOOD))
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "magic_user"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    # One submit carries proficiencies AND spells AND the section markers.
    r = client.post(f"/wizard/{draft_id}/hp", data={
        "section": ["proficiencies", "spells"],
        "weapon": ["dagger"],
        "spell_magic_user": ["magic_user_magic_missile"],
    })
    assert r.status_code == 303
    assert r.headers["location"].endswith("/identity")
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["proficiencies"]["weapons"] == ["dagger"]
    assert draft["spellbooks"]["magic_user"] == ["magic_user_magic_missile"]


def test_consolidated_next_without_markers_still_advances(tmp_path):
    # Backward-compat: sections saved via their own routes, bare /hp advances.
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(weapon_proficiency="on"))
    _set_abilities(client, draft_id, dict(_GOOD))
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/proficiencies", data={"weapon": ["sword"]})
    r = client.post(f"/wizard/{draft_id}/hp")  # no markers, no data
    assert r.headers["location"].endswith("/identity")


def test_consolidated_next_rejects_wrong_proficiency_count(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(weapon_proficiency="on"))
    _set_abilities(client, draft_id, dict(_GOOD))
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    r = client.post(f"/wizard/{draft_id}/hp", data={"section": "proficiencies"})  # zero weapons
    assert r.status_code == 400


def test_class_setup_page_has_no_per_section_save_buttons(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(weapon_proficiency="on"))
    _set_abilities(client, draft_id, dict(_GOOD))
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "magic_user"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    body = client.get(f"/wizard/{draft_id}/class_setup").text
    assert "Save proficiencies" not in body
    assert "Save magic_user spells" not in body and "Save Magic-User spells" not in body
```

Verify `load_draft` is imported at the top of `test_wizard_class_setup.py`; if not, add `from aose.characters import load_draft`.

- [ ] **Step 2: Run them to watch them fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py -q -k consolidated or no_per_section`
Expected: `test_consolidated_next_saves_all_sections` fails (data ignored), `no_per_section` fails (buttons still present).

- [ ] **Step 3: Extract `_apply_proficiencies` and `_apply_spells`**

In `wizard.py`, extract the body of `post_proficiencies` (lines ~1235-1269) into a helper, and have the route call it:

```python
def _apply_proficiencies(draft: dict[str, Any], form, data) -> None:
    weapons = list(dict.fromkeys(form.getlist("weapon")))
    specialisations = list(dict.fromkeys(form.getlist("specialise")))
    ids = _class_ids(draft)
    classes = [data.classes[cid] for cid in ids if cid in data.classes]
    pairs = [(c, 1) for c in classes]
    required = total_proficiency_slots(pairs)
    allowed = allowed_weapon_ids(classes, data, _ruleset_of(draft))
    allow_special = specialisation_allowed(classes)
    if allowed != "all":
        bad = [w for w in weapons if w not in allowed]
        if bad:
            raise HTTPException(400, f"Weapon(s) not allowed for this class: {bad}")
    if specialisations and not allow_special:
        raise HTTPException(400, "This class cannot specialise.")
    if any(s not in weapons for s in specialisations):
        raise HTTPException(400, "Can only specialise a weapon you are proficient with.")
    spent = len(weapons) + len(specialisations)
    if spent != required:
        raise HTTPException(
            400,
            f"Must spend exactly {required} proficiency slot(s) at creation; "
            f"spent {spent} (each weapon = 1, each specialisation = +1).",
        )
    draft["proficiencies"] = {"weapons": weapons, "specialisations": specialisations}


@router.post("/{draft_id}/proficiencies")
async def post_proficiencies(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    form = await request.form()
    _apply_proficiencies(draft, form, data)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/class_setup")
```

Do the same for `post_spells` (lines ~1472-1512) — move the per-class validation loop into `_apply_spells(draft, form, data)` which sets `draft["spellbooks"]` and `draft["spells_done"] = True`, and have the route call it then redirect.

```python
def _apply_spells(draft: dict[str, Any], form, data) -> None:
    int_score = draft["abilities"].get("INT", 10)
    ruleset = _ruleset_of(draft)
    books: dict[str, list[str]] = dict(draft.get("spellbooks", {}))
    for cid in _class_ids(draft):
        cls = data.classes[cid]
        if not _casts_at_level_1(cls):
            continue
        entry = ClassEntry(class_id=cid, level=1)
        ctype = spell_engine.caster_type_of(cls, data)
        if ctype == "divine":
            books[cid] = []
            continue
        chosen = list(dict.fromkeys(form.getlist(f"spell_{cid}")))
        required = spell_engine.beginning_spell_count(entry, cls, int_score, ruleset)
        noun = "power" if ctype == "mental" else "starting spell"
        if len(chosen) != required:
            raise HTTPException(
                400, f"{cls.name} must choose exactly {required} {noun}(s); "
                     f"got {len(chosen)}.")
        accessible = spell_engine.accessible_levels(entry, cls)
        for sid in chosen:
            spell = data.spells.get(sid)
            on_list = spell is not None and bool(set(spell.spell_lists) & set(cls.spell_lists))
            if not on_list or (ctype == "arcane" and spell.level not in accessible):
                raise HTTPException(400, f"{sid!r} is not a valid {cls.name} {noun}.")
        books[cid] = chosen
    draft["spellbooks"] = books
    draft["spells_done"] = True


@router.post("/{draft_id}/spells")
async def post_spells(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    form = await request.form()
    _apply_spells(draft, form, data)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft, data)}")
```

- [ ] **Step 4: Make `post_hp` the consolidated advance handler**

Replace `post_hp` (currently lines ~1420-1426) with:

```python
@router.post("/{draft_id}/hp")
async def post_hp(request: Request, draft_id: str):
    """Single 'Next' action for Class Setup. Sections present in the form
    (declared via hidden ``section`` markers) are validated and saved here;
    sections saved earlier via their own routes are left untouched. Advances
    only when every applicable section is complete."""
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    form = await request.form()
    sections = set(form.getlist("section"))
    if "proficiencies" in sections:
        _apply_proficiencies(draft, form, data)
    if "spells" in sections:
        _apply_spells(draft, form, data)
    if "features" in sections and not _ruleset_of(draft).strict_mode:
        _apply_feature_overrides(draft, form, data)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft, data)}")
```

- [ ] **Step 5: Add `rolls_ready` to `get_class_setup`**

In `get_class_setup` (ends ~line 1385), after the feature-choice context is merged, add:

```python
    ctx["rolls_ready"] = (
        ctx["hp_done"]
        and ((not choice_ctx["has_feature_choices"]) or _feature_choices_complete(draft, data))
    )
    ctx["ready"] = _class_setup_complete(draft, data)
```

(`ctx["hp_done"]` already comes from `_hp_context`.) Keep `ctx["ready"]` for completeness, but the template's Next button is now gated on `rolls_ready` + client JS instead of `ready`.

- [ ] **Step 6: Consolidate the template into one form + markers; remove per-section Save buttons**

Edit `class_setup.html`:

1. **Wrap the proficiency, spell, and feature sections in one form.** Immediately after the Hit Points `</section>` (line ~61) open the consolidated form, and close it just before the old standalone Continue form at the bottom:

```html
<form method="post" action="/wizard/{{ draft_id }}/hp" id="class-setup-form" class="step-form">
```

2. **Proficiencies section:** remove its own `<form ...>`/`</form>` wrapper and the `<button>Save proficiencies</button>`. Add a hidden marker at the top of the section:

```html
{% if show_proficiencies %}
<input type="hidden" name="section" value="proficiencies">
```

Keep the table and the `prof-table` script (Task 4 extends it). The checkboxes already use `name="weapon"` / `name="specialise"`.

3. **Spells section:** remove each per-caster `<form>`/`</form>` and the `Save … spells` / `Confirm … spells` buttons and the hidden `class_id` inputs. Add one marker once at the top of the section:

```html
{% if show_spells %}
<input type="hidden" name="section" value="spells">
```

Keep the spell `card-grid`s and their script. For divine casters, the marker alone is enough (`_apply_spells` writes the empty book).

4. **Features section (non-strict override checkboxes):** the checkboxes from Task 1 already carry `form="class-setup-form"`. Add the features marker once, rendered only when at least one group is rolled and not locked:

```html
{% if has_feature_choices and not feature_choices_locked %}
<input type="hidden" name="section" value="features" form="class-setup-form">
{% endif %}
```

5. **Replace the standalone Continue form** (lines ~247-250) with the consolidated form's submit, then close the form:

```html
    <button type="submit" class="primary" id="cs-next"
            {% if not rolls_ready %}disabled{% endif %}>Next: Identity &rarr;</button>
</form>
```

> Note: the roll buttons (HP roll, per-feature Roll/Re-roll) remain their **own** little `<form>`s *outside* `#class-setup-form` (a nested form is invalid HTML). The HP section is above the consolidated form already; the feature roll buttons from Task 1 are separate `inline-form`s — keep them outside, which they are since they are full `<form>` elements (browsers don't nest them even if visually inside; to be safe, the feature Roll forms should render *before* `#class-setup-form` opens or use the same `form`-attribute trick. Simplest: leave the Features `<section>` inside the consolidated form but render each Roll/Re-roll `<button>` with `formaction` + `formnovalidate` posting to the roll route instead of a nested `<form>`.)

Revise the Task 1 feature Roll buttons to use `formaction` so they live happily inside `#class-setup-form`:

```html
<button type="submit" formnovalidate
        formaction="/wizard/{{ draft_id }}/feature-choices/roll"
        name="group_id" value="{{ g.id }}">Roll {{ g.roll_dice or "" }}</button>
```

(The button's `name=group_id`/`value` submit the group id; `formnovalidate` skips the form's other required fields.)

- [ ] **Step 7: Add the Next-gating script**

At the very bottom of `class_setup.html`, add a script that enables `#cs-next` only when every selection section is valid (it also gets called by the section scripts via `window.csValidate`):

```html
<script>
    (function () {
        const next = document.getElementById('cs-next');
        if (!next) return;
        const rollsReady = next.dataset.rollsReady === '1';
        window.csValidate = function () {
            let ok = true;
            // proficiency table: spent === required
            const prof = document.querySelector('.prof-table');
            if (prof) {
                const req = parseInt(prof.dataset.required, 10);
                let spent = 0;
                prof.querySelectorAll('.prof-weapon:checked').forEach(() => spent += 1);
                prof.querySelectorAll('.prof-special:checked').forEach(() => spent += 1);
                if (spent !== req) ok = false;
            }
            // each spell grid: checked === required
            document.querySelectorAll('.card-grid[data-required]').forEach(function (grid) {
                if (grid.closest('.feature-group')) return;  // features handled separately
                const req = parseInt(grid.dataset.required, 10);
                const n = grid.querySelectorAll('.spell-checkbox:checked').length;
                if (n !== req) ok = false;
            });
            // non-strict feature overrides: each grid pick === required
            document.querySelectorAll('.feature-group .card-grid[data-required]').forEach(function (grid) {
                const req = parseInt(grid.dataset.required, 10);
                const n = grid.querySelectorAll('.choice-checkbox:checked').length;
                if (n !== req) ok = false;
            });
            next.disabled = !(rollsReady && ok);
        };
        window.csValidate();
    })();
</script>
```

Set the data attribute on the button: change it to `id="cs-next" data-rolls-ready="{{ 1 if rolls_ready else 0 }}"` and drop the server `disabled` (the script now owns it) — except keep a server fallback so non-JS users aren't fully stuck: render `{% if not rolls_ready %}disabled{% endif %}` too; the script will re-enable when valid.

Wire the existing spell script and prof script to call `window.csValidate()` inside their `update()`/`refresh()` functions (add `if (window.csValidate) window.csValidate();` at the end of each).

- [ ] **Step 8: Run the class-setup tests, then the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py -q`
Expected: PASS, including the new consolidated tests and the existing `test_full_flow_caster_with_proficiencies_and_blessed` (it drives sections separately + bare `/hp` — still valid via backward-compat).

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 9: Verify in the browser (preview tools)**

Start the dev server and walk a Magic-User with weapon proficiency on: confirm one page, no per-section Save buttons, Next disabled until HP rolled + spell/prof counts exact, and a single click advances. Use `preview_start`, `preview_snapshot`, `preview_click`, `preview_screenshot`.

- [ ] **Step 10: Commit**

```bash
git add aose/web/wizard.py aose/web/templates/wizard/class_setup.html tests/test_wizard_class_setup.py
git commit -m "feat(wizard): consolidate Class Setup into one save-and-advance

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Client-side selection caps

**Files:**
- Modify: `aose/web/templates/wizard/class_setup.html` (proficiency cap)
- Modify: `aose/web/templates/wizard/identity.html` (language cap)
- Test: `tests/test_wizard_class_setup.py`, `tests/test_wizard_languages.py` (markup presence)

- [ ] **Step 1: Write markup-presence tests**

JS behaviour can't be unit-tested without a browser, so assert the cap machinery is present. Append to `tests/test_wizard_class_setup.py`:

```python
def test_proficiency_table_carries_cap_metadata(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(weapon_proficiency="on"))
    _set_abilities(client, draft_id, dict(_GOOD))
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    body = client.get(f"/wizard/{draft_id}/class_setup").text
    assert 'data-required="1"' in body  # fighter: 1 slot
    assert "prof-weapon" in body
```

In `tests/test_wizard_languages.py`, add a test asserting the language fieldset exposes the slot count for the cap script. The file already defines `_make_client`, `_drive_to_identity(client, abilities, ...)`, and `HIGH_INT` (INT 16 → 2 additional slots):

```python
def test_language_section_exposes_slot_cap(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, HIGH_INT)  # INT 16 -> 2 additional slots
    body = client.get(f"/wizard/{draft_id}/identity").text
    assert 'data-language-slots="2"' in body
```

- [ ] **Step 2: Run to watch them fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py::test_proficiency_table_carries_cap_metadata tests/test_wizard_languages.py -q`
Expected: language test fails (no `data-language-slots`); proficiency test may already pass (table has `data-required`) — that's fine.

- [ ] **Step 3: Cap proficiency selections**

In `class_setup.html`, extend the existing `prof-table` script's `refresh()` so it disables further selections at the cap (accounting for specialisation = 2 slots):

```javascript
            function refresh() {
                table.querySelectorAll('.prof-special:checked').forEach(s => {
                    const w = rowOf(s).querySelector('.prof-weapon');
                    if (w && !w.checked) { w.checked = true; }
                });
                const n = spent();
                table.querySelectorAll('.prof-weapon').forEach(w => {
                    if (!w.checked) w.disabled = n >= required;
                });
                table.querySelectorAll('.prof-special').forEach(sp => {
                    if (sp.checked) return;
                    const w = rowOf(sp).querySelector('.prof-weapon');
                    const cost = (w && w.checked) ? 1 : 2;  // unchecked weapon ⇒ +2
                    sp.disabled = n + cost > required;
                });
                counter.textContent = `Spent ${n} of ${required}.`;
                counter.className = (n === required) ? '' : 'muted';
                if (window.csValidate) window.csValidate();
            }
```

- [ ] **Step 4: Cap language selections**

In `identity.html`, give the language checkbox container the slot count and add a cap script. Change the wrapper (line ~64) to:

```html
        <div class="checkbox-stack" data-language-slots="{{ language_slots }}">
```

Add at the end of `identity.html`:

```html
<script>
    (function () {
        const box = document.querySelector('.checkbox-stack[data-language-slots]');
        if (!box) return;
        const max = parseInt(box.dataset.languageSlots, 10);
        const boxes = Array.from(box.querySelectorAll('input[type="checkbox"][name="language"]'));
        function update() {
            const checked = boxes.filter(b => b.checked).length;
            boxes.forEach(b => { if (!b.checked) b.disabled = checked >= max; });
        }
        boxes.forEach(b => b.addEventListener('change', update));
        update();
    })();
</script>
```

> Spells already cap at exactly N in the existing spell script (`b.disabled = !b.checked && checked >= required`) — no change needed beyond the `csValidate` hook added in Task 3.

- [ ] **Step 5: Run the tests, then the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py tests/test_wizard_languages.py -q`
Expected: PASS.

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 6: Verify caps in the browser**

With the dev server running, confirm: a fighter can't check a 2nd weapon proficiency; a high-INT human can't exceed the language allowance; a Magic-User can't pick more than the required spells. Use `preview_click` + `preview_snapshot`.

- [ ] **Step 7: Commit**

```bash
git add aose/web/templates/wizard/class_setup.html aose/web/templates/wizard/identity.html tests/test_wizard_class_setup.py tests/test_wizard_languages.py
git commit -m "feat(wizard): cap proficiency & language selections client-side

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Documentation

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: Update ARCHITECTURE.md**

Find the Wizard subsystem section (`grep -n "Wizard" docs/ARCHITECTURE.md`). Edit the Class Setup / feature-choices / secondary-skill prose **in place** to describe: roll-first features (per-table `/feature-choices/roll`, Strict locks, non-strict re-roll + override), roll-first secondary skill (`/identity/skill-roll`), the consolidated `POST /hp` advance gated by hidden `section` markers (with the standalone routes retained for compatibility), the `rolls_ready` (server) + client-JS selection gate split, and the retirement of `feature_choices_done` in favour of computed `_feature_choices_complete`. Do not append a dated entry — edit the existing topic.

- [ ] **Step 2: Add a CHANGELOG.md row**

Add one row to the top of the dated table in `docs/CHANGELOG.md`:

```
| 2026-06-10 | Interactive wizard rolls + Class Setup consolidation | feat/interactive-wizard-rolls | interactive-wizard-rolls |
```

(Match the existing column format in that file.)

- [ ] **Step 3: Commit**

```bash
git add docs/ARCHITECTURE.md docs/CHANGELOG.md
git commit -m "docs: interactive wizard rolls + class-setup consolidation

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification

- [ ] **Run the whole suite once more**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all pass (ignore the trailing `pytest-current` PermissionError).

- [ ] **Manual smoke via preview**

Create three characters end-to-end: (a) Strict Mutoid — must press Roll for mutations, locked after; (b) non-strict Tiefling — roll each of the two tables, re-roll one, override the other by checkbox, single Next; (c) Strict Human Magic-User with weapon proficiency + Secondary Skills — confirm one-click Class Setup advance and the roll-first secondary skill on Identity.
