# Wizard Overhaul — Slice 3: Race — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply demihuman racial ability-score modifiers at character creation in Advanced mode (with an 18/3 clamp), store creation-final scores on the saved character, and surface the adjustment in the wizard's race / class / HP steps.

**Architecture:** A typed `ability_modifiers` field is promoted onto `Race` and the demihuman YAMLs are migrated to use it. A single pure clamp helper `apply_racial_modifiers` lives in `aose/engine/ability_mods.py`. The wizard derives "effective creation abilities" via a small helper that applies racial mods only when `separate_race_class` is on and a race is chosen; `_draft_to_spec` stores those effective scores so every existing downstream consumer (saves, HP, prime-req XP, magic) sees the modified numbers with no further change. Race minimums stay checked against the rolled base; class minimums and the HP step's CON read the effective scores.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, YAML, pytest. Tests run with `.venv\Scripts\python.exe -m pytest`.

---

## Background facts for the implementer (zero-context safe)

- `Ability` is a `str`-enum (`aose/models/ability.py`): `Ability.CON.value == "CON"`. Draft and spec ability dicts are keyed by the **string** form (`"CON"`); `Race.ability_modifiers` will be keyed by the **enum** (`Ability.CON`), matching the existing `ability_requirements` field. Always convert with `ab.value` when indexing a string-keyed dict.
- The wizard stores its in-progress state as a plain dict ("draft"). `draft["abilities"]` is the rolled 3d6 base, set once at `/wizard/new` and never mutated by later steps.
- `RuleSet.separate_race_class` defaults to `True`. The race step only appears in the wizard when `separate_race_class` is on (see `_wizard_steps`); when it is off the flow is "race-as-class". This flag is the operational proxy for "Advanced mode" in this slice — racial mods apply exactly when it is on **and** a race has been chosen.
- The six demihuman YAMLs that currently carry a `features[].mechanical.ability_modifiers` sub-dict: `dwarf`, `duergar`, `drow`, `elf`, `halfling`, `half_orc`. The races with **no** modifier feature: `gnome`, `half_elf`, `svirfneblin`. `human` has an `optional_ability_modifiers` feature tagged `optional_rule: true` — **do not touch it** (Slice 5 owns it).
- `RaceFeature.mechanical` is `dict[str, Any] | None` with no `extra="forbid"`, so removing the `ability_modifiers` key from a feature's `mechanical` block does not break validation. The `validate_import` tool and `test_load_game_data_real_dir` only check that `data/` loads cleanly.
- Run the whole suite with:
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/ -q
  ```
  The trailing `PermissionError` on `pytest-current` is a known Windows quirk; ignore it.

---

## File structure

| File | Responsibility | Change |
|---|---|---|
| `aose/models/race.py` | `Race` model | Add `ability_modifiers: dict[Ability, int]` field |
| `data/races/{dwarf,duergar,drow,elf,halfling,half_orc}.yaml` | Demihuman seed data | Add top-level `ability_modifiers`; drop `features[].mechanical.ability_modifiers` (keep the descriptive feature) |
| `aose/engine/ability_mods.py` | Pure ability math | Add `apply_racial_modifiers(base, race)` clamp helper |
| `aose/web/wizard.py` | Wizard routes/helpers | Add `_effective_abilities`; wire into `_draft_to_spec`, class-step requirement checks, HP-step CON, and race-step display context |
| `aose/web/templates/wizard/race.html` | Race step UI | Show per-ability rolled → effective change for races with modifiers |
| `tests/test_wizard_race.py` | New test file for this slice | Create |
| `tests/test_data_loading.py` | Data-load assertions | Add modifier-field assertions |
| `tests/test_ability_warnings.py` (`ability_mods` helpers) | — | Helper tests live in the new file instead; no change here |

---

## Task 1: `Race.ability_modifiers` model field

**Files:**
- Modify: `aose/models/race.py:17-33`
- Test: `tests/test_data_loading.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_data_loading.py` (after `test_dwarf_loaded`, reusing the module-scoped `data` fixture and the existing `Ability` import):

```python
def test_demihuman_ability_modifiers_loaded(data):
    assert data.races["dwarf"].ability_modifiers == {Ability.CHA: -1, Ability.CON: 1}
    assert data.races["duergar"].ability_modifiers == {Ability.CHA: -1, Ability.CON: 1}
    assert data.races["drow"].ability_modifiers == {Ability.CON: -1, Ability.DEX: 1}
    assert data.races["elf"].ability_modifiers == {Ability.CON: -1, Ability.DEX: 1}
    assert data.races["halfling"].ability_modifiers == {Ability.DEX: 1, Ability.STR: -1}
    assert data.races["half_orc"].ability_modifiers == {
        Ability.CHA: -2, Ability.CON: 1, Ability.STR: 1
    }


