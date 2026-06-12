# Combat Talents + Level-Up Choices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Carcass Crawler #1 "Combat Talents" optional rule for fighters (talents at levels 1/5/10), and build the shared "spend a slot you earned on level-up" mechanism it needs — reusing it to close the existing weapon-proficiency level-up gap.

**Architecture:** A subsystem-agnostic *unspent-capacity* engine (`earned` vs `spent`) drives a shared picker rendered both in the level-up modal and inline on the sheet. Two providers feed it: weapon proficiencies (existing slot math) and combat talents (new level-banded pick count). Two talents drive real numbers via existing plumbing — Slayer as a conditional `attack/damage` modifier, Weapon specialist via the existing `weapon_specialisations` +1/+1 path; the other four are descriptive text.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, YAML, pytest. Windows/PowerShell — run Python as `.venv\Scripts\python.exe -m ...`.

**Spec:** `docs/superpowers/specs/2026-06-11-combat-talents-design.md`

**Conventions:**
- Run a single test: `.venv\Scripts\python.exe -m pytest tests/test_x.py::test_name -q`
- Run all tests: `.venv\Scripts\python.exe -m pytest tests/ -q`
- The trailing `PermissionError` on `pytest-current` is a known Windows quirk — ignore it.
- Talent group id is `combat_talents`; source id is `carcass_crawler_1`.
- This plan does NOT commit on its own branch (working tree is mid-flight on unrelated work); the user manages git. Each "Commit" step still stages the right files — run it only if/when the user has set up a branch.

---

## File Structure

**Phase A — shared mechanism + proficiency retrofit**
- Create `aose/engine/level_choices.py` — `Capacity` model + capacity providers (`proficiency_capacity`, `talent_capacities`, `all_capacities`). One responsibility: "what can this character still spend?"
- Modify `aose/web/routes.py` — new `POST /character/{id}/proficiency/add` endpoint.
- Modify `aose/sheet/view.py` — expose unspent-proficiency picker data on the sheet.
- Modify `aose/web/templates/sheet.html` — inline proficiency picker + modal note.
- Create `aose/web/templates/_levelup_choices.html` — shared picker partial.

**Phase B — combat talents**
- Modify `aose/models/choice.py` — `OptionParam`, `FeatureChoice.requires_rule`/`pick_by_level`, `ChoiceOption.excluded_when_rule`/`param`.
- Modify `aose/models/ruleset.py` — `combat_talents` flag.
- Modify `aose/models/character.py` — `CharacterSpec.choice_params`.
- Modify `aose/engine/feature_choices.py` — `effective_pick`, `pick` overrides.
- Modify `aose/engine/features.py` — `{param}` condition substitution.
- Modify `aose/engine/attacks.py` — widen specialisation gate.
- Modify `aose/engine/level_choices.py` — talent capacity provider (from Phase A file).
- Modify `data/classes/fighter.yaml` — combat-talents group.
- Modify `aose/web/settings_routes.py` — register `combat_talents` rule.
- Modify `aose/web/wizard.py` — cascading clear; L1 talent pick honors `pick_by_level`; param inputs.
- Modify `aose/web/templates/wizard/class_setup.html` — talent param inputs.
- Modify `aose/web/routes.py` — `POST /character/{id}/talent/add`.
- Modify `aose/sheet/view.py` + `sheet.html` — talent picker + descriptive talents.
- Modify `docs/CHANGELOG.md`, `docs/ARCHITECTURE.md`.

---

# PHASE A — Shared unspent-capacity mechanism + proficiency retrofit

## Task A1: Capacity model + proficiency provider

**Files:**
- Create: `aose/engine/level_choices.py`
- Test: `tests/test_level_choices.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_level_choices.py
from aose.data.loader import GameData
from aose.engine.level_choices import proficiency_capacity

DATA = GameData.load("data")


def _fighter(level: int):
    from aose.models import CharacterSpec, ClassEntry, RuleSet
    return CharacterSpec(
        name="T", abilities={"STR": 12, "INT": 9, "WIS": 9, "DEX": 12, "CON": 12, "CHA": 9},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=level)],
        alignment="neutral", ruleset=RuleSet(weapon_proficiency=True),
    )


def test_proficiency_capacity_off_when_rule_disabled():
    spec = _fighter(1)
    spec.ruleset.weapon_proficiency = False
    assert proficiency_capacity(spec, DATA) is None


def test_proficiency_capacity_level1_fighter_4_slots_none_spent():
    cap = proficiency_capacity(_fighter(1), DATA)
    assert (cap.earned, cap.spent, cap.remaining) == (4, 0, 4)


def test_proficiency_capacity_level7_fighter_earns_two_more():
    # THAC0 improves at 4 and 7 -> 6 slots total at L7.
    cap = proficiency_capacity(_fighter(7), DATA)
    assert cap.earned == 6 and cap.remaining == 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_level_choices.py -q`
Expected: FAIL — `ModuleNotFoundError: aose.engine.level_choices`.

- [ ] **Step 3: Write minimal implementation**

```python
# aose/engine/level_choices.py
"""Unspent-capacity model: how many selections a character has *earned* by their
current level vs. *spent*. Subsystem-agnostic — each provider (weapon
proficiencies, combat talents) reports its own capacity, and any with
``remaining > 0`` contributes a picker to the level-up/sheet UI.

Cycle-free: imports models, the loader, and ``proficiency`` only.
"""
from __future__ import annotations

from pydantic import BaseModel

from aose.data.loader import GameData
from aose.engine.proficiency import slots_spent, total_proficiency_slots
from aose.models import CharacterSpec


class Capacity(BaseModel):
    kind: str                 # "proficiency" | "talent"
    group_id: str | None      # FeatureChoice id for talents; None for proficiencies
    label: str
    earned: int
    spent: int

    @property
    def remaining(self) -> int:
        return max(0, self.earned - self.spent)


def proficiency_capacity(spec: CharacterSpec, data: GameData) -> Capacity | None:
    """Weapon-proficiency slots earned vs spent. ``None`` when the rule is off."""
    if not spec.ruleset.weapon_proficiency:
        return None
    pairs = [(data.classes[e.class_id], e.level) for e in spec.classes
             if e.class_id in data.classes]
    return Capacity(
        kind="proficiency", group_id=None, label="Weapon Proficiency",
        earned=total_proficiency_slots(pairs), spent=slots_spent(spec),
    )


def all_capacities(spec: CharacterSpec, data: GameData) -> list[Capacity]:
    """Every provider's capacity with ``remaining > 0`` (talents added in Task B2)."""
    out: list[Capacity] = []
    prof = proficiency_capacity(spec, data)
    if prof is not None and prof.remaining > 0:
        out.append(prof)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_level_choices.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/level_choices.py tests/test_level_choices.py
git commit -m "feat(engine): unspent-capacity model + weapon-proficiency provider"
```

