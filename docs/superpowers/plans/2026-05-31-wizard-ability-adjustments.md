# Wizard Slice 4 — Ability Score Adjustments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new always-shown wizard step that lets a player trade 2 points down from eligible abilities for 1 point up on a prime requisite (post-racial, capped at 18, floored at `max(9, class requirement)`), persisting the result into the character's creation-final ability scores.

**Architecture:** A typed `non_reducible_abilities` field on `CharClass` (forbid-only restriction layer) feeds three pure helpers in `aose/engine/ability_mods.py` (`adjustable_abilities`, `validate_ability_adjustments`, `apply_ability_adjustments`). The wizard splits its existing `_effective_abilities` helper into `_post_racial_abilities` (pre-adjustment, used by class gating) and `_creation_abilities` (post-adjustment, used by HP/finalize), and inserts an `adjust` step between `class` and `alignment`. Server-side validation is the source of truth; the template is a plain no-JS allocation form.

**Tech Stack:** Python 3, FastAPI, Pydantic v2, Jinja2, pytest. Run tests with `.venv\Scripts\python.exe -m pytest`.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `aose/models/character_class.py` | `CharClass` Pydantic model | Modify — add `non_reducible_abilities` field |
| `data/classes/acrobat.yaml`, `assassin.yaml`, `thief.yaml` | Class seed data | Modify — add `non_reducible_abilities: [STR]` |
| `aose/engine/ability_mods.py` | Pure ability math | Modify — add `AdjustmentError` + 3 helpers |
| `aose/web/wizard.py` | Wizard routes + draft helpers | Modify — rename helper, add `_creation_abilities`, add `adjust` step + routes + clears |
| `aose/web/templates/wizard/adjust.html` | Adjust-step partial | Create |
| `tests/test_wizard_ability_adjust.py` | All Slice-4 tests | Create |

Notes for the implementer (read once):
- Ability values are the plain strings `"STR" "INT" "WIS" "DEX" "CON" "CHA"` (`aose/models/ability.py`, a `str` Enum). `CharClass.prime_requisites` and `CharClass.ability_requirements` keys are `Ability` enum members; use `.value` to get the string and `Ability("STR")` to go the other way.
- `cls.ability_requirements` is `dict[Ability, int]`, defaulting empty. In the current dataset acrobat/assassin/thief/fighter/magic_user all have **no** ability requirements, so the lower floor reduces to `9`.
- The wizard stores draft state as a plain `dict` persisted via `save_draft`. A step is "complete" when its marker key is present.
- Run the **whole** suite (`.venv\Scripts\python.exe -m pytest tests/ -q`) after the refactor task — it is the regression guard for the rename. Ignore the trailing `pytest-current` PermissionError (known Windows quirk).

---

## Task 1: `non_reducible_abilities` field + class data

**Files:**
- Modify: `aose/models/character_class.py:32-51`
- Modify: `data/classes/acrobat.yaml`, `data/classes/assassin.yaml`, `data/classes/thief.yaml`
- Test: `tests/test_wizard_ability_adjust.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_wizard_ability_adjust.py` with this header and first test:

```python
"""Slice 4 (Ability Adjustments): typed restriction field, engine helpers,
and wizard wiring."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_draft, save_draft, save_settings
from aose.data.loader import GameData
from aose.models import Ability, RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


# ── Task 1: typed restriction field ───────────────────────────────────────

def test_restricted_classes_forbid_lowering_str(data):
    for cid in ("acrobat", "assassin", "thief"):
        assert data.classes[cid].non_reducible_abilities == [Ability.STR]


def test_other_classes_have_no_restriction(data):
    assert data.classes["fighter"].non_reducible_abilities == []
    assert data.classes["magic_user"].non_reducible_abilities == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_ability_adjust.py -q`
Expected: FAIL — either `pydantic` rejects the unknown YAML key (`extra="forbid"`) on load, or `non_reducible_abilities` attribute does not exist.

- [ ] **Step 3: Add the model field**

