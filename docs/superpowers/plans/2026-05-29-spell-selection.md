# Spell Selection & Sheet Spell Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the wizard select a caster's starting *known* spells when their class casts at level 1, and let the live sheet manage both known spells and a slot-capped daily *prepared* loadout — all restricted to spells the character can actually access.

**Architecture:** Faithful AOSE known-vs-prepared model. Arcane/divine caster type lives on a new `SpellList` registry (so the type is decided once per list, not per class). A pure, cycle-free `aose/engine/spells.py` core mirrors `engine/magic.py`. Per-`ClassEntry` storage splits into `spellbook` (known) and `prepared` (daily). The standard-vs-advanced spellbook rules are exposed as the `advanced_spell_books` optional rule. Wizard sets known; sheet manages both, via shared route shapes.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, YAML data, pytest. Windows/PowerShell: run Python via `.venv\Scripts\python.exe`.

**Reference spec:** `docs/superpowers/specs/2026-05-29-spell-selection-design.md`

**Test command (used throughout):**
```
.venv\Scripts\python.exe -m pytest tests/ -q
```
(The trailing `PermissionError` on `pytest-current` is a known Windows pytest-9 tempdir quirk — ignore it.)

---

## File Structure

**New files**
- `aose/models/spell_list.py` — `SpellList` model (id, name, caster_type).
- `aose/engine/spells.py` — pure spell engine (derivation + mutators).
- `data/spell_lists.yaml` — registry seed (magic_user=arcane, druid=divine).
- `data/spells/magic_user_spells.yaml`, `data/spells/druid_spells.yaml` — seed L1 spells.
- `aose/web/templates/wizard/spells.html` — wizard spell step.
- `import/cribs/spell-list.md`, `import/prompts/phase2-spell-list.md` — import docs.
- `tests/test_spells.py` — model/loader/engine/view tests.
- `tests/test_spell_routes.py` — wizard + sheet HTTP route tests.

**Modified files**
- `aose/models/__init__.py` — export `SpellList`.
- `aose/models/character.py` — `ClassEntry`: replace `chosen_spells` with `spellbook` + `prepared`.
- `aose/data/loader.py` — load `spell_lists`.
- `aose/models/ruleset.py` — add `advanced_spell_books`.
- `aose/web/settings_routes.py` — wire `advanced_spell_books` (labels, group, implemented set).
- `aose/sheet/view.py` — `spells_view` + `CharacterSheet.spells`.
- `aose/web/routes.py` — sheet spell routes.
- `aose/web/wizard.py` — spells step (gating, handlers, draft→spec).
- `aose/web/templates/sheet.html` — Spells section.
- `data/classes/magic_user.yaml` — add `spell_lists: [magic_user]`.
- `examples/thorin.json` — drop `chosen_spells`.
- `tools/validate_import.py` — spell-list reference integrity.
- `import/cribs/class.md`, `import/cribs/spell.md` — reference the registry.
- `CLAUDE.md` — document the feature.

---

## Task 1: SpellList model + registry loader + seed

**Files:**
- Create: `aose/models/spell_list.py`
- Modify: `aose/models/__init__.py`
- Modify: `aose/data/loader.py`
- Create: `data/spell_lists.yaml`
- Test: `tests/test_spells.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_spells.py`:

```python
"""Spell selection: SpellList registry, loader, spell engine, and sheet view."""
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def test_spell_list_model_parses():
    from aose.models import SpellList
    sl = SpellList(id="magic_user", name="Magic-User", caster_type="arcane")
    assert sl.caster_type == "arcane"
    assert sl.description is None


def test_spell_list_rejects_bad_caster_type():
    from aose.models import SpellList
    with pytest.raises(ValueError):
        SpellList(id="x", name="X", caster_type="psionic")


def test_spell_list_forbids_extra_fields():
    from aose.models import SpellList
    with pytest.raises(ValueError):
        SpellList(id="x", name="X", caster_type="arcane", bogus=1)


def test_loader_reads_spell_lists():
    from aose.data.loader import GameData
    data = GameData.load(DATA_DIR)
    assert data.spell_lists["magic_user"].caster_type == "arcane"
    assert data.spell_lists["druid"].caster_type == "divine"


def test_loader_spell_lists_empty_when_absent(tmp_path):
    from aose.data.loader import GameData
    data = GameData.load(tmp_path)
    assert data.spell_lists == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -q`
Expected: FAIL — `ImportError: cannot import name 'SpellList'`.

- [ ] **Step 3: Create the SpellList model**

Create `aose/models/spell_list.py`:

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SpellList(BaseModel):
    """A spell pool / tradition (e.g. magic_user, druid).  Its ``caster_type``
    decides whether classes casting from it are arcane (spellbook, limited
    known) or divine (knows the whole list, prays daily).  Classes reference a
    list by id via ``CharClass.spell_lists``; spells via ``Spell.spell_lists``.
    """
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    caster_type: Literal["arcane", "divine"]
    description: str | None = None
```

- [ ] **Step 4: Export it from the models package**

In `aose/models/__init__.py`, add the import after the `Spell` import:

```python
from .spell import Spell
from .spell_list import SpellList
```

And add `"SpellList",` to `__all__` (next to `"Spell",`).

- [ ] **Step 5: Load the registry in GameData**

In `aose/data/loader.py`:

Add `SpellList` to the models import block:

```python
from aose.models import (
    CharClass,
    Item,
    Race,
    Spell,
    SpellList,
)
```

Add this loader helper after `_load_secondary_skills`:

```python
def _load_spell_lists(data_dir: Path) -> dict[str, SpellList]:
    """Read ``spell_lists.yaml`` (a list of mappings) into an id-keyed dict.

    Returns an empty dict when the file is absent so minimal test fixtures
    (a bare data dir) still load.
    """
    path = data_dir / "spell_lists.yaml"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    if not isinstance(raw, list):
        raise ValueError("spell_lists.yaml must be a YAML list of mappings")
    result: dict[str, SpellList] = {}
    for obj in raw:
        parsed = SpellList.model_validate(obj)
        result[parsed.id] = parsed
    return result
```

Add the field to the `GameData` dataclass (after `spells`):

```python
    spells: dict[str, Spell] = field(default_factory=dict)
    spell_lists: dict[str, SpellList] = field(default_factory=dict)
```

And populate it in `GameData.load`:

```python
        return cls(
            races=_load_models(data_dir / "races", Race),
            classes=_load_models(data_dir / "classes", CharClass),
            spells=_load_models(data_dir / "spells", Spell),
            spell_lists=_load_spell_lists(data_dir),
            items=_load_items(data_dir / "equipment"),
            secondary_skills=_load_secondary_skills(data_dir),
        )
```

- [ ] **Step 6: Create the registry seed**

Create `data/spell_lists.yaml`:

```yaml
- id: magic_user
  name: Magic-User
  caster_type: arcane
  description: Arcane spells learned through study and recorded in a spell book.
- id: druid
  name: Druid
  caster_type: divine
  description: Divine spells granted by nature; the whole list is known.
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -q`
Expected: PASS (5 tests).

- [ ] **Step 8: Commit**

```bash
git add aose/models/spell_list.py aose/models/__init__.py aose/data/loader.py data/spell_lists.yaml tests/test_spells.py
git commit -m "feat: SpellList registry model + loader + seed"
```

---

## Task 2: ClassEntry — replace chosen_spells with spellbook + prepared

**Files:**
- Modify: `aose/models/character.py:43-49`
- Modify: `examples/thorin.json:12-18`
- Test: `tests/test_spells.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_spells.py`:

```python
def test_class_entry_has_spellbook_and_prepared():
    from aose.models import ClassEntry
    e = ClassEntry(class_id="magic_user", level=1, hp_rolls=[3])
    assert e.spellbook == []
    assert e.prepared == []


def test_class_entry_rejects_old_chosen_spells_field():
    from aose.models import ClassEntry
    with pytest.raises(ValueError):
        ClassEntry(class_id="magic_user", chosen_spells=["x"])