---

## Task A2: Post-creation "add proficiency" endpoint

**Files:**
- Modify: `aose/web/routes.py`
- Test: `tests/test_proficiency_levelup.py`

Mirror the existing wizard validation in `aose/web/wizard.py:_apply_proficiencies` (allowed-weapon check, specialise-needs-martial, specialise-needs-proficient) but for a *single* slot, and cap by `proficiency_capacity(...).remaining`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_proficiency_levelup.py
import pytest
from fastapi.testclient import TestClient

from aose.web.app import create_app
from aose.models import CharacterSpec, ClassEntry, RuleSet


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AOSE_DATA_DIR", "data")
    app = create_app(characters_dir=tmp_path / "chars", drafts_dir=tmp_path / "drafts",
                     settings_path=tmp_path / "settings.json")
    return TestClient(app)


def _save_fighter(client, level=4):
    from aose.characters.storage import save_character
    spec = CharacterSpec(
        name="Prof", abilities={"STR": 13, "INT": 9, "WIS": 9, "DEX": 12, "CON": 12, "CHA": 9},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=level)],
        alignment="neutral", ruleset=RuleSet(weapon_proficiency=True),
        weapon_proficiencies=["sword", "dagger", "spear", "mace"],  # 4 spent (L1 slots)
    )
    return save_character(spec, client.app.state.characters_dir)


def test_add_proficiency_spends_an_earned_slot(client):
    cid = _save_fighter(client, level=4)  # 5 slots earned, 4 spent -> 1 remaining
    r = client.post(f"/character/{cid}/proficiency/add",
                    data={"weapon_id": "battle_axe"}, follow_redirects=False)
    assert r.status_code == 303
    from aose.characters.storage import load_character
    spec = load_character(cid, client.app.state.characters_dir)
    assert "battle_axe" in spec.weapon_proficiencies


def test_add_proficiency_refused_when_no_slot_remaining(client):
    cid = _save_fighter(client, level=1)  # 4 earned, 4 spent -> 0 remaining
    r = client.post(f"/character/{cid}/proficiency/add",
                    data={"weapon_id": "battle_axe"}, follow_redirects=False)
    assert r.status_code == 400
```

> Adjust the `create_app`/`save_character`/`load_character` import paths and the
> `client` fixture to match `tests/` conventions — open an existing web test
> (e.g. `tests/test_wizard*.py` or `tests/test_routes*.py`) and copy its app
> fixture verbatim rather than guessing.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_proficiency_levelup.py -q`
Expected: FAIL — 404 (route missing) / fixture import errors to fix first.

- [ ] **Step 3: Write minimal implementation**

Add to `aose/web/routes.py` (near the other `/character/{character_id}/...` POST routes). Reuse helpers already imported there for loading/saving a character; mirror the load/save pattern used by `level_up_class`.

```python
from aose.engine.level_choices import proficiency_capacity
from aose.engine.proficiency import (
    allowed_weapon_ids, base_weapon_id, specialisation_allowed,
)
from aose.models import Weapon


@router.post("/character/{character_id}/proficiency/add")
async def add_proficiency(request: Request, character_id: str,
                          weapon_id: str = Form(...),
                          specialise: bool = Form(False)):
    data = request.app.state.game_data
    spec = _load_character(request, character_id)        # mirror level_up_class's loader
    cap = proficiency_capacity(spec, data)
    if cap is None or cap.remaining <= 0:
        raise HTTPException(400, "No weapon-proficiency slots remaining.")
    classes = [data.classes[e.class_id] for e in spec.classes if e.class_id in data.classes]
    allowed = allowed_weapon_ids(classes, data, spec.ruleset)
    item = data.items.get(weapon_id)
    if not isinstance(item, Weapon) or base_weapon_id(item) != weapon_id:
        raise HTTPException(400, "Pick a base weapon type.")
    if allowed != "all" and weapon_id not in allowed:
        raise HTTPException(400, "Weapon not allowed for this class.")
    if specialise:
        if not specialisation_allowed(classes):
            raise HTTPException(400, "This class cannot specialise.")
        if cap.remaining < 2 and weapon_id not in spec.weapon_proficiencies:
            raise HTTPException(400, "Specialising a new weapon needs 2 slots.")
    if weapon_id not in spec.weapon_proficiencies:
        spec.weapon_proficiencies.append(weapon_id)
    if specialise and weapon_id not in spec.weapon_specialisations:
        spec.weapon_specialisations.append(weapon_id)
    _save_character(request, character_id, spec)         # mirror level_up_class's saver
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

> Replace `_load_character` / `_save_character` with the exact load/save calls
> `level_up_class` uses (read `routes.py:402-414`).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_proficiency_levelup.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_proficiency_levelup.py
git commit -m "feat(web): spend an earned weapon-proficiency slot post-creation"
```

---

## Task A3: Shared picker partial + inline proficiency picker on the sheet

**Files:**
- Create: `aose/web/templates/_levelup_choices.html`
- Modify: `aose/sheet/view.py` (expose capacities + weapon options)
- Modify: `aose/web/templates/sheet.html`
- Test: `tests/test_sheet_capacity.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sheet_capacity.py
from aose.data.loader import GameData
from aose.sheet.view import build_sheet
from aose.models import CharacterSpec, ClassEntry, RuleSet

DATA = GameData.load("data")


def _fighter(level, **kw):
    return CharacterSpec(
        name="Cap", abilities={"STR": 13, "INT": 9, "WIS": 9, "DEX": 12, "CON": 12, "CHA": 9},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=level)],
        alignment="neutral", **kw,
    )


def test_sheet_exposes_remaining_proficiency_slots():
    spec = _fighter(4, ruleset=RuleSet(weapon_proficiency=True),
                    weapon_proficiencies=["sword", "dagger", "spear", "mace"])
    sheet = build_sheet(spec, DATA)
    cap = next(c for c in sheet.level_choices if c.kind == "proficiency")
    assert cap.remaining == 1


def test_sheet_no_capacity_when_all_spent():
    spec = _fighter(1, ruleset=RuleSet(weapon_proficiency=True),
                    weapon_proficiencies=["sword", "dagger", "spear", "mace"])
    sheet = build_sheet(spec, DATA)
    assert all(c.kind != "proficiency" for c in sheet.level_choices)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_capacity.py -q`
Expected: FAIL — `CharacterSheet` has no attribute `level_choices`.

- [ ] **Step 3: Write minimal implementation**

In `aose/sheet/view.py`:
1. Add a sheet field. Find the `CharacterSheet` model (the big `class CharacterSheet(BaseModel)` it returns) and add:

```python
    level_choices: list = Field(default_factory=list)
    # weapon options for the inline proficiency picker: [{"id","name"}], base types only
    proficiency_weapon_options: list = Field(default_factory=list)
```

2. In `build_sheet(...)`, before the `return CharacterSheet(...)`, compute:

```python
    from aose.engine.level_choices import all_capacities
    _caps = all_capacities(spec, data)
    _prof_weapon_opts = []
    if any(c.kind == "proficiency" for c in _caps):
        from aose.models import Weapon as _W
        from aose.engine.proficiency import base_weapon_id as _bwid, allowed_weapon_ids as _awi
        _classes = [data.classes[e.class_id] for e in spec.classes if e.class_id in data.classes]
        _allowed = _awi(_classes, data, spec.ruleset)
        for w in sorted((i for i in data.items.values()
                         if isinstance(i, _W) and _bwid(i) == i.id), key=lambda w: w.name):
            if _allowed == "all" or w.id in _allowed:
                _prof_weapon_opts.append({"id": w.id, "name": w.name})
```

3. Pass them into the `CharacterSheet(...)` constructor:

```python
        level_choices=_caps,
        proficiency_weapon_options=_prof_weapon_opts,
```

Create `aose/web/templates/_levelup_choices.html` (the shared picker — proficiency arm now; talent arm added in Task B8):

```html
{# Renders pickers for any unspent capacity. Expects: character_id, sheet. #}
{% for cap in sheet.level_choices %}
  {% if cap.kind == "proficiency" %}
  <div class="capacity-picker" data-kind="proficiency">
    <div class="subhead">New Weapon Proficiency ({{ cap.remaining }} slot{{ "s" if cap.remaining != 1 }})</div>
    <form method="post" action="/character/{{ character_id }}/proficiency/add" class="inline-form">
      <select name="weapon_id" required>
        {% for w in sheet.proficiency_weapon_options %}<option value="{{ w.id }}">{{ w.name }}</option>{% endfor %}
      </select>
      <label class="small"><input type="checkbox" name="specialise" value="true"> specialise (+1 slot)</label>
      <button class="btn solid" type="submit">Add</button>
    </form>
  </div>
  {% endif %}
{% endfor %}
```

In `aose/web/templates/sheet.html`, include the partial right after the read-only Weapon Proficiencies block (after line ~223):

```html
          {% include "_levelup_choices.html" %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_capacity.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full suite + smoke the page**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all green (ignore the pytest-current PermissionError). Then start the app (`.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`), open a weapon-proficiency fighter levelled to 4+, confirm the "New Weapon Proficiency" picker shows and adding a weapon persists.

- [ ] **Step 6: Commit**

```bash
git add aose/sheet/view.py aose/web/templates/_levelup_choices.html aose/web/templates/sheet.html tests/test_sheet_capacity.py
git commit -m "feat(sheet): inline picker for unspent weapon-proficiency slots"
```

---

## Task A4: Surface the picker inside the level-up modal

**Files:**
- Modify: `aose/web/templates/sheet.html` (level-up modal, lines ~971-1017)
- Test: manual (covered by A3 unit tests + smoke)

- [ ] **Step 1: Add a "choices available" note to the modal**

In the level-up modal body, after the Confirm/Cancel block, add a reminder that links the player to the inline picker (the modal closes on confirm; the inline picker is the durable surface):

```html
    {% if sheet.level_choices %}
    <p class="muted small" style="margin-top:8px">
      You have selections to make below (new proficiencies/talents) — they appear on your sheet after confirming.
    </p>
    {% endif %}
```

- [ ] **Step 2: Smoke test**

Run the app, level a weapon-proficiency fighter from 3→4, confirm the modal shows the note and the inline picker appears on the sheet afterward.

- [ ] **Step 3: Commit**

```bash
git add aose/web/templates/sheet.html
git commit -m "feat(web): level-up modal points to pending level-up choices"
```

---

# PHASE B — Combat talents

## Task B1: Model fields

**Files:**
- Modify: `aose/models/choice.py`, `aose/models/ruleset.py`, `aose/models/character.py`
- Test: `tests/test_combat_talent_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_combat_talent_models.py
from aose.models import RuleSet, CharacterSpec, ClassEntry
from aose.models.choice import FeatureChoice, ChoiceOption, OptionParam


def test_ruleset_has_combat_talents_default_off():
    assert RuleSet().combat_talents is False


def test_feature_choice_optional_gating_fields():
    g = FeatureChoice(id="combat_talents", name="Combat Talents",
                      requires_rule="combat_talents", pick_by_level={1: 1, 5: 2, 10: 3},
                      options=[ChoiceOption(id="cleave", name="Cleave")])
    assert g.requires_rule == "combat_talents"
    assert g.pick_by_level[10] == 3


def test_choice_option_param_and_exclusion():
    o = ChoiceOption(id="weapon_specialist", name="Weapon specialist",
                     excluded_when_rule="weapon_proficiency",
                     param=OptionParam(kind="weapon", label="Weapon"))
    assert o.excluded_when_rule == "weapon_proficiency"
    assert o.param.kind == "weapon"


def test_spec_choice_params_default_empty():
    spec = CharacterSpec(name="x", abilities={"STR": 9, "INT": 9, "WIS": 9, "DEX": 9, "CON": 9, "CHA": 9},
                         race_id="human", classes=[ClassEntry(class_id="fighter")], alignment="neutral")
    assert spec.choice_params == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_combat_talent_models.py -q`
Expected: FAIL — `OptionParam` import error / unknown fields under `extra="forbid"`.

- [ ] **Step 3: Write minimal implementation**

In `aose/models/choice.py`, add `OptionParam` and the new fields:

```python
class OptionParam(BaseModel):
    """A free player-chosen parameter attached to a ChoiceOption.

    ``kind="text"`` → a free-text value substituted into the option's modifier
    ``condition`` where it contains ``{param}`` (Slayer's enemy type).
    ``kind="weapon"`` → a base-weapon id written to
    ``CharacterSpec.weapon_specialisations`` (Weapon specialist).
    """
    model_config = ConfigDict(extra="forbid")

    kind: Literal["text", "weapon"]
    label: str
```

Add `from typing import Literal` at the top if not present. Extend `ChoiceOption`:

```python
    excluded_when_rule: str | None = None
    param: "OptionParam | None" = None
```

Extend `FeatureChoice`:

```python
    requires_rule: str | None = None
    pick_by_level: dict[int, int] | None = None
```

In `aose/models/ruleset.py`, add to `RuleSet` (alongside the other flags):

```python
    combat_talents: bool = False
```

In `aose/models/character.py`, add to `CharacterSpec` (near `feature_choices`):

```python
    # Free player-chosen params for parameterised choice options: option id ->
    # value. Slayer: enemy-type text. (Weapon specialist's weapon lives in
    # weapon_specialisations.)
    choice_params: dict[str, str] = Field(default_factory=dict)
```

Confirm `OptionParam` is exported if the package re-exports choice models (check `aose/models/__init__.py` and add `OptionParam` next to `FeatureChoice`/`ChoiceOption`).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_combat_talent_models.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/models/ tests/test_combat_talent_models.py
git commit -m "feat(models): combat-talent gating fields + choice params"
```