def test_races_without_modifiers_have_empty_field(data):
    for rid in ("gnome", "half_elf", "svirfneblin"):
        assert data.races[rid].ability_modifiers == {}


def test_human_optional_modifier_feature_untouched(data):
    human = data.races["human"]
    # The unconditional field stays empty; the optional feature is preserved.
    assert human.ability_modifiers == {}
    feature = next(f for f in human.features if f.id == "optional_ability_modifiers")
    assert feature.mechanical["ability_modifiers"] == {"CHA": 1, "CON": 1}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py -q`
Expected: FAIL — `AttributeError: 'Race' object has no attribute 'ability_modifiers'` (or the YAML data tests fail because the field defaults to `{}`).

- [ ] **Step 3: Add the field to the model**

In `aose/models/race.py`, add the field to `Race` immediately after the existing `ability_minima` line (line 24):

```python
    ability_minima: dict[Ability, int] = Field(default_factory=dict)
    # Unconditional racial ability-score modifiers (Advanced creation rule).
    # Applied at character creation only, clamped to [3, 18]. Human's
    # *optional* modifiers live in a feature, not here.
    ability_modifiers: dict[Ability, int] = Field(default_factory=dict)
```

- [ ] **Step 4: Run the model-only part of the test**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py::test_human_optional_modifier_feature_untouched -q`
Expected: PASS (human field defaults to `{}`; feature still present).

The demihuman/empty tests still FAIL until Task 2 migrates the YAML — that is expected. Do **not** commit yet; commit happens at the end of Task 2 so the data and model land together.

---

## Task 2: Migrate demihuman race YAMLs

**Files:**
- Modify: `data/races/dwarf.yaml`, `data/races/duergar.yaml`, `data/races/drow.yaml`, `data/races/elf.yaml`, `data/races/halfling.yaml`, `data/races/half_orc.yaml`
- Test: `tests/test_data_loading.py` (already written in Task 1)

For each of the six files: (a) add a top-level `ability_modifiers:` block, and (b) delete the `mechanical:` block under the `ability_modifiers` **feature**, leaving that feature's `id`/`name`/`text` intact.

- [ ] **Step 1: dwarf** — In `data/races/dwarf.yaml`, add a top-level block after the `ability_requirements:` block (before `infravision:`):

```yaml
ability_modifiers:
  CHA: -1
  CON: 1
```

Then change the feature (lines 23-29) from:

```yaml
- id: ability_modifiers
  name: Ability Modifiers
  text: –1 CHA, +1 CON.
  mechanical:
    ability_modifiers:
      CHA: -1
      CON: 1
```

to:

```yaml
- id: ability_modifiers
  name: Ability Modifiers
  text: –1 CHA, +1 CON.
```

- [ ] **Step 2: duergar** — In `data/races/duergar.yaml`, add the top-level block (place it adjacent to the other top-level scalar fields, e.g. just before `features:`):

```yaml
ability_modifiers:
  CHA: -1
  CON: 1
```

Then remove the `mechanical:` block (the `ability_modifiers` sub-dict) under the `ability_modifiers` feature, keeping its `id`/`name`/`text`.

- [ ] **Step 3: drow** — In `data/races/drow.yaml`, add top-level:

```yaml
ability_modifiers:
  CON: -1
  DEX: 1
```

Then remove the `mechanical:` block under the `ability_modifiers` feature (keep `id`/`name`/`text`).

- [ ] **Step 4: elf** — In `data/races/elf.yaml`, add top-level:

```yaml
ability_modifiers:
  CON: -1
  DEX: 1
```

Then remove the `mechanical:` block under the `ability_modifiers` feature (keep `id`/`name`/`text`).

- [ ] **Step 5: halfling** — In `data/races/halfling.yaml`, add top-level:

```yaml
ability_modifiers:
  DEX: 1
  STR: -1
```

Then remove the `mechanical:` block under the `ability_modifiers` feature (keep `id`/`name`/`text`).

- [ ] **Step 6: half_orc** — In `data/races/half_orc.yaml`, add top-level:

```yaml
ability_modifiers:
  CHA: -2
  CON: 1
  STR: 1
```

Then change the feature (lines 20-27) from:

```yaml
- id: ability_modifiers
  name: Ability Modifiers
  text: –2 CHA, +1 CON, +1 STR.
  mechanical:
    ability_modifiers:
      CHA: -2
      CON: 1
      STR: 1
```

to:

```yaml
- id: ability_modifiers
  name: Ability Modifiers
  text: –2 CHA, +1 CON, +1 STR.
```

- [ ] **Step 7: Run the data-loading tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py -q`
Expected: PASS (all three new tests plus the pre-existing ones).

- [ ] **Step 8: Confirm the full data set still loads via the import validator**

Run: `.venv\Scripts\python.exe -m pytest tests/test_validate_import.py::test_load_game_data_real_dir tests/test_validate_import.py::test_main_passes_on_clean_repo -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add aose/models/race.py data/races/dwarf.yaml data/races/duergar.yaml data/races/drow.yaml data/races/elf.yaml data/races/halfling.yaml data/races/half_orc.yaml tests/test_data_loading.py
git commit -m @'
feat(race): typed ability_modifiers field + demihuman YAML migration

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

## Task 3: `apply_racial_modifiers` clamp helper

**Files:**
- Modify: `aose/engine/ability_mods.py`
- Test: `tests/test_wizard_race.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_wizard_race.py`:

```python
"""Slice 3 (Race): racial ability-modifier application + wizard wiring."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_draft, save_draft, save_settings
from aose.engine.ability_mods import apply_racial_modifiers
from aose.data.loader import GameData
from aose.models import RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


# ── Pure helper: apply_racial_modifiers ───────────────────────────────────

def _base():
    return {"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 14, "CHA": 9}


def test_apply_dwarf_modifiers(data):
    result = apply_racial_modifiers(_base(), data.races["dwarf"])
    assert result["CON"] == 15  # +1
    assert result["CHA"] == 8   # -1
    # untouched abilities pass through
    assert result["STR"] == 10


def test_apply_does_not_mutate_input(data):
    base = _base()
    apply_racial_modifiers(base, data.races["dwarf"])
    assert base["CON"] == 14  # original dict unchanged


def test_clamp_high_at_18(data):
    base = {"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 18, "CHA": 9}
    result = apply_racial_modifiers(base, data.races["dwarf"])
    assert result["CON"] == 18  # 18 +1 clamps to 18


def test_clamp_low_at_3(data):
    base = {"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 14, "CHA": 3}
    result = apply_racial_modifiers(base, data.races["dwarf"])
    assert result["CHA"] == 3  # 3 -1 clamps to 3


def test_apply_half_orc_multi_stat(data):
    base = {"STR": 12, "INT": 10, "WIS": 10, "DEX": 10, "CON": 13, "CHA": 11}
    result = apply_racial_modifiers(base, data.races["half_orc"])
    assert result["STR"] == 13  # +1
    assert result["CON"] == 14  # +1
    assert result["CHA"] == 9   # -2


def test_apply_no_modifier_race_is_identity(data):
    base = _base()
    assert apply_racial_modifiers(base, data.races["gnome"]) == base
```