def test_thorin_example_loads():
    import json
    from aose.models import CharacterSpec
    raw = json.loads((PROJECT_ROOT / "examples" / "thorin.json").read_text(encoding="utf-8"))
    spec = CharacterSpec.model_validate(raw)
    assert spec.classes[0].spellbook == []
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -k "class_entry or thorin" -q`
Expected: FAIL — `spellbook`/`prepared` don't exist; `chosen_spells` still accepted.

- [ ] **Step 3: Update the ClassEntry model**

In `aose/models/character.py`, replace the `ClassEntry` body:

```python
class ClassEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class_id: str
    level: int = 1
    hp_rolls: list[int] = Field(default_factory=list)
    # Known spells (arcane spellbook).  Empty for divine casters, who know
    # their whole list automatically; see aose/engine/spells.py.
    spellbook: list[str] = Field(default_factory=list)
    # Daily prepared / memorised loadout; duplicates allowed (memorise a spell
    # twice with two slots).  Hard-capped per spell level by spell_slots.
    prepared: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Update the example character**

In `examples/thorin.json`, change the class entry (remove the `chosen_spells` line and its trailing comma):

```json
  "classes": [
    {
      "class_id": "fighter",
      "level": 1,
      "hp_rolls": [7]
    }
  ],
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -k "class_entry or thorin" -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Run the full suite to catch fallout**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (no test referenced `chosen_spells` beyond the model + example, both updated). Fix any stragglers if they surface.

- [ ] **Step 7: Commit**

```bash
git add aose/models/character.py examples/thorin.json tests/test_spells.py
git commit -m "feat: ClassEntry spellbook + prepared (replaces unused chosen_spells)"
```

---

## Task 3: Seed spell data + class tags

**Files:**
- Create: `data/spells/magic_user_spells.yaml`
- Create: `data/spells/druid_spells.yaml`
- Modify: `data/classes/magic_user.yaml`
- Test: `tests/test_spells.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_spells.py`:

```python
def test_seed_spells_loaded_and_tagged():
    from aose.data.loader import GameData
    data = GameData.load(DATA_DIR)
    rm = data.spells["read_magic"]
    assert rm.level == 1
    assert "magic_user" in rm.spell_lists
    # detect_magic is shared by both lists
    dm = data.spells["detect_magic"]
    assert {"magic_user", "druid"} <= set(dm.spell_lists)


def test_magic_user_class_tags_its_list():
    from aose.data.loader import GameData
    data = GameData.load(DATA_DIR)
    assert data.classes["magic_user"].spell_lists == ["magic_user"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -k "seed_spells or class_tags" -q`
Expected: FAIL — `KeyError: 'read_magic'`.

- [ ] **Step 3: Create magic-user seed spells**

Create `data/spells/magic_user_spells.yaml`:

```yaml
- id: read_magic
  name: Read Magic
  level: 1
  spell_lists: [magic_user]
  source: ose-advanced
  range: "0 (caster)"
  duration: 1 turn
  description: >-
    The caster can read magical writing (e.g. spell books, scrolls). The spell
    does not activate the magic in writing, but reveals what it is.
- id: detect_magic
  name: Detect Magic
  level: 1
  spell_lists: [magic_user, druid]
  source: ose-advanced
  range: "60'"
  duration: 2 turns
  description: Magical items, places, or auras within range glow when viewed by the caster.
- id: magic_missile
  name: Magic Missile
  level: 1
  spell_lists: [magic_user]
  source: ose-advanced
  range: "150'"
  duration: instant
  description: >-
    A glowing dart speeds toward a target and strikes unerringly for 1d6+1
    damage. +1 missile at levels 6, 11, and 16.
- id: sleep
  name: Sleep
  level: 1
  spell_lists: [magic_user]
  source: ose-advanced
  range: "240'"
  duration: 4d4 turns
  description: >-
    Puts 2d8 Hit Dice of living creatures into an enchanted slumber. Affects the
    lowest-HD creatures first. Creatures of 4+1 HD or more are unaffected.
- id: charm_person
  name: Charm Person
  level: 1
  spell_lists: [magic_user]
  source: ose-advanced
  range: "120'"
  duration: until dispelled
  description: >-
    One humanoid creature of up to 4+1 HD must save versus spells or regard the
    caster as a trusted friend and ally.
```

- [ ] **Step 4: Create druid seed spells**

Create `data/spells/druid_spells.yaml`:

```yaml
- id: faerie_fire
  name: Faerie Fire
  level: 1
  spell_lists: [druid]
  source: ose-advanced
  range: "80'"
  duration: 1 turn
  description: >-
    Outlines targets in pale glowing light, granting attackers +2 to hit them.
- id: entangle
  name: Entangle
  level: 1
  spell_lists: [druid]
  source: ose-advanced
  range: "80'"
  duration: 1 turn
  description: >-
    Plants in the area of effect entangle and hold creatures that fail a save
    versus spells.
- id: predict_weather
  name: Predict Weather
  level: 1
  spell_lists: [druid]
  source: ose-advanced
  range: "0 (caster)"
  duration: 12 hours
  description: The caster learns the weather for the coming 12 hours within 1 mile.
```

(`detect_magic` lives in the magic-user file but is tagged for both lists — do not duplicate the id.)

- [ ] **Step 5: Tag the magic-user class with its list**

In `data/classes/magic_user.yaml`, add after the `shields_allowed:` line (before `progression:`):

```yaml
shields_allowed: false
spell_lists: [magic_user]
progression:
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -k "seed_spells or class_tags" -q`
Expected: PASS (2 tests).

- [ ] **Step 7: Run the import validator (cross-reference sanity)**

Run: `.venv\Scripts\python.exe tools/validate_import.py`
Expected: ends with `ALL OK` (no duplicate ids; GameData loads).

- [ ] **Step 8: Commit**

```bash
git add data/spells/magic_user_spells.yaml data/spells/druid_spells.yaml data/classes/magic_user.yaml tests/test_spells.py
git commit -m "data: seed L1 magic-user + druid spells; tag magic_user spell list"
```

---

## Task 4: `advanced_spell_books` optional rule

**Files:**
- Modify: `aose/models/ruleset.py:13-22`
- Modify: `aose/web/settings_routes.py`
- Test: `tests/test_spells.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_spells.py`:

```python
def test_ruleset_has_advanced_spell_books_default_off():
    from aose.models import RuleSet
    assert RuleSet().advanced_spell_books is False


def test_advanced_spell_books_is_wired():
    from aose.web.settings_routes import IMPLEMENTED_RULES, RULE_GROUPS, RULE_LABELS
    assert "advanced_spell_books" in IMPLEMENTED_RULES
    assert "advanced_spell_books" in RULE_LABELS
    all_group_fields = {f for _, fields in RULE_GROUPS for f, _ in fields}
    assert "advanced_spell_books" in all_group_fields
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -k "advanced_spell_books or has_advanced" -q`
Expected: FAIL — attribute / membership errors.

- [ ] **Step 3: Add the RuleSet field**

In `aose/models/ruleset.py`, add to the `RuleSet` body (after `variable_weapon_damage`):

```python
    variable_weapon_damage: bool = False
    advanced_spell_books: bool = False
```

- [ ] **Step 4: Wire it into settings**

In `aose/web/settings_routes.py`:

Add to `RULE_LABELS`:

```python
    "multiclassing": "Multiclassing",
    "advanced_spell_books": "Advanced Spell Books",
}
```

Add to `IMPLEMENTED_RULES`:

```python
    "variable_weapon_damage",
    "advanced_spell_books",
}
```

Add a new group to the end of the `RULE_GROUPS` list (after the "Skills & Multiclass" tuple):

```python
    ("Magic", [
        ("advanced_spell_books",
         "Arcane spell books have no size limit and the number of beginning "
         "spells is set by Intelligence. Off = standard rules: the book holds "
         "exactly the spells the caster can memorise."),
    ]),
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -k "advanced_spell_books or has_advanced" -q`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add aose/models/ruleset.py aose/web/settings_routes.py tests/test_spells.py
git commit -m "feat: advanced_spell_books optional rule, wired end-to-end"
```