---

## Task B2: Level-banded pick count + talent capacity provider

**Files:**
- Modify: `aose/engine/feature_choices.py` (add `effective_pick`, `pick` overrides)
- Modify: `aose/engine/level_choices.py` (talent provider)
- Test: `tests/test_talent_capacity.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_talent_capacity.py
from aose.data.loader import GameData
from aose.engine.feature_choices import effective_pick
from aose.engine.level_choices import talent_capacities
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.models.choice import FeatureChoice, ChoiceOption

DATA = GameData.load("data")

GROUP = FeatureChoice(id="combat_talents", name="Combat Talents",
                      requires_rule="combat_talents", pick_by_level={1: 1, 5: 2, 10: 3},
                      options=[ChoiceOption(id=o, name=o) for o in
                               ["cleave", "defender", "leader", "slayer"]])


def test_effective_pick_bands_by_level():
    assert effective_pick(GROUP, 1) == 1
    assert effective_pick(GROUP, 4) == 1
    assert effective_pick(GROUP, 5) == 2
    assert effective_pick(GROUP, 10) == 3
    assert effective_pick(GROUP, 14) == 3


def test_effective_pick_falls_back_to_flat_pick():
    flat = FeatureChoice(id="g", name="g", pick=2,
                         options=[ChoiceOption(id="a", name="a"), ChoiceOption(id="b", name="b")])
    assert effective_pick(flat, 9) == 2


def _fighter(level, picked=(), rule=True):
    return CharacterSpec(
        name="T", abilities={"STR": 12, "INT": 9, "WIS": 9, "DEX": 12, "CON": 12, "CHA": 9},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=level)],
        alignment="neutral", ruleset=RuleSet(combat_talents=rule),
        feature_choices={"combat_talents": list(picked)},
    )


def test_talent_capacity_level5_one_picked_one_remaining():
    # Requires Task B5 fighter data to be loaded.
    caps = talent_capacities(_fighter(5, picked=["cleave"]), DATA)
    cap = next(c for c in caps if c.group_id == "combat_talents")
    assert cap.earned == 2 and cap.spent == 1 and cap.remaining == 1


def test_no_talent_capacity_when_rule_off():
    assert talent_capacities(_fighter(5, rule=False), DATA) == []
```

> The two `talent_capacity` tests depend on the fighter data from Task B5. Order
> Task B5 before running them, or mark them `xfail` until B5 lands.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_talent_capacity.py -q`
Expected: FAIL — `effective_pick` / `talent_capacities` undefined.

- [ ] **Step 3: Write minimal implementation**

In `aose/engine/feature_choices.py`:

```python
def _band_lookup(table: dict[int, int], key: int) -> int:
    candidates = [k for k in table if k <= key]
    return table[max(candidates)] if candidates else 0


def effective_pick(group, level: int) -> int:
    """Total picks allowed for ``group`` at ``level`` — the banded
    ``pick_by_level`` value if set, else the flat ``pick``."""
    if group.pick_by_level:
        return _band_lookup(group.pick_by_level, level)
    return group.pick
```

Update `roll_choice` and `validate_choice` to accept an optional `pick` override:

```python
def roll_choice(group, rng=None, pick=None):
    _rng = rng or _random.Random()
    ids = [o.id for o in group.options]
    k = min(group.pick if pick is None else pick, len(ids))
    return _rng.sample(ids, k)


def validate_choice(group, chosen, pick=None):
    want = group.pick if pick is None else pick
    ids = {o.id for o in group.options}
    if len(chosen) != want:
        raise ChoiceError(f"{group.name}: choose exactly {want} (got {len(chosen)}).")
    if len(set(chosen)) != len(chosen):
        raise ChoiceError(f"{group.name}: choices must be distinct.")
    bad = [c for c in chosen if c not in ids]
    if bad:
        raise ChoiceError(f"{group.name}: unknown option(s) {bad}.")
```

In `aose/engine/level_choices.py`, add the talent provider and fold it into `all_capacities`:

```python
def talent_capacities(spec: CharacterSpec, data: GameData) -> list[Capacity]:
    """One Capacity per applicable level-banded choice group whose ``requires_rule``
    is satisfied (combat talents today). ``earned`` bands by the granting class's
    level; ``spent`` is how many options are already chosen."""
    from aose.engine.feature_choices import effective_pick
    out: list[Capacity] = []
    for entry in spec.classes:
        cls = data.classes.get(entry.class_id)
        if cls is None:
            continue
        for g in cls.feature_choices:
            if g.pick_by_level is None:
                continue
            if g.requires_rule and not getattr(spec.ruleset, g.requires_rule, False):
                continue
            out.append(Capacity(
                kind="talent", group_id=g.id, label=g.name,
                earned=effective_pick(g, entry.level),
                spent=len(spec.feature_choices.get(g.id, [])),
            ))
    return out
```

Update `all_capacities` to append talent capacities too:

```python
def all_capacities(spec: CharacterSpec, data: GameData) -> list[Capacity]:
    out: list[Capacity] = []
    prof = proficiency_capacity(spec, data)
    if prof is not None and prof.remaining > 0:
        out.append(prof)
    out += [c for c in talent_capacities(spec, data) if c.remaining > 0]
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_talent_capacity.py -q` (after Task B5 for the data-backed cases)
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/feature_choices.py aose/engine/level_choices.py tests/test_talent_capacity.py
git commit -m "feat(engine): level-banded pick count + talent capacity provider"
```

---

## Task B3: `{param}` substitution into modifier conditions (Slayer)

**Files:**
- Modify: `aose/engine/features.py:feature_modifiers`
- Test: `tests/test_talent_param_modifier.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_talent_param_modifier.py
from aose.data.loader import GameData
from aose.engine.features import feature_modifiers
from aose.models import CharacterSpec, ClassEntry, RuleSet

DATA = GameData.load("data")


def _slayer_fighter(enemy="undead"):
    # Requires Task B5 (slayer option with condition "vs {param}").
    return CharacterSpec(
        name="S", abilities={"STR": 12, "INT": 9, "WIS": 9, "DEX": 12, "CON": 12, "CHA": 9},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1)],
        alignment="neutral", ruleset=RuleSet(combat_talents=True),
        feature_choices={"combat_talents": ["slayer"]},
        choice_params={"slayer": enemy},
    )


def test_slayer_condition_substitutes_chosen_enemy_type():
    mods = feature_modifiers(_slayer_fighter("dragons"), DATA)
    atk = [m for m in mods if m.target == "attack" and m.value == 1]
    assert any(m.condition == "vs dragons" for m in atk)
    assert not any("{param}" in (m.condition or "") for m in mods)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_talent_param_modifier.py -q`
Expected: FAIL — condition is still `"vs {param}"` (needs both B3 and B5).

