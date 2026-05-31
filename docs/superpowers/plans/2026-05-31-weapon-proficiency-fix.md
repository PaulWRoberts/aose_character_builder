# Weapon Proficiency Fix + Book-Accurate Weapon Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the Weapon Proficiency optional rule (per-weapon proficiencies, correct slot counts/penalties by martial category, full leveling, specialisation), replace invented weapon metadata with book-accurate data + quality definitions, and enforce class weapon/armour/shield restrictions at equip time.

**Architecture:** The `combat_category` (martial / semi_martial / non_martial) is *derived* from each class's existing THAC0 progression — no class-data compression, no new category field. `aose/engine/proficiency.py` is rewritten from group-based to per-weapon: it owns category derivation, slot maths, penalties, proficiency/specialisation accounting, and a class-allowance resolver. `attacks.py` and `equip.py` consume those pure helpers; the wizard and sheet render per-weapon pickers/views. A new `WeaponQuality` catalog (loaded into `GameData.qualities`) backs an in-game qualities reference.

**Tech Stack:** Python 3, FastAPI, Jinja2, Pydantic v2, YAML data. Tests: pytest via `.venv\Scripts\python.exe -m pytest`.

**Spec:** `docs/superpowers/specs/2026-05-31-weapon-proficiency-fix-design.md` (source of truth — re-read §3–§6 before each part).

**Conventions for every task:**
- Run tests with: `.venv\Scripts\python.exe -m pytest <args> -q`
- The trailing `PermissionError` on `pytest-current` is a known Windows quirk — ignore it.
- Commit messages use the repo's `type(scope): summary` style; end with the `Co-Authored-By` trailer the repo uses if running via git directly is required. Commit after each task.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `aose/models/weapon_quality.py` | `WeaponQuality` value model (id/name/description) | Create |
| `aose/models/__init__.py` | Export `WeaponQuality`; drop `ProficiencyConfig` | Modify |
| `aose/models/item.py` | Drop `Weapon.proficiency_group` | Modify |
| `aose/models/character_class.py` | Remove `ProficiencyConfig` + `CharClass.proficiency` | Modify |
| `aose/models/character.py` | Swap `chosen_proficiencies` → `weapon_proficiencies` + `weapon_specialisations` + migration | Modify |
| `data/equipment/weapon_qualities.yaml` | Quality definitions catalog | Create |
| `data/equipment/weapons.yaml` | Book-accurate rewrite (per-weapon, qualities, renames, new ids) | Rewrite |
| `aose/data/loader.py` | Load `weapon_qualities.yaml` into `GameData.qualities`; exclude it from item glob | Modify |
| `aose/engine/proficiency.py` | Rewrite: category, slots, penalty, accounting, allowance resolver | Rewrite |
| `aose/engine/attacks.py` | Per-weapon proficiency, category penalty, specialisation, `specialised` flag | Modify |
| `aose/engine/equip.py` | Allowance enforcement on equip | Modify |
| `aose/web/wizard.py` | Per-weapon picker routes, slot maths, specialisation; equip allowances | Modify |
| `aose/web/templates/wizard/proficiencies.html` | Per-weapon picker + specialise toggle | Rewrite |
| `aose/web/routes.py` | Pass allowances into sheet equip route | Modify |
| `aose/sheet/view.py` | `proficiencies_view` (per-weapon) + qualities reference | Modify |
| `aose/web/templates/sheet.html` / `sheet_print.html` / `wizard/review.html` | Per-weapon proficiency rendering + qualities reference | Modify |
| `tests/test_weapon_proficiency.py` | Rewrite to per-weapon model | Rewrite |
| `tests/test_equip_attacks.py` | Update to new field names + penalties + ids | Modify |
| `tests/test_weapon_data.py` | Book-accurate data assertions + qualities | Create |
| `tests/test_equip_enforcement.py` | Allowance resolver + equip gating | Create |

> **Id renames** (`long_sword`→`sword`, `light_crossbow`→`crossbow`) ripple through tests. Several tasks below include the exact renames. Numeric data changes that affect existing assertions: `two_handed_sword` weight `100`→`150`; `crossbow` (was `light_crossbow`) cost `16`→`30`. `sword` keeps weight 60 and cost 10, so encumbrance/cost tests that used `long_sword` only need the id renamed.

---

## Part 1 — Book-accurate weapon & armour data + qualities

### Task 1: `WeaponQuality` model

**Files:**
- Create: `aose/models/weapon_quality.py`
- Modify: `aose/models/__init__.py`
- Test: `tests/test_weapon_data.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_weapon_data.py`:

```python
"""Book-accurate weapon data + weapon-quality catalog."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.models import WeaponQuality

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def test_weapon_quality_model_fields():
    q = WeaponQuality(id="blunt", name="Blunt", description="May be used by clerics.")
    assert q.id == "blunt"
    assert q.name == "Blunt"
    assert q.description == "May be used by clerics."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_data.py::test_weapon_quality_model_fields -q`
Expected: FAIL — `ImportError: cannot import name 'WeaponQuality'`.

- [ ] **Step 3: Create the model**

`aose/models/weapon_quality.py`:

```python
from pydantic import BaseModel, ConfigDict


class WeaponQuality(BaseModel):
    """A weapon quality definition (Blunt, Brace, Charge, …) — referenceable
    in-game.  Not an ``Item``; loaded into ``GameData.qualities``."""
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
```

- [ ] **Step 4: Export it**

In `aose/models/__init__.py`, add the import after the `spell_list` import line:

```python
from .weapon_quality import WeaponQuality
```

and add `"WeaponQuality",` to `__all__` (next to `"SpellList",`).

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_data.py::test_weapon_quality_model_fields -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/models/weapon_quality.py aose/models/__init__.py tests/test_weapon_data.py
git commit -m "feat(models): add WeaponQuality value model"
```

---

### Task 2: `weapon_qualities.yaml` data + loader into `GameData.qualities`

**Files:**
- Create: `data/equipment/weapon_qualities.yaml`
- Modify: `aose/data/loader.py`
- Test: `tests/test_weapon_data.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_weapon_data.py`:

```python
def test_weapon_qualities_load_into_game_data():
    data = GameData.load(DATA_DIR)
    assert "blunt" in data.qualities
    assert isinstance(data.qualities["blunt"], WeaponQuality)
    assert data.qualities["blunt"].description == "May be used by clerics."
    # All nine book qualities present.
    assert {
        "blunt", "brace", "charge", "melee", "missile",
        "reload", "slow", "splash_weapon", "two_handed",
    }.issubset(set(data.qualities))


def test_qualities_not_loaded_as_items():
    data = GameData.load(DATA_DIR)
    assert "blunt" not in data.items
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_data.py -q`
Expected: FAIL — `GameData` has no `qualities` attribute.

- [ ] **Step 3: Create the data file**

`data/equipment/weapon_qualities.yaml`:

```yaml
# Weapon quality definitions (AOSE).  Referenced by id from each weapon's
# `qualities` list.  Loaded into GameData.qualities — NOT items.
- id: blunt
  name: Blunt
  description: May be used by clerics.
- id: brace
  name: Brace
  description: >-
    May be set against a charge. If it hits a charging opponent, it inflicts
    double damage.
- id: charge
  name: Charge
  description: >-
    When used while mounted and charging, the weapon inflicts double damage on
    a hit.
- id: melee
  name: Melee
  description: May be used to attack adjacent opponents (within 5 feet).
- id: missile
  name: Missile
  description: May be used to make ranged attacks, using the listed ranges.
- id: reload
  name: Reload
  description: >-
    Loading the weapon takes time: the wielder may only fire it every other
    round.
- id: slow
  name: Slow
  description: The character always acts last in a combat round (ignoring initiative).
- id: splash_weapon
  name: Splash weapon
  description: >-
    Thrown to shatter on impact, affecting an area. A miss may scatter to a
    nearby location.
- id: two_handed
  name: Two-handed
  description: >-
    Requires both hands to use; a shield may not be employed. The wielder always
    acts last in a combat round.
```

- [ ] **Step 4: Modify the loader**

In `aose/data/loader.py`:

(a) Add the import to the `from aose.models import (...)` block:

```python
from aose.models import (
    CharClass,
    Item,
    Race,
    Spell,
    SpellList,
    WeaponQuality,
)
```

(b) Change `_read_yaml_objects` to accept an exclusion set, and make `_load_items` skip the qualities file:

```python
def _read_yaml_objects(directory: Path, exclude_names: set[str] | None = None) -> list[dict]:
    """Read every *.yaml in a directory, yielding each top-level object.
    A file may contain a single mapping or a list of mappings.
    Filenames in ``exclude_names`` are skipped."""
    objs: list[dict] = []
    if not directory.exists():
        return objs
    exclude = exclude_names or set()
    for path in sorted(directory.glob("*.yaml")):
        if path.name in exclude:
            continue
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if raw is None:
            continue
        if isinstance(raw, list):
            objs.extend(raw)
        else:
            objs.append(raw)
    return objs