---

## Task 5: `engine/spells.py` — derivation helpers

**Files:**
- Create: `aose/engine/spells.py`
- Test: `tests/test_spells.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_spells.py`:

```python
from aose.models import CharacterSpec, ClassEntry, RuleSet


def _spec(class_id, level=1, abilities=None, spellbook=None, prepared=None, advanced=False):
    ab = abilities or {"STR": 10, "INT": 13, "WIS": 13, "DEX": 10, "CON": 10, "CHA": 10}
    return CharacterSpec(
        name="T", abilities=ab, race_id="human",
        classes=[ClassEntry(class_id=class_id, level=level, hp_rolls=[3],
                            spellbook=spellbook or [], prepared=prepared or [])],
        alignment="neutral",
        ruleset=RuleSet(advanced_spell_books=advanced),
    )


def test_caster_type_of():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    assert spells.caster_type_of(data.classes["magic_user"], data) == "arcane"
    assert spells.caster_type_of(data.classes["druid"], data) == "divine"
    assert spells.caster_type_of(data.classes["fighter"], data) is None


def test_accessible_levels_and_slots():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="magic_user", level=1)
    cls = data.classes["magic_user"]
    assert spells.accessible_levels(e, cls) == {1}
    assert spells.memorizable_slots(e, cls) == {1: 1}


def test_divine_known_is_full_accessible_list():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="druid", level=1)
    cls = data.classes["druid"]
    known_ids = {s.id for s in spells.known_spells(e, cls, data)}
    assert {"faerie_fire", "entangle", "predict_weather", "detect_magic"} <= known_ids


def test_arcane_known_is_just_the_spellbook():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_missile"])
    cls = data.classes["magic_user"]
    assert [s.id for s in spells.known_spells(e, cls, data)] == ["magic_missile"]


def test_learnable_excludes_known_and_off_level():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_missile"])
    cls = data.classes["magic_user"]
    ids = {s.id for s in spells.learnable_spells(e, cls, data)}
    assert "magic_missile" not in ids          # already known
    assert "read_magic" in ids                  # available, not known
    assert all(s.level == 1 for s in spells.learnable_spells(e, cls, data))


def test_beginning_spell_count_standard_vs_advanced():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="magic_user", level=1)
    cls = data.classes["magic_user"]
    # standard: total memorizable at L1 == 1
    assert spells.beginning_spell_count(e, cls, 13, RuleSet()) == 1
    # advanced: INT table — 13 -> 3, 10 -> 3, 9 -> 2, 18 -> 5
    adv = RuleSet(advanced_spell_books=True)
    assert spells.beginning_spell_count(e, cls, 13, adv) == 3
    assert spells.beginning_spell_count(e, cls, 9, adv) == 2
    assert spells.beginning_spell_count(e, cls, 18, adv) == 5
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -k "caster_type or accessible or known or learnable or beginning" -q`
Expected: FAIL — `ModuleNotFoundError: aose.engine.spells`.

- [ ] **Step 3: Create the engine derivation core**

Create `aose/engine/spells.py`:

```python
"""Spell engine — the cycle-free core for spell access, known/prepared sets,
and spellbook/prepared mutations.

Imports only models + the data loader (like ``engine/magic.py``); no derivation
module imports it back.  Arcane vs divine is read from the SpellList registry,
not the class.
"""
from __future__ import annotations

from typing import Literal

from aose.data.loader import GameData
from aose.models import CharClass, ClassEntry, RuleSet, Spell

CasterType = Literal["arcane", "divine"]


class SpellError(ValueError):
    """Base for all spell access / mutation errors (routes map to HTTP 400)."""


# ── Derivation / queries ──────────────────────────────────────────────────

def caster_type_of(cls: CharClass, data: GameData) -> CasterType | None:
    """The common caster type of the class's referenced spell lists.

    Returns None for a non-caster (no spell_lists).  Raises if a referenced
    list is unknown, or if the class mixes arcane and divine lists (AOSE has
    no such class)."""
    if not cls.spell_lists:
        return None
    types: set[CasterType] = set()
    for list_id in cls.spell_lists:
        sl = data.spell_lists.get(list_id)
        if sl is None:
            raise SpellError(f"{cls.id!r} references unknown spell list {list_id!r}")
        types.add(sl.caster_type)
    if len(types) > 1:
        raise SpellError(f"{cls.id!r} mixes arcane and divine spell lists")
    return next(iter(types))


def _level_row(entry: ClassEntry, cls: CharClass):
    return cls.progression.get(entry.level)


def accessible_levels(entry: ClassEntry, cls: CharClass) -> set[int]:
    """Spell levels the class can cast at the entry's level (has ≥1 slot)."""
    row = _level_row(entry, cls)
    if row is None or not row.spell_slots:
        return set()
    return {lvl for lvl, n in row.spell_slots.items() if n > 0}


def memorizable_slots(entry: ClassEntry, cls: CharClass) -> dict[int, int]:
    """spell-level -> slot count at the entry's level.  Prepared cap, and (under
    standard rules) the per-level spellbook size.  Empty if no casting yet."""
    row = _level_row(entry, cls)
    if row is None or not row.spell_slots:
        return {}
    return dict(row.spell_slots)


def _on_class_lists(spell: Spell, cls: CharClass) -> bool:
    return bool(set(spell.spell_lists) & set(cls.spell_lists))


def known_spells(entry: ClassEntry, cls: CharClass, data: GameData) -> list[Spell]:
    """Spells the character knows.

    arcane: the resolved spellbook (in stored order).
    divine: every spell on the class's lists at an accessible level (by id order).
    """
    ctype = caster_type_of(cls, data)
    if ctype == "arcane":
        return [data.spells[s] for s in entry.spellbook if s in data.spells]
    if ctype == "divine":
        levels = accessible_levels(entry, cls)
        return sorted(
            (s for s in data.spells.values()
             if _on_class_lists(s, cls) and s.level in levels),
            key=lambda s: (s.level, s.name),
        )
    return []


def learnable_spells(entry: ClassEntry, cls: CharClass, data: GameData) -> list[Spell]:
    """Arcane-only: accessible-level spells on the class's lists not yet known."""
    if caster_type_of(cls, data) != "arcane":
        return []
    levels = accessible_levels(entry, cls)
    known = set(entry.spellbook)
    return sorted(
        (s for s in data.spells.values()
         if _on_class_lists(s, cls) and s.level in levels and s.id not in known),
        key=lambda s: (s.level, s.name),
    )


_INT_BEGINNING_SPELLS = [
    (3, 1), (5, 1), (7, 2), (9, 2), (12, 3), (14, 3), (16, 4), (17, 4), (18, 5),
]


def beginning_spells_for_int(int_score: int) -> int:
    """OSE Advanced 'Advanced Spell Book Rules' beginning-spells table (p112)."""
    for ceiling, count in _INT_BEGINNING_SPELLS:
        if int_score <= ceiling:
            return count
    return 5  # INT 18+


def beginning_spell_count(entry: ClassEntry, cls: CharClass, int_score: int,
                          ruleset: RuleSet) -> int:
    """How many spells an arcane caster begins with.

    advanced rule: INT-table lookup.  standard: total memorizable at the
    entry's level (sum of slots; 1 for an L1 magic-user).
    """
    if ruleset.advanced_spell_books:
        return beginning_spells_for_int(int_score)
    return sum(memorizable_slots(entry, cls).values())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -k "caster_type or accessible or known or learnable or beginning" -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/spells.py tests/test_spells.py
git commit -m "feat: spell engine derivation (caster type, known/learnable, beginning count)"
```

---

## Task 6: `engine/spells.py` — mutators (learn / forget / prepare / unprepare)

**Files:**
- Modify: `aose/engine/spells.py`
- Test: `tests/test_spells.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_spells.py`:

```python
def test_learn_adds_to_spellbook():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="magic_user", level=1, spellbook=[])
    cls = data.classes["magic_user"]
    e2 = spells.learn(e, cls, data, RuleSet(), "magic_missile")
    assert e2.spellbook == ["magic_missile"]
    assert e.spellbook == []  # original untouched


def test_learn_rejects_off_list_or_off_level():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="magic_user", level=1)
    cls = data.classes["magic_user"]
    with pytest.raises(spells.SpellError):
        spells.learn(e, cls, data, RuleSet(), "faerie_fire")   # druid-only


def test_learn_standard_caps_at_memorizable():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    # L1 magic-user: standard cap at level 1 == 1 spell
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_missile"])
    cls = data.classes["magic_user"]
    with pytest.raises(spells.SpellError):
        spells.learn(e, cls, data, RuleSet(), "sleep")
    # advanced rules: uncapped
    e3 = spells.learn(e, cls, data, RuleSet(advanced_spell_books=True), "sleep")
    assert set(e3.spellbook) == {"magic_missile", "sleep"}


def test_learn_rejects_divine():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="druid", level=1)
    with pytest.raises(spells.SpellError):
        spells.learn(e, data.classes["druid"], data, RuleSet(), "faerie_fire")


def test_forget_removes():
    from aose.engine import spells
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_missile", "sleep"])
    e2 = spells.forget(e, "magic_missile")
    assert e2.spellbook == ["sleep"]


def test_prepare_respects_known_and_slot_cap():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    cls = data.classes["magic_user"]
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_missile"])
    e2 = spells.prepare(e, cls, data, "magic_missile")
    assert e2.prepared == ["magic_missile"]
    # second prepare at level 1 exceeds the single slot
    with pytest.raises(spells.SpellError):
        spells.prepare(e2, cls, data, "magic_missile")
    # preparing an unknown (not in book) spell fails
    with pytest.raises(spells.SpellError):
        spells.prepare(e, cls, data, "sleep")


def test_prepare_divine_from_full_list():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    cls = data.classes["druid"]
    e = ClassEntry(class_id="druid", level=1)
    e2 = spells.prepare(e, cls, data, "faerie_fire")  # known via full list
    assert e2.prepared == ["faerie_fire"]


def test_unprepare_removes_one_instance():
    from aose.engine import spells
    e = ClassEntry(class_id="druid", level=1, prepared=["faerie_fire", "faerie_fire"])
    e2 = spells.unprepare(e, "faerie_fire")
    assert e2.prepared == ["faerie_fire"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -k "learn or forget or prepare or unprepare" -q`
Expected: FAIL — mutators not defined.

- [ ] **Step 3: Add the mutators**

Append to `aose/engine/spells.py`:

```python
# ── Mutators (return a new ClassEntry; raise SpellError on violation) ───────

def _require_spell(data: GameData, spell_id: str) -> Spell:
    spell = data.spells.get(spell_id)
    if spell is None:
        raise SpellError(f"Unknown spell {spell_id!r}")
    return spell


def learn(entry: ClassEntry, cls: CharClass, data: GameData, ruleset: RuleSet,
          spell_id: str) -> ClassEntry:
    """Add a spell to an arcane caster's spellbook.

    Enforces: arcane only; spell on a class list and at an accessible level;
    not already known; and (standard rules) the per-level spellbook cap."""
    if caster_type_of(cls, data) != "arcane":
        raise SpellError(f"{cls.id!r} is not an arcane caster; nothing to learn")
    spell = _require_spell(data, spell_id)
    if not _on_class_lists(spell, cls):
        raise SpellError(f"{spell_id!r} is not on {cls.id!r}'s spell list")
    if spell.level not in accessible_levels(entry, cls):
        raise SpellError(f"{spell_id!r} (level {spell.level}) is not castable yet")
    if spell_id in entry.spellbook:
        raise SpellError(f"{spell_id!r} is already known")
    if not ruleset.advanced_spell_books:
        cap = memorizable_slots(entry, cls).get(spell.level, 0)
        have = sum(1 for s in entry.spellbook
                   if s in data.spells and data.spells[s].level == spell.level)
        if have >= cap:
            raise SpellError(
                f"Standard spell-book rules: only {cap} level-{spell.level} "
                f"spell(s) may be known at this level"
            )
    return entry.model_copy(update={"spellbook": [*entry.spellbook, spell_id]})


def forget(entry: ClassEntry, spell_id: str) -> ClassEntry:
    if spell_id not in entry.spellbook:
        raise SpellError(f"{spell_id!r} is not in the spell book")
    book = list(entry.spellbook)
    book.remove(spell_id)
    return entry.model_copy(update={"spellbook": book})


def prepare(entry: ClassEntry, cls: CharClass, data: GameData,
            spell_id: str) -> ClassEntry:
    """Add a spell to the daily prepared loadout.

    Enforces: spell is known (arcane spellbook / divine full list) and a free
    slot exists at its level (hard cap)."""
    spell = _require_spell(data, spell_id)
    known_ids = {s.id for s in known_spells(entry, cls, data)}
    if spell_id not in known_ids:
        raise SpellError(f"{spell_id!r} is not known and cannot be prepared")
    cap = memorizable_slots(entry, cls).get(spell.level, 0)
    used = sum(1 for s in entry.prepared
               if s in data.spells and data.spells[s].level == spell.level)
    if used >= cap:
        raise SpellError(
            f"No free level-{spell.level} slot (cap {cap})"
        )
    return entry.model_copy(update={"prepared": [*entry.prepared, spell_id]})


def unprepare(entry: ClassEntry, spell_id: str) -> ClassEntry:
    if spell_id not in entry.prepared:
        raise SpellError(f"{spell_id!r} is not prepared")
    prep = list(entry.prepared)
    prep.remove(spell_id)
    return entry.model_copy(update={"prepared": prep})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -k "learn or forget or prepare or unprepare" -q`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/spells.py tests/test_spells.py
git commit -m "feat: spell engine mutators (learn/forget/prepare/unprepare)"
```

---

## Task 7: Sheet view — `spells_view` + `CharacterSheet.spells`

**Files:**
- Modify: `aose/sheet/view.py`
- Test: `tests/test_spells.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_spells.py`:

```python
def test_spells_view_arcane_shape():
    from aose.data.loader import GameData
    from aose.sheet.view import build_sheet
    data = GameData.load(DATA_DIR)
    spec = _spec("magic_user", spellbook=["magic_missile"], prepared=["magic_missile"])
    sheet = build_sheet(spec, data)
    assert len(sheet.spells) == 1
    block = sheet.spells[0]
    assert block.caster_type == "arcane"
    assert block.can_learn is True
    assert [s.id for s in block.known] == ["magic_missile"]
    # prepared grouped by level with slot counts
    grp = block.prepared_groups[0]
    assert grp.level == 1 and grp.slots == 1
    assert [s.id for s in grp.prepared] == ["magic_missile"]
    assert any(s.id == "read_magic" for s in block.learnable)


def test_spells_view_divine_shape():
    from aose.data.loader import GameData
    from aose.sheet.view import build_sheet
    data = GameData.load(DATA_DIR)
    spec = _spec("druid", abilities={"STR": 10, "INT": 10, "WIS": 13,
                                     "DEX": 10, "CON": 10, "CHA": 10})
    sheet = build_sheet(spec, data)
    block = sheet.spells[0]
    assert block.caster_type == "divine"
    assert block.can_learn is False
    assert block.learnable == []
    assert {s.id for s in block.known} >= {"faerie_fire", "entangle"}


def test_spells_view_empty_for_noncaster():
    from aose.data.loader import GameData
    from aose.sheet.view import build_sheet
    data = GameData.load(DATA_DIR)
    spec = _spec("fighter")
    sheet = build_sheet(spec, data)
    assert sheet.spells == []