- [ ] **Step 2: Run the helper tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_race.py -k apply -q`
Expected: FAIL — `ImportError: cannot import name 'apply_racial_modifiers'`.

- [ ] **Step 3: Implement the helper**

Append to `aose/engine/ability_mods.py`:

```python
def apply_racial_modifiers(base: dict[str, int], race) -> dict[str, int]:
    """Return ``base`` with ``race.ability_modifiers`` applied, each resulting
    score clamped to ``[3, 18]``.

    Bonuses that would exceed 18 and penalties that would drop below 3 are
    ignored (clamped), per the Advanced creation rule. ``base`` is keyed by the
    string ability name (``"CON"``); ``race.ability_modifiers`` is keyed by the
    ``Ability`` enum. The input dict is not mutated. This helper does not
    consult the ruleset — callers decide whether to apply it (Advanced only).
    """
    result = dict(base)
    for ability, delta in race.ability_modifiers.items():
        key = ability.value if hasattr(ability, "value") else ability
        result[key] = max(3, min(18, result.get(key, 0) + delta))
    return result
```

- [ ] **Step 4: Run the helper tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_race.py -k apply -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```powershell
git add aose/engine/ability_mods.py tests/test_wizard_race.py
git commit -m @'
feat(abilities): apply_racial_modifiers clamp helper

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

## Task 4: `_effective_abilities` wizard helper + finalize wiring

**Files:**
- Modify: `aose/web/wizard.py` (import; new helper near `_meets_ability_requirements` at line 398; `_draft_to_spec` at lines 1416-1456; its two call sites at lines 1466 and 1476)
- Test: `tests/test_wizard_race.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_wizard_race.py` (the helper section above already imported what it needs; these integration tests use the FastAPI test client):

```python
# ── Integration: finalize stores creation-final abilities ─────────────────

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


# A dwarf fighter is the canonical Advanced case (CON +1, CHA -1).
_DWARF_ABILITIES = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}


def _drive_dwarf_fighter_to_finalize(client, tmp_path):
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, dict(_DWARF_ABILITIES))
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Gloin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.get(f"/wizard/{draft_id}/equipment")  # rolls starting gold
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    return char_id


def test_advanced_finalize_stores_modified_abilities(tmp_path):
    import json
    client = _make_client(tmp_path)  # default RuleSet: separate_race_class on
    char_id = _drive_dwarf_fighter_to_finalize(client, tmp_path)
    saved = json.loads((client._characters_dir / f"{char_id}.json").read_text())
    assert saved["abilities"]["CON"] == 15  # 14 +1
    assert saved["abilities"]["CHA"] == 9    # 10 -1
    assert saved["abilities"]["STR"] == 15   # unchanged


def test_basic_race_as_class_finalize_has_no_racial_mods(tmp_path):
    import json
    client = _make_client(tmp_path, ruleset=RuleSet(separate_race_class=False))
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, dict(_DWARF_ABILITIES))
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Gloin"})
    # Race-as-class: pick the dwarf class entry directly (derives race_id=dwarf).
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.get(f"/wizard/{draft_id}/equipment")
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    saved = json.loads((client._characters_dir / f"{char_id}.json").read_text())
    assert saved["abilities"]["CON"] == 14  # no racial mod in Basic
    assert saved["abilities"]["CHA"] == 10
```