In `aose/models/character_class.py`, inside `CharClass` (after `race_locked`, around line 51), add:

```python
    # Abilities this class forbids *lowering* during the ability-adjustment
    # step, layered on top of the {STR,INT,WIS} base set (forbid-only). Empty
    # = no extra restriction. Today: acrobat/assassin/thief forbid STR.
    non_reducible_abilities: list[Ability] = Field(default_factory=list)
```

`Ability` and `Field` are already imported at the top of the file.

- [ ] **Step 4: Populate the three class YAML files**

In `data/classes/acrobat.yaml`, `data/classes/assassin.yaml`, and `data/classes/thief.yaml`, add this top-level key (place it right after the `prime_requisites:` block in each file):

```yaml
non_reducible_abilities:
- STR
```

Leave the existing `adjust_ability_scores` feature text in place — only the *enforcement* moves to the typed field; the prose stays for the sheet.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_ability_adjust.py -q`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add aose/models/character_class.py data/classes/acrobat.yaml data/classes/assassin.yaml data/classes/thief.yaml tests/test_wizard_ability_adjust.py
git commit -m "feat(abilities): typed non_reducible_abilities restriction layer"
```

---

## Task 2: `adjustable_abilities` engine helper

**Files:**
- Modify: `aose/engine/ability_mods.py` (add import + `AdjustmentError` + helper)
- Test: `tests/test_wizard_ability_adjust.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_wizard_ability_adjust.py`:

```python
# ── Task 2: adjustable_abilities ───────────────────────────────────────────

from aose.engine.ability_mods import adjustable_abilities


def test_adjustable_fighter(data):
    adj = adjustable_abilities([data.classes["fighter"]])
    assert adj["raisable"] == {"STR"}
    assert adj["lowerable"] == {"INT", "WIS"}


def test_adjustable_magic_user(data):
    adj = adjustable_abilities([data.classes["magic_user"]])
    assert adj["raisable"] == {"INT"}
    assert adj["lowerable"] == {"STR", "WIS"}


def test_adjustable_thief_removes_str_via_restriction(data):
    adj = adjustable_abilities([data.classes["thief"]])
    assert adj["raisable"] == {"DEX"}
    assert adj["lowerable"] == {"INT", "WIS"}  # STR removed by restriction layer


def test_adjustable_multiclass_union(data):
    adj = adjustable_abilities([data.classes["fighter"], data.classes["magic_user"]])
    assert adj["raisable"] == {"STR", "INT"}
    assert adj["lowerable"] == {"WIS"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_ability_adjust.py -q -k adjustable`
Expected: FAIL with `ImportError: cannot import name 'adjustable_abilities'`.

- [ ] **Step 3: Add the import, error class, and helper**

At the top of `aose/engine/ability_mods.py` (the file currently has no imports), add:

```python
from aose.models import Ability
```

Then append to the file:

```python
class AdjustmentError(ValueError):
    """Raised when a proposed ability-score adjustment violates the rules."""


# Only STR/INT/WIS may ever be lowered (the base set); a class may remove
# entries from this set via non_reducible_abilities, never add to it.
_BASE_LOWERABLE = {"STR", "INT", "WIS"}


def adjustable_abilities(classes) -> dict:
    """Return ``{'raisable': set[str], 'lowerable': set[str]}`` for the selected
    classes.

    * raisable  = union of every class's prime requisites.
    * lowerable = {STR,INT,WIS} minus the raisable set minus the union of every
      class's ``non_reducible_abilities``.
    """
    raisable: set[str] = set()
    non_reducible: set[str] = set()
    for cls in classes:
        raisable |= {a.value for a in cls.prime_requisites}
        non_reducible |= {a.value for a in cls.non_reducible_abilities}
    lowerable = _BASE_LOWERABLE - raisable - non_reducible
    return {"raisable": raisable, "lowerable": lowerable}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_ability_adjust.py -q -k adjustable`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/ability_mods.py tests/test_wizard_ability_adjust.py