```

(Note: `_spec` for druid needs `race_id="human"` — already the default in the helper. The druid class is not race-locked, so a human druid builds fine for the view test.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -k "spells_view" -q`
Expected: FAIL — `CharacterSheet` has no `spells`.

- [ ] **Step 3: Add view models + builder**

In `aose/sheet/view.py`:

Add `spells` to the engine import line:

```python
from aose.engine import ability_mods, armor_class, attack_bonus, hp, saves, spells as spell_engine
```

Add these view models near `MagicItemView` (before `CharacterSheet`):

```python
class SpellEntryView(BaseModel):
    id: str
    name: str
    level: int
    description: str
    reversible: bool


class SpellLevelGroup(BaseModel):
    level: int
    slots: int
    prepared: list[SpellEntryView]


class SpellClassView(BaseModel):
    class_id: str
    class_name: str
    caster_type: str            # "arcane" | "divine"
    can_learn: bool             # arcane only
    known: list[SpellEntryView]
    prepared_groups: list[SpellLevelGroup]
    learnable: list[SpellEntryView]
```

Add `spells` to `CharacterSheet` (after `magic_items`):

```python
    magic_items: list[MagicItemView]
    spells: list["SpellClassView"]
```

Add the builder function (before `build_sheet`):

```python
def _spell_entry(spell) -> SpellEntryView:
    return SpellEntryView(
        id=spell.id, name=spell.name, level=spell.level,
        description=spell.description, reversible=spell.reversible,
    )


def spells_view(spec: CharacterSpec, data: GameData) -> list["SpellClassView"]:
    """One block per casting class entry; shared by the live sheet and the
    wizard review.  Arcane blocks expose learnable spells; divine know their
    whole accessible list."""
    out: list[SpellClassView] = []
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        ctype = spell_engine.caster_type_of(cls, data)
        if ctype is None:
            continue
        known = spell_engine.known_spells(entry, cls, data)
        slots = spell_engine.memorizable_slots(entry, cls)
        groups: list[SpellLevelGroup] = []
        for level in sorted(slots):
            prepared_here = [
                _spell_entry(data.spells[s]) for s in entry.prepared
                if s in data.spells and data.spells[s].level == level
            ]
            groups.append(SpellLevelGroup(level=level, slots=slots[level],
                                          prepared=prepared_here))
        out.append(SpellClassView(
            class_id=entry.class_id,
            class_name=cls.name,
            caster_type=ctype,
            can_learn=(ctype == "arcane"),
            known=[_spell_entry(s) for s in known],
            prepared_groups=groups,
            learnable=[_spell_entry(s) for s in spell_engine.learnable_spells(entry, cls, data)],
        ))
    return out
```

Wire it into `build_sheet`'s return (after `magic_items=_magic_items(spec, data),`):

```python
        magic_items=_magic_items(spec, data),
        spells=spells_view(spec, data),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -k "spells_view" -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full suite (build_sheet is widely used)**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/sheet/view.py tests/test_spells.py
git commit -m "feat: spells_view + CharacterSheet.spells"
```

---

## Task 8: Sheet template + sheet spell routes

**Files:**
- Modify: `aose/web/routes.py`
- Modify: `aose/web/templates/sheet.html`
- Test: `tests/test_spell_routes.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_spell_routes.py`:

```python
"""HTTP route tests for spell management on the live sheet and in the wizard."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, load_draft, save_character, save_draft
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.web.app import create_app

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
        data_dir=DATA_DIR, characters_dir=characters_dir, drafts_dir=drafts_dir,
        examples_dir=examples_dir, settings_path=settings_path,
    )
    c = TestClient(app, follow_redirects=False)
    c._characters_dir = characters_dir
    c._drafts_dir = drafts_dir
    return c


def _save_mu(client, spellbook=None, prepared=None, advanced=False):
    spec = CharacterSpec(
        name="Mu", abilities={"STR": 10, "INT": 13, "WIS": 10,
                              "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="magic_user", level=1, hp_rolls=[3],
                            spellbook=spellbook or [], prepared=prepared or [])],
        alignment="neutral", ruleset=RuleSet(advanced_spell_books=advanced),
    )
    save_character("mu", spec, client._characters_dir)
    return spec


def test_sheet_learn_route(client):
    _save_mu(client, advanced=True)
    r = client.post("/character/mu/spells/learn",
                    data={"class_id": "magic_user", "spell_id": "magic_missile"})
    assert r.status_code == 303
    spec = load_character("mu", client._characters_dir)
    assert spec.classes[0].spellbook == ["magic_missile"]


def test_sheet_prepare_and_unprepare(client):
    _save_mu(client, spellbook=["magic_missile"])
    client.post("/character/mu/spells/prepare",
                data={"class_id": "magic_user", "spell_id": "magic_missile"})
    assert load_character("mu", client._characters_dir).classes[0].prepared == ["magic_missile"]
    client.post("/character/mu/spells/unprepare",
                data={"class_id": "magic_user", "spell_id": "magic_missile"})
    assert load_character("mu", client._characters_dir).classes[0].prepared == []


def test_sheet_prepare_over_cap_400(client):
    _save_mu(client, spellbook=["magic_missile"], prepared=["magic_missile"])
    r = client.post("/character/mu/spells/prepare",
                    data={"class_id": "magic_user", "spell_id": "magic_missile"})
    assert r.status_code == 400


def test_sheet_forget_route(client):
    _save_mu(client, spellbook=["magic_missile"])
    client.post("/character/mu/spells/forget",
                data={"class_id": "magic_user", "spell_id": "magic_missile"})
    assert load_character("mu", client._characters_dir).classes[0].spellbook == []


def test_sheet_renders_spells_section(client):
    _save_mu(client, spellbook=["magic_missile"], prepared=["magic_missile"])
    r = client.get("/character/mu")
    assert r.status_code == 200
    assert "Magic Missile" in r.text
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_routes.py -k "sheet" -q`
Expected: FAIL — routes return 404 / section absent.

- [ ] **Step 3: Add the sheet spell routes**

In `aose/web/routes.py`, add to the imports block:

```python
from aose.engine import spells as spell_engine
```

Add a helper + the four routes at the end of the file:

```python
# ── Spell management on the live sheet ─────────────────────────────────────

def _find_class_entry(spec, class_id: str) -> int:
    for i, e in enumerate(spec.classes):
        if e.class_id == class_id:
            return i
    raise HTTPException(400, f"Character has no class {class_id!r}")


@router.post("/character/{character_id}/spells/learn")
async def sheet_spell_learn(request: Request, character_id: str,
                            class_id: str = Form(...), spell_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = spell_engine.learn(
            spec.classes[idx], data.classes[class_id], data, spec.ruleset, spell_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/spells/forget")
async def sheet_spell_forget(request: Request, character_id: str,
                             class_id: str = Form(...), spell_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = spell_engine.forget(spec.classes[idx], spell_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/spells/prepare")
async def sheet_spell_prepare(request: Request, character_id: str,
                              class_id: str = Form(...), spell_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = spell_engine.prepare(
            spec.classes[idx], data.classes[class_id], data, spell_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/spells/unprepare")
async def sheet_spell_unprepare(request: Request, character_id: str,
                                class_id: str = Form(...), spell_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = spell_engine.unprepare(spec.classes[idx], spell_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Add the Spells section to the sheet template**

In `aose/web/templates/sheet.html`, insert this block immediately after the Magic Items section's closing `{% endif %}` (the line at/near 302, before `<section class="section"><h2>Equipment</h2>`):

```html
            {% if sheet.spells %}
            <section class="section">
                <h2>Spells</h2>
                {% for block in sheet.spells %}
                <div class="spell-block">
                    <h3>{{ block.class_name }}
                        <span class="small muted">({{ block.caster_type }})</span></h3>

                    <h4>Prepared</h4>
                    {% for grp in block.prepared_groups %}
                    <div class="spell-level">
                        <strong>Level {{ grp.level }}</strong>
                        <span class="small muted">{{ grp.prepared | length }} / {{ grp.slots }}</span>
                        <ul>
                            {% for s in grp.prepared %}
                            <li>
                                {{ s.name }}
                                <form method="post" class="no-print inline"
                                      action="/character/{{ character_id }}/spells/unprepare">
                                    <input type="hidden" name="class_id" value="{{ block.class_id }}">
                                    <input type="hidden" name="spell_id" value="{{ s.id }}">
                                    <button type="submit" class="link-button">unprepare</button>
                                </form>
                            </li>
                            {% endfor %}
                        </ul>
                    </div>
                    {% endfor %}

                    <h4>Known</h4>
                    <ul>
                        {% for s in block.known %}
                        <li>
                            <strong>{{ s.name }}</strong> <span class="small muted">(L{{ s.level }})</span>
                            <form method="post" class="no-print inline"
                                  action="/character/{{ character_id }}/spells/prepare">
                                <input type="hidden" name="class_id" value="{{ block.class_id }}">
                                <input type="hidden" name="spell_id" value="{{ s.id }}">
                                <button type="submit" class="link-button">prepare</button>
                            </form>
                            {% if block.can_learn %}
                            <form method="post" class="no-print inline"
                                  action="/character/{{ character_id }}/spells/forget">
                                <input type="hidden" name="class_id" value="{{ block.class_id }}">
                                <input type="hidden" name="spell_id" value="{{ s.id }}">
                                <button type="submit" class="link-button">forget</button>
                            </form>
                            {% endif %}
                            <details class="spell-desc">
                                <summary class="small muted">Description</summary>
                                <div class="feature-text">{{ s.description }}</div>
                            </details>
                        </li>
                        {% endfor %}
                    </ul>

                    {% if block.can_learn and block.learnable %}
                    <form method="post" class="no-print"
                          action="/character/{{ character_id }}/spells/learn">
                        <input type="hidden" name="class_id" value="{{ block.class_id }}">
                        <label>Learn a spell:
                            <select name="spell_id">
                                {% for s in block.learnable %}
                                <option value="{{ s.id }}">{{ s.name }} (L{{ s.level }})</option>
                                {% endfor %}
                            </select>
                        </label>
                        <button type="submit" class="primary">Add to spell book</button>
                    </form>
                    {% endif %}
                </div>
                {% endfor %}
            </section>
            {% endif %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_routes.py -k "sheet" -q`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add aose/web/routes.py aose/web/templates/sheet.html tests/test_spell_routes.py
git commit -m "feat: sheet Spells section + learn/forget/prepare/unprepare routes"
```

---

## Task 9: Wizard spells step

**Files:**
- Modify: `aose/web/wizard.py`
- Create: `aose/web/templates/wizard/spells.html`
- Test: `tests/test_spell_routes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_spell_routes.py`:

```python
def _start_caster_draft(client, class_id, int_score=13, advanced=False):
    """Drive the wizard to just-before the spells step for a single caster."""
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].rsplit("/", 2)[1]
    # Force abilities so the class requirement (INT 9) is met, and set rules.
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 10, "INT": int_score, "WIS": 13,
                          "DEX": 10, "CON": 10, "CHA": 10}
    draft["ruleset"]["advanced_spell_books"] = advanced
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Caster"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": class_id})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "neutral"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    return draft_id


def test_wizard_skips_spells_for_noncaster(client):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].rsplit("/", 2)[1]
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Grog"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    r = client.post(f"/wizard/{draft_id}/hp")
    # Non-caster: HP advances straight to equipment, not spells.
    assert r.headers["location"].endswith("/equipment")


def test_wizard_arcane_requires_exact_count(client):
    draft_id = _start_caster_draft(client, "magic_user")  # standard -> 1 spell
    r = client.get(f"/wizard/{draft_id}/spells")
    assert r.status_code == 200 and "Magic Missile" in r.text
    # too many rejected
    bad = client.post(f"/wizard/{draft_id}/spells",
                      data={"class_id": "magic_user",
                            "spell_id": ["magic_missile", "sleep"]})
    assert bad.status_code == 400
    # exactly one accepted
    ok = client.post(f"/wizard/{draft_id}/spells",
                     data={"class_id": "magic_user", "spell_id": ["magic_missile"]})
    assert ok.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["spellbooks"]["magic_user"] == ["magic_missile"]


def test_wizard_divine_autocompletes(client):
    draft_id = _start_caster_draft(client, "druid", int_score=10)
    r = client.get(f"/wizard/{draft_id}/spells")
    assert r.status_code == 200 and "know" in r.text.lower()
    # divine submits nothing; the step completes and advances to equipment
    r = client.post(f"/wizard/{draft_id}/spells", data={"class_id": "druid"})
    assert r.headers["location"].endswith("/equipment")


def test_wizard_finalize_persists_spellbook(client):
    draft_id = _start_caster_draft(client, "magic_user")
    client.post(f"/wizard/{draft_id}/spells",
                data={"class_id": "magic_user", "spell_id": ["magic_missile"]})
    client.get(f"/wizard/{draft_id}/equipment")
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].rsplit("/", 1)[1]
    spec = load_character(char_id, client._characters_dir)
    assert spec.classes[0].spellbook == ["magic_missile"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_routes.py -k "wizard" -q`
Expected: FAIL — no spells step / route.

- [ ] **Step 3: Wire the step into the wizard scaffolding**

In `aose/web/wizard.py`:

Add `"spells": "Spells",` to `STEP_LABELS` (after `"hp"`):

```python
    "hp": "Hit Points",
    "spells": "Spells",
    "equipment": "Equipment",
```

Add the spell engine import (with the other engine imports):

```python
from aose.engine import spells as spell_engine
```

In `_wizard_steps`, replace the final `steps += ["hp", "equipment", "review"]` line:

```python
    steps.append("hp")
    if draft.get("spellcasting"):
        steps.append("spells")
    steps += ["equipment", "review"]
    return steps
```

Add a helper near `_class_ids` to detect L1 casting (no game_data needed):

```python
def _casts_at_level_1(cls) -> bool:
    """True if the class has a spell list and at least one spell slot at L1."""
    row = cls.progression.get(1)
    return bool(cls.spell_lists) and bool(row and row.spell_slots)
```

In `_next_incomplete_step`, insert the spells check between the HP check and the
equipment check:

```python
    if not _has_hp(draft):
        return "hp"
    if draft.get("spellcasting") and not draft.get("spells_done"):
        return "spells"
    if "gold" not in draft:
        return "equipment"
    return "review"
```

In each of the three clear helpers, also drop the spell keys. Change them to:

```python
def _clear_after_abilities(draft: dict[str, Any]) -> None:
    for k in ("race_id", "class_id", "class_ids", "hp_roll", "hp_rolls",
             "proficiencies", "spellcasting", "spellbooks", "spells_done"):
        draft.pop(k, None)


def _clear_after_race(draft: dict[str, Any]) -> None:
    for k in ("class_id", "class_ids", "hp_roll", "hp_rolls", "proficiencies",
             "spellcasting", "spellbooks", "spells_done"):
        draft.pop(k, None)


def _clear_after_class(draft: dict[str, Any]) -> None:
    for k in ("hp_roll", "hp_rolls", "proficiencies",
             "spellcasting", "spellbooks", "spells_done"):
        draft.pop(k, None)
```

- [ ] **Step 4: Set the spellcasting flag when a class is picked**

In `post_class` (both the single-class and multi-class branches), set the flag
just before each `save_draft(...)` call. Add this helper above `post_class`:

```python
def _set_spellcasting_flag(draft: dict[str, Any], data) -> None:
    """Cache whether any picked class casts at L1 so the draft-only step
    helpers (_wizard_steps / _next_incomplete_step) can gate the spells step."""
    draft["spellcasting"] = any(
        _casts_at_level_1(data.classes[cid]) for cid in _class_ids(draft)
    )
```

In the single-class branch, after `draft["class_id"] = cid` and before
`save_draft(...)`:

```python
        draft.pop("class_ids", None)
        draft["class_id"] = cid
        _set_spellcasting_flag(draft, data)
        save_draft(draft_id, draft, _drafts_dir(request))
```

In the multi-class branch, after `draft["class_ids"] = ids` and before
`save_draft(...)`:

```python
    draft.pop("class_id", None)
    draft["class_ids"] = ids
    _set_spellcasting_flag(draft, data)
    save_draft(draft_id, draft, _drafts_dir(request))
```

- [ ] **Step 5: Add the GET and POST handlers**

In `aose/web/wizard.py`, add after the `post_hp` handler (before the Equipment
section):

```python
# ── Spells (optional step; only when a picked class casts at L1) ───────────

def _caster_entries(draft: dict[str, Any], data) -> list[dict]:
    """Per-casting-class rendering rows for the spells step."""
    abilities = draft["abilities"]
    ruleset = _ruleset_of(draft)
    int_score = abilities.get("INT", 10)
    books = draft.get("spellbooks", {})
    rows: list[dict] = []
    for cid in _class_ids(draft):
        cls = data.classes[cid]
        if not _casts_at_level_1(cls):
            continue
        entry = ClassEntry(class_id=cid, level=1, spellbook=books.get(cid, []))
        ctype = spell_engine.caster_type_of(cls, data)
        candidates = sorted(
            (s for s in data.spells.values()
             if set(s.spell_lists) & set(cls.spell_lists)
             and s.level in spell_engine.accessible_levels(entry, cls)),
            key=lambda s: (s.level, s.name),
        )
        rows.append({
            "class_id": cid,
            "class_name": cls.name,
            "caster_type": ctype,
            "required": (spell_engine.beginning_spell_count(entry, cls, int_score, ruleset)
                         if ctype == "arcane" else 0),
            "advanced": ruleset.advanced_spell_books,
            "candidates": [{"id": s.id, "name": s.name, "level": s.level,
                            "description": s.description,
                            "selected": s.id in books.get(cid, [])}
                           for s in candidates],
        })
    return rows


@router.get("/{draft_id}/spells", response_class=HTMLResponse)
async def get_spells(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "spells", draft_id)
    if redirect:
        return redirect
    ctx = _base_context(request, draft_id, draft, "spells")
    ctx["caster_classes"] = _caster_entries(draft, request.app.state.game_data)
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/spells")
async def post_spells(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    form = await request.form()
    int_score = draft["abilities"].get("INT", 10)
    ruleset = _ruleset_of(draft)
    books: dict[str, list[str]] = dict(draft.get("spellbooks", {}))

    for cid in _class_ids(draft):
        cls = data.classes[cid]
        if not _casts_at_level_1(cls):
            continue
        entry = ClassEntry(class_id=cid, level=1)
        ctype = spell_engine.caster_type_of(cls, data)
        if ctype != "arcane":
            books[cid] = []          # divine: nothing to pick; known is the full list
            continue
        chosen = form.getlist(f"spell_{cid}") or form.getlist("spell_id")
        chosen = list(dict.fromkeys(chosen))  # de-dup, keep order
        required = spell_engine.beginning_spell_count(entry, cls, int_score, ruleset)
        if len(chosen) != required:
            raise HTTPException(
                400, f"{cls.name} must choose exactly {required} starting spell(s); "
                     f"got {len(chosen)}."
            )
        accessible = spell_engine.accessible_levels(entry, cls)
        for sid in chosen:
            spell = data.spells.get(sid)
            if spell is None or not (set(spell.spell_lists) & set(cls.spell_lists)) \
                    or spell.level not in accessible:
                raise HTTPException(400, f"{sid!r} is not a valid {cls.name} starting spell.")
        books[cid] = chosen

    draft["spellbooks"] = books
    draft["spells_done"] = True
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")
```

- [ ] **Step 6: Carry the spellbook into the spec**

In `_draft_to_spec`, update the `classes` list comprehension to include the
spellbook:

```python
    books = draft.get("spellbooks", {})
    classes = [
        ClassEntry(class_id=cid, level=1, hp_rolls=[hp_rolls[i]],
                   spellbook=list(books.get(cid, [])))
        for i, cid in enumerate(ids)
    ]
```

- [ ] **Step 7: Create the wizard step template**

Create `aose/web/templates/wizard/spells.html`:

```html
<h2>Spells</h2>

{% for c in caster_classes %}
<div class="spell-class">
    <h3>{{ c.class_name }}</h3>

    {% if c.caster_type == "divine" %}
    <p>{{ c.class_name }} casters know <strong>every spell</strong> on their list
       that they are high enough level to cast. Nothing to choose here — you'll
       pick which spells to prepare each day on the character sheet.</p>
    <ul>
        {% for s in c.candidates %}
        <li><strong>{{ s.name }}</strong> <span class="small muted">(L{{ s.level }})</span></li>
        {% endfor %}
    </ul>
    <form method="post" action="/wizard/{{ draft_id }}/spells" class="step-form">
        <input type="hidden" name="class_id" value="{{ c.class_id }}">
        <button type="submit" class="primary">Next: Equipment &rarr;</button>
    </form>

    {% else %}
    <p>Choose <strong>{{ c.required }}</strong> starting spell(s) for your spell
       book{% if c.advanced %} (Advanced Spell Book rules: determined by Intelligence){% else %} (the spells you can memorise at this level){% endif %}.</p>
    <form method="post" action="/wizard/{{ draft_id }}/spells" class="step-form"
          data-required="{{ c.required }}">
        <input type="hidden" name="class_id" value="{{ c.class_id }}">
        <div class="card-grid">
            {% for s in c.candidates %}
            <label class="card {% if s.selected %}selected{% endif %}">
                <input type="checkbox" name="spell_{{ c.class_id }}" value="{{ s.id }}"
                       class="spell-checkbox" {% if s.selected %}checked{% endif %}>
                <div class="card-name">{{ s.name }}</div>
                <div class="card-detail small">{{ s.description }}</div>
            </label>
            {% endfor %}
        </div>
        <p class="muted spell-counter">Pick exactly {{ c.required }}.</p>
        <button type="submit" class="primary">Next: Equipment &rarr;</button>
    </form>
    {% endif %}
</div>
{% endfor %}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_routes.py -k "wizard" -q`
Expected: PASS (4 tests).

- [ ] **Step 9: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add aose/web/wizard.py aose/web/templates/wizard/spells.html tests/test_spell_routes.py
git commit -m "feat: wizard spells step (arcane known-selection; divine read-only)"
```

---

## Task 10: Import pipeline — crib, prompt, validator

**Files:**
- Create: `import/cribs/spell-list.md`
- Create: `import/prompts/phase2-spell-list.md`
- Modify: `import/cribs/class.md`
- Modify: `import/cribs/spell.md`
- Modify: `tools/validate_import.py`
- Test: `tests/test_validate_import.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_validate_import.py` (re-using its existing imports of the
module under test; if it imports `from tools import validate_import as vi`, match
that — otherwise add `from tools.validate_import import unresolved_spell_list_refs`):

```python
def test_unresolved_spell_list_refs_flags_bad_reference(tmp_path):
    from tools.validate_import import unresolved_spell_list_refs
    (tmp_path / "spell_lists.yaml").write_text(
        "- {id: magic_user, name: Magic-User, caster_type: arcane}\n", encoding="utf-8")
    (tmp_path / "classes").mkdir()
    (tmp_path / "classes" / "bard.yaml").write_text(
        "id: bard\nname: Bard\nprime_requisites: [CHA]\nhit_die: 1d6\n"
        "weapons_allowed: all\narmor_allowed: []\nshields_allowed: false\n"
        "spell_lists: [made_up_list]\n", encoding="utf-8")
    errors = unresolved_spell_list_refs(tmp_path)
    assert any("made_up_list" in e for e in errors)


def test_unresolved_spell_list_refs_passes_real_data():
    from pathlib import Path
    from tools.validate_import import unresolved_spell_list_refs
    data_dir = Path(__file__).parent.parent / "data"
    assert unresolved_spell_list_refs(data_dir) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_validate_import.py -k "spell_list_refs" -q`
Expected: FAIL — `ImportError: cannot import name 'unresolved_spell_list_refs'`.

- [ ] **Step 3: Add the reference-integrity check**

In `tools/validate_import.py`, add `SpellList` to the models import:

```python
from aose.models import CharClass, Item, Race, Spell, SpellList
```

Add this function after `all_duplicate_ids`:

```python
def _known_spell_list_ids(data_dir: Path) -> set[str]:
    path = data_dir / "spell_lists.yaml"
    if not path.exists():
        return set()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    ids: set[str] = set()
    for obj in raw if isinstance(raw, list) else []:
        try:
            ids.add(SpellList.model_validate(obj).id)
        except ValidationError:
            continue
    return ids


def unresolved_spell_list_refs(data_dir: Path = DATA_DIR) -> list[str]:
    """Every spell_lists id used by a class or spell must resolve to a defined
    SpellList in spell_lists.yaml."""
    known = _known_spell_list_ids(data_dir)
    errors: list[str] = []
    for sub in ("classes", "spells"):
        directory = data_dir / sub
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.yaml")):
            for obj in _read_objects(path):
                if not isinstance(obj, dict):
                    continue
                for ref in obj.get("spell_lists", []) or []:
                    if ref not in known:
                        errors.append(
                            f"{sub}/{path.name}: unknown spell list {ref!r}"
                        )
    return errors
```

Wire it into the repo-wide checks in `main()` (extend the final loop):

```python
    # Repo-wide checks always run.
    for e in load_game_data() + all_duplicate_ids() + unresolved_spell_list_refs():
        failed = True
        print(f"FAIL repo: {e}")
```

- [ ] **Step 4: Create the spell-list crib**

Create `import/cribs/spell-list.md`:

```markdown
# Crib: spell-list

Target model: `SpellList` (`aose/models/spell_list.py`). `extra="forbid"`.
All lists live in ONE file: `data/spell_lists.yaml` (a YAML list of mappings).

## Fields
| Field | Type | Req | Notes |
|---|---|---|---|
| id | str | yes | snake_case pool id (e.g. magic_user, cleric, druid, illusionist) |
| name | str | yes | display name |
| caster_type | "arcane" \| "divine" | yes | see decision rule below |
| description | str \| null | no | one line |

## Deciding caster_type (the one judgment call)
- **arcane** — the tradition uses a *spell book*; casters "learn"/"study" spells
  and are limited to a known set (magic-user, illusionist, elf's borrowed list).
- **divine** — casters "pray"/"are granted" spells and know their *entire* class
  list (cleric, druid).

Make this decision ONCE per list. Classes and spells reference the list by id;
they never restate the caster type.

## Example
```yaml
- id: magic_user
  name: Magic-User
  caster_type: arcane
  description: Arcane spells learned through study and recorded in a spell book.
- id: druid
  name: Druid
  caster_type: divine
```
```

- [ ] **Step 5: Create the spell-list phase prompt**

Create `import/prompts/phase2-spell-list.md`:

```markdown
# Phase 2 — Define a spell list

Add or update entries in `data/spell_lists.yaml` for the spell pools a book
introduces.

- Read the schema crib at `import/cribs/spell-list.md`.
- Output ONLY YAML — append mappings to the existing list (one per pool).
- Decide `caster_type` per the crib's rule (spell book = arcane; prayer / whole
  list = divine). Decide it once; classes and spells just reference the id.
- A pool that already exists must not be duplicated.
```

- [ ] **Step 6: Update the class and spell cribs**

In `import/cribs/class.md`, replace the `spell_lists` row note and the
"Caster progression rows" guidance so it points at the registry. Change the
table row to:

```markdown
| spell_lists | list[str] | no | which pool(s) this class casts from; each id MUST be defined in `data/spell_lists.yaml` (define it first if new). `[]` = non-caster. The arcane/divine behaviour comes from the list, not the class. |
```

And add one line under "Caster progression rows" (after the `spell_lists: [magic_user]` example line):

```markdown
- The class's known-vs-prepared behaviour is NOT set here — it comes from the
  referenced list's `caster_type` (see `import/cribs/spell-list.md`).
```

In `import/cribs/spell.md`, change the `spell_lists` field row note to:

```markdown
| spell_lists | list[str] | no | pool IDs; each MUST be defined in `data/spell_lists.yaml`: magic_user, cleric, druid, illusionist… |
```

- [ ] **Step 7: Run tests + validator to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_validate_import.py -k "spell_list_refs" -q`
Expected: PASS (2 tests).

Run: `.venv\Scripts\python.exe tools/validate_import.py`
Expected: ends with `ALL OK`.

- [ ] **Step 8: Commit**

```bash
git add import/cribs/spell-list.md import/prompts/phase2-spell-list.md import/cribs/class.md import/cribs/spell.md tools/validate_import.py tests/test_validate_import.py
git commit -m "feat: import pipeline support for the SpellList registry + ref integrity"
```

---

## Task 11: Documentation (CLAUDE.md)

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add a Spells concept entry**

In `CLAUDE.md`, under the "Key concepts now live:" bullets (after the Magic items
bullet), add:

```markdown
- **Spells** — data-driven, faithful known-vs-prepared. A `SpellList` registry
  (`data/spell_lists.yaml`: id → `caster_type` arcane|divine) is the single home
  for the known-vs-prepared distinction; a class derives its behaviour from the
  list(s) in `CharClass.spell_lists` (no per-class flag). `ClassEntry` carries
  `spellbook` (known; arcane) + `prepared` (daily, slot-capped). `aose/engine/
  spells.py` is the cycle-free core (imports only models + loader):
  `caster_type_of`, `accessible_levels`, `memorizable_slots`, `known_spells`
  (arcane=spellbook, divine=full accessible list), `learnable_spells`,
  `beginning_spell_count` (standard=memorizable total, advanced=INT table), and
  the `learn`/`forget`/`prepare`/`unprepare` mutators (return a new `ClassEntry`,
  raise `SpellError`). The standard-vs-advanced spell-book rules are the
  `advanced_spell_books` optional rule (off=standard cap = memorizable; on=INT
  beginning spells + uncapped book). Wizard `spells` step (after HP, before
  Equipment; gated by a cached `draft["spellcasting"]` flag) selects the arcane
  starting book / shows the divine list read-only. Sheet Spells section + routes
  (`/spells/learn|forget|prepare|unprepare`) manage both layers. Seed data:
  `data/spells/*.yaml` (incl. `read_magic` as an ordinary spell — there is NO
  special Read Magic rule). Spec/plan:
  `docs/superpowers/{specs,plans}/2026-05-29-spell-selection*`.
```

- [ ] **Step 2: Run the full suite one final time**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (all green; ignore the pytest-current PermissionError).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document the spell-selection feature in CLAUDE.md"
```

---

## Self-Review notes (for the implementer)

- **Spec coverage:** registry (T1), model split (T2), seed data + class tags (T3),
  optional rule (T4), engine derivation (T5) + mutators (T6), sheet view (T7),
  sheet routes/template (T8), wizard step (T9), import pipeline + validator (T10),
  docs (T11). All spec sections map to a task.
- **Type consistency:** `caster_type_of`, `accessible_levels`, `memorizable_slots`,
  `known_spells`, `learnable_spells`, `beginning_spell_count`, `learn`, `forget`,
  `prepare`, `unprepare` are named identically in the engine, view, routes, and
  wizard. `SpellClassView` fields (`class_id`, `class_name`, `caster_type`,
  `can_learn`, `known`, `prepared_groups`, `learnable`) match the template.
- **Draft keys:** `spellcasting`, `spellbooks` (dict class_id→list), `spells_done`
  are set in `post_class`/`post_spells` and cleared in every `_clear_after_*`.
- **Multiclass:** all per-entry logic keys on `class_id`; non-casting entries are
  skipped in `spells_view` and `_caster_entries`.
```
