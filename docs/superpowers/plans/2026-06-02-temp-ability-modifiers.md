# Temporary Ability-Score Modifiers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the player set one signed temporary modifier per ability on the live character sheet; it stacks with magic-item modifiers, clamps the final effective score to [3, 18], never touches the real score, and shows a per-ability breakdown of what composes the final score.

**Architecture:** A new `temp_ability_modifiers: dict[Ability, int]` field on `CharacterSpec` stores the modifiers (non-zero only). `effective_abilities()` in the cycle-free `magic.py` becomes the single clamp point, folding temp deltas in after magic modifiers so all derivations (HP, attacks, AC) pick them up automatically. The sheet view exposes a breakdown on `AbilityRow`; a new POST route + an input/Set control per ability row in `sheet.html` drive it.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, pytest. Run tests with `.venv\Scripts\python.exe -m pytest`.

---

### Task 1: Add the `temp_ability_modifiers` field to `CharacterSpec`

**Files:**
- Modify: `aose/models/character.py` (the `CharacterSpec` class, near the other play-state fields)
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_models.py`:

```python
def test_character_spec_temp_ability_modifiers_default_empty():
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="T",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="law",
    )
    assert spec.temp_ability_modifiers == {}


def test_character_spec_temp_ability_modifiers_keyed_by_ability_enum():
    from aose.models import Ability, CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="T",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="law",
        temp_ability_modifiers={"STR": -2},
    )
    assert spec.temp_ability_modifiers[Ability.STR] == -2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models.py -k temp_ability_modifiers -v`
Expected: FAIL — `temp_ability_modifiers` is rejected by `extra="forbid"` / `AttributeError`.

- [ ] **Step 3: Add the field**

In `aose/models/character.py`, inside `class CharacterSpec`, add the field right after `damage_taken` (it is play-state, like `damage_taken`):

```python
    # Play-state: temporary per-ability score adjustments set on the live sheet.
    # Signed deltas keyed by Ability; only non-zero entries are stored. They
    # stack with magic-item ability modifiers and clamp the final effective
    # score to [3, 18] (see aose/engine/magic.py). The real `abilities` are
    # never altered.
    temp_ability_modifiers: dict[Ability, int] = Field(default_factory=dict)
```

`Ability` and `Field` are already imported in this module.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models.py -k temp_ability_modifiers -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/models/character.py tests/test_models.py
git commit -m "feat: add temp_ability_modifiers field to CharacterSpec"
```

---

### Task 2: Fold temp modifiers + clamping into `effective_abilities`, add setter helper

**Files:**
- Modify: `aose/engine/magic.py` (`effective_abilities`, plus a new `set_temp_ability_modifier`)
- Test: `tests/test_magic_items.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_magic_items.py` (the module already has `_fake_magic_data`, `_minimal_spec`, and imports `Ability`/`MagicItemInstance` inside tests):

```python
def test_effective_abilities_temp_stacks_with_magic_set():
    from aose.engine.magic import effective_abilities
    from aose.models import Ability, MagicItemInstance
    fake = _fake_magic_data()
    spec = _minimal_spec(
        abilities={"STR": 9, "INT": 12, "WIS": 11, "DEX": 13, "CON": 12, "CHA": 10},
        magic_items=[MagicItemInstance(instance_id="i", catalog_id="gauntlets", equipped=True)],
        temp_ability_modifiers={"STR": -2},   # 18 (set) - 2 = 16
    )
    assert effective_abilities(spec, fake)[Ability.STR] == 16


def test_effective_abilities_temp_clamps_high():
    from aose.engine.magic import effective_abilities
    from aose.models import Ability
    fake = _fake_magic_data()
    spec = _minimal_spec(
        abilities={"STR": 17, "INT": 12, "WIS": 11, "DEX": 13, "CON": 12, "CHA": 10},
        temp_ability_modifiers={"STR": 5},    # 22 -> clamp 18
    )
    assert effective_abilities(spec, fake)[Ability.STR] == 18


def test_effective_abilities_temp_clamps_low():
    from aose.engine.magic import effective_abilities
    from aose.models import Ability
    fake = _fake_magic_data()
    spec = _minimal_spec(
        abilities={"STR": 6, "INT": 12, "WIS": 11, "DEX": 13, "CON": 12, "CHA": 10},
        temp_ability_modifiers={"STR": -10},  # -4 -> clamp 3
    )
    assert effective_abilities(spec, fake)[Ability.STR] == 3


def test_set_temp_ability_modifier_sets_and_replaces():
    from aose.engine.magic import set_temp_ability_modifier
    from aose.models import Ability
    temp = set_temp_ability_modifier({}, Ability.STR, -2)
    assert temp == {Ability.STR: -2}
    temp = set_temp_ability_modifier(temp, Ability.STR, 3)   # replaces, not stacks
    assert temp == {Ability.STR: 3}


def test_set_temp_ability_modifier_zero_clears_key():
    from aose.engine.magic import set_temp_ability_modifier
    from aose.models import Ability
    temp = set_temp_ability_modifier({Ability.STR: -2, Ability.DEX: 1}, Ability.STR, 0)
    assert temp == {Ability.DEX: 1}


def test_set_temp_ability_modifier_does_not_mutate_input():
    from aose.engine.magic import set_temp_ability_modifier
    from aose.models import Ability
    original = {Ability.STR: -2}
    set_temp_ability_modifier(original, Ability.DEX, 1)
    assert original == {Ability.STR: -2}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "temp_ability or set_temp_ability" -v`