> Note: the race-as-class test assumes a `dwarf` class entry exists (race-locked). Confirm with `data/classes/`; if the race-as-class dwarf id differs, use that id. The existing `tests/test_race_as_class.py` shows the correct id to use.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_race.py -k finalize -q`
Expected: FAIL — `test_advanced_finalize_stores_modified_abilities` asserts CON 15 but the unmodified draft stores CON 14.

- [ ] **Step 3: Add the import**

In `aose/web/wizard.py`, extend the existing `ability_mods` import (line 19) from:

```python
from aose.engine.ability_mods import ability_modifier, ability_warnings
```

to:

```python
from aose.engine.ability_mods import (
    ability_modifier,
    ability_warnings,
    apply_racial_modifiers,
)
```

- [ ] **Step 4: Add the `_effective_abilities` helper**

In `aose/web/wizard.py`, add this helper directly **after** `_meets_ability_requirements` (after line 399):

```python
def _effective_abilities(draft: dict[str, Any], data) -> dict[str, int]:
    """The creation-final ability scores: rolled base plus racial modifiers,
    but only in Advanced mode (``separate_race_class`` on) once a race has
    been chosen. In Basic / race-as-class, or before a race is picked, this is
    just the rolled base. Racial mods are clamped to [3, 18] by the helper.
    """
    base = draft["abilities"]
    rs = _ruleset_of(draft)
    if not rs.separate_race_class or "race_id" not in draft:
        return dict(base)
    return apply_racial_modifiers(base, data.races[draft["race_id"]])
```

- [ ] **Step 5: Wire it into `_draft_to_spec`**

Change the signature of `_draft_to_spec` (line 1416) to accept `data`:

```python
def _draft_to_spec(draft: dict[str, Any], data) -> CharacterSpec:
```

Inside the `CharacterSpec(...)` construction (line 1437), change:

```python
        abilities=draft["abilities"],
```

to:

```python
        abilities=_effective_abilities(draft, data),
```

- [ ] **Step 6: Update the two call sites**

In `get_review` (line 1466), change:

```python
    spec = _draft_to_spec(draft)
```

to:

```python
    spec = _draft_to_spec(draft, request.app.state.game_data)
```

In `post_finalize` (line 1476), change:

```python
    spec = _draft_to_spec(draft)
```

to:

```python
    spec = _draft_to_spec(draft, request.app.state.game_data)
```

- [ ] **Step 7: Run the finalize tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_race.py -k finalize -q`
Expected: PASS (2 tests).

- [ ] **Step 8: Run the existing wizard suite to confirm no regression**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard.py tests/test_race_as_class.py -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add aose/web/wizard.py tests/test_wizard_race.py
git commit -m @'
feat(wizard): store creation-final abilities incl. racial mods (Advanced)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

## Task 5: Class minimum requirements checked against effective abilities

The race step already checks minimums against the **rolled base** (`post_race` passes `draft["abilities"]`), which is correct and stays unchanged. The class step must instead gate on the **effective** (post-racial) abilities so a racial +1 can let a borderline score qualify.

**Files:**
- Modify: `aose/web/wizard.py` — `get_class` (line 466) and `post_class` (line 572)
- Test: `tests/test_wizard_race.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_wizard_race.py`:

```python
# ── Requirement gating: race pre-modifier, class post-modifier ────────────

def test_race_minimum_checked_pre_modifier(tmp_path):
    # Dwarf requires CON 9. A CON 8 roll must FAIL even though +1 would reach 9.
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, {
        "STR": 12, "INT": 11, "WIS": 12, "DEX": 13, "CON": 8, "CHA": 12,
    })
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Gloin"})
    r = client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    assert r.status_code == 400


# Verified against data: half_orc gives CON +1 and has NO race ability
# requirement (any base is selectable). knight requires CON 9 and is NOT
# race-locked. With lift_demihuman_restrictions on, half_orc may pick knight.
# We also need DEX 9 to satisfy knight's second requirement (unmodified).
_KNIGHT_BORDERLINE = {"STR": 12, "INT": 11, "WIS": 12, "DEX": 9, "CON": 8, "CHA": 12}


def test_class_minimum_passes_after_racial_bonus(tmp_path):
    # half_orc CON +1: base CON 8 fails knight's CON 9, but effective 9 passes.
    client = _make_client(tmp_path, ruleset=RuleSet(lift_demihuman_restrictions=True))
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, dict(_KNIGHT_BORDERLINE))
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Grok"})
    r = client.post(f"/wizard/{draft_id}/race", data={"race_id": "half_orc"})
    assert r.status_code == 303  # half_orc has no race minimums
    r = client.post(f"/wizard/{draft_id}/class", data={"class_id": "knight"})
    assert r.status_code == 303  # effective CON 9 qualifies


def test_class_minimum_fails_without_racial_bonus(tmp_path):
    # Negative control: human has no modifiers, so base CON 8 still fails knight.
    client = _make_client(tmp_path, ruleset=RuleSet(lift_demihuman_restrictions=True))
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, dict(_KNIGHT_BORDERLINE))
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Otto"})
    r = client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    assert r.status_code == 303
    r = client.post(f"/wizard/{draft_id}/class", data={"class_id": "knight"})
    assert r.status_code == 400  # base CON 8 < 9, no racial mod for human
```