```

```python
def _load_items(directory: Path) -> dict[str, Item]:
    adapter = TypeAdapter(Item)
    result: dict[str, Item] = {}
    for obj in _read_yaml_objects(directory, exclude_names={"weapon_qualities.yaml"}):
        parsed = adapter.validate_python(obj)
        result[parsed.id] = parsed
    return result
```

(c) Add a qualities loader function (place after `_load_spell_lists`):

```python
def _load_weapon_qualities(data_dir: Path) -> dict[str, WeaponQuality]:
    """Read ``equipment/weapon_qualities.yaml`` (a list of mappings) into an
    id-keyed dict.  Returns an empty dict when absent (minimal fixtures)."""
    path = data_dir / "equipment" / "weapon_qualities.yaml"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    if not isinstance(raw, list):
        raise ValueError("weapon_qualities.yaml must be a YAML list of mappings")
    result: dict[str, WeaponQuality] = {}
    for obj in raw:
        parsed = WeaponQuality.model_validate(obj)
        result[parsed.id] = parsed
    return result
```

(d) Add the field to `GameData` and wire it in `load` (place `qualities` after `items`):

```python
@dataclass
class GameData:
    races: dict[str, Race] = field(default_factory=dict)
    classes: dict[str, CharClass] = field(default_factory=dict)
    spells: dict[str, Spell] = field(default_factory=dict)
    spell_lists: dict[str, SpellList] = field(default_factory=dict)
    items: dict[str, Item] = field(default_factory=dict)
    qualities: dict[str, WeaponQuality] = field(default_factory=dict)
    secondary_skills: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, data_dir: Path) -> "GameData":
        return cls(
            races=_load_models(data_dir / "races", Race),
            classes=_load_models(data_dir / "classes", CharClass),
            spells=_load_models(data_dir / "spells", Spell),
            spell_lists=_load_spell_lists(data_dir),
            items=_load_items(data_dir / "equipment"),
            qualities=_load_weapon_qualities(data_dir),
            secondary_skills=_load_secondary_skills(data_dir),
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_data.py -q`
Expected: PASS (all three tests).

- [ ] **Step 6: Commit**

```bash
git add data/equipment/weapon_qualities.yaml aose/data/loader.py tests/test_weapon_data.py
git commit -m "feat(data): weapon-quality catalog loaded into GameData.qualities"
```

---

### Task 3: Book-accurate `weapons.yaml` rewrite + drop `proficiency_group`

**Files:**
- Modify: `aose/models/item.py`
- Rewrite: `data/equipment/weapons.yaml`
- Test: `tests/test_weapon_data.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_weapon_data.py`:

```python
def test_weapons_match_book_table():
    data = GameData.load(DATA_DIR)
    # Renames applied.
    assert "long_sword" not in data.items
    assert "light_crossbow" not in data.items
    assert "sword" in data.items
    assert "crossbow" in data.items
    # New ids present.
    for new_id in ("javelin", "lance", "staff", "silver_dagger"):
        assert new_id in data.items, f"missing {new_id}"

    sword = data.items["sword"]
    assert sword.name == "Sword"
    assert sword.cost_gp == 10
    assert sword.weight_cn == 60
    assert sword.damage.variable == "1d8"
    assert sword.qualities == ["melee"]

    crossbow = data.items["crossbow"]
    assert crossbow.cost_gp == 30
    assert crossbow.melee is False
    assert crossbow.ranged is True
    assert (crossbow.range_short, crossbow.range_medium, crossbow.range_long) == (80, 160, 240)
    assert set(crossbow.qualities) == {"missile", "reload", "slow", "two_handed"}


def test_every_weapon_quality_is_defined():
    data = GameData.load(DATA_DIR)
    from aose.models import Weapon
    for item in data.items.values():
        if isinstance(item, Weapon):
            for q in item.qualities:
                assert q in data.qualities, f"{item.id} references unknown quality {q!r}"


def test_proficiency_group_field_removed():
    from aose.models import Weapon
    assert "proficiency_group" not in Weapon.model_fields
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_data.py -q`
Expected: FAIL — old ids/qualities/field mismatch.

- [ ] **Step 3: Drop the model field**

In `aose/models/item.py`, remove this line from `Weapon`:

```python
    proficiency_group: str | None = None
```

- [ ] **Step 4: Rewrite the data file**

Replace the entire contents of `data/equipment/weapons.yaml` with (values from spec §3.2; `damage.default` stays `1d6` for the standard rule, `damage.variable` is the book die; `melee`/`ranged`/`hands` and ranges follow the qualities):

```yaml
# Weapons (AOSE, book-accurate).  `damage.default` is the 1d6 used under the
# standard rule; `damage.variable` is used when the Variable Weapon Damage
# optional rule is in effect.  `qualities` reference weapon_qualities.yaml.

- id: battle_axe
  item_type: weapon
  name: Battle Axe
  category: weapons
  cost_gp: 7
  weight_cn: 50
  damage: { default: "1d6", variable: "1d8" }
  hands: 2
  qualities: [melee, slow, two_handed]

- id: club
  item_type: weapon
  name: Club
  category: weapons
  cost_gp: 3
  weight_cn: 50
  damage: { default: "1d6", variable: "1d4" }
  hands: 1
  qualities: [blunt, melee]

- id: crossbow
  item_type: weapon
  name: Crossbow
  category: weapons
  cost_gp: 30
  weight_cn: 50
  damage: { default: "1d6", variable: "1d6" }
  hands: 2
  melee: false
  ranged: true
  range_short: 80
  range_medium: 160
  range_long: 240
  qualities: [missile, reload, slow, two_handed]

- id: dagger
  item_type: weapon
  name: Dagger
  category: weapons
  cost_gp: 3
  weight_cn: 10
  damage: { default: "1d6", variable: "1d4" }
  hands: 1
  ranged: true
  range_short: 10
  range_medium: 20
  range_long: 30
  qualities: [melee, missile]

- id: hand_axe
  item_type: weapon
  name: Hand Axe
  category: weapons
  cost_gp: 4
  weight_cn: 30
  damage: { default: "1d6", variable: "1d6" }
  hands: 1
  ranged: true
  range_short: 10
  range_medium: 20
  range_long: 30
  qualities: [melee, missile]

- id: javelin
  item_type: weapon
  name: Javelin
  category: weapons
  cost_gp: 1
  weight_cn: 20
  damage: { default: "1d6", variable: "1d4" }
  hands: 1
  melee: false
  ranged: true
  range_short: 30
  range_medium: 60
  range_long: 90
  qualities: [missile]

- id: lance
  item_type: weapon
  name: Lance
  category: weapons
  cost_gp: 5
  weight_cn: 120
  damage: { default: "1d6", variable: "1d6" }
  hands: 1
  qualities: [charge, melee]

- id: long_bow
  item_type: weapon
  name: Long Bow
  category: weapons
  cost_gp: 40
  weight_cn: 30
  damage: { default: "1d6", variable: "1d6" }
  hands: 2
  melee: false
  ranged: true
  range_short: 70
  range_medium: 140
  range_long: 210
  qualities: [missile, two_handed]

- id: mace
  item_type: weapon
  name: Mace
  category: weapons
  cost_gp: 5
  weight_cn: 30
  damage: { default: "1d6", variable: "1d6" }
  hands: 1
  qualities: [blunt, melee]

- id: polearm
  item_type: weapon
  name: Pole-arm
  category: weapons
  cost_gp: 7
  weight_cn: 150
  damage: { default: "1d6", variable: "1d10" }
  hands: 2
  qualities: [brace, melee, slow, two_handed]

- id: short_bow
  item_type: weapon
  name: Short Bow
  category: weapons
  cost_gp: 25
  weight_cn: 30
  damage: { default: "1d6", variable: "1d6" }
  hands: 2
  melee: false
  ranged: true
  range_short: 50
  range_medium: 100
  range_long: 150
  qualities: [missile, two_handed]

- id: short_sword
  item_type: weapon
  name: Short Sword
  category: weapons
  cost_gp: 7
  weight_cn: 30
  damage: { default: "1d6", variable: "1d6" }
  hands: 1
  qualities: [melee]

- id: silver_dagger
  item_type: weapon
  name: Silver Dagger
  category: weapons
  cost_gp: 30
  weight_cn: 10
  damage: { default: "1d6", variable: "1d4" }
  hands: 1
  ranged: true
  range_short: 10
  range_medium: 20
  range_long: 30
  qualities: [melee, missile]

- id: sling
  item_type: weapon
  name: Sling
  category: weapons
  cost_gp: 2
  weight_cn: 20
  damage: { default: "1d6", variable: "1d4" }
  hands: 1
  melee: false
  ranged: true
  range_short: 40
  range_medium: 80
  range_long: 160
  qualities: [blunt, missile]

- id: spear
  item_type: weapon
  name: Spear
  category: weapons
  cost_gp: 4
  weight_cn: 30
  damage: { default: "1d6", variable: "1d6" }
  hands: 1
  versatile: true
  ranged: true
  range_short: 20
  range_medium: 40
  range_long: 60
  qualities: [brace, melee, missile]

- id: staff
  item_type: weapon
  name: Staff
  category: weapons
  cost_gp: 2
  weight_cn: 40
  damage: { default: "1d6", variable: "1d4" }
  hands: 2
  qualities: [blunt, melee, slow, two_handed]

- id: sword
  item_type: weapon
  name: Sword
  category: weapons
  cost_gp: 10
  weight_cn: 60
  damage: { default: "1d6", variable: "1d8" }
  hands: 1
  qualities: [melee]

- id: two_handed_sword
  item_type: weapon
  name: Two-Handed Sword
  category: weapons
  cost_gp: 15
  weight_cn: 150
  damage: { default: "1d6", variable: "1d10" }
  hands: 2
  qualities: [melee, slow, two_handed]

- id: war_hammer
  item_type: weapon
  name: War Hammer
  category: weapons
  cost_gp: 5
  weight_cn: 30
  damage: { default: "1d6", variable: "1d6" }
  hands: 1
  qualities: [blunt, melee]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_data.py -q`
Expected: PASS.

- [ ] **Step 6: Rename ids in unrelated tests so the suite still imports/collects**

These tests reference the old ids but are not about proficiency; rename `long_sword`→`sword` and `light_crossbow`→`crossbow` in:
- `tests/test_encumbrance.py` (uses `long_sword`, weight 60 unchanged — rename only)
- `tests/test_equipment.py` (uses `long_sword`; `sword` keeps cost 10/weight 60 — rename only)
- `tests/test_containers.py` (rename only)

Run (PowerShell, from repo root):

```powershell
(Get-Content tests/test_encumbrance.py) -replace 'long_sword','sword' | Set-Content tests/test_encumbrance.py -Encoding utf8
(Get-Content tests/test_equipment.py)  -replace 'long_sword','sword' -replace 'light_crossbow','crossbow' | Set-Content tests/test_equipment.py -Encoding utf8
(Get-Content tests/test_containers.py) -replace 'long_sword','sword' -replace 'light_crossbow','crossbow' | Set-Content tests/test_containers.py -Encoding utf8
```

Then run those three files and fix any cost/weight assertion that changed (`crossbow` cost is now 30; `two_handed_sword` weight is now 150):

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py tests/test_equipment.py tests/test_containers.py -q`
Expected: PASS (adjust any literal `16`→`30` crossbow-cost or `100`→`150` two-handed-sword-weight assertion if present).

> `tests/test_weapon_proficiency.py` and `tests/test_equip_attacks.py` still reference removed functions and will be rewritten in Tasks 5–8. Do **not** try to make them pass yet.

- [ ] **Step 7: Commit**

```bash
git add aose/models/item.py data/equipment/weapons.yaml tests/test_weapon_data.py tests/test_encumbrance.py tests/test_equipment.py tests/test_containers.py
git commit -m "data: book-accurate weapons.yaml; drop proficiency_group; id renames"
```

---

## Part 2 — Weapon Proficiency rule engine

### Task 4: Category derivation + slot maths + penalty

**Files:**
- Rewrite: `aose/engine/proficiency.py`
- Test: `tests/test_weapon_proficiency.py`

> This task replaces the whole module's public surface. The old functions (`proficiency_groups`, `starting_proficiency_count`, `is_proficient_with`, `_DEFAULT_STARTING_SLOTS`, `ProficiencyGroup`) are removed. Importers (`attacks.py`, `wizard.py`, `sheet/view.py`) are updated in Tasks 7, 10, 11. Expect those modules to break until then — run only the targeted test file in this task.

- [ ] **Step 1: Write the failing test**

Replace the entire contents of `tests/test_weapon_proficiency.py` with the engine-only tests below (web/sheet tests are re-added in Tasks 10–11):

```python
"""Weapon Proficiency optional rule — engine."""
from pathlib import Path

from aose.data.loader import GameData
from aose.engine.proficiency import (
    base_slot_count,
    combat_category,
    improvements_through_level,
    nonproficiency_penalty,
    proficiency_slots,
)

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def test_combat_category_derivation():
    data = GameData.load(DATA_DIR)
    assert combat_category(data.classes["fighter"]) == "martial"
    assert combat_category(data.classes["cleric"]) == "semi_martial"
    assert combat_category(data.classes["magic_user"]) == "non_martial"


def test_base_slot_count_by_category():
    assert base_slot_count("martial") == 4
    assert base_slot_count("semi_martial") == 3
    assert base_slot_count("non_martial") == 1


def test_nonproficiency_penalty_by_category():
    assert nonproficiency_penalty("martial") == -2
    assert nonproficiency_penalty("semi_martial") == -3
    assert nonproficiency_penalty("non_martial") == -5


def test_improvements_through_level_fighter():
    data = GameData.load(DATA_DIR)
    fighter = data.classes["fighter"]
    assert improvements_through_level(fighter, 1) == 0
    assert improvements_through_level(fighter, 4) == 1   # drop at L4
    assert improvements_through_level(fighter, 7) == 2   # +drop at L7
    assert improvements_through_level(fighter, 13) == 4  # L4/7/10/13


def test_proficiency_slots_full_leveling():
    data = GameData.load(DATA_DIR)
    fighter = data.classes["fighter"]
    assert proficiency_slots(fighter, 1) == 4
    assert proficiency_slots(fighter, 7) == 6
    assert proficiency_slots(fighter, 13) == 8
    assert proficiency_slots(data.classes["cleric"], 1) == 3
    assert proficiency_slots(data.classes["magic_user"], 1) == 1
    assert proficiency_slots(data.classes["magic_user"], 6) == 2  # first drop at L6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_proficiency.py -q`
Expected: FAIL — `ImportError` (functions don't exist yet).

- [ ] **Step 3: Rewrite the module (category + slots + penalty portion)**

Replace the entire contents of `aose/engine/proficiency.py` with:

```python
"""Weapon Proficiency optional rule — per-weapon proficiencies.

The character's *combat category* (martial / semi_martial / non_martial) is
DERIVED from the rate at which its THAC0 improves, so class data stays the
single source of truth:

* martial      — THAC0 improves every 3 levels (first drop at L4) → 4 slots, -2
* semi_martial — every 4 levels (first drop at L5)               → 3 slots, -3
* non_martial  — every 5 levels (first drop at L6)               → 1 slot,  -5

One extra proficiency slot is gained each time THAC0 improves.
"""
from __future__ import annotations

from typing import Literal

from aose.models import CharClass, CharacterSpec

Category = Literal["martial", "semi_martial", "non_martial"]

_BASE_SLOTS: dict[Category, int] = {"martial": 4, "semi_martial": 3, "non_martial": 1}
_PENALTY: dict[Category, int] = {"martial": -2, "semi_martial": -3, "non_martial": -5}
# Most-martial-first ordering for multi-class resolution.
_MARTIALNESS: dict[Category, int] = {"martial": 0, "semi_martial": 1, "non_martial": 2}


def combat_category(cls: CharClass) -> Category:
    """Derive the proficiency category from the THAC0 progression's improvement
    rate.  Falls back to ``non_martial`` (safest: fewest slots) if the table
    never improves."""
    levels = sorted(cls.progression)
    if not levels:
        return "non_martial"
    base = cls.progression[levels[0]].thac0
    for lvl in levels[1:]:
        if cls.progression[lvl].thac0 < base:
            period = lvl - 1
            if period <= 3:
                return "martial"
            if period == 4:
                return "semi_martial"
            return "non_martial"
    return "non_martial"


def base_slot_count(category: Category) -> int:
    return _BASE_SLOTS[category]


def nonproficiency_penalty(category: Category) -> int:
    return _PENALTY[category]


def improvements_through_level(cls: CharClass, level: int) -> int:
    """Count THAC0 improvements (drops) at levels ≤ ``level``."""
    levels = sorted(cls.progression)
    if not levels:
        return 0
    count = 0
    prev = cls.progression[levels[0]].thac0
    for lvl in levels[1:]:
        if lvl > level:
            break
        cur = cls.progression[lvl].thac0
        if cur < prev:
            count += 1
        prev = cur
    return count


def proficiency_slots(cls: CharClass, level: int) -> int:
    """Total proficiency slots for a single class at ``level`` = base + gained."""
    return base_slot_count(combat_category(cls)) + improvements_through_level(cls, level)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_proficiency.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/proficiency.py tests/test_weapon_proficiency.py
git commit -m "feat(proficiency): derive combat category + slot maths from THAC0"
```

---

### Task 5: Model swap — `weapon_proficiencies` / `weapon_specialisations` + remove `ProficiencyConfig`

**Files:**
- Modify: `aose/models/character.py`
- Modify: `aose/models/character_class.py`
- Modify: `aose/models/__init__.py`
- Test: `tests/test_weapon_proficiency.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_weapon_proficiency.py`:

```python
from aose.models import CharacterSpec, ClassEntry, RuleSet


def _base_spec(**over):
    kwargs = dict(
        name="X",
        abilities={"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10},
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="law",
    )
    kwargs.update(over)
    return CharacterSpec(**kwargs)


def test_new_proficiency_fields_default_empty():
    spec = _base_spec()
    assert spec.weapon_proficiencies == []
    assert spec.weapon_specialisations == []


def test_legacy_chosen_proficiencies_is_dropped_on_load():
    raw = _base_spec().model_dump()
    raw["chosen_proficiencies"] = ["sword", "axe"]
    spec = CharacterSpec.model_validate(raw)  # must not raise under extra=forbid
    assert not hasattr(spec, "chosen_proficiencies")
    assert spec.weapon_proficiencies == []


def test_proficiency_config_removed():
    import aose.models as m
    assert not hasattr(m, "ProficiencyConfig")
    from aose.models import CharClass
    assert "proficiency" not in CharClass.model_fields
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_proficiency.py -q`
Expected: FAIL — fields/validator not present; `ProficiencyConfig` still exported.

- [ ] **Step 3: Update `CharacterSpec`**

In `aose/models/character.py`, replace the field:

```python
    chosen_proficiencies: list[str] = Field(default_factory=list)
```

with:

```python
    # Weapon Proficiency optional rule (per-weapon).  Specialised weapons must
    # also appear in weapon_proficiencies; specialisation costs a 2nd slot.
    weapon_proficiencies: list[str] = Field(default_factory=list)
    weapon_specialisations: list[str] = Field(default_factory=list)
```

Add a before-validator on `CharacterSpec` (next to `_migrate_legacy_global_xp`):

```python
    @model_validator(mode="before")
    @classmethod
    def _drop_legacy_chosen_proficiencies(cls, data):
        """Drop the pre-per-weapon ``chosen_proficiencies`` field (group ids,
        meaningless now).  Affected characters re-pick.  Keeps old saves
        loadable under ``extra='forbid'``."""
        if isinstance(data, dict) and "chosen_proficiencies" in data:
            data = {k: v for k, v in data.items() if k != "chosen_proficiencies"}
        return data
```

- [ ] **Step 4: Remove `ProficiencyConfig` + `CharClass.proficiency`**

In `aose/models/character_class.py`, delete the `ProficiencyConfig` class entirely:

```python
class ProficiencyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starting_slots: int
    new_slot_every_levels: int
```

and delete this line from `CharClass`:

```python
    proficiency: ProficiencyConfig | None = None
```

In `aose/models/__init__.py`, remove `ProficiencyConfig` from both the `from .character_class import (...)` block and `__all__`.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_proficiency.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/models/character.py aose/models/character_class.py aose/models/__init__.py tests/test_weapon_proficiency.py
git commit -m "feat(models): per-weapon proficiency fields; remove ProficiencyConfig"
```

---

### Task 6: Proficiency/specialisation accounting + multi-class helpers

**Files:**
- Modify: `aose/engine/proficiency.py`
- Test: `tests/test_weapon_proficiency.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_weapon_proficiency.py`:

```python
from aose.engine.proficiency import (
    category_for_classes,
    is_proficient,
    is_specialised,
    penalty_for_classes,
    slots_spent,
    specialisation_allowed,
    total_proficiency_slots,
)


def test_is_proficient_and_specialised():
    spec = _base_spec(weapon_proficiencies=["sword", "spear"],
                      weapon_specialisations=["sword"])
    assert is_proficient("sword", spec) is True
    assert is_proficient("spear", spec) is True
    assert is_proficient("club", spec) is False
    assert is_specialised("sword", spec) is True
    assert is_specialised("spear", spec) is False


def test_slots_spent_counts_specialisation_extra():
    spec = _base_spec(weapon_proficiencies=["sword", "spear"],
                      weapon_specialisations=["sword"])
    # 2 proficiencies + 1 specialisation extra = 3 slots
    assert slots_spent(spec) == 3


def test_multiclass_category_and_penalty_most_martial(data):
    fighter = data.classes["fighter"]        # martial
    magic_user = data.classes["magic_user"]  # non_martial
    assert category_for_classes([fighter, magic_user]) == "martial"
    assert penalty_for_classes([fighter, magic_user]) == -2
    assert specialisation_allowed([fighter, magic_user]) is True
    assert specialisation_allowed([magic_user]) is False


def test_total_proficiency_slots_is_max_over_classes(data):
    fighter = data.classes["fighter"]        # 4 @ L1
    magic_user = data.classes["magic_user"]  # 1 @ L1
    assert total_proficiency_slots([(fighter, 1), (magic_user, 1)]) == 4
```

Add a module-level `data` fixture at the top of the file if not present:

```python
import pytest


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_proficiency.py -q`
Expected: FAIL — `ImportError` for the new helpers.

- [ ] **Step 3: Add the helpers to `aose/engine/proficiency.py`**

Append (after `proficiency_slots`):

```python
# ── Per-character accounting ────────────────────────────────────────────────

def is_proficient(weapon_id: str, spec: CharacterSpec) -> bool:
    return weapon_id in spec.weapon_proficiencies


def is_specialised(weapon_id: str, spec: CharacterSpec) -> bool:
    return weapon_id in spec.weapon_specialisations


def slots_spent(spec: CharacterSpec) -> int:
    """Each proficiency costs 1 slot; each specialisation costs 1 extra."""
    return len(spec.weapon_proficiencies) + len(spec.weapon_specialisations)


# ── Multi-class resolution (book is silent; most-martial wins) ──────────────

def category_for_classes(classes: list[CharClass]) -> Category:
    """The most martial category among the classes (smallest penalty)."""
    return min((combat_category(c) for c in classes),
               key=lambda cat: _MARTIALNESS[cat], default="non_martial")


def penalty_for_classes(classes: list[CharClass]) -> int:
    return nonproficiency_penalty(category_for_classes(classes))


def specialisation_allowed(classes: list[CharClass]) -> bool:
    """Specialisation is offered when any class is martial."""
    return any(combat_category(c) == "martial" for c in classes)


def total_proficiency_slots(pairs: list[tuple[CharClass, int]]) -> int:
    """Total slots for a (possibly multi-class) character: the max over classes
    of that class's slot count at its level."""
    return max((proficiency_slots(c, lvl) for c, lvl in pairs), default=0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_proficiency.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/proficiency.py tests/test_weapon_proficiency.py
git commit -m "feat(proficiency): per-weapon accounting + multi-class resolution"
```

---

### Task 7: Attack calculator — per-weapon penalty + specialisation

**Files:**
- Modify: `aose/engine/attacks.py`
- Test: `tests/test_equip_attacks.py`

- [ ] **Step 1: Update existing tests + add specialisation tests**

In `tests/test_equip_attacks.py`:

(a) Change the `_spec` helper signature/body to the new fields:

```python
def _spec(abilities=None, inventory=None, equipped=None, equipped_weapons=None,
          ruleset=None, weapon_proficiencies=None, weapon_specialisations=None):
    return CharacterSpec(
        name="Thorin",
        abilities=abilities or {"STR": 16, "INT": 10, "WIS": 11, "DEX": 12, "CON": 14, "CHA": 9},
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[7])],
        alignment="law",
        inventory=list(inventory or []),
        equipped=dict(equipped or {}),
        equipped_weapons=list(equipped_weapons or []),
        weapon_proficiencies=list(weapon_proficiencies or []),
        weapon_specialisations=list(weapon_specialisations or []),
        ruleset=ruleset or RuleSet(),
    )
```

(b) Replace the two proficiency tests (fighter is **martial** → penalty −2; ids now `sword`):

```python
def test_non_proficiency_applies_martial_penalty(data):
    all_profiles = attack_profiles(
        _spec(inventory=["sword"], equipped_weapons=["sword"],
              ruleset=RuleSet(weapon_proficiency=True),
              weapon_proficiencies=["hand_axe"]),  # not "sword"
        data,
    )
    sword = next(p for p in all_profiles if p.weapon_id == "sword")
    assert sword.proficient is False
    # base 19, STR +2, martial penalty -2 → 19 - 2 - (-2) = 19
    assert sword.to_hit_thac0 == 19


def test_proficient_user_takes_no_penalty(data):
    all_profiles = attack_profiles(
        _spec(inventory=["sword"], equipped_weapons=["sword"],
              ruleset=RuleSet(weapon_proficiency=True),
              weapon_proficiencies=["sword"]),
        data,
    )
    sword = next(p for p in all_profiles if p.weapon_id == "sword")
    assert sword.proficient is True
    assert sword.to_hit_thac0 == 17  # STR mod applied, no penalty


def test_specialisation_adds_plus_one_to_hit_and_damage(data):
    all_profiles = attack_profiles(
        _spec(inventory=["sword"], equipped_weapons=["sword"],
              ruleset=RuleSet(weapon_proficiency=True, variable_weapon_damage=True),
              weapon_proficiencies=["sword"],
              weapon_specialisations=["sword"]),
        data,
    )
    sword = next(p for p in all_profiles if p.weapon_id == "sword")
    assert sword.specialised is True
    # base 19, STR +2, spec +1 → 19 - 2 - 1 = 16
    assert sword.to_hit_thac0 == 16
    # sword variable 1d8, STR +2, spec +1 → 1d8+3
    assert sword.damage == "1d8+3"
```

Also fix any other reference in this file: line that did `_spec(inventory=["long_sword"], ...)` and `weapon_id == "long_sword"` → `sword`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_attacks.py -q`
Expected: FAIL — `AttackProfile` has no `specialised`; still imports `is_proficient_with`.

- [ ] **Step 3: Update `aose/engine/attacks.py`**

(a) Change the import:

```python
from aose.engine.proficiency import is_proficient, is_specialised, penalty_for_classes
```

(b) Add the `specialised` field to `AttackProfile` (after `proficient`):

```python
    specialised: bool = False  # weapon-specialisation +1/+1 active
```

(c) In `_profile_for`, replace the proficiency block:

```python
    # Proficiency penalty applies only when the rule is on AND we lack the weapon.
    proficient = True
    prof_pen = 0
    specialised = False
    if spec.ruleset.weapon_proficiency:
        classes = [data.classes[e.class_id] for e in spec.classes if e.class_id in data.classes]
        proficient = is_proficient(weapon.id, spec)
        if not proficient:
            prof_pen = penalty_for_classes(classes)
        specialised = is_specialised(weapon.id, spec)
    spec_hit = 1 if specialised else 0
    spec_dmg = 1 if specialised else 0
```

(d) Update the three inner helpers to fold in the specialisation bonus:

```python
    def hit_thac0(extra: int) -> int:
        return base_thac0 - atk_mod - prof_pen - spec_hit - extra - g_atk

    def hit_asc(extra: int) -> int:
        return base_attack + atk_mod + prof_pen + spec_hit + extra + g_atk

    def dmg(extra: int) -> str:
        return _format_damage(base_damage, dmg_mod + g_dmg + spec_dmg + extra)
```

(e) Add `specialised=specialised,` to the `AttackProfile(...)` return in `_profile_for` (next to `proficient=proficient,`).

> The synthetic unarmed profile keeps `specialised=False` by default — no change needed in `_unarmed_profile`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_attacks.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/attacks.py tests/test_equip_attacks.py
git commit -m "feat(attacks): per-weapon proficiency penalty + specialisation +1/+1"
```

---

## Part 3 — Equip-time class enforcement

### Task 8: Allowance resolver

**Files:**
- Modify: `aose/engine/proficiency.py`
- Test: `tests/test_equip_enforcement.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_equip_enforcement.py`:

```python
"""Class weapon/armour/shield allowance resolver + equip enforcement."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine.proficiency import (
    allowed_armor_ids,
    allowed_weapon_ids,
    shields_allowed,
)

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


def test_fighter_unrestricted(data):
    fighter = data.classes["fighter"]
    assert allowed_weapon_ids([fighter], data) == "all"
    assert allowed_armor_ids([fighter], data) == "all"
    assert shields_allowed([fighter]) is True


def test_cleric_weapon_list_resolved_with_spaces(data):
    cleric = data.classes["cleric"]
    ids = allowed_weapon_ids([cleric], data)
    # "war hammer" normalised to war_hammer; staff/club/mace/sling present
    assert ids != "all"
    assert {"club", "mace", "sling", "staff", "war_hammer"}.issubset(ids)


def test_thief_armor_leather_resolved(data):
    thief = data.classes["thief"]
    armor = allowed_armor_ids([thief], data)
    assert armor != "all"
    assert "leather_armor" in armor
    assert shields_allowed([thief]) is False


def test_freeform_allowance_fails_open(data):
    # A class with an unresolvable entry → unrestricted for that category.
    bogus = data.classes["fighter"].model_copy(
        update={"weapons_allowed": ["any appropriate to size"]}
    )
    assert allowed_weapon_ids([bogus], data) == "all"


def test_multiclass_union_unrestricted_wins(data):
    cleric = data.classes["cleric"]      # weapon list
    fighter = data.classes["fighter"]    # all
    assert allowed_weapon_ids([cleric, fighter], data) == "all"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_enforcement.py -q`
Expected: FAIL — resolver functions don't exist.

- [ ] **Step 3: Add the resolver to `aose/engine/proficiency.py`**

Add the import at the top (extend the models import):

```python
from aose.models import Armor, CharClass, CharacterSpec, Weapon
```

Append the resolver section:

```python
# ── Class allowance resolver ────────────────────────────────────────────────

AllowedIds = "set[str] | Literal['all']"  # documentation alias


def _normalize(text: str) -> str:
    return text.strip().lower().replace(" ", "_").replace("-", "_")


def _resolve_entries(entries: list[str], candidates) -> "set[str] | str":
    """Resolve prose allowance entries to item ids by matching normalised ids
    and names.  Any entry that resolves to nothing → ``"all"`` (fail-open)."""
    by_key: dict[str, str] = {}
    for item in candidates:
        by_key[_normalize(item.id)] = item.id
        by_key[_normalize(item.name)] = item.id
    resolved: set[str] = set()
    for entry in entries:
        match = by_key.get(_normalize(entry))
        if match is None:
            return "all"  # freeform / unrecognised → unrestricted
        resolved.add(match)
    return resolved


def _union(values: list["set[str] | str"]) -> "set[str] | str":
    out: set[str] = set()
    for v in values:
        if v == "all":
            return "all"
        out |= v
    return out


def allowed_weapon_ids(classes: list[CharClass], data) -> "set[str] | str":
    weapons = [i for i in data.items.values() if isinstance(i, Weapon)]
    per_class: list["set[str] | str"] = []
    for cls in classes:
        if cls.weapons_allowed == "all":
            per_class.append("all")
        else:
            per_class.append(_resolve_entries(list(cls.weapons_allowed), weapons))
    return _union(per_class)


def allowed_armor_ids(classes: list[CharClass], data) -> "set[str] | str":
    armors = [i for i in data.items.values() if isinstance(i, Armor) and not i.is_shield]
    per_class: list["set[str] | str"] = []
    for cls in classes:
        if cls.armor_allowed == "all":
            per_class.append("all")
        elif not cls.armor_allowed:           # empty list → nothing allowed
            per_class.append(set())
        else:
            per_class.append(_resolve_entries(list(cls.armor_allowed), armors))
    return _union(per_class)


def shields_allowed(classes: list[CharClass]) -> bool:
    return any(cls.shields_allowed for cls in classes)
```

> Note `Literal` is already imported at the top of the module (Task 4). The string aliases above are documentation only — the real return type is `set[str] | str` where the string is the sentinel `"all"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_enforcement.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/proficiency.py tests/test_equip_enforcement.py
git commit -m "feat(proficiency): class weapon/armour/shield allowance resolver"
```

---

### Task 9: `equip()` enforcement

**Files:**
- Modify: `aose/engine/equip.py`
- Test: `tests/test_equip_enforcement.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_equip_enforcement.py`:

```python
from aose.engine.equip import equip


def test_equip_rejects_disallowed_weapon(data):
    # cleric: weapons limited; a sword is not allowed.
    allowed = allowed_weapon_ids([data.classes["cleric"]], data)
    with pytest.raises(ValueError, match="cannot use"):
        equip(["sword"], {}, [], "sword", data, allowed_weapons=allowed)


def test_equip_allows_allowed_weapon(data):
    allowed = allowed_weapon_ids([data.classes["cleric"]], data)
    _eq, weapons = equip(["mace"], {}, [], "mace", data, allowed_weapons=allowed)
    assert weapons == ["mace"]


def test_equip_rejects_disallowed_armor(data):
    allowed = allowed_armor_ids([data.classes["thief"]], data)  # leather only
    with pytest.raises(ValueError, match="cannot use"):
        equip(["plate_mail"], {}, [], "plate_mail", data, allowed_armor=allowed)


def test_equip_rejects_shield_when_not_allowed(data):
    with pytest.raises(ValueError, match="shield"):
        equip(["shield"], {}, [], "shield", data, allow_shields=False)


def test_equip_unrestricted_by_default(data):
    # No allowance args → no enforcement (backward compatible).
    _eq, weapons = equip(["sword"], {}, [], "sword", data)
    assert weapons == ["sword"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_enforcement.py -q`
Expected: FAIL — `equip()` has no allowance keyword args.

- [ ] **Step 3: Update `aose/engine/equip.py`**

Change the `equip` signature and add enforcement. Replace the function definition through the `Armor`/`Weapon` branches:

```python
def equip(inventory: list[str], equipped: dict[str, str],
          equipped_weapons: list[str], item_id: str,
          data: GameData,
          allowed_weapons: "set[str] | str" = "all",
          allowed_armor: "set[str] | str" = "all",
          allow_shields: bool = True) -> tuple[dict[str, str], list[str]]:
    """Equip one copy of ``item_id`` from ``inventory``.  Returns new
    (equipped, equipped_weapons).  Raises ValueError if the item isn't owned
    or isn't equippable, if a copy is already equipped past the inventory
    count, or if the character's class allowances forbid it.

    ``allowed_weapons`` / ``allowed_armor`` are either the sentinel ``"all"``
    (unrestricted) or a set of permitted ids; ``allow_shields`` gates shields.
    Defaults are unrestricted so callers that don't enforce stay unaffected."""
    if item_id not in data.items:
        raise ValueError(f"Unknown item {item_id!r}")
    item = data.items[item_id]
    owned = _count(inventory, item_id)
    if owned == 0:
        raise ValueError(f"{item.name!r} is not in inventory")

    new_eq = dict(equipped)
    new_weapons = list(equipped_weapons)

    if isinstance(item, Armor):
        if item.is_shield:
            if not allow_shields:
                raise ValueError(f"This class cannot use a shield")
        elif allowed_armor != "all" and item_id not in allowed_armor:
            raise ValueError(f"This class cannot use {item.name!r}")
        slot = "shield" if item.is_shield else "armor"
        new_eq[slot] = item_id
        return new_eq, new_weapons

    if isinstance(item, Weapon):
        if allowed_weapons != "all" and item_id not in allowed_weapons:
            raise ValueError(f"This class cannot use {item.name!r}")
        already_equipped = _count(equipped_weapons, item_id)
        if already_equipped >= owned:
            raise ValueError(
                f"All {owned} copies of {item.name!r} already equipped"
            )
        new_weapons.append(item_id)
        return new_eq, new_weapons

    raise ValueError(f"{item.name!r} is not equippable")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_enforcement.py -q`
Expected: PASS.

- [ ] **Step 5: Wire allowances into the sheet equip route**

In `aose/web/routes.py`, update `equipment_equip` to compute and pass allowances:

```python
@router.post("/character/{character_id}/equipment/equip")
async def equipment_equip(request: Request, character_id: str,
                          item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    classes = [data.classes[e.class_id] for e in spec.classes if e.class_id in data.classes]
    try:
        spec.equipped, spec.equipped_weapons = _equip(
            spec.inventory, spec.equipped, spec.equipped_weapons,
            item_id, data,
            allowed_weapons=allowed_weapon_ids(classes, data),
            allowed_armor=allowed_armor_ids(classes, data),
            allow_shields=shields_allowed(classes),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

Add the import near the top of `routes.py` (with the other engine imports):

```python
from aose.engine.proficiency import (
    allowed_armor_ids,
    allowed_weapon_ids,
    shields_allowed,
)
```

- [ ] **Step 6: Wire allowances into the wizard equip route**

In `aose/web/wizard.py`, update `post_equipment_equip`:

```python
@router.post("/{draft_id}/equipment/equip")
async def post_equipment_equip(request: Request, draft_id: str, item_id: str = Form(...)):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    classes = [data.classes[cid] for cid in _class_ids(draft) if cid in data.classes]
    try:
        new_eq, new_weapons = _equip(
            draft.get("inventory", []),
            draft.get("equipped", {}),
            draft.get("equipped_weapons", []),
            item_id, data,
            allowed_weapons=allowed_weapon_ids(classes, data),
            allowed_armor=allowed_armor_ids(classes, data),
            allow_shields=shields_allowed(classes),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["equipped"] = new_eq
    draft["equipped_weapons"] = new_weapons
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")
```

Update the `aose/web/wizard.py` proficiency import line (currently `from aose.engine.proficiency import proficiency_groups, starting_proficiency_count`) to also bring in the resolver — final import is set in Task 10; for now add the resolver names so this route resolves:

```python
from aose.engine.proficiency import (
    allowed_armor_ids,
    allowed_weapon_ids,
    shields_allowed,
)
```

> The old `proficiency_groups` / `starting_proficiency_count` imports are removed here and the proficiency routes are rewritten in Task 10 — `wizard.py` will not import cleanly until Task 10 is done. Run the equip-enforcement tests (which don't import `wizard.py`) to validate Task 9; the web smoke tests run after Task 10.

- [ ] **Step 7: Run targeted tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_enforcement.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add aose/engine/equip.py aose/web/routes.py aose/web/wizard.py tests/test_equip_enforcement.py
git commit -m "feat(equip): enforce class weapon/armour/shield allowances at equip time"
```

---

## Part 4 — Wizard + sheet UI

### Task 10: Wizard per-weapon picker

**Files:**
- Modify: `aose/web/wizard.py`
- Rewrite: `aose/web/templates/wizard/proficiencies.html`
- Modify: `tests/test_weapon_proficiency.py`

- [ ] **Step 1: Write the failing web tests**

Append a web section to `tests/test_weapon_proficiency.py`:

```python
from fastapi.testclient import TestClient

from aose.characters import load_character, load_draft, save_draft, save_settings
from aose.web.app import create_app


@pytest.fixture
def client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, RuleSet(weapon_proficiency=True))
    app = create_app(
        data_dir=DATA_DIR, characters_dir=characters_dir, drafts_dir=drafts_dir,
        examples_dir=examples_dir, settings_path=settings_path,
    )
    c = TestClient(app, follow_redirects=False)
    c._settings_path = settings_path
    c._drafts_dir = drafts_dir
    c._characters_dir = characters_dir
    return c


def _start_fighter(client):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    return draft_id


def _start_magic_user(client):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 10, "INT": 15, "WIS": 11, "DEX": 13, "CON": 12, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Raistlin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "magic_user"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "neutral"})
    return draft_id


def test_fighter_picker_shows_four_slots_and_weapons(client):
    draft_id = _start_fighter(client)
    r = client.get(f"/wizard/{draft_id}/proficiencies")
    assert r.status_code == 200
    assert "4" in r.text          # martial slot count
    assert "Sword" in r.text      # individual weapon, not a group
    assert "Specialise" in r.text  # martial → specialise option offered


def test_magic_user_picker_shows_one_slot_filtered(client):
    draft_id = _start_magic_user(client)
    r = client.get(f"/wizard/{draft_id}/proficiencies")
    assert r.status_code == 200
    assert "Dagger" in r.text
    assert "Staff" in r.text
    assert "Sword" not in r.text          # filtered out — not allowed
    assert "Specialise" not in r.text     # non-martial → no specialisation


def test_magic_user_post_one_weapon_advances(client):
    draft_id = _start_magic_user(client)
    r = client.post(f"/wizard/{draft_id}/proficiencies",
                    data={"weapon": ["dagger"]})
    assert r.status_code == 303
    assert r.headers["location"].endswith("/hp")
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["proficiencies"]["weapons"] == ["dagger"]


def test_post_wrong_count_rejected(client):
    draft_id = _start_magic_user(client)
    r = client.post(f"/wizard/{draft_id}/proficiencies",
                    data={"weapon": ["dagger", "staff"]})  # 2 > 1 slot
    assert r.status_code == 400


def test_post_disallowed_weapon_rejected(client):
    draft_id = _start_magic_user(client)
    r = client.post(f"/wizard/{draft_id}/proficiencies",
                    data={"weapon": ["sword"]})  # not allowed for magic-user
    assert r.status_code == 400


def test_fighter_specialise_costs_two_slots(client):
    draft_id = _start_fighter(client)
    # 1 specialised weapon (2 slots) + 2 plain (2 slots) = 4 slots total
    r = client.post(f"/wizard/{draft_id}/proficiencies",
                    data={"weapon": ["sword", "spear", "mace"],
                          "specialise": ["sword"]})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["proficiencies"]["weapons"] == ["sword", "spear", "mace"]
    assert draft["proficiencies"]["specialisations"] == ["sword"]


def test_specialise_for_non_martial_rejected(client):
    draft_id = _start_magic_user(client)
    r = client.post(f"/wizard/{draft_id}/proficiencies",
                    data={"weapon": ["dagger"], "specialise": ["dagger"]})
    assert r.status_code == 400


def test_proficiencies_persist_to_character(client):
    draft_id = _start_fighter(client)
    client.post(f"/wizard/{draft_id}/proficiencies",
                data={"weapon": ["sword", "spear", "mace", "hand_axe"]})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    spec = load_character(char_id, client._characters_dir)
    assert set(spec.weapon_proficiencies) == {"sword", "spear", "mace", "hand_axe"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_proficiency.py -q`
Expected: FAIL (and `wizard.py` may still import removed names).

- [ ] **Step 3: Rewrite the proficiency routes in `aose/web/wizard.py`**

(a) Set the final proficiency import block (replacing the Task-9 stopgap and the old import):

```python
from aose.engine.proficiency import (
    allowed_armor_ids,
    allowed_weapon_ids,
    category_for_classes,
    shields_allowed,
    specialisation_allowed,
    total_proficiency_slots,
)
```

(b) Replace `_proficiency_slots_for` and both route handlers with:

```python
def _proficiency_context(draft: dict[str, Any], data) -> dict:
    """Slots, weapon options (filtered to class allowances), and specialise
    flag for the proficiency step."""
    ids = _class_ids(draft)
    classes = [data.classes[cid] for cid in ids if cid in data.classes]
    pairs = [(c, 1) for c in classes]                 # creation = level 1
    required = total_proficiency_slots(pairs)
    allow_special = specialisation_allowed(classes)
    allowed = allowed_weapon_ids(classes, data)
    from aose.models import Weapon
    weapons = sorted(
        (i for i in data.items.values() if isinstance(i, Weapon)),
        key=lambda w: w.name,
    )
    if allowed != "all":
        weapons = [w for w in weapons if w.id in allowed]
    label = " / ".join(c.name for c in classes) if classes else ""
    chosen = draft.get("proficiencies", {}) or {}
    chosen_weapons = set(chosen.get("weapons", []))
    chosen_special = set(chosen.get("specialisations", []))
    rows = [
        {
            "id": w.id,
            "name": w.name,
            "qualities": ", ".join(w.qualities),
            "selected": w.id in chosen_weapons,
            "specialised": w.id in chosen_special,
        }
        for w in weapons
    ]
    return {
        "class_name": label,
        "required": required,
        "weapons": rows,
        "allow_specialise": allow_special,
    }


@router.get("/{draft_id}/proficiencies", response_class=HTMLResponse)
async def get_proficiencies(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "proficiencies", draft_id)
    if redirect:
        return redirect
    data = request.app.state.game_data
    ctx = _base_context(request, draft_id, draft, "proficiencies")
    ctx.update(_proficiency_context(draft, data))
    if not ctx["weapons"]:
        raise HTTPException(
            500,
            "Weapon Proficiency rule is active but the class has no usable "
            "weapons in the data set.",
        )
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/proficiencies")
async def post_proficiencies(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    form = await request.form()
    weapons = list(dict.fromkeys(form.getlist("weapon")))
    specialisations = list(dict.fromkeys(form.getlist("specialise")))

    ids = _class_ids(draft)
    classes = [data.classes[cid] for cid in ids if cid in data.classes]
    pairs = [(c, 1) for c in classes]
    required = total_proficiency_slots(pairs)
    allowed = allowed_weapon_ids(classes, data)
    allow_special = specialisation_allowed(classes)

    # Every pick must be allowed.
    if allowed != "all":
        bad = [w for w in weapons if w not in allowed]
        if bad:
            raise HTTPException(400, f"Weapon(s) not allowed for this class: {bad}")
    # Specialisations must be proficient weapons, and only when martial.
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
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/hp")
```

(c) Update the finalize `CharacterSpec(...)` construction (currently `chosen_proficiencies=list(draft.get("proficiencies", []))`) to read the new dict shape:

```python
        weapon_proficiencies=list((draft.get("proficiencies") or {}).get("weapons", [])),
        weapon_specialisations=list((draft.get("proficiencies") or {}).get("specialisations", [])),
```

- [ ] **Step 4: Rewrite the template**

Replace the entire contents of `aose/web/templates/wizard/proficiencies.html`:

```html
<h2>Weapon Proficiencies</h2>
<p>{{ class_name }} starts with <strong>{{ required }}</strong> weapon
   proficiency slot{{ "s" if required != 1 else "" }}. Proficiency is chosen
   per individual weapon. Non-proficient attacks suffer a to-hit penalty by
   class.{% if allow_specialise %} A martial character may
   <strong>specialise</strong> in a weapon (costs 2 slots) for +1 to hit and
   +1 damage.{% endif %}</p>

<form method="post" action="/wizard/{{ draft_id }}/proficiencies" class="step-form">
    <table class="prof-table" data-required="{{ required }}"
           data-specialise="{{ 1 if allow_specialise else 0 }}">
        <thead>
            <tr>
                <th>Proficient</th><th>Weapon</th><th>Qualities</th>
                {% if allow_specialise %}<th>Specialise (2)</th>{% endif %}
            </tr>
        </thead>
        <tbody>
            {% for w in weapons %}
            <tr>
                <td><input type="checkbox" name="weapon" value="{{ w.id }}"
                           class="prof-weapon" {% if w.selected %}checked{% endif %}></td>
                <td>{{ w.name }}</td>
                <td class="muted small">{{ w.qualities }}</td>
                {% if allow_specialise %}
                <td><input type="checkbox" name="specialise" value="{{ w.id }}"
                           class="prof-special" {% if w.specialised %}checked{% endif %}></td>
                {% endif %}
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <p class="muted" id="prof-counter">Spend exactly {{ required }} slot{{ "s" if required != 1 else "" }}.</p>
    <button type="submit" class="primary">Next: Hit Points &rarr;</button>
</form>

<script>
    (function () {
        const required = {{ required }};
        const table = document.querySelector('.prof-table');
        const counter = document.getElementById('prof-counter');

        function rowOf(el) { return el.closest('tr'); }

        function spent() {
            let n = 0;
            table.querySelectorAll('.prof-weapon:checked').forEach(() => n += 1);
            table.querySelectorAll('.prof-special:checked').forEach(() => n += 1);
            return n;
        }
        function refresh() {
            // A specialise tick implies proficiency in the same row.
            table.querySelectorAll('.prof-special:checked').forEach(s => {
                const w = rowOf(s).querySelector('.prof-weapon');
                if (w && !w.checked) { w.checked = true; }
            });
            const n = spent();
            counter.textContent = `Spent ${n} of ${required}.`;
            counter.className = (n === required) ? '' : 'muted';
        }
        table.addEventListener('change', refresh);
        refresh();
    })();
</script>
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_proficiency.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/web/wizard.py aose/web/templates/wizard/proficiencies.html tests/test_weapon_proficiency.py
git commit -m "feat(wizard): per-weapon proficiency picker with class filtering + specialisation"
```

---

### Task 11: Sheet per-weapon proficiency view + qualities reference

**Files:**
- Modify: `aose/sheet/view.py`
- Modify: `aose/web/templates/sheet.html`, `sheet_print.html`, `wizard/review.html`
- Modify: `tests/test_weapon_proficiency.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_weapon_proficiency.py`:

```python
from aose.sheet.view import build_sheet


def test_sheet_proficiency_view_per_weapon(data):
    spec = _base_spec(
        weapon_proficiencies=["sword", "spear"],
        weapon_specialisations=["sword"],
        ruleset=RuleSet(weapon_proficiency=True),
    )
    sheet = build_sheet(spec, data)
    view = sheet.proficiencies
    names = {p.name for p in view.weapons}
    assert names == {"Sword", "Spear"}
    sword = next(p for p in view.weapons if p.name == "Sword")
    assert sword.specialised is True
    assert view.category == "martial"
    assert view.penalty == -2


def test_sheet_proficiency_view_empty_when_rule_off(data):
    spec = _base_spec(weapon_proficiencies=["sword"],
                      ruleset=RuleSet(weapon_proficiency=False))
    sheet = build_sheet(spec, data)
    assert sheet.proficiencies is None
    assert sheet.weapon_proficiency_active is False


def test_sheet_lists_qualities_reference_for_equipped_weapons(data):
    spec = _base_spec(
        inventory=["sword"],
        equipped_weapons=["sword"],
        ruleset=RuleSet(weapon_proficiency=True),
        weapon_proficiencies=["sword"],
    )
    sheet = build_sheet(spec, data)
    ref_ids = {q.id for q in sheet.weapon_qualities_reference}
    assert "melee" in ref_ids  # sword has the melee quality


def test_sheet_html_renders_per_weapon_section(client):
    draft_id = _start_fighter(client)
    client.post(f"/wizard/{draft_id}/proficiencies",
                data={"weapon": ["sword", "spear", "mace", "hand_axe"]})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    r = client.get(f"/character/{char_id}")
    assert "Weapon Proficiencies" in r.text
    assert "Sword" in r.text
    assert "&minus;2" in r.text  # martial penalty shown
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_proficiency.py -q`
Expected: FAIL — `proficiencies` is still the old list type; no `weapon_qualities_reference`.

- [ ] **Step 3: Update the view models in `aose/sheet/view.py`**

Replace the `WeaponDisplay` / `ProficiencyDisplay` classes:

```python
class ProficientWeaponView(BaseModel):
    id: str
    name: str
    damage: str
    specialised: bool = False


class ProficiencyView(BaseModel):
    category: str                       # "martial" / "semi_martial" / "non_martial"
    penalty: int                        # non-proficiency to-hit penalty
    slots_total: int
    slots_spent: int
    weapons: list[ProficientWeaponView]


class WeaponQualityRef(BaseModel):
    id: str
    name: str
    description: str
```

In the `CharacterSheet` model, change the proficiency fields:

```python
    proficiencies: "ProficiencyView | None"  # None when rule off
    weapon_proficiency_active: bool
    weapon_qualities_reference: list["WeaponQualityRef"]
```

- [ ] **Step 4: Replace `_proficiency_display` with `_proficiency_view` + qualities ref**

Replace the `_proficiency_display` function with:

```python
def _proficiency_view(spec: CharacterSpec, data: GameData) -> "ProficiencyView | None":
    """Per-weapon proficiency view for the sheet.  None when the rule is off."""
    from aose.engine.proficiency import (
        category_for_classes,
        penalty_for_classes,
        slots_spent,
        total_proficiency_slots,
    )
    from aose.models import Weapon

    if not spec.ruleset.weapon_proficiency:
        return None

    classes = [data.classes[e.class_id] for e in spec.classes if e.class_id in data.classes]
    pairs = [(data.classes[e.class_id], e.level) for e in spec.classes
             if e.class_id in data.classes]
    use_variable = spec.ruleset.variable_weapon_damage
    weapons: list[ProficientWeaponView] = []
    for wid in spec.weapon_proficiencies:
        item = data.items.get(wid)
        if not isinstance(item, Weapon):
            continue
        weapons.append(ProficientWeaponView(
            id=item.id,
            name=item.name,
            damage=(item.damage.variable if use_variable else item.damage.default),
            specialised=wid in spec.weapon_specialisations,
        ))
    weapons.sort(key=lambda w: w.name)
    return ProficiencyView(
        category=category_for_classes(classes) if classes else "non_martial",
        penalty=penalty_for_classes(classes) if classes else -5,
        slots_total=total_proficiency_slots(pairs),
        slots_spent=slots_spent(spec),
        weapons=weapons,
    )


def _weapon_qualities_reference(spec: CharacterSpec, data: GameData) -> list["WeaponQualityRef"]:
    """Quality definitions for qualities present on the character's equipped or
    owned weapons — for the in-game reference block."""
    from aose.models import Weapon

    present: set[str] = set()
    for wid in set(spec.inventory) | set(spec.equipped_weapons):
        item = data.items.get(wid)
        if isinstance(item, Weapon):
            present.update(item.qualities)
    refs = [
        WeaponQualityRef(id=q.id, name=q.name, description=q.description)
        for qid in sorted(present)
        if (q := data.qualities.get(qid)) is not None
    ]
    return refs
```

- [ ] **Step 5: Wire the new fields into `build_sheet`**

In `build_sheet`, replace:

```python
        proficiencies=_proficiency_display(spec, data),
        weapon_proficiency_active=spec.ruleset.weapon_proficiency,
```

with:

```python
        proficiencies=_proficiency_view(spec, data),
        weapon_proficiency_active=spec.ruleset.weapon_proficiency,
        weapon_qualities_reference=_weapon_qualities_reference(spec, data),
```

- [ ] **Step 6: Update `sheet.html`**

Replace the proficiency `<section>` (the `{% if sheet.weapon_proficiency_active %}` block) with:

```html
            {% if sheet.weapon_proficiency_active %}
            <section class="section">
                <h2>Weapon Proficiencies</h2>
                {% if sheet.proficiencies and sheet.proficiencies.weapons %}
                <p class="small muted">
                    {{ sheet.proficiencies.category | replace("_", "-") | title }} &mdash;
                    non-proficient attacks: &minus;{{ -sheet.proficiencies.penalty }} to hit
                    ({{ sheet.proficiencies.slots_spent }}/{{ sheet.proficiencies.slots_total }} slots used)
                </p>
                <ul>
                    {% for w in sheet.proficiencies.weapons %}
                    <li>
                        <strong>{{ w.name }}</strong>
                        <span class="muted small">({{ w.damage }})</span>
                        {% if w.specialised %}
                        <span class="small">&mdash; specialised (+1 hit / +1 dmg)</span>
                        {% endif %}
                    </li>
                    {% endfor %}
                </ul>
                {% else %}
                <p class="muted">None</p>
                {% if sheet.proficiencies %}
                <p class="small muted">Non-proficient attacks: &minus;{{ -sheet.proficiencies.penalty }} to hit.</p>
                {% endif %}
                {% endif %}

                {% if sheet.weapon_qualities_reference %}
                <details class="qualities-ref">
                    <summary>Weapon Qualities</summary>
                    <ul>
                        {% for q in sheet.weapon_qualities_reference %}
                        <li><strong>{{ q.name }}</strong> &mdash; {{ q.description }}</li>
                        {% endfor %}
                    </ul>
                </details>
                {% endif %}
            </section>
            {% endif %}
```

Also update the attacks table non-prof marker (around line 84) to show the per-class penalty and specialisation. Replace the `{% if not atk.proficient %}` snippet with:

```html
                                {% if not atk.proficient %}
                                <span class="muted small" title="Non-proficient: penalty applied">(non-prof)</span>
                                {% endif %}
                                {% if atk.specialised %}
                                <span class="small" title="Weapon specialisation: +1 hit / +1 damage">(spec.)</span>
                                {% endif %}
```

- [ ] **Step 7: Update `sheet_print.html`**

Replace its `{% if sheet.weapon_proficiency_active %}` block (around line 116) with:

```html
    {% if sheet.weapon_proficiency_active %}
    <div class="prof-block">
        <strong>Weapon Proficiencies</strong>
        {% if sheet.proficiencies and sheet.proficiencies.weapons %}
        <span class="muted small">
            ({{ sheet.proficiencies.category | replace("_", "-") | title }};
            non-prof &minus;{{ -sheet.proficiencies.penalty }})
        </span>
        <ul>
            {% for w in sheet.proficiencies.weapons %}
            <li>{{ w.name }} ({{ w.damage }}){% if w.specialised %} — spec.{% endif %}</li>
            {% endfor %}
        </ul>
        {% else %}
        <p class="muted small" style="margin:3pt 0 0 0;">None</p>
        {% endif %}
    </div>
    {% endif %}
```

- [ ] **Step 8: Update `wizard/review.html`**

Replace the proficiency stat-row (line ~55) with:

```html
            {% if sheet.weapon_proficiency_active %}
            <div class="stat-row"><span>Profs</span><span>{{ sheet.proficiencies.weapons | map(attribute='name') | join(", ") if (sheet.proficiencies and sheet.proficiencies.weapons) else "—" }}</span></div>
            {% endif %}
```

- [ ] **Step 9: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_proficiency.py -q`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add aose/sheet/view.py aose/web/templates/sheet.html aose/web/templates/sheet_print.html aose/web/templates/wizard/review.html tests/test_weapon_proficiency.py
git commit -m "feat(sheet): per-weapon proficiency view + weapon qualities reference"
```

---

### Task 12: Full-suite green + multi-class spot check

**Files:**
- Modify: `tests/test_multiclassing.py` (only if it references removed fields)

- [ ] **Step 1: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: any remaining failures are references to `chosen_proficiencies`, `proficiency_group`, `is_proficient_with`, `starting_proficiency_count`, `ProficiencyConfig`, or the old ids `long_sword`/`light_crossbow`.

- [ ] **Step 2: Fix stragglers**

For each failing file, apply the mechanical replacements:
- `chosen_proficiencies=[...]` → `weapon_proficiencies=[...]`
- `long_sword` → `sword`, `light_crossbow` → `crossbow`
- Remove/rename any assertions on the deleted helpers.

In `tests/test_multiclassing.py`, if it sets `chosen_proficiencies` or asserts proficiency behaviour, update to `weapon_proficiencies`/`weapon_specialisations`. If it asserts a fighter/magic-user multi-class slot count, the expected total is `max` of the per-class slots (e.g. fighter+magic_user @ L1 = 4).

- [ ] **Step 3: Re-run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing `pytest-current` PermissionError).

- [ ] **Step 4: Manual smoke (optional but recommended)**

Run the app and walk a magic-user through with Weapon Proficiency on; confirm 1 slot, only Dagger/Staff offered, no Specialise option; then a fighter: 4 slots, all allowed weapons, Specialise column present; try to equip a forbidden weapon on the magic-user and confirm the 400.

```powershell
.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload
```

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: reconcile remaining suites with per-weapon proficiency model"
```

---

## Self-Review

**Spec coverage:**
- §3.1 drop `proficiency_group`, populate `qualities` → Tasks 3, 3-data ✓
- §3.2 weapons rewrite (renames, new ids, book stats) → Task 3 ✓
- §3.3 `weapon_qualities.yaml` + `WeaponQuality` + loader → Tasks 1, 2 ✓
- §3.4 armour sanity (no change) → covered by existing tests staying green (Task 12) ✓
- §3.5 sheet quality chips + reference → Task 11 (qualities reference; attack rows show quality via existing weapon rows) ✓
- §4.1 `combat_category` + helpers → Task 4 ✓
- §4.2 full leveling + creation-spend rule (exact at L1) → Tasks 4 (slots), 10 (exact-spend validation) ✓
- §4.3 per-weapon accounting + specialisation slot cost + invariant (specialise⊆proficient) → Tasks 6, 10 ✓
- §4.4 attack calculator penalty + specialisation + `specialised` flag → Task 7 ✓
- §5.1 allowance resolver (normalise, fail-open, union) → Task 8 ✓
- §5.2 `equip()` enforcement, buying unaffected → Task 9 ✓
- §6.1 model swap + migration → Task 5 ✓
- §6.2 picker filtered + specialise + live counter → Task 10 ✓
- §6.3 sheet per-weapon view + qualities reference + templates → Task 11 ✓
- §7 edge cases (legacy drop, id-rename orphans accepted, ProficiencyConfig removed) → Tasks 3, 5 ✓

**Type consistency:** `combat_category`/`category_for_classes` return the `Category` literal; `ProficiencyView.category` stored as `str`. `proficiencies` on the sheet is `ProficiencyView | None` (templates guard with `if sheet.proficiencies`). `equip()` allowance args are `set[str] | "all"` sentinel, defaulting unrestricted. Draft `proficiencies` key is consistently `{"weapons": [...], "specialisations": [...]}` across Tasks 10–11 and finalize.

**Placeholder scan:** No TBD/TODO; every code step shows full code. The cleric `staff`/`war hammer` and magic-user `dagger`/`staff` allowance data already exist and resolve against the new weapon ids.