Expected: FAIL — `set_temp_ability_modifier` not defined; `effective_abilities` ignores `temp_ability_modifiers`.

- [ ] **Step 3: Rewrite `effective_abilities` and add the setter**

In `aose/engine/magic.py`, replace the whole `effective_abilities` function:

```python
def effective_abilities(spec: CharacterSpec, data: GameData) -> dict[Ability, int]:
    """``spec.abilities`` with magic ``ability:*`` modifiers and temporary
    per-ability modifiers applied, then clamped to [3, 18].

    Order per ability: base -> magic modifiers (unclamped, as authored in
    seed data) -> + temp delta -> clamp(3, 18).  Clamping applies to every
    ability so an effective score can never sit outside the legal range.
    """
    mods = active_modifiers(spec, data)
    temp = spec.temp_ability_modifiers
    scores: dict[Ability, int] = {}
    for ab in Ability:
        base = spec.abilities[ab]
        target = f"ability:{ab.value}"
        val = apply_modifiers(base, mods, target) if any(m.target == target for m in mods) else base
        val += temp.get(ab, 0)
        scores[ab] = max(3, min(18, val))
    return scores
```

Then add this helper directly below `effective_abilities`:

```python
def set_temp_ability_modifier(temp: dict[Ability, int], ability: Ability,
                              value: int) -> dict[Ability, int]:
    """Return a new temp-modifier dict with ``ability`` set to ``value``.

    A single modifier per ability (replaces any prior).  ``value == 0`` removes
    the key so only meaningful modifiers are stored.  Does not mutate ``temp``.
    """
    updated = {k: v for k, v in temp.items() if k != ability}
    if value != 0:
        updated[ability] = value
    return updated
```

- [ ] **Step 4: Run the new tests, then the full magic suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -v`
Expected: PASS — the new tests plus the existing `effective_abilities` tests (e.g. `test_effective_abilities_applies_set_and_leaves_rest`, `test_effective_abilities_base_when_unequipped`) still pass; base 9/13 stay in range so clamping is a no-op there.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/magic.py tests/test_magic_items.py
git commit -m "feat: fold temp ability modifiers + [3,18] clamp into effective_abilities"
```

---

### Task 3: Expose the breakdown on `AbilityRow` in the sheet view

**Files:**
- Modify: `aose/sheet/view.py` (`class AbilityRow`, and the abilities loop in `build_sheet`)
- Test: `tests/test_sheet.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_sheet.py` (uses the existing `make_spec` / `data` fixtures):

```python
def test_ability_row_breakdown_temp_only(data):
    spec = make_spec(temp_ability_modifiers={"STR": -3})  # base STR 16 -> 13
    sheet = build_sheet(spec, data)
    row = next(r for r in sheet.abilities if r.ability == "STR")
    assert row.base_score == 16
    assert row.equip_delta == 0
    assert row.temp_delta == -3
    assert row.score == 13
    assert row.modified is True


def test_ability_row_breakdown_unmodified(data):
    sheet = build_sheet(make_spec(), data)
    row = next(r for r in sheet.abilities if r.ability == "INT")
    assert row.base_score == 10
    assert row.equip_delta == 0
    assert row.temp_delta == 0
    assert row.modified is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet.py -k ability_row_breakdown -v`