git commit -m "feat(abilities): adjustable_abilities raisable/lowerable derivation"
```

---

## Task 3: `validate_ability_adjustments` + `apply_ability_adjustments`

**Files:**
- Modify: `aose/engine/ability_mods.py`
- Test: `tests/test_wizard_ability_adjust.py`

Convention for the `adjustments` dict (used everywhere downstream): keyed by
ability string, **positive = raise, negative = lower**, zeros omitted. Example
`{"STR": +1, "INT": -2}` means raise STR by 1, lower INT by 2.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_wizard_ability_adjust.py`:

```python
# ── Task 3: validate + apply ───────────────────────────────────────────────

from aose.engine.ability_mods import (
    AdjustmentError,
    apply_ability_adjustments,
    validate_ability_adjustments,
)

_POST_RACIAL = {"STR": 12, "INT": 13, "WIS": 13, "DEX": 12, "CON": 12, "CHA": 10}


def test_validate_exact_two_to_one_passes(data):
    # Fighter: raise STR by 1, lower INT+WIS by 1 each (2 down → 1 up).
    validate_ability_adjustments(
        _POST_RACIAL, [data.classes["fighter"]], {"STR": 1, "INT": -1, "WIS": -1}
    )


def test_validate_waste_fails(data):
    # 3 down, 1 up — wasteful, not exactly 2:1.
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            _POST_RACIAL, [data.classes["fighter"]],
            {"STR": 1, "INT": -2, "WIS": -1},
        )


def test_validate_lower_below_nine_fails(data):
    scores = {**_POST_RACIAL, "INT": 9, "WIS": 13}
    # Lowering INT from 9 would breach the floor of 9.
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            scores, [data.classes["fighter"]], {"STR": 1, "INT": -1, "WIS": -1}
        )


def test_validate_raise_above_eighteen_fails(data):
    scores = {**_POST_RACIAL, "STR": 18}
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            scores, [data.classes["fighter"]], {"STR": 1, "INT": -1, "WIS": -1}
        )


def test_validate_lower_prime_fails(data):
    # STR is the fighter's prime — it is raisable, never lowerable.
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            _POST_RACIAL, [data.classes["fighter"]], {"INT": 1, "STR": -2}
        )


def test_validate_raise_non_prime_fails(data):
    # WIS is not a fighter prime requisite.
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            _POST_RACIAL, [data.classes["fighter"]], {"WIS": 1, "INT": -2}
        )


def test_validate_lower_restricted_str_fails(data):
    # Thief forbids lowering STR even though STR is not its prime.
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            _POST_RACIAL, [data.classes["thief"]], {"DEX": 1, "STR": -2}
        )


def test_validate_empty_is_valid(data):
    validate_ability_adjustments(_POST_RACIAL, [data.classes["fighter"]], {})


def test_apply_adds_deltas():
    result = apply_ability_adjustments(
        {"STR": 12, "INT": 13, "WIS": 13, "DEX": 12, "CON": 12, "CHA": 10},
        {"STR": 1, "INT": -1, "WIS": -1},
    )
    assert result["STR"] == 13
    assert result["INT"] == 12
    assert result["WIS"] == 12
    assert result["DEX"] == 12  # untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_ability_adjust.py -q -k "validate or apply"`
Expected: FAIL with `ImportError` for `validate_ability_adjustments` / `apply_ability_adjustments`.

- [ ] **Step 3: Add the helpers**

Append to `aose/engine/ability_mods.py`:

```python
def _ability_floor(ability: str, classes) -> int:
    """The lowest a lowered ability may reach: ``max(9, highest class
    requirement for that ability)``."""
    reqs = [cls.ability_requirements.get(Ability(ability), 0) for cls in classes]
    return max(9, max(reqs, default=0))


def validate_ability_adjustments(post_racial: dict, classes,
                                 adjustments: dict) -> None:
    """Raise ``AdjustmentError`` unless every rule holds:

    * raised abilities ⊆ raisable; lowered ⊆ lowerable
    * ``lowered_total == 2 * raised_total`` (exact, no waste)
    * each lowered post-value ≥ ``max(9, class requirement)``
    * each raised post-value ≤ 18
    """
    adj = adjustable_abilities(classes)
    raised = {a: d for a, d in adjustments.items() if d > 0}
    lowered = {a: -d for a, d in adjustments.items() if d < 0}  # positive amounts

    bad_raise = set(raised) - adj["raisable"]
    if bad_raise:
        raise AdjustmentError(
            f"Cannot raise non-prime-requisite abilities: {sorted(bad_raise)}"
        )
    bad_lower = set(lowered) - adj["lowerable"]
    if bad_lower:
        raise AdjustmentError(f"Cannot lower abilities: {sorted(bad_lower)}")

    raised_total = sum(raised.values())
    lowered_total = sum(lowered.values())
    if lowered_total != 2 * raised_total:
        raise AdjustmentError(
            "Must lower exactly 2 points for every 1 raised (no waste): "
            f"lowered {lowered_total}, raised {raised_total}."
        )

    for ability, amount in lowered.items():
        new_value = post_racial[ability] - amount
        floor = _ability_floor(ability, classes)
        if new_value < floor:
            raise AdjustmentError(
                f"{ability} may not drop below {floor} (would be {new_value})."
            )
    for ability, amount in raised.items():
        new_value = post_racial[ability] + amount
        if new_value > 18:
            raise AdjustmentError(
                f"{ability} may not exceed 18 (would be {new_value})."
            )


def apply_ability_adjustments(scores: dict, adjustments: dict) -> dict:
    """Return ``scores`` with ``adjustments`` added per key. No clamping —
    validation has already bounded the result. Input is not mutated."""
    result = dict(scores)
    for ability, delta in adjustments.items():
        result[ability] = result.get(ability, 0) + delta
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_ability_adjust.py -q -k "validate or apply"`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/ability_mods.py tests/test_wizard_ability_adjust.py
git commit -m "feat(abilities): validate + apply ability adjustments (2:1, floors, cap)"
```

---

## Task 4: Split `_effective_abilities` into `_post_racial_abilities` + `_creation_abilities`

Pure refactor: rename the existing helper and add the post-adjustment variant.
With no adjustments stored yet, `_creation_abilities` is the identity over
`_post_racial_abilities`, so all existing behaviour is preserved.

**Files:**
- Modify: `aose/web/wizard.py:406-416` (helper), `:494`, `:598`, `:833`, `:1466` (call sites)

- [ ] **Step 1: Add the import for `apply_ability_adjustments`**

In `aose/web/wizard.py`, extend the existing `ability_mods` import (lines 19-23):

```python
from aose.engine.ability_mods import (
    ability_modifier,
    ability_warnings,
    apply_ability_adjustments,
    apply_racial_modifiers,
)
```

- [ ] **Step 2: Rename the helper and add `_creation_abilities`**

Replace the whole `_effective_abilities` function (lines 406-416) with:

```python
def _post_racial_abilities(draft: dict[str, Any], data) -> dict[str, int]:
    """Rolled base plus racial modifiers (Advanced only, once a race is chosen).

    In Basic / race-as-class mode, or before a race is picked, this is the
    rolled base unchanged. Modifiers are clamped to [3, 18]. This is the input
    and baseline for the ability-adjustment step and the class requirement check.
    """
    base = draft["abilities"]
    rs = _ruleset_of(draft)
    if not rs.separate_race_class or "race_id" not in draft:
        return dict(base)
    return apply_racial_modifiers(base, data.races[draft["race_id"]])


def _creation_abilities(draft: dict[str, Any], data) -> dict[str, int]:
    """Post-racial scores with the player's ability adjustments applied — the
    creation-final scores stored on the character. Used by HP, finalize, review."""
    return apply_ability_adjustments(
        _post_racial_abilities(draft, data),
        draft.get("ability_adjustments", {}),
    )