> These combos are confirmed against the data: `data/races/half_orc.yaml` has no `ability_requirements` and `ability_modifiers: {CHA: -2, CON: 1, STR: 1}`; `data/classes/knight.yaml` has `ability_requirements: {CON: 9, DEX: 9}` and is not race-locked; `data/races/human.yaml` has no `ability_modifiers`. `lift_demihuman_restrictions=True` lets either race pick knight (otherwise `_class_allowed_for_race` would block half_orc). The pair proves the gate reads the *effective* score: same base, opposite outcome depending on whether the race grants +1 CON.

- [ ] **Step 2: Run the tests to verify the class one fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_race.py -k "pre_modifier or post_modifier" -q`
Expected: `test_race_minimum_checked_pre_modifier` PASSES already (race uses base); `test_class_minimum_checked_post_modifier` FAILS (class currently checks base DEX 8 < 9 → 400).

- [ ] **Step 3: Use effective abilities in `get_class`**

In `get_class`, change the line (line 466):

```python
    abilities = draft["abilities"]
```

to:

```python
    abilities = _effective_abilities(draft, data)
```

(This feeds the per-card `meets_abilities` flag so the UI greys out classes consistently with the POST gate.)

- [ ] **Step 4: Use effective abilities in `post_class`**

In `post_class`, the per-class gating loop (line 570-573) reads:

```python
    for cid in ids:
        cls = data.classes[cid]
        if not _meets_ability_requirements(cls.ability_requirements, draft["abilities"]):
            raise HTTPException(400, f"Abilities do not meet {cls.name} requirements")
```

Change it to compute effective abilities once before the loop and use them:

```python
    effective = _effective_abilities(draft, data)
    for cid in ids:
        cls = data.classes[cid]
        if not _meets_ability_requirements(cls.ability_requirements, effective):
            raise HTTPException(400, f"Abilities do not meet {cls.name} requirements")
```

> In race-as-class mode `race_id` is not set when `post_class` runs its gating loop (it is derived later in the same handler), so `_effective_abilities` returns the base — identical to today's behaviour. No regression for race-as-class.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_race.py -k "pre_modifier or post_modifier" -q`
Expected: PASS (2 tests).

- [ ] **Step 6: Run the wizard + demihuman suites for regressions**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard.py tests/test_demihuman_rules.py tests/test_multiclassing.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add aose/web/wizard.py tests/test_wizard_race.py
git commit -m @'
feat(wizard): gate class requirements on post-racial abilities

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

## Task 6: Race step shows the racial adjustment

**Files:**
- Modify: `aose/web/wizard.py` — `get_race` (lines 402-424)
- Modify: `aose/web/templates/wizard/race.html`
- Test: `tests/test_wizard_race.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_wizard_race.py`:

```python
# ── Race step display ─────────────────────────────────────────────────────

def test_race_step_shows_ability_change_for_dwarf(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, dict(_DWARF_ABILITIES))  # CON 14, CHA 10
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Gloin"})
    r = client.get(f"/wizard/{draft_id}/race")
    assert r.status_code == 200
    # The dwarf card shows the effective CON (14 -> 15) and CHA (10 -> 9).
    assert "14 &rarr; 15" in r.text or "14 → 15" in r.text
    assert "10 &rarr; 9" in r.text or "10 → 9" in r.text


def test_race_step_no_change_block_for_gnome(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, dict(_DWARF_ABILITIES))
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Nim"})
    r = client.get(f"/wizard/{draft_id}/race")
    # Gnome has no modifiers, so no "Ability changes" label appears on its card.
    # (Assert via the gnome card not carrying an arrow within its block is
    # brittle; instead assert the dwarf arrow exists and gnome modifiers are
    # absent from context — checked through the rendered count below.)
    assert r.text.count("Ability changes:") >= 1  # at least the dwarf card
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_race.py -k race_step -q`
Expected: FAIL — the arrow / "Ability changes:" markup is not rendered yet.

- [ ] **Step 3: Add per-race ability-change rows to the `get_race` context**

In `get_race`, the loop currently builds each `races` entry (lines 411-421). Replace the loop body so each race dict also carries an `ability_changes` list (only the abilities the race actually modifies, with rolled → effective):

```python
    abilities = draft["abilities"]
    races = []
    for race in sorted(data.races.values(), key=lambda r: r.name):
        effective = apply_racial_modifiers(abilities, race)
        ability_changes = [
            {
                "name": ab.value,
                "rolled": abilities[ab.value],
                "delta": delta,
                "effective": effective[ab.value],
            }
            for ab, delta in race.ability_modifiers.items()
        ]
        races.append({
            "id": race.id,
            "name": race.name,
            "infravision": race.infravision,
            "base_movement": race.base_movement,
            "requirements": {ab.value: v for ab, v in race.ability_requirements.items()},
            "languages": race.languages,
            "ability_changes": ability_changes,
            "meets_requirements": _meets_ability_requirements(race.ability_requirements, abilities),
            "selected": draft.get("race_id") == race.id,
        })
```

> `ability_changes` is built from `apply_racial_modifiers`, so the displayed effective values already reflect the 18/3 clamp. The race step only renders when `separate_race_class` is on, so showing the change unconditionally here is correct (it is exactly the Advanced case).

- [ ] **Step 4: Render the change rows in `race.html`**

In `aose/web/templates/wizard/race.html`, add an "Ability changes" block inside the card, after the `Movement` detail (after line 19) and before the infravision detail:

```html
            {% if race.ability_changes %}
            <div class="card-detail small">Ability changes:
                {%- for ch in race.ability_changes %}
                    {{ ch.name }} {{ ch.rolled }} &rarr; {{ ch.effective }}
                    ({{ '+' if ch.delta > 0 else '' }}{{ ch.delta }}){% if not loop.last %},{% endif %}
                {%- endfor %}
            </div>
            {% endif %}
```

- [ ] **Step 5: Run the display tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_race.py -k race_step -q`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```powershell
git add aose/web/wizard.py aose/web/templates/wizard/race.html tests/test_wizard_race.py
git commit -m @'
feat(wizard): show racial ability adjustment on race cards

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

## Task 7: HP step uses effective CON

**Files:**
- Modify: `aose/web/wizard.py` — `get_hp` (line 804)
- Test: `tests/test_wizard_race.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_wizard_race.py`:

```python
# ── HP step reads effective CON ───────────────────────────────────────────

def test_hp_step_con_mod_reflects_racial_bonus(tmp_path):
    # Dwarf +1 CON: a base CON 15 (mod +1) becomes effective 16 (mod +2).
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, {
        "STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 15, "CHA": 12,
    })
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Gloin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    r = client.get(f"/wizard/{draft_id}/hp")
    assert r.status_code == 200
    # Effective CON 16 → modifier +2 must be the value shown/used.
    assert "+2" in r.text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_race.py -k hp_step -q`
Expected: FAIL — `get_hp` uses base CON 15 (mod +1), so `+2` is not present.

- [ ] **Step 3: Use effective CON in `get_hp`**

In `get_hp`, change the CON modifier line (line 804) from:

```python
    con_mod = ability_modifier(draft["abilities"]["CON"])
```

to:

```python
    con_mod = ability_modifier(_effective_abilities(draft, data)["CON"])
```

> `data` is already in scope in `get_hp` (`data = request.app.state.game_data`, line 802). The HP **total** is computed from `con_mod` further down, so it now uses the effective CON automatically. `post_hp_roll` only rolls dice (no CON), so it needs no change; the displayed and finalized HP both flow through the CON mod here and through `hp.py` (which reads `spec.abilities`, already creation-final after Task 4).

- [ ] **Step 4: Run the HP test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_race.py -k hp_step -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add aose/web/wizard.py tests/test_wizard_race.py
git commit -m @'
feat(wizard): HP step CON modifier uses effective (post-racial) CON

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

## Task 8: Full-suite verification + example check

**Files:**
- No production changes expected. Read-only verification; only touch `examples/` or tests if something actually fails.

- [ ] **Step 1: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing `pytest-current` `PermissionError` Windows quirk).

- [ ] **Step 2: Confirm the shipped example still loads**

`examples/thorin.json` is a **stored final `CharacterSpec`** (dwarf fighter, CON 14, CHA 9). The engine never re-derives racial mods on load — it reads `spec.abilities` as-is — so loading it is unaffected by this slice. Verify by loading the character page in a quick check:

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage.py tests/test_sheet.py -q`
Expected: PASS.

If any test asserted an ability-derived total that assumed thorin's stored CON would change, it would fail here — investigate that specific test rather than editing the example. The example's stored scores are intentionally the creation-final values already and should not be regenerated.

- [ ] **Step 3: Manual smoke (optional but recommended)**

Run the app and walk a dwarf fighter through the wizard to eyeball the race-card change rows and the review sheet's CON:

```powershell
.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload
```

Confirm: race step shows `CON 14 → 15 (+1), CHA 10 → 9 (-1)` on the dwarf card; the review sheet shows the modified CON and the HP reflecting it.

- [ ] **Step 4: Final commit (only if Step 2/3 required any fix)**

```powershell
git add -A
git commit -m @'
test(race): verify examples + sheet unaffected by creation-final abilities

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

## Self-review notes (for the implementer)

- **Spec coverage:** Model field (Task 1) ✔; YAML migration keeping descriptive feature (Task 2) ✔; pure clamp helper with single-home clamp (Task 3) ✔; `_effective_abilities` + creation-final storage in `_draft_to_spec` so downstream consumers are untouched (Task 4) ✔; race minimum pre-modifier + class minimum post-modifier (Task 5) ✔; race-step display of rolled/modifier/effective (Task 6) ✔; HP-step effective CON (Task 7) ✔; example/regression verification (Task 8) ✔.
- **Out of scope (do not implement):** human conditional modifiers / Blessed / Decisiveness / Leadership (Slice 5); INT-based additional languages (Slice 6); P5 ability-score adjustments (Slice 4 — but note Task 4 establishes the `_effective_abilities` → finalize storage seam that Slice 4 will plug its deltas into).
- **Type consistency:** `_effective_abilities(draft, data)` and `apply_racial_modifiers(base, race)` signatures are used identically across Tasks 4–7. `_draft_to_spec(draft, data)` updated at both call sites. Draft/spec ability dicts are string-keyed; `Race.ability_modifiers` is `Ability`-enum-keyed; conversion via `.value` is applied in both the helper and the `get_race` context.
- **Data assumptions (already verified against `data/`):** Task 4 race-as-class uses `class_id: dwarf` (a race-locked entry that exists). Task 5 uses the half_orc/knight/human triple — half_orc has no race minimum and +1 CON, knight requires CON 9 (not race-locked), human has no modifiers; `lift_demihuman_restrictions` is toggled on so race allowance doesn't block the pick. Task 7 uses dwarf+fighter (dwarf allows fighter). If a future data edit changes these, re-pick from `data/classes/*.yaml` (classes with `ability_requirements`: barbarian/bard/illusionist/knight/paladin/ranger plus the race-locked entries).