Expected: FAIL — `AbilityRow` has no `base_score` / `equip_delta` / `temp_delta`.

- [ ] **Step 3: Add the fields and populate them**

In `aose/sheet/view.py`, extend `AbilityRow`:

```python
class AbilityRow(BaseModel):
    ability: str
    score: int            # final effective score (clamped)
    modifier: int
    base_score: int = 0   # real underlying score
    equip_delta: int = 0  # magic-effective minus base (works for add & set ops)
    temp_delta: int = 0   # temporary modifier (signed)
    modified: bool = False
```

Update the import line that brings in `effective_abilities` to also pull the two helpers (change `from aose.engine.magic import effective_abilities` to):

```python
from aose.engine.magic import active_modifiers, apply_modifiers, effective_abilities
```

Then replace the `abilities = [...]` comprehension in `build_sheet` with:

```python
    eff = effective_abilities(spec, data)
    mods = active_modifiers(spec, data)
    abilities = []
    for ab in ABILITY_ORDER:
        base = spec.abilities[ab]
        target = f"ability:{ab.value}"
        after_equip = (
            apply_modifiers(base, mods, target)
            if any(m.target == target for m in mods)
            else base
        )
        final = eff[ab]
        abilities.append(AbilityRow(
            ability=ab.value,
            score=final,
            modifier=ability_mods.ability_modifier(final),
            base_score=base,
            equip_delta=after_equip - base,
            temp_delta=spec.temp_ability_modifiers.get(ab, 0),
            modified=(final != base),
        ))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet.py -v`
Expected: PASS — new breakdown tests plus existing `test_build_sheet_abilities` (STR score 16, modifier 2) still pass.

- [ ] **Step 5: Commit**

```bash
git add aose/sheet/view.py tests/test_sheet.py
git commit -m "feat: expose ability score breakdown (base/equip/temp) on AbilityRow"
```

---

### Task 4: Add the `temp-modifier` POST route

**Files:**
- Modify: `aose/web/routes.py` (import the helper; add the route near the HP routes)
- Test: `tests/test_rest_routes.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_rest_routes.py` (it already has the `client` fixture, `_save_fighter`, and imports `load_character`):

```python
def test_temp_ability_modifier_route_sets(client):
    _save_fighter(client)
    r = client.post("/character/bran/abilities/temp-modifier",
                    data={"ability": "STR", "value": -2})
    assert r.status_code == 303
    from aose.models import Ability
    spec = load_character("bran", client._characters_dir)
    assert spec.temp_ability_modifiers[Ability.STR] == -2


def test_temp_ability_modifier_route_zero_clears(client):
    from aose.models import CharacterSpec, ClassEntry
    from aose.characters import save_character
    spec = CharacterSpec(
        name="Bran",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[12])],
        alignment="neutral",
        temp_ability_modifiers={"STR": -2},
    )
    save_character("bran", spec, client._characters_dir)
    client.post("/character/bran/abilities/temp-modifier",
                data={"ability": "STR", "value": 0})
    reloaded = load_character("bran", client._characters_dir)
    assert reloaded.temp_ability_modifiers == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rest_routes.py -k temp_ability_modifier -v`
Expected: FAIL — route returns 404 (not yet defined).

- [ ] **Step 3: Import the helper and add the route**

In `aose/web/routes.py`, add `set_temp_ability_modifier as _set_temp_ability_modifier` to the existing `from aose.engine.magic import (...)` block (keep it alphabetical-ish alongside `set_magic_note`):

```python
    set_magic_note as _set_magic_note,
    set_temp_ability_modifier as _set_temp_ability_modifier,
```

Add the route immediately after the `hp_set` route (around line 244):

```python
@router.post("/character/{character_id}/abilities/temp-modifier")
async def abilities_temp_modifier(request: Request, character_id: str,
                                  ability: str = Form(...), value: int = Form(...)):
    """Set (or clear, when value is 0) a temporary modifier on one ability.
    Replaces any prior modifier for that ability; never touches the real score."""
    from aose.models import Ability
    spec = _load_spec_or_404(request, character_id)
    try:
        ab = Ability(ability)
    except ValueError:
        raise HTTPException(400, f"Unknown ability {ability!r}")
    spec.temp_ability_modifiers = _set_temp_ability_modifier(
        spec.temp_ability_modifiers, ab, value,
    )
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rest_routes.py -k temp_ability_modifier -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_rest_routes.py
git commit -m "feat: add temp ability-modifier sheet route"
```