```

- [ ] **Step 3: Update the four call sites**

- `get_class` (was line 494): `abilities = _post_racial_abilities(draft, data)` — class gating is **pre**-adjustment.
- `post_class` (was line 598): `effective = _post_racial_abilities(draft, data)` — same.
- `get_hp` (was line 833): `con_mod = ability_modifier(_creation_abilities(draft, data)["CON"])` — HP reads creation-final CON.
- `_draft_to_spec` (was line 1466): `abilities=_creation_abilities(draft, data),` — saved scores are post-adjustment.

- [ ] **Step 4: Verify no stale references remain**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: full suite PASS (same count as before the change). If a `NameError: _effective_abilities` appears, a call site was missed — grep and fix.

- [ ] **Step 5: Commit**

```bash
git add aose/web/wizard.py
git commit -m "refactor(wizard): split effective abilities into post-racial + creation"
```

---

## Task 5: Wire the `adjust` step into the flow

Step plumbing only — no route handlers yet. After this task the wizard knows the
step exists, gates it, labels it, and clears it; visiting `/adjust` would 404
until Task 6 adds the handlers.

**Files:**
- Modify: `aose/web/wizard.py` — `STEP_LABELS`, `_wizard_steps`, `_next_incomplete_step`, the three `_clear_after_*` helpers
- Test: `tests/test_wizard_ability_adjust.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_wizard_ability_adjust.py` (integration harness + first gating test):

```python
# ── Task 5/6: wizard integration ───────────────────────────────────────────

def _make_client(tmp_path, ruleset=None):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True)
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, ruleset or RuleSet())
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._drafts_dir = drafts_dir
    client._characters_dir = characters_dir
    return client


def _new_draft(client):
    r = client.get("/wizard/new")
    return r.headers["location"].split("/")[2]


def _set_abilities(client, draft_id, abilities):
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = abilities
    save_draft(draft_id, draft, client._drafts_dir)


# STR 13 so a fighter can spend 2 down (INT/WIS) for 1 up (STR) within floors.
_FIGHTER_ABILITIES = {"STR": 13, "INT": 13, "WIS": 13, "DEX": 12, "CON": 12, "CHA": 10}


def _drive_to_adjust(client, ruleset_kwargs=None, abilities=None, race="human",
                     cls="fighter"):
    """Create a draft and advance it to (but not past) the adjust step."""
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, dict(abilities or _FIGHTER_ABILITIES))
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Conan"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": race})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": cls})
    return draft_id


def test_adjust_step_between_class_and_alignment(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    # After picking class, the next incomplete step is adjust (not alignment).
    r = client.get(f"/wizard/{draft_id}/alignment")
    assert r.status_code == 303
    assert r.headers["location"].endswith("/adjust")


def test_adjust_step_present_in_basic_mode(tmp_path):
    client = _make_client(tmp_path, ruleset=RuleSet(separate_race_class=False))
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, dict(_FIGHTER_ABILITIES))
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Conan"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    r = client.get(f"/wizard/{draft_id}/alignment")
    assert r.status_code == 303
    assert r.headers["location"].endswith("/adjust")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_ability_adjust.py -q -k adjust_step`
Expected: FAIL — the redirect target is `/alignment` (or `/adjust` does not yet exist in the step list), so the assertions on `/adjust` fail.

- [ ] **Step 3: Add the step label**

In `STEP_LABELS` (around line 91), add after the `"class"` entry:

```python
    "adjust": "Ability Adjustments",
```

- [ ] **Step 4: Insert the step in `_wizard_steps`**

In `_wizard_steps`, change the line `steps += ["class", "alignment"]` to:

```python
    steps += ["class", "adjust", "alignment"]
```

- [ ] **Step 5: Gate the step in `_next_incomplete_step`**

In `_next_incomplete_step`, between the class-pick check and the alignment check, insert:

```python
    if "ability_adjustments" not in draft:
        return "adjust"