- [ ] **Step 3: Write minimal implementation**

In `aose/engine/features.py`, in `feature_modifiers`, substitute `{param}` using `spec.choice_params` keyed by the entity id:

```python
def feature_modifiers(spec: CharacterSpec, data: GameData) -> list[Modifier]:
    eff = effective_abilities(spec, data)
    out: list[Modifier] = []
    for feat, level, _src in iter_reached(spec, data):
        for g in feat.granted_modifiers:
            condition = g.condition
            if condition and "{param}" in condition:
                condition = condition.replace("{param}", spec.choice_params.get(feat.id, ""))
            out.append(Modifier(
                target=g.target, op=g.op,
                value=resolve_value(g, level=level, eff=eff),
                condition=condition, source=feat.name,
            ))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_talent_param_modifier.py -q` (after Task B5)
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/features.py tests/test_talent_param_modifier.py
git commit -m "feat(engine): substitute chosen param into modifier conditions"
```

---

## Task B4: Widen the specialisation gate (Weapon specialist without the proficiency rule)

**Files:**
- Modify: `aose/engine/attacks.py:_profile_for` (lines ~146-158)
- Test: `tests/test_weapon_specialist_talent.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_weapon_specialist_talent.py
from aose.data.loader import GameData
from aose.engine.attacks import attack_profiles
from aose.models import CharacterSpec, ClassEntry, RuleSet

DATA = GameData.load("data")


def _spec(rule_combat=True, rule_prof=False):
    return CharacterSpec(
        name="W", abilities={"STR": 12, "INT": 9, "WIS": 9, "DEX": 12, "CON": 12, "CHA": 9},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1)],
        alignment="neutral",
        ruleset=RuleSet(combat_talents=rule_combat, weapon_proficiency=rule_prof),
        equipped={"main_hand": "sword"},
        inventory=["sword"],
        weapon_specialisations=["sword"],
    )


def _sword(profiles):
    return next(p for p in profiles if p.weapon_id == "sword")


def test_talent_specialisation_applies_plus_one_without_proficiency_rule():
    p = _sword(attack_profiles(_spec(), DATA))
    assert p.specialised is True
    # STR 12 -> +0; spec +1 to hit -> ascending +1, damage +1 over base "1d6".
    assert p.to_hit_ascending == 1
    assert p.damage.endswith("+1")


def test_no_specialisation_when_neither_rule_on():
    spec = _spec(rule_combat=False, rule_prof=False)
    p = _sword(attack_profiles(spec, DATA))
    assert p.specialised is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_specialist_talent.py -q`
Expected: FAIL — `specialised` is False (gate still requires `weapon_proficiency`).

- [ ] **Step 3: Write minimal implementation**

In `aose/engine/attacks.py`, `_profile_for`, replace the block at ~146-158 with:

```python
    # Proficiency penalty applies only under the weapon_proficiency rule.
    # Specialisation (+1/+1) applies under weapon_proficiency OR combat_talents
    # (Weapon specialist is hidden under proficiency, so the two never overlap).
    proficient = True
    prof_pen = 0
    specialised = False
    base_id = base_weapon_id(weapon)   # magic variants count as their base type
    if spec.ruleset.weapon_proficiency or spec.ruleset.combat_talents:
        specialised = is_specialised(base_id, spec)
    if spec.ruleset.weapon_proficiency:
        classes = [data.classes[e.class_id] for e in spec.classes if e.class_id in data.classes]
        proficient = is_proficient(base_id, spec)
        if not proficient:
            prof_pen = penalty_for_classes(classes)
    spec_hit = 1 if specialised else 0
    spec_dmg = 1 if specialised else 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_specialist_talent.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/attacks.py tests/test_weapon_specialist_talent.py
git commit -m "feat(engine): apply weapon specialisation under combat-talents rule"
```

---

## Task B5: Fighter combat-talents data

**Files:**
- Modify: `data/classes/fighter.yaml`
- Test: `tests/test_fighter_talent_data.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fighter_talent_data.py
from aose.data.loader import GameData

DATA = GameData.load("data")


def test_fighter_has_combat_talents_group():
    fighter = DATA.classes["fighter"]
    g = next(g for g in fighter.feature_choices if g.id == "combat_talents")
    assert g.requires_rule == "combat_talents"
    assert g.pick_by_level == {1: 1, 5: 2, 10: 3}
    ids = {o.id for o in g.options}
    assert ids == {"cleave", "defender", "leader", "main_gauche", "slayer", "weapon_specialist"}


def test_slayer_option_has_text_param_and_conditional_modifiers():
    g = next(g for g in DATA.classes["fighter"].feature_choices if g.id == "combat_talents")
    slayer = next(o for o in g.options if o.id == "slayer")
    assert slayer.param.kind == "text"
    conds = {m.condition for m in slayer.granted_modifiers}
    assert conds == {"vs {param}"}
    assert {m.target for m in slayer.granted_modifiers} == {"attack", "damage"}


def test_weapon_specialist_excluded_under_proficiency_rule():
    g = next(g for g in DATA.classes["fighter"].feature_choices if g.id == "combat_talents")
    ws = next(o for o in g.options if o.id == "weapon_specialist")
    assert ws.excluded_when_rule == "weapon_proficiency"
    assert ws.param.kind == "weapon"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_fighter_talent_data.py -q`
Expected: FAIL — fighter has no `combat_talents` group.

- [ ] **Step 3: Write minimal implementation**

Append to `data/classes/fighter.yaml` (top-level key, sibling of `features:`). Note the `source: carcass_crawler_1` on the group is informational only if the model doesn't carry it — omit if `FeatureChoice` has no `source` field.

```yaml
feature_choices:
- id: combat_talents
  name: Combat Talents
  requires_rule: combat_talents
  pick_by_level:
    1: 1
    5: 2
    10: 3
  text: |-
    Carcass Crawler #1 optional rule. Select one combat talent at 1st, 5th, and
    10th level.
  options:
  - id: cleave
    name: Cleave
    text: |-
      When in melee with multiple foes, if you strike a killing blow you may
      immediately make another attack against a second foe at −2.
  - id: defender
    name: Defender
    text: |-
      While you are in melee with a foe, any attacks that foe makes against
      characters other than you are penalised at −2.
  - id: leader
    name: Leader
    text: |-
      Mercenaries or retainers under your command within 60′ gain +1 to
      morale/loyalty. All allies within 60′ gain +1 to saves vs fear.
  - id: main_gauche
    name: Main gauche
    text: |-
      When fighting with a dagger in the off hand (in place of a shield), choose
      each round to gain +1 AC or +1 to attack rolls.
  - id: slayer
    name: Slayer
    text: |-
      +1 to attack and damage rolls against foes of a chosen type (chosen when
      this talent is taken).
    param:
      kind: text
      label: Enemy type
    granted_modifiers:
    - target: attack
      op: add
      value: 1
      condition: "vs {param}"
    - target: damage
      op: add
      value: 1
      condition: "vs {param}"
  - id: weapon_specialist
    name: Weapon specialist
    text: |-
      +1 to attack and damage rolls with a chosen weapon type. Disallowed when
      the optional Weapon Proficiency rule is in use.
    excluded_when_rule: weapon_proficiency
    param:
      kind: weapon
      label: Weapon
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_fighter_talent_data.py -q`
Expected: PASS (3 passed). Now also re-run the B2/B3 data-backed tests:
`.venv\Scripts\python.exe -m pytest tests/test_talent_capacity.py tests/test_talent_param_modifier.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add data/classes/fighter.yaml tests/test_fighter_talent_data.py
git commit -m "feat(data): fighter combat-talents table"
```

---

## Task B6: Register the `combat_talents` optional rule (settings + wizard /rules)

**Files:**
- Modify: `aose/web/settings_routes.py`
- Test: `tests/test_combat_talents_settings.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_combat_talents_settings.py
from aose.web.settings_routes import (
    RULE_LABELS, RULE_DESCRIPTIONS, IMPLEMENTED_RULES, SOURCE_RULES, flatten_rule_fields,
)