---

### Task 5: Add the input control + breakdown footnote to `sheet.html`

**Files:**
- Modify: `aose/web/templates/sheet.html` (the Abilities section, lines ~22-41)

This task is template-only; verify it via the existing route test from Task 4 (which renders nothing) plus a manual smoke run. There is no unit test for raw HTML in this project, so the verification step is the full suite + a manual render check.

- [ ] **Step 1: Replace the Abilities section markup**

In `aose/web/templates/sheet.html`, replace the entire `<section class="section">` block for Abilities (the one containing `<table class="abilities">`) with:

```html
            <section class="section">
                <h2>Abilities</h2>
                <table class="abilities">
                    <thead>
                        <tr><th>Ability</th><th>Score</th><th>Mod</th><th>Temp</th></tr>
                    </thead>
                    <tbody>
                    {% for ab in sheet.abilities %}
                        <tr>
                            <td>{{ ab.ability }}</td>
                            <td class="num">{{ ab.score }}{% if ab.modified %}<span class="ability-modified" title="Modified — see breakdown below">*</span>{% endif %}</td>
                            <td class="num">{{ "%+d"|format(ab.modifier) }}</td>
                            <td>
                                <form method="post" action="/character/{{ character_id }}/abilities/temp-modifier" class="temp-mod-form">
                                    <input type="hidden" name="ability" value="{{ ab.ability }}">
                                    <input type="number" name="value" value="{{ ab.temp_delta }}" step="1" class="temp-mod-input" aria-label="Temporary {{ ab.ability }} modifier">
                                    <button type="submit">Set</button>
                                </form>
                            </td>
                        </tr>
                    {% endfor %}
                    </tbody>
                </table>
                {% set modified_rows = sheet.abilities | selectattr("modified") | list %}
                {% if modified_rows %}
                <ul class="small muted ability-breakdown">
                    {% for ab in modified_rows %}
                    <li>{{ ab.ability }}: base {{ ab.base_score }}{% if ab.equip_delta %}, equipment {{ "%+d"|format(ab.equip_delta) }}{% endif %}{% if ab.temp_delta %}, temporary {{ "%+d"|format(ab.temp_delta) }}{% endif %} &rarr; {{ ab.score }}</li>
                    {% endfor %}
                </ul>
                {% endif %}
            </section>
```

Note: only non-zero adjustments render — `{% if ab.equip_delta %}` / `{% if ab.temp_delta %}` skip zero deltas. Base and final (`&rarr; score`) always show. `"%+d"` renders the sign.

- [ ] **Step 2: Run the full test suite (no regressions)**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all tests pass (ignore the known trailing `PermissionError` on `pytest-current` per CLAUDE.md).

- [ ] **Step 3: Manual smoke render**

Start the app:
`.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
Open a character sheet, set STR temp to `-2`, press Set. Confirm: STR score drops by 2 (clamped to ≥3), a `*` appears, and the footnote reads e.g. `STR: base 16, temporary -2 → 14`. Set it back to `0` and confirm the modifier and footnote line disappear. Confirm a magic-item-modified ability shows an `equipment` term and stacks correctly.

- [ ] **Step 4: Commit**

```bash
git add aose/web/templates/sheet.html
git commit -m "feat: temp ability-modifier input + score breakdown on the sheet"
```

---

## Self-Review Notes

- **Spec coverage:** data model (Task 1), engine stack+clamp+setter (Task 2), breakdown fields (Task 3), route (Task 4), UI control + non-zero-only footnote (Task 5). All spec sections covered.
- **Clamp-all behaviour:** verified the only seed ability modifier is Girdle `set STR=18` (in range), so existing `effective_abilities` tests stay green.
- **Type consistency:** `set_temp_ability_modifier(temp, ability, value)` signature is identical across Task 2 (definition), Task 4 (call). `AbilityRow` fields `base_score`/`equip_delta`/`temp_delta` consistent across Tasks 3 and 5. `temp_ability_modifiers` keyed by `Ability` enum throughout.
- **Derivation propagation:** because HP/attacks/AC already call `effective_abilities`, no per-derivation edits are needed; this is intentional and matches existing magic-item behaviour.
```