```

(Place it immediately after `if not _has_class_pick(draft): return "class"` and before `if "alignment" not in draft: return "alignment"`.)

- [ ] **Step 6: Add `ability_adjustments` to the downstream clears**

In each of `_clear_after_abilities`, `_clear_after_race`, and `_clear_after_class`, add `"ability_adjustments"` to the tuple of keys popped. For example `_clear_after_class` becomes:

```python
def _clear_after_class(draft: dict[str, Any]) -> None:
    for k in ("hp_roll", "hp_rolls", "proficiencies", "ability_adjustments",
              "spellcasting", "spellbooks", "spells_done"):
        draft.pop(k, None)
```

Add `"ability_adjustments"` to the key tuples in `_clear_after_abilities` and `_clear_after_race` the same way.

- [ ] **Step 7: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_ability_adjust.py -q -k adjust_step`
Expected: PASS (2 tests). The redirect now lands on `/adjust`.

- [ ] **Step 8: Commit**

```bash
git add aose/web/wizard.py tests/test_wizard_ability_adjust.py
git commit -m "feat(wizard): insert ability-adjustment step into flow + clears"
```

---

## Task 6: `adjust` GET/POST routes + template

**Files:**
- Modify: `aose/web/wizard.py` — add `get_adjust` / `post_adjust` (place right after `post_class`, before `get_alignment`)
- Create: `aose/web/templates/wizard/adjust.html`
- Test: `tests/test_wizard_ability_adjust.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_wizard_ability_adjust.py`:

```python
def test_adjust_get_renders_scores_and_marks(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    r = client.get(f"/wizard/{draft_id}/adjust")
    assert r.status_code == 200
    # Fighter: STR raisable, INT/WIS lowerable.
    assert "raise_STR" in r.text
    assert "lower_INT" in r.text
    assert "lower_WIS" in r.text
    # STR is a prime — it must not be offered as lowerable.
    assert "lower_STR" not in r.text


def test_adjust_post_valid_stores_and_advances(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    r = client.post(f"/wizard/{draft_id}/adjust", data={
        "raise_STR": "1", "lower_INT": "1", "lower_WIS": "1",
    })
    assert r.status_code == 303
    assert r.headers["location"].endswith("/alignment")
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["ability_adjustments"] == {"STR": 1, "INT": -1, "WIS": -1}


def test_adjust_post_zero_is_valid(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    r = client.post(f"/wizard/{draft_id}/adjust", data={})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["ability_adjustments"] == {}


def test_adjust_post_waste_rejected(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    r = client.post(f"/wizard/{draft_id}/adjust", data={
        "raise_STR": "1", "lower_INT": "1", "lower_WIS": "2",
    })
    assert r.status_code == 400


def test_finalize_reflects_adjustment(tmp_path):
    import json
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    client.post(f"/wizard/{draft_id}/adjust", data={
        "raise_STR": "1", "lower_INT": "1", "lower_WIS": "1",
    })
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.get(f"/wizard/{draft_id}/equipment")
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    saved = json.loads((client._characters_dir / f"{char_id}.json").read_text())
    assert saved["abilities"]["STR"] == 14  # 13 +1
    assert saved["abilities"]["INT"] == 12  # 13 -1
    assert saved["abilities"]["WIS"] == 12  # 13 -1


def test_changing_class_clears_adjustment(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    client.post(f"/wizard/{draft_id}/adjust", data={
        "raise_STR": "1", "lower_INT": "1", "lower_WIS": "1",
    })
    # Re-pick a different class — the stored adjustment must be cleared.
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "thief"})
    draft = load_draft(draft_id, client._drafts_dir)
    assert "ability_adjustments" not in draft
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_ability_adjust.py -q -k "adjust_get or adjust_post or finalize_reflects or changing_class"`
Expected: FAIL — GET/POST `/adjust` return 404 (no handler / no template) and `test_changing_class_clears_adjustment` may already pass from Task 5's clears.

- [ ] **Step 3: Add the route handlers**

In `aose/web/wizard.py`, immediately after `post_class` (before `get_alignment`, around line 635), add:

```python
def _adjust_context(draft: dict[str, Any], data) -> dict:
    """Per-ability rows for the adjust step: post-racial score, raisable /
    lowerable marks, floor, and any previously stored allocation."""
    from aose.engine.ability_mods import adjustable_abilities, _ability_floor

    classes = [data.classes[cid] for cid in _class_ids(draft) if cid in data.classes]
    post_racial = _post_racial_abilities(draft, data)
    adj = adjustable_abilities(classes)
    stored = draft.get("ability_adjustments", {})
    rows = []
    for ab in ABILITY_ORDER:
        name = ab.value
        delta = stored.get(name, 0)
        rows.append({
            "name": name,
            "score": post_racial[name],
            "raisable": name in adj["raisable"],
            "lowerable": name in adj["lowerable"],
            "floor": _ability_floor(name, classes) if name in adj["lowerable"] else None,
            "raise_val": delta if delta > 0 else 0,
            "lower_val": -delta if delta < 0 else 0,
        })
    return {"adjust_rows": rows}


@router.get("/{draft_id}/adjust", response_class=HTMLResponse)
async def get_adjust(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "adjust", draft_id)
    if redirect:
        return redirect
    ctx = _base_context(request, draft_id, draft, "adjust")
    ctx.update(_adjust_context(draft, request.app.state.game_data))
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/adjust")
async def post_adjust(request: Request, draft_id: str):
    from aose.engine.ability_mods import (
        AdjustmentError,
        validate_ability_adjustments,
    )

    draft = _load(request, draft_id)
    data = request.app.state.game_data
    classes = [data.classes[cid] for cid in _class_ids(draft) if cid in data.classes]
    post_racial = _post_racial_abilities(draft, data)

    form = await request.form()
    adjustments: dict[str, int] = {}
    for ab in ABILITY_ORDER:
        name = ab.value
        try:
            up = int(form.get(f"raise_{name}", 0) or 0)
            down = int(form.get(f"lower_{name}", 0) or 0)
        except ValueError:
            raise HTTPException(400, f"Invalid number for {name}")
        if up < 0 or down < 0:
            raise HTTPException(400, "Adjustment amounts must be non-negative.")
        delta = up - down
        if delta:
            adjustments[name] = delta

    try:
        validate_ability_adjustments(post_racial, classes, adjustments)
    except AdjustmentError as e:
        raise HTTPException(400, str(e))

    draft["ability_adjustments"] = adjustments
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")
```

- [ ] **Step 4: Create the template**

Create `aose/web/templates/wizard/adjust.html`:

```html
<h2>Ability Score Adjustments</h2>
<p class="muted">
    Optionally trade points down to raise a prime requisite. Every <strong>2
    points lowered</strong> buys <strong>1 point raised</strong> — no waste.
    Only prime requisites may be raised (max 18); only STR/INT/WIS that aren't a
    prime (or class-restricted) may be lowered (floor shown). Leave everything at
    0 to skip.
</p>

<form method="post" action="/wizard/{{ draft_id }}/adjust" class="step-form">
    <table class="abilities-roll">
        <thead>
            <tr><th>Ability</th><th>Score</th><th>Raise</th><th>Lower</th></tr>
        </thead>
        <tbody>
        {% for row in adjust_rows %}
            <tr>
                <td>{{ row.name }}</td>
                <td class="num">{{ row.score }}</td>
                <td class="num">
                    {% if row.raisable %}
                    <input type="number" name="raise_{{ row.name }}" min="0"
                           value="{{ row.raise_val }}" step="1">
                    {% else %}—{% endif %}
                </td>
                <td class="num">
                    {% if row.lowerable %}
                    <input type="number" name="lower_{{ row.name }}" min="0"
                           value="{{ row.lower_val }}" step="1">
                    <span class="muted">(floor {{ row.floor }})</span>
                    {% else %}—{% endif %}
                </td>
            </tr>
        {% endfor %}
        </tbody>
    </table>
    <button type="submit" class="primary">Next: Choose Alignment &rarr;</button>
</form>
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_ability_adjust.py -q`
Expected: PASS (whole Slice-4 file).

- [ ] **Step 6: Commit**