def test_combat_talents_registered_and_implemented():
    assert "combat_talents" in RULE_LABELS
    assert "combat_talents" in RULE_DESCRIPTIONS
    assert "combat_talents" in IMPLEMENTED_RULES  # never renders a "pending" badge


def test_combat_talents_attached_to_carcass_crawler_1():
    fields = flatten_rule_fields(SOURCE_RULES["carcass_crawler_1"])
    assert "combat_talents" in fields
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_combat_talents_settings.py -q`
Expected: FAIL — `KeyError: 'carcass_crawler_1'` / missing label.

- [ ] **Step 3: Write minimal implementation**

In `aose/web/settings_routes.py`:
- Add to `RULE_LABELS`: `"combat_talents": "Combat Talents",`
- Add to `IMPLEMENTED_RULES`: `"combat_talents",`
- Add to `RULE_DESCRIPTIONS`:

```python
    "combat_talents":
        "Fighters may select a combat talent at 1st, 5th, and 10th level "
        "(Cleave, Defender, Leader, Main gauche, Slayer, Weapon specialist).",
```

- Add a `carcass_crawler_1` entry to `SOURCE_RULES`:

```python
    "carcass_crawler_1": [
        _rule("combat_talents"),
    ],
```

> Update the comment above `SOURCE_RULES` (currently "Carcass Crawler 1 & 3
> contribute no optional rules") to drop CC1.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_combat_talents_settings.py -q`
Expected: PASS (2 passed). Also re-run any existing "no pending badge" settings regression test to confirm it stays green.

- [ ] **Step 5: Commit**

```bash
git add aose/web/settings_routes.py tests/test_combat_talents_settings.py
git commit -m "feat(settings): register Combat Talents optional rule (CC1)"
```

---

## Task B7: Wizard — cascading clear + L1 talent pick with params

**Files:**
- Modify: `aose/web/wizard.py` (`_apply_rule_changes`, `_active_choice_groups`, `_feature_choices_context`, `_apply_feature_overrides`)
- Modify: `aose/web/templates/wizard/class_setup.html`
- Test: `tests/test_wizard_combat_talents.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wizard_combat_talents.py
from aose.data.loader import GameData
from aose.web.wizard import (
    _active_choice_groups, _feature_choices_context, _apply_feature_overrides,
    _apply_rule_changes,
)
from aose.models import RuleSet

DATA = GameData.load("data")


def _draft(combat=True, prof=False):
    return {
        "ruleset": RuleSet(combat_talents=combat, weapon_proficiency=prof).model_dump(),
        "class_ids": ["fighter"],
        "abilities": {"STR": 12, "INT": 9, "WIS": 9, "DEX": 12, "CON": 12, "CHA": 9},
        "feature_choices": {},
        "choice_params": {},
        "weapon_specialisations": [],
    }


def test_talent_group_hidden_when_rule_off():
    assert all(g.id != "combat_talents"
               for g in _active_choice_groups(_draft(combat=False), DATA))


def test_talent_group_shown_pick_one_at_creation():
    ctx = _feature_choices_context(_draft(), DATA)
    row = next(r for r in ctx["feature_groups"] if r["id"] == "combat_talents")
    assert row["pick"] == 1  # pick_by_level[1]


def test_weapon_specialist_option_hidden_under_proficiency():
    ctx = _feature_choices_context(_draft(prof=True), DATA)
    row = next(r for r in ctx["feature_groups"] if r["id"] == "combat_talents")
    assert all(o["id"] != "weapon_specialist" for o in row["options"])


def test_apply_slayer_pick_records_param():
    from starlette.datastructures import FormData
    draft = _draft()
    form = FormData([("choice_combat_talents", "slayer"), ("param_slayer", "undead")])
    _apply_feature_overrides(draft, form, DATA)
    assert draft["feature_choices"]["combat_talents"] == ["slayer"]
    assert draft["choice_params"]["slayer"] == "undead"


def test_toggling_combat_talents_off_clears_talent_state():
    draft = _draft()
    draft["feature_choices"]["combat_talents"] = ["weapon_specialist"]
    draft["choice_params"] = {}
    draft["weapon_specialisations"] = ["sword"]
    old = RuleSet(combat_talents=True)
    new = RuleSet(combat_talents=False)
    _apply_rule_changes(draft, old, new, DATA)
    assert "combat_talents" not in draft.get("feature_choices", {})
    assert draft.get("weapon_specialisations", []) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_combat_talents.py -q`
Expected: FAIL — group not filtered by rule / pick not banded / params not read / no clear.

- [ ] **Step 3: Write minimal implementation**

In `aose/web/wizard.py`:

**3a.** Filter groups by `requires_rule` in `_active_choice_groups` (single chokepoint — `_has_feature_choices`, completion, and the context all flow through it). After collecting `groups`, before returning:

```python
    rs = _ruleset_of(draft)
    groups = [g for g in groups
              if not g.requires_rule or getattr(rs, g.requires_rule, False)]
    return groups
```

**3b.** In `_feature_choices_context`, resolve the per-row pick via `effective_pick` (creation is always level 1) and drop options excluded by an active rule:

```python
    from aose.engine.feature_choices import effective_pick
    rs = _ruleset_of(draft)
    ...
    for g in groups:
        chosen = set(chosen_map.get(g.id, []))
        pick = effective_pick(g, 1)
        rows.append({
            "id": g.id, "name": g.name, "text": g.text, "pick": pick,
            "cosmetic": g.cosmetic, "roll_dice": g.roll_dice,
            "rolled": g.id in chosen_map,
            "options": [
                {"id": o.id, "name": o.name, "text": o.text,
                 "selected": o.id in chosen,
                 "param": (o.param.model_dump() if o.param else None)}
                for o in g.options
                if not (o.excluded_when_rule and getattr(rs, o.excluded_when_rule, False))
            ],
        })
```