```bash
git add aose/web/wizard.py aose/web/templates/wizard/adjust.html tests/test_wizard_ability_adjust.py
git commit -m "feat(wizard): ability-adjustment step routes + template"
```

---

## Task 7: Prime-requisite XP reflects the raised score

A focused regression that the saved adjustment flows through to leveling — no
new production code, just proof the wiring (`_creation_abilities` → spec) does
what the slice is for.

**Files:**
- Test: `tests/test_wizard_ability_adjust.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_wizard_ability_adjust.py`:

```python
# ── Task 7: prime-req XP reflects the adjustment ───────────────────────────

from aose.engine.ability_mods import prime_requisite_xp_multiplier


def test_raised_prime_increases_xp_multiplier(data):
    # Fighter prime is STR. Post-racial STR 15 → multiplier 1.05.
    # Raise to 16 (lower INT+WIS) → multiplier 1.10.
    post_racial = {"STR": 15, "INT": 13, "WIS": 13, "DEX": 12, "CON": 12, "CHA": 10}
    before = prime_requisite_xp_multiplier(post_racial["STR"])
    creation = apply_ability_adjustments(
        post_racial, {"STR": 1, "INT": -1, "WIS": -1}
    )
    after = prime_requisite_xp_multiplier(creation["STR"])
    assert before == 1.05
    assert after == 1.10
```

- [ ] **Step 2: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_ability_adjust.py -q -k xp_multiplier`
Expected: PASS — `apply_ability_adjustments` and `prime_requisite_xp_multiplier` already exist; this asserts the slice's intent end-to-end.

(If it fails, the bug is in `apply_ability_adjustments` from Task 3, not here.)

- [ ] **Step 3: Run the whole suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: full suite PASS. (Ignore the trailing `pytest-current` PermissionError.)

- [ ] **Step 4: Commit**

```bash
git add tests/test_wizard_ability_adjust.py
git commit -m "test(abilities): raised prime requisite lifts XP multiplier"
```

---

## Self-Review

**Spec coverage:**
- Raise prime reqs, cap 18 → `validate_ability_adjustments` raised-bound (Task 3). ✓
- Lower STR/INT/WIS not a prime → `adjustable_abilities` lowerable set (Task 2). ✓
- Per-class restriction layer (acrobat/assassin/thief forbid STR) → `non_reducible_abilities` field + data (Task 1), removed in `adjustable_abilities` (Task 2). ✓
- 2:1 no waste → `lowered_total == 2 * raised_total` (Task 3). ✓
- Raised across multiple primes → multi-class union test (Task 2) + arbitrary raise inputs (Task 6). ✓
- Floor `max(9, class requirement)` → `_ability_floor` (Task 3). ✓
- Always shown, zero-adjust valid, no RuleSet flag → step always in `_wizard_steps`, empty-dict completion (Task 5), `test_adjust_post_zero_is_valid` (Task 6). ✓
- Operates on post-racial → `_post_racial_abilities` baseline (Task 4/6). ✓
- Model field + keep prose feature → Task 1. ✓
- `_post_racial_abilities` / `_creation_abilities` split → Task 4. ✓
- `_draft_to_spec` uses creation abilities → Task 4; leveling unchanged → Task 7 proves it. ✓
- Step order after class / before alignment, STEP_LABELS, completion marker, downstream clears in all three helpers → Task 5. ✓
- GET marks raisable/lowerable + allocation form; POST parses deltas, validates (400), stores omitting zeros → Task 6. ✓
- Tests enumerated in spec §5 → mapped across Tasks 1–3, 6, 7. ✓

**Placeholder scan:** No TBD/"handle edge cases"/"similar to" — every code step contains complete code. ✓

**Type consistency:** `adjustments` is `dict[str,int]` (positive=raise, negative=lower) everywhere; `adjustable_abilities` returns `{"raisable","lowerable"}` sets of strings, consumed identically in engine tests and `_adjust_context`; `_post_racial_abilities` / `_creation_abilities` names match between definition (Task 4) and all call sites (Tasks 4/6); `non_reducible_abilities` consistent across model, data, and helper. ✓