**3c.** In `_apply_feature_overrides`, pass the banded pick to `validate_choice`, read `param_<option_id>` fields, and route weapon params into `weapon_specialisations`:

```python
    from aose.engine.feature_choices import effective_pick
    groups = {g.id: g for g in _active_choice_groups(draft, data)}
    chosen_map = dict(draft.get("feature_choices", {}))
    params = dict(draft.get("choice_params", {}))
    specials = list(draft.get("weapon_specialisations", []))
    for gid, g in groups.items():
        field = form.getlist(f"choice_{gid}")
        if not field:
            continue
        picked = list(dict.fromkeys(field))
        try:
            validate_choice(g, picked, pick=effective_pick(g, 1))
        except ChoiceError as e:
            raise HTTPException(400, str(e))
        chosen_map[gid] = picked
        for opt in g.options:
            if opt.id not in picked or opt.param is None:
                continue
            raw = (form.get(f"param_{opt.id}") or "").strip()
            if not raw:
                raise HTTPException(400, f"{opt.name}: choose {opt.param.label}.")
            if opt.param.kind == "weapon":
                if raw not in specials:
                    specials.append(raw)
            else:
                params[opt.id] = raw
    draft["feature_choices"] = chosen_map
    draft["choice_params"] = params
    draft["weapon_specialisations"] = specials
```

**3d.** Add a cascading clear in `_apply_rule_changes` (alongside the other rule-change clears, after the `weapon_proficiency` block):

```python
    if old_rs.combat_talents and not new_rs.combat_talents:
        fc = dict(draft.get("feature_choices", {}))
        removed = fc.pop("combat_talents", [])
        draft["feature_choices"] = fc
        # Drop talent-granted specialisation(s) and Slayer params.
        if "weapon_specialist" in removed:
            draft["weapon_specialisations"] = []
        draft["choice_params"] = {k: v for k, v in draft.get("choice_params", {}).items()
                                  if k not in removed}
```

> The wizard draft seeds the talent into `feature_choices` at the `class_setup`
> step; this clear runs when the player flips the rule off at `/rules`.

In `aose/web/templates/wizard/class_setup.html`, find the feature-choices options loop and add a param input shown when an option is selected and has a `param`. Mirror the existing option markup; for `kind == "weapon"` render a select of the class's allowed base weapons (the template already has access to the proficiency weapon list pattern — if not, expose `feature_weapon_options` from `_feature_choices_context` the same way Task A3 exposes `proficiency_weapon_options`). Example:

```html
{% if opt.param %}
  {% if opt.param.kind == "weapon" %}
  <select name="param_{{ opt.id }}">
    {% for w in feature_weapon_options %}<option value="{{ w.id }}">{{ w.name }}</option>{% endfor %}
  </select>
  {% else %}
  <input type="text" name="param_{{ opt.id }}" placeholder="{{ opt.param.label }}">
  {% endif %}
{% endif %}
```

> Add `feature_weapon_options` (base weapons allowed to the drafted class) to the
> dict returned by `_feature_choices_context`, reusing the Task A3 weapon-option
> builder so the wizard and sheet share one list source.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_combat_talents.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Smoke test**

Run the app, create a fighter with Combat Talents on: confirm the talent table appears at the HP & Skills step, picking Slayer prompts for an enemy type, picking Weapon specialist offers a weapon dropdown, and Weapon specialist vanishes when Weapon Proficiency is also on.

- [ ] **Step 6: Commit**

```bash
git add aose/web/wizard.py aose/web/templates/wizard/class_setup.html tests/test_wizard_combat_talents.py
git commit -m "feat(wizard): combat-talents L1 pick, params, and cascading clear"
```

---

## Task B8: Talent picker on the sheet (level-up + inline) + descriptive talents

**Files:**
- Modify: `aose/web/routes.py` (`POST /character/{id}/talent/add`)
- Modify: `aose/web/templates/_levelup_choices.html` (talent arm)
- Modify: `aose/sheet/view.py` (expose talent option options per group)
- Test: `tests/test_talent_levelup.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_talent_levelup.py
import pytest
from fastapi.testclient import TestClient

from aose.web.app import create_app
from aose.models import CharacterSpec, ClassEntry, RuleSet


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AOSE_DATA_DIR", "data")
    app = create_app(characters_dir=tmp_path / "chars", drafts_dir=tmp_path / "drafts",
                     settings_path=tmp_path / "settings.json")
    return TestClient(app)


def _save(client, level=5, picked=("cleave",)):
    from aose.characters.storage import save_character
    spec = CharacterSpec(
        name="Tal", abilities={"STR": 13, "INT": 9, "WIS": 9, "DEX": 12, "CON": 12, "CHA": 9},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=level)],
        alignment="neutral", ruleset=RuleSet(combat_talents=True),
        feature_choices={"combat_talents": list(picked)},
    )
    return save_character(spec, client.app.state.characters_dir)


def test_add_second_talent_at_level5(client):
    cid = _save(client, level=5, picked=["cleave"])  # earned 2, spent 1
    r = client.post(f"/character/{cid}/talent/add",
                    data={"group_id": "combat_talents", "option_id": "defender"},
                    follow_redirects=False)
    assert r.status_code == 303
    from aose.characters.storage import load_character
    spec = load_character(cid, client.app.state.characters_dir)
    assert spec.feature_choices["combat_talents"] == ["cleave", "defender"]


def test_slayer_requires_param(client):
    cid = _save(client, level=5, picked=["cleave"])
    r = client.post(f"/character/{cid}/talent/add",
                    data={"group_id": "combat_talents", "option_id": "slayer"},
                    follow_redirects=False)
    assert r.status_code == 400  # missing enemy type


def test_cannot_exceed_earned_talents(client):
    cid = _save(client, level=4, picked=["cleave"])  # earned 1, spent 1
    r = client.post(f"/character/{cid}/talent/add",
                    data={"group_id": "combat_talents", "option_id": "defender"},
                    follow_redirects=False)
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_talent_levelup.py -q`
Expected: FAIL — 404 (route missing).

- [ ] **Step 3: Write minimal implementation**

Add to `aose/web/routes.py`:

```python
from aose.engine.level_choices import talent_capacities


@router.post("/character/{character_id}/talent/add")
async def add_talent(request: Request, character_id: str,
                     group_id: str = Form(...), option_id: str = Form(...),
                     param: str = Form("")):
    data = request.app.state.game_data
    spec = _load_character(request, character_id)
    caps = {c.group_id: c for c in talent_capacities(spec, data)}
    cap = caps.get(group_id)
    if cap is None or cap.remaining <= 0:
        raise HTTPException(400, "No talent selections remaining.")
    group = next((g for e in spec.classes if (cls := data.classes.get(e.class_id))
                  for g in cls.feature_choices if g.id == group_id), None)
    if group is None:
        raise HTTPException(400, "Unknown talent group.")
    opt = next((o for o in group.options if o.id == option_id), None)
    if opt is None:
        raise HTTPException(400, "Unknown talent.")
    if opt.excluded_when_rule and getattr(spec.ruleset, opt.excluded_when_rule, False):
        raise HTTPException(400, "That talent is unavailable under the current rules.")
    chosen = list(spec.feature_choices.get(group_id, []))
    if option_id in chosen:
        raise HTTPException(400, "Talent already taken.")
    raw = (param or "").strip()
    if opt.param is not None and not raw:
        raise HTTPException(400, f"{opt.name}: choose {opt.param.label}.")
    chosen.append(option_id)
    spec.feature_choices[group_id] = chosen
    if opt.param is not None:
        if opt.param.kind == "weapon":
            if raw not in spec.weapon_specialisations:
                spec.weapon_specialisations.append(raw)
        else:
            spec.choice_params[option_id] = raw
    _save_character(request, character_id, spec)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

> Use the same `_load_character`/`_save_character` calls as Task A2.

Extend `aose/sheet/view.py` to expose per-group talent options for the picker.
Add a sheet field `talent_options: dict = Field(default_factory=list)` and build,
for each talent capacity, the selectable (not-yet-chosen, not-excluded) options
plus their `param` descriptor:

```python
    _talent_opts = {}
    for c in _caps:
        if c.kind != "talent":
            continue
        grp = next((g for e in spec.classes if (cl := data.classes.get(e.class_id))
                    for g in cl.feature_choices if g.id == c.group_id), None)
        if grp is None:
            continue
        already = set(spec.feature_choices.get(c.group_id, []))
        _talent_opts[c.group_id] = [
            {"id": o.id, "name": o.name,
             "param": (o.param.model_dump() if o.param else None)}
            for o in grp.options
            if o.id not in already
            and not (o.excluded_when_rule and getattr(spec.ruleset, o.excluded_when_rule, False))
        ]
```

Pass `talent_options=_talent_opts` into `CharacterSheet(...)`.

Add the talent arm to `aose/web/templates/_levelup_choices.html`:

```html
  {% if cap.kind == "talent" %}
  <div class="capacity-picker" data-kind="talent">
    <div class="subhead">New Combat Talent ({{ cap.remaining }} to choose)</div>
    <form method="post" action="/character/{{ character_id }}/talent/add" class="inline-form">
      <input type="hidden" name="group_id" value="{{ cap.group_id }}">
      <select name="option_id" required>
        {% for o in sheet.talent_options.get(cap.group_id, []) %}
        <option value="{{ o.id }}"{% if o.param %} data-param="{{ o.param.kind }}"{% endif %}>{{ o.name }}</option>
        {% endfor %}
      </select>
      {# Param field: text for Slayer, weapon dropdown for Weapon specialist.
         Always-visible text input keeps it simple (the weapon path accepts a
         base-weapon id; show the dropdown when any option needs a weapon). #}
      <input type="text" name="param" placeholder="Enemy type (Slayer) / weapon id (Specialist)">
      <button class="btn solid" type="submit">Add</button>
    </form>
  </div>
  {% endif %}
```

> The single text `param` field keeps Task B8 small and matches the endpoint.
> Optional polish (own step/PR): swap to a weapon `<select>` driven by
> `sheet.proficiency_weapon_options` when the focused option's `data-param` is
> `weapon`, via the existing sheet JS pattern.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_talent_levelup.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Smoke test**

Run the app: take a fighter created with Combat Talents, grant XP, level to 5 → confirm a "New Combat Talent" picker appears on the sheet; add Slayer with an enemy type and verify the conditional `+1 vs <type>` line shows in the Attack modal; add Weapon specialist with a weapon id and verify the matching attack row shows the `spec` tag and +1/+1.

- [ ] **Step 6: Commit**

```bash
git add aose/web/routes.py aose/web/templates/_levelup_choices.html aose/sheet/view.py tests/test_talent_levelup.py
git commit -m "feat(web): pick combat talents on level-up (sheet + modal)"
```

---

## Task B9: Docs

**Files:**
- Modify: `docs/CHANGELOG.md`, `docs/ARCHITECTURE.md`

- [ ] **Step 1: CHANGELOG row**

Add a one-line row to the top of `docs/CHANGELOG.md`:

```
| 2026-06-12 | Combat Talents (CC1) + level-up choice mechanism | feat/combat-talents | combat-talents |
```

> Match the existing column layout in that file.

- [ ] **Step 2: ARCHITECTURE update**

In `docs/ARCHITECTURE.md`, update the feature/choice subsystem section (and the proficiency section) in place to describe: the `level_choices.py` unspent-capacity model, the two providers (proficiencies, talents), `pick_by_level` banding, `requires_rule`/`excluded_when_rule` gating, `choice_params` param substitution, and the widened specialisation gate. Edit existing topics — do not append a dated entry.

- [ ] **Step 3: Full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all green (ignore the pytest-current PermissionError).

- [ ] **Step 4: Commit**

```bash
git add docs/CHANGELOG.md docs/ARCHITECTURE.md
git commit -m "docs: combat talents + level-up choice mechanism"
```

---

## Self-review notes (for the implementer)

- **Slayer damage display:** the conditional `+1 damage vs <type>` is carried as a
  modifier but does NOT get a headline number (only `attack` situational lines are
  surfaced by `attack_modifiers_detail`). This is intended per spec — the talent's
  descriptive text covers it. Do not add a conditional-damage breakdown here.
- **Weapon specialist storage:** under combat talents the chosen weapon lands in
  `weapon_specialisations` WITHOUT a matching `weapon_proficiencies` entry; that is
  correct (no proficiency system active). The read-only Weapon Proficiencies block
  stays hidden (renders only under `weapon_proficiency`); the +1/+1 shows on the
  attack row's `spec` tag.
- **Mutual exclusion:** Weapon specialist is hidden whenever `weapon_proficiency`
  is on, so `weapon_specialisations` is only ever populated by one subsystem at a
  time — no double-counting in `attacks.py`.
- **Single chokepoint:** all group visibility flows through
  `_active_choice_groups` (rule filtering) and `effective_pick` (count) — keep new
  call sites going through them.
- **Descriptive talents need no new rendering task:** `_class_features`
  (`aose/sheet/view.py:665-667`) already lists chosen options via
  `selected_options(...)` (gated by `_feature_visible`). Cleave/Defender/Leader/
  Main gauche surface under "Class: Fighter" automatically once chosen; Slayer and
  Weapon specialist show their text there too, alongside their mechanical effect.
  Verify in the Task B8 smoke test.
```
