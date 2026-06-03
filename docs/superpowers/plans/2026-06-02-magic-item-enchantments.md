# Magic Item Enchantments — extensible composition model (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Model magic weapons/armour as a runtime *composition* of a base item + a reusable `Enchantment`, so a new base weapon/armour is adopted into every relevant magic chart by tagging alone — no combinatorial hand-authoring.

**Architecture:** A new `Enchantment` registry (`data/enchantments.yaml` → `GameData.enchantments`) is independent of any base item. A per-character `EnchantedInstance` pairs a base id + enchantment id; a cycle-free engine module `aose/engine/enchant.py` resolves the pair to a synthetic `Weapon`/`Armor` on the fly. Derivation modules (AC, attacks, saves, encumbrance) consume the resolved items and the enchantment's passive `Modifier`s, which `magic.py::active_modifiers` now also collects. Nothing composed is persisted. Acquisition is sheet-only and Add-only (GM grant, no gold).

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, pytest. Windows/PowerShell; run via `.venv\Scripts\python.exe`.

---

## Conventions for every task

- Run tests with: `.venv\Scripts\python.exe -m pytest tests/ -q` (the trailing `pytest-current` PermissionError is a known Windows quirk — ignore it).
- Run a single test file/case with e.g. `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -q`.
- Pydantic models in this codebase use `model_config = ConfigDict(extra="forbid")`.
- This app is local single-user and **not deployed** — no data migrations; just change shapes.
- Commit after each task with the message shown.

## File structure (what gets created / changed)

| File | Responsibility | Change |
|---|---|---|
| `aose/models/enchantment.py` | `Enchantment`, `AppliesTo` registry models | **create** |
| `aose/models/item.py` | add `Weapon.groups`, `Armor.groups`, `Armor.ac_bonus` | modify |
| `aose/models/character.py` | add `EnchantedInstance`, `CharacterSpec.enchanted` | modify |
| `aose/models/__init__.py` | export new models | modify |
| `aose/data/loader.py` | load `enchantments.yaml` into `GameData.enchantments` | modify |
| `aose/engine/enchant.py` | matching/resolution/lifecycle (cycle-free core) | **create** |
| `aose/engine/magic.py` | `active_modifiers` also collects enchanted modifiers | modify |
| `aose/engine/armor_class.py` | shield `ac_bonus` refactor + enchanted base/shield | modify |
| `aose/engine/attacks.py` | second loop: equipped enchanted weapons | modify |
| `aose/engine/encumbrance.py` | count enchanted-instance weight | modify |
| `aose/sheet/view.py` | enchanted rows in the Magic Items view | modify |
| `aose/web/routes.py` | sheet enchanted routes + Add picker | modify |
| `aose/web/wizard.py` | mundane-only equipment (no magic/enchanted acquisition) | modify |
| `aose/web/templates/_equipment_ui.html` | gate magic UI; enchanted panel + Add picker | modify |
| `aose/web/templates/sheet.html` | enchanted instances already flow via `sheet.magic_items` | (no change expected) |
| `data/enchantments.yaml` | minimal representative seed | **create** |
| `data/equipment/weapons.yaml` | add `groups` + 2 new base weapons | modify |
| `data/equipment/armor.yaml` | add `groups` + `ac_bonus`; `shield` → `ac_bonus: 1` | modify |
| `data/equipment/magic_items.yaml` | **delete** (placeholder removed) | delete |
| `tests/test_enchantments.py` | all new-feature tests | **create** |
| `tests/test_magic_items.py` | rework DATA_DIR-dependent web tests | modify |
| `tests/test_equip_enforcement.py` | migrate magic-variant tests to enchanted | modify |
| `tests/test_weapon_proficiency.py` | migrate magic-variant tests to enchanted | modify |

---

## Task 1: `Enchantment` registry model

**Files:**
- Create: `aose/models/enchantment.py`
- Modify: `aose/models/__init__.py`
- Test: `tests/test_enchantments.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_enchantments.py`:

```python
"""Tests for the magic-item enchantment composition model (Phase 1)."""
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def test_enchantment_parses_minimal():
    from aose.models import Enchantment
    e = Enchantment(
        id="plus_1",
        name_template="{base} +1",
        kind="weapon",
        applies_to={"include": ["any_weapon"]},
    )
    assert e.magic_bonus == 0
    assert e.conditional_bonus is None
    assert e.modifiers == []
    assert e.applies_to.include == ["any_weapon"]
    assert e.applies_to.exclude == []
    assert e.cursed is False


def test_enchantment_full_fields():
    from aose.models import Enchantment
    e = Enchantment(
        id="sword_plus_1_vs_undead",
        name_template="{base} +1, +3 vs Undead",
        kind="weapon",
        applies_to={"include": ["sword"], "exclude": []},
        magic_bonus=1,
        conditional_bonus={"vs": "undead", "bonus": 2},
        modifiers=[{"target": "save:all", "op": "add", "value": 1}],
        charge_dice="1d4+16",
        cursed=False,
        description="A blessed blade.",
    )
    assert e.conditional_bonus.vs == "undead"
    assert e.conditional_bonus.bonus == 2
    assert e.modifiers[0].target == "save:all"
    assert e.charge_dice == "1d4+16"
    assert e.name_template.format(base="Long Sword") == "Long Sword +1, +3 vs Undead"


def test_enchantment_rejects_bad_kind():
    from aose.models import Enchantment
    with pytest.raises(ValueError):
        Enchantment(id="x", name_template="{base}", kind="potion",
                    applies_to={"include": ["any_weapon"]})


def test_enchantment_forbids_extra_fields():
    from aose.models import Enchantment
    with pytest.raises(ValueError):
        Enchantment(id="x", name_template="{base}", kind="weapon",
                    applies_to={"include": ["any_weapon"]}, bogus=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -q`
Expected: FAIL — `ImportError: cannot import name 'Enchantment'`.

- [ ] **Step 3: Create the model**

Create `aose/models/enchantment.py`:

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .item import ConditionalBonus
from .modifier import Modifier


class AppliesTo(BaseModel):
    """Token lists for matching an enchantment to compatible base items.

    A base item matches a token ``T`` if ``T == base.id``, ``T in base.groups``,
    or ``T`` is the kind wildcard (``any_weapon`` / ``any_armour`` /
    ``any_shield``).  A base is compatible when it matches at least one
    ``include`` token and no ``exclude`` token (exclude wins).
    """
    model_config = ConfigDict(extra="forbid")

    include: list[str]
    exclude: list[str] = Field(default_factory=list)


class Enchantment(BaseModel):
    """A reusable magical enchantment, independent of any base item.  Lives in
    its own registry (``data/enchantments.yaml`` → ``GameData.enchantments``),
    not in the item catalog.  Composed with a base weapon/armour at runtime by
    ``aose/engine/enchant.py`` — nothing composed is persisted.
    """
    model_config = ConfigDict(extra="forbid")

    id: str
    name_template: str                       # .format(base=base.name) → display name
    kind: Literal["weapon", "armor", "shield"]
    applies_to: AppliesTo
    magic_bonus: int = 0                      # to-hit & damage (weapons); AC (armour/shield)
    conditional_bonus: ConditionalBonus | None = None   # weapons only
    modifiers: list[Modifier] = Field(default_factory=list)
    charge_dice: str | None = None
    max_charges: int | None = None
    cursed: bool = False
    description: str | None = None
```

- [ ] **Step 4: Export from the models package**

In `aose/models/__init__.py`, add the import after the `from .modifier import Modifier` line:

```python
from .enchantment import AppliesTo, Enchantment
```

And add `"AppliesTo"` and `"Enchantment"` to the `__all__` list (next to `"Modifier"`).

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -q`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```powershell
git add aose/models/enchantment.py aose/models/__init__.py tests/test_enchantments.py
git commit -m "feat(models): add Enchantment registry model"
```

---

## Task 2: Base-item tagging fields (`groups`, `ac_bonus`)

**Files:**
- Modify: `aose/models/item.py:34-60`
- Test: `tests/test_enchantments.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enchantments.py`:

```python
def test_weapon_has_groups_default_empty():
    from aose.models import Weapon, WeaponDamage
    w = Weapon(id="dagger", name="Dagger", category="weapons", item_type="weapon",
               cost_gp=3, weight_cn=10, damage=WeaponDamage())
    assert w.groups == []


def test_weapon_groups_set():
    from aose.models import Weapon, WeaponDamage
    w = Weapon(id="short_sword", name="Short Sword", category="weapons",
               item_type="weapon", cost_gp=7, weight_cn=30,
               damage=WeaponDamage(), groups=["sword"])
    assert w.groups == ["sword"]


def test_armor_has_groups_and_ac_bonus_defaults():
    from aose.models import Armor
    a = Armor(id="leather", name="Leather", category="armor", item_type="armor",
              cost_gp=20, weight_cn=200, ac_descending=7, movement_impact="leather")
    assert a.groups == []
    assert a.ac_bonus == 0


def test_armor_shield_ac_bonus():
    from aose.models import Armor
    a = Armor(id="shield", name="Shield", category="armor", item_type="armor",
              cost_gp=10, weight_cn=100, ac_descending=0, is_shield=True, ac_bonus=1)
    assert a.ac_bonus == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "groups or ac_bonus" -q`
Expected: FAIL — `ValidationError: extra fields not permitted (groups / ac_bonus)`.

- [ ] **Step 3: Add the fields**

In `aose/models/item.py`, in class `Weapon`, after the `qualities` line add:

```python
    groups: list[str] = Field(default_factory=list)  # e.g. ["sword"], ["axe"] — enchantment matching tags
```

In class `Armor`, after `is_shield: bool = False` add:

```python
    groups: list[str] = Field(default_factory=list)  # enchantment matching tags
    ac_bonus: int = 0                # AC improvement granted while worn (shields: 1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "groups or ac_bonus" -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```powershell
git add aose/models/item.py tests/test_enchantments.py
git commit -m "feat(models): add groups tags to Weapon/Armor and ac_bonus to Armor"
```

---

## Task 3: `EnchantedInstance` per-character model

**Files:**
- Modify: `aose/models/character.py` (add class after `MagicItemInstance`, field on `CharacterSpec`)
- Modify: `aose/models/__init__.py`
- Test: `tests/test_enchantments.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enchantments.py`:

```python
def _minimal_spec(**overrides):
    from aose.models import CharacterSpec, ClassEntry, RuleSet
    base = dict(
        name="Tester",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="law",
        ruleset=RuleSet(),
    )
    base.update(overrides)
    return CharacterSpec(**base)


def test_enchanted_instance_defaults():
    from aose.models import EnchantedInstance
    inst = EnchantedInstance(instance_id="i1", base_id="long_sword",
                             enchantment_id="plus_1")
    assert inst.equipped is False
    assert inst.charges_max is None
    assert inst.charges_remaining is None
    assert inst.extra_modifiers == []
    assert inst.note == ""


def test_character_spec_defaults_enchanted_empty():
    spec = _minimal_spec()
    assert spec.enchanted == []


def test_character_spec_accepts_enchanted():
    from aose.models import EnchantedInstance
    spec = _minimal_spec(enchanted=[
        EnchantedInstance(instance_id="i1", base_id="long_sword",
                          enchantment_id="plus_1", equipped=True),
    ])
    assert spec.enchanted[0].equipped is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k enchanted_instance -q`
Expected: FAIL — `ImportError: cannot import name 'EnchantedInstance'`.

- [ ] **Step 3: Add the model and the spec field**

In `aose/models/character.py`, after the `MagicItemInstance` class (ends ~line 26) add:

```python
class EnchantedInstance(BaseModel):
    """A specific magic weapon/armour the character owns, modelled as a
    composition of a base catalog item + a reusable ``Enchantment``.  Resolved
    to a synthetic ``Weapon``/``Armor`` at display time by
    ``aose/engine/enchant.py``; nothing composed is persisted.  Not stored in
    ``inventory``/``equipped``/``equipped_weapons`` — carries its own
    ``equipped`` bool.  Passive enchantment modifiers apply only while equipped.
    """
    model_config = ConfigDict(extra="forbid")

    instance_id: str                  # uuid4 hex
    base_id: str                      # references a Weapon or Armor
    enchantment_id: str               # references an Enchantment
    equipped: bool = False
    charges_max: int | None = None
    charges_remaining: int | None = None
    extra_modifiers: list[Modifier] = Field(default_factory=list)  # escape hatch
    note: str = ""
```

In class `CharacterSpec`, after the `magic_items: ...` field (line 119) add:

```python
    enchanted: list[EnchantedInstance] = Field(default_factory=list)
```

- [ ] **Step 4: Export from the models package**

In `aose/models/__init__.py`, update the character import line to include `EnchantedInstance`:

```python
from .character import (
    CharacterSpec, ClassEntry, ContainerInstance, EnchantedInstance,
    MagicItemInstance, SpellSlot,
)
```

Add `"EnchantedInstance"` to `__all__`.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "enchanted" -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add aose/models/character.py aose/models/__init__.py tests/test_enchantments.py
git commit -m "feat(models): add EnchantedInstance and CharacterSpec.enchanted"
```

---

## Task 4: Loader reads `data/enchantments.yaml`

**Files:**
- Modify: `aose/data/loader.py`
- Test: `tests/test_enchantments.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enchantments.py`:

```python
def test_loader_reads_enchantments(tmp_path):
    from aose.data.loader import GameData
    (tmp_path / "enchantments.yaml").write_text(
        "- id: plus_1\n"
        "  name_template: \"{base} +1\"\n"
        "  kind: weapon\n"
        "  applies_to: {include: [any_weapon]}\n"
        "  magic_bonus: 1\n",
        encoding="utf-8",
    )
    data = GameData.load(tmp_path)
    assert "plus_1" in data.enchantments
    assert data.enchantments["plus_1"].magic_bonus == 1


def test_loader_enchantments_absent_is_empty(tmp_path):
    from aose.data.loader import GameData
    data = GameData.load(tmp_path)
    assert data.enchantments == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k loader_reads_enchantments -q`
Expected: FAIL — `AttributeError: 'GameData' object has no attribute 'enchantments'`.

- [ ] **Step 3: Add loader support**

In `aose/data/loader.py`:

Add `Enchantment` to the model import block:

```python
from aose.models import (
    CharClass,
    Enchantment,
    Item,
    LanguageData,
    Race,
    Spell,
    SpellList,
    WeaponQuality,
)
```

Add a loader helper after `_load_spell_lists` (mirrors it):

```python
def _load_enchantments(data_dir: Path) -> dict[str, Enchantment]:
    """Read ``enchantments.yaml`` (a list of mappings) into an id-keyed dict.

    Returns an empty dict when the file is absent so minimal test fixtures
    (a bare data dir) still load.
    """
    path = data_dir / "enchantments.yaml"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    if not isinstance(raw, list):
        raise ValueError("enchantments.yaml must be a YAML list of mappings")
    result: dict[str, Enchantment] = {}
    for obj in raw:
        parsed = Enchantment.model_validate(obj)
        result[parsed.id] = parsed
    return result
```

Add the field to the `GameData` dataclass (after `qualities`):

```python
    enchantments: dict[str, Enchantment] = field(default_factory=dict)
```

Add to the `load` classmethod constructor call (after `qualities=...`):

```python
            enchantments=_load_enchantments(data_dir),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "loader" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add aose/data/loader.py tests/test_enchantments.py
git commit -m "feat(loader): load enchantments.yaml into GameData.enchantments"
```

---

## Task 5: Shield `ac_bonus` refactor + base-item `groups`/`ac_bonus` seed

This task is **atomic**: removing `SHIELD_AC_BONUS` and setting `shield.ac_bonus: 1`
must land together or the mundane shield AC changes.

**Files:**
- Modify: `aose/engine/armor_class.py:7-39`
- Modify: `data/equipment/armor.yaml`
- Modify: `data/equipment/weapons.yaml`
- Test: `tests/test_enchantments.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enchantments.py`:

```python
import pytest as _pytest


@_pytest.fixture(scope="module")
def data():
    from aose.data.loader import GameData
    return GameData.load(DATA_DIR)


def test_mundane_shield_ac_bonus_from_data(data):
    from aose.models import Armor
    shield = data.items["shield"]
    assert isinstance(shield, Armor)
    assert shield.is_shield is True
    assert shield.ac_bonus == 1


def test_mundane_shield_still_minus_one_ac(data):
    from aose.engine.armor_class import armor_class
    spec = _minimal_spec(abilities={"STR": 12, "INT": 12, "WIS": 11,
                                    "DEX": 10, "CON": 12, "CHA": 10})
    spec.inventory = ["shield"]
    spec.equipped = {"shield": "shield"}
    desc, _ = armor_class(spec, data)
    assert desc == 8   # unarmoured 9, shield bonus 1


def test_base_swords_carry_sword_group(data):
    # short_sword and any newly-added swords are tagged for enchantment matching
    assert "sword" in data.items["short_sword"].groups
```

> Note: confirm the mundane sword's id with `data.items` if `short_sword` is
> absent; the repo's `weapons.yaml` uses ids like `short_sword`, `sword`,
> `two_handed_sword`. Adjust the assertion to a real id.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "shield or sword_group" -q`
Expected: FAIL — `shield.ac_bonus == 0` and `groups` empty.

- [ ] **Step 3: Refactor `armor_class.py`**

Replace the top constants and the shield block. Change lines 7-8 from:

```python
UNARMORED_AC_DESCENDING = 9
SHIELD_AC_BONUS = 1
```

to:

```python
UNARMORED_AC_DESCENDING = 9
```

Change the shield block (lines ~29-34) from:

```python
    shield_bonus = 0
    shield_id = spec.equipped.get("shield")
    if shield_id and shield_id in data.items:
        item = data.items[shield_id]
        if isinstance(item, Armor) and item.is_shield:
            shield_bonus = SHIELD_AC_BONUS + item.magic_bonus
```

to (reads the bonus from data; `ac_bonus` carries the former constant):

```python
    shield_bonus = 0
    shield_id = spec.equipped.get("shield")
    if shield_id and shield_id in data.items:
        item = data.items[shield_id]
        if isinstance(item, Armor) and item.is_shield:
            shield_bonus = item.ac_bonus + item.magic_bonus
```

- [ ] **Step 4: Seed base-item tags**

In `data/equipment/armor.yaml`, change the `shield` entry's line
`ac_descending: 0   # ...` block to add `ac_bonus: 1`:

```yaml
- id: shield
  item_type: armor
  name: Shield
  category: armor
  cost_gp: 10
  weight_cn: 100
  ac_descending: 0
  ac_bonus: 1        # the -1-to-AC shield bonus, formerly a code constant
  movement_impact: none
  is_shield: true
```

Add `groups` to the armour entries so plate-mail-only and metal-armour
enchantments can match. Add to `leather_armor`: `groups: [leather_armour]`;
to `chain_mail`: `groups: [metal_armour]`; to `plate_mail`: `groups: [metal_armour]`.

In `data/equipment/weapons.yaml` the existing weapon ids are: `battle_axe`,
`club`, `crossbow`, `dagger`, `hand_axe`, `javelin`, `lance`, `long_bow`, `mace`,
`polearm`, `short_bow`, `short_sword`, `silver_dagger`, `sling`, `spear`, `staff`,
`sword`, `two_handed_sword`, `war_hammer`. Add `groups: [sword]` to `short_sword`,
`sword`, and `two_handed_sword`; add `groups: [axe]` to `battle_axe` and
`hand_axe`. (There is **no** trident — add one below.)

Add three NEW base weapons used by tests/seed (use the file's existing field
style — copy a nearby weapon entry for the damage/qualities shape):

```yaml
- id: bastard_sword
  item_type: weapon
  name: Bastard Sword
  category: weapons
  cost_gp: 15
  weight_cn: 80
  damage: {default: "1d6", variable: "1d8"}
  melee: true
  groups: [sword]

- id: lightsaber
  item_type: weapon
  name: Lightsaber
  category: weapons
  cost_gp: 0
  weight_cn: 30
  damage: {default: "1d6", variable: "1d8"}
  melee: true
  groups: [sword]      # matches sword enchantments by TAG, not by name

- id: trident
  item_type: weapon
  name: Trident
  category: weapons
  cost_gp: 5
  weight_cn: 50
  damage: {default: "1d6", variable: "1d6"}
  melee: true
  groups: [trident]
```

> The `lightsaber` (no "sword" in its name) proves tag-based matching. The
> `trident` base is required by the `trident_fish_command` seed (Task 13) and the
> charged-route test (Task 15).

- [ ] **Step 5: Run tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "shield or sword_group" -q`
Expected: PASS.

Run the AC and proficiency suites to catch the constant removal fallout:
`.venv\Scripts\python.exe -m pytest tests/test_armor_class.py tests/ -q -k "shield or ac"`
Expected: PASS (mundane shield still −1). If any test referenced
`SHIELD_AC_BONUS`, update it to read `data.items["shield"].ac_bonus`.

- [ ] **Step 6: Commit**

```powershell
git add aose/engine/armor_class.py data/equipment/armor.yaml data/equipment/weapons.yaml tests/test_enchantments.py
git commit -m "refactor(ac): shield bonus from data ac_bonus; tag base weapons/armour with groups"
```

---

## Task 6: `enchant.py` — matching core

**Files:**
- Create: `aose/engine/enchant.py`
- Test: `tests/test_enchantments.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enchantments.py`:

```python
def _wpn(id, groups=(), is_shield=False):
    from aose.models import Weapon, WeaponDamage
    return Weapon(id=id, name=id.title(), category="weapons", item_type="weapon",
                  cost_gp=1, weight_cn=10, damage=WeaponDamage(), groups=list(groups))


def _arm(id, groups=(), is_shield=False, ac=7):
    from aose.models import Armor
    return Armor(id=id, name=id.title(), category="armor", item_type="armor",
                 cost_gp=1, weight_cn=100, ac_descending=ac, is_shield=is_shield,
                 groups=list(groups))


def _ench(id, kind, include, exclude=()):
    from aose.models import Enchantment
    return Enchantment(id=id, name_template="{base} +1", kind=kind,
                       applies_to={"include": list(include), "exclude": list(exclude)})


def test_matches_by_id_group_and_wildcard():
    from aose.engine.enchant import matches
    sword = _wpn("short_sword", groups=["sword"])
    assert matches(sword, "short_sword")          # base id
    assert matches(sword, "sword")                # group tag
    assert matches(sword, "any_weapon")           # weapon wildcard
    assert not matches(sword, "axe")


def test_wildcards_respect_nature():
    from aose.engine.enchant import matches
    plate = _arm("plate_mail", groups=["metal_armour"])
    shield = _arm("shield", is_shield=True)
    assert matches(plate, "any_armour")
    assert not matches(plate, "any_shield")
    assert matches(shield, "any_shield")
    assert not matches(shield, "any_armour")


def test_lightsaber_matches_sword_by_tag_not_name():
    from aose.engine.enchant import is_compatible
    saber = _wpn("lightsaber", groups=["sword"])
    sword_ench = _ench("sword_plus_1", "weapon", ["sword"])
    assert is_compatible(saber, sword_ench)


def test_exclude_wins_generic_not_swords():
    from aose.engine.enchant import is_compatible
    sword = _wpn("short_sword", groups=["sword"])
    axe = _wpn("battle_axe", groups=["axe"])
    generic = _ench("generic_plus_1", "weapon", ["any_weapon"], ["sword"])
    assert not is_compatible(sword, generic)   # excluded
    assert is_compatible(axe, generic)


def test_compatibility_requires_kind_match():
    from aose.engine.enchant import is_compatible
    sword = _wpn("short_sword", groups=["sword"])
    armour_ench = _ench("armour_plus_1", "armor", ["any_armour"])
    assert not is_compatible(sword, armour_ench)


def test_compatible_bases_lists_matches():
    from aose.engine.enchant import compatible_bases
    from aose.data.loader import GameData
    d = GameData(items={
        "short_sword": _wpn("short_sword", groups=["sword"]),
        "battle_axe": _wpn("battle_axe", groups=["axe"]),
        "plate_mail": _arm("plate_mail", groups=["metal_armour"]),
    })
    ench = _ench("sword_plus_1", "weapon", ["sword"])
    ids = {b.id for b in compatible_bases(ench, d)}
    assert ids == {"short_sword"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "matches or compatib or wildcard or exclude or lightsaber" -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aose.engine.enchant'`.

- [ ] **Step 3: Create the matching core**

Create `aose/engine/enchant.py`:

```python
"""Enchantment engine — the cycle-free core for magic-item composition.

Imports only models, the data loader, and dice (like ``magic.py``).  The
derivation modules import *from here*, never the other way round.

A magic weapon/armour is composed at runtime from a base catalog item + a
reusable ``Enchantment``.  ``resolve_weapon`` / ``resolve_armor`` return a
synthetic ``Weapon`` / ``Armor``; nothing composed is persisted.
"""
from __future__ import annotations

import random
import uuid

from aose.data.loader import GameData
from aose.engine.dice import roll
from aose.models import (
    Armor,
    Enchantment,
    EnchantedInstance,
    Weapon,
)


class UnknownEnchantment(ValueError):
    pass


class IncompatibleBase(ValueError):
    pass


class NoCharges(ValueError):
    pass


_WILDCARDS = {"any_weapon", "any_armour", "any_shield"}


def _is_weapon(base) -> bool:
    return isinstance(base, Weapon)


def _is_armour(base) -> bool:
    return isinstance(base, Armor) and not base.is_shield


def _is_shield(base) -> bool:
    return isinstance(base, Armor) and base.is_shield


def matches(base, token: str) -> bool:
    """A base item matches ``token`` if it is the kind wildcard for the base's
    nature, equals the base id, or appears in ``base.groups``."""
    if token == "any_weapon":
        return _is_weapon(base)
    if token == "any_armour":
        return _is_armour(base)
    if token == "any_shield":
        return _is_shield(base)
    if token == base.id:
        return True
    return token in getattr(base, "groups", [])


def _nature_matches_kind(base, kind: str) -> bool:
    return (
        (kind == "weapon" and _is_weapon(base))
        or (kind == "armor" and _is_armour(base))
        or (kind == "shield" and _is_shield(base))
    )


def is_compatible(base, ench: Enchantment) -> bool:
    """A base is compatible when its nature matches the enchantment kind, it
    matches at least one ``include`` token, and no ``exclude`` token (exclude
    wins)."""
    if not _nature_matches_kind(base, ench.kind):
        return False
    if any(matches(base, t) for t in ench.applies_to.exclude):
        return False
    return any(matches(base, t) for t in ench.applies_to.include)


def compatible_bases(ench: Enchantment, data: GameData) -> list:
    """Every catalog base item compatible with ``ench``, sorted by name."""
    out = [item for item in data.items.values()
           if isinstance(item, (Weapon, Armor)) and is_compatible(item, ench)]
    out.sort(key=lambda i: i.name)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "matches or compatib or wildcard or exclude or lightsaber" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add aose/engine/enchant.py tests/test_enchantments.py
git commit -m "feat(enchant): tag-based matching and compatibility core"
```

---

## Task 7: `enchant.py` — resolution to synthetic Weapon/Armor

**Files:**
- Modify: `aose/engine/enchant.py`
- Test: `tests/test_enchantments.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enchantments.py`:

```python
def test_resolve_weapon_carries_base_stats_and_ench_bonus():
    from aose.engine.enchant import resolve_weapon
    from aose.models import Enchantment, Weapon, WeaponDamage
    base = Weapon(id="long_sword", name="Long Sword", category="weapons",
                  item_type="weapon", cost_gp=10, weight_cn=60,
                  damage=WeaponDamage(default="1d6", variable="1d8"),
                  qualities=["melee"], groups=["sword"])
    ench = Enchantment(id="sword_vs_undead", name_template="{base} +1, +3 vs Undead",
                       kind="weapon", applies_to={"include": ["sword"]},
                       magic_bonus=1, conditional_bonus={"vs": "undead", "bonus": 2})
    w = resolve_weapon(base, ench, "abc123")
    assert isinstance(w, Weapon)
    assert w.name == "Long Sword +1, +3 vs Undead"
    assert w.magic_bonus == 1
    assert w.conditional_bonus.vs == "undead"
    assert w.damage.variable == "1d8"
    assert w.base_weapon == "long_sword"     # proficiency counts as base type
    assert w.id == "ench:abc123"
    assert w.qualities == ["melee"]


def test_resolve_armor_half_weight_and_base_armor():
    from aose.engine.enchant import resolve_armor
    from aose.models import Armor, Enchantment
    base = Armor(id="chain_mail", name="Chain Mail", category="armor",
                 item_type="armor", cost_gp=40, weight_cn=400, ac_descending=5,
                 movement_impact="metal", groups=["metal_armour"])
    ench = Enchantment(id="armour_plus_1", name_template="{base} +1",
                       kind="armor", applies_to={"include": ["any_armour"]},
                       magic_bonus=1)
    a = resolve_armor(base, ench, "xyz")
    assert isinstance(a, Armor)
    assert a.name == "Chain Mail +1"
    assert a.magic_bonus == 1
    assert a.ac_descending == 5            # base AC; magic_bonus applied downstream
    assert a.weight_multiplier == 0.5      # half-weight enchanted armour
    assert a.base_armor == "chain_mail"
    assert a.movement_impact == "metal"
    assert a.id == "ench:xyz"


def test_resolve_shield_carries_ac_bonus():
    from aose.engine.enchant import resolve_armor
    from aose.models import Armor, Enchantment
    base = Armor(id="shield", name="Shield", category="armor", item_type="armor",
                 cost_gp=10, weight_cn=100, ac_descending=0, is_shield=True, ac_bonus=1)
    ench = Enchantment(id="shield_plus_1", name_template="{base} +1",
                       kind="shield", applies_to={"include": ["any_shield"]},
                       magic_bonus=1)
    a = resolve_armor(base, ench, "s1")
    assert a.is_shield is True
    assert a.ac_bonus == 1
    assert a.magic_bonus == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "resolve" -q`
Expected: FAIL — `ImportError: cannot import name 'resolve_weapon'`.

- [ ] **Step 3: Add the resolvers**

Append to `aose/engine/enchant.py`:

```python
def resolve_weapon(base: Weapon, ench: Enchantment, instance_id: str) -> Weapon:
    """Synthetic ``Weapon`` = base combat stats + enchantment bonus.  ``id`` is
    namespaced by the instance id so attack profiles are stable and unique;
    ``base_weapon`` makes proficiency count the weapon as its base type."""
    return Weapon(
        id=f"ench:{instance_id}",
        name=ench.name_template.format(base=base.name),
        category=base.category,
        cost_gp=0,
        weight_cn=base.weight_cn,
        magic=True,
        item_type="weapon",
        damage=base.damage,
        hands=base.hands,
        versatile=base.versatile,
        melee=base.melee,
        ranged=base.ranged,
        range_short=base.range_short,
        range_medium=base.range_medium,
        range_long=base.range_long,
        qualities=list(base.qualities),
        groups=list(base.groups),
        magic_bonus=ench.magic_bonus,
        conditional_bonus=ench.conditional_bonus,
        base_weapon=base.id,
    )


def resolve_armor(base: Armor, ench: Enchantment, instance_id: str) -> Armor:
    """Synthetic ``Armor`` = base defence stats + enchantment bonus.  Enchanted
    armour is half-weight (``weight_multiplier=0.5``); ``base_armor`` makes class
    allowances count it as its base type."""
    return Armor(
        id=f"ench:{instance_id}",
        name=ench.name_template.format(base=base.name),
        category=base.category,
        cost_gp=0,
        weight_cn=base.weight_cn,
        magic=True,
        item_type="armor",
        ac_descending=base.ac_descending,
        ac_bonus=base.ac_bonus,
        movement_impact=base.movement_impact,
        is_shield=base.is_shield,
        groups=list(base.groups),
        magic_bonus=ench.magic_bonus,
        weight_multiplier=0.5,
        base_armor=base.id,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "resolve" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add aose/engine/enchant.py tests/test_enchantments.py
git commit -m "feat(enchant): resolve base+enchantment to synthetic Weapon/Armor"
```

---

## Task 8: `enchant.py` — instance lifecycle

**Files:**
- Modify: `aose/engine/enchant.py`
- Test: `tests/test_enchantments.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enchantments.py`:

```python
def _lifecycle_data():
    from aose.data.loader import GameData
    from aose.models import Enchantment
    d = GameData(items={
        "short_sword": _wpn("short_sword", groups=["sword"]),
        "battle_axe": _wpn("battle_axe", groups=["axe"]),
    })
    d.enchantments = {
        "sword_plus_1": Enchantment(
            id="sword_plus_1", name_template="{base} +1", kind="weapon",
            applies_to={"include": ["sword"]}, magic_bonus=1),
        "charged_trident": Enchantment(
            id="charged_trident", name_template="{base} of Fish Command",
            kind="weapon", applies_to={"include": ["any_weapon"]},
            charge_dice="2d6"),
    }
    return d


def test_new_enchanted_instance_validates_compat():
    from aose.engine.enchant import new_enchanted_instance, IncompatibleBase
    d = _lifecycle_data()
    inst = new_enchanted_instance("short_sword", "sword_plus_1", d)
    assert inst.base_id == "short_sword"
    assert inst.enchantment_id == "sword_plus_1"
    assert inst.equipped is False
    assert len(inst.instance_id) >= 16
    with pytest.raises(IncompatibleBase):
        new_enchanted_instance("battle_axe", "sword_plus_1", d)  # axe vs sword-only


def test_new_enchanted_instance_rolls_charges():
    import random as _r
    from aose.engine.enchant import new_enchanted_instance
    d = _lifecycle_data()
    inst = new_enchanted_instance("short_sword", "charged_trident", d, rng=_r.Random(1))
    assert inst.charges_max == inst.charges_remaining
    assert 2 <= inst.charges_max <= 12


def test_new_enchanted_instance_unknown_raises():
    from aose.engine.enchant import new_enchanted_instance, UnknownEnchantment
    d = _lifecycle_data()
    with pytest.raises(UnknownEnchantment):
        new_enchanted_instance("short_sword", "nope", d)
    with pytest.raises(ValueError):
        new_enchanted_instance("missing_base", "sword_plus_1", d)


def test_add_equip_unequip_remove_roundtrip():
    from aose.engine.enchant import (
        add_free_enchanted, equip, unequip, remove, set_note)
    d = _lifecycle_data()
    items = add_free_enchanted([], "short_sword", "sword_plus_1", d)
    iid = items[0].instance_id
    items = equip(items, iid)
    assert items[0].equipped is True
    items = unequip(items, iid)
    assert items[0].equipped is False
    items = set_note(items, iid, "hoard")
    assert items[0].note == "hoard"
    items = remove(items, iid)
    assert items == []


def test_use_and_reset_charges():
    from aose.engine.enchant import (
        add_free_enchanted, use_charge, reset_charges, NoCharges)
    d = _lifecycle_data()
    items = add_free_enchanted([], "short_sword", "charged_trident", d)
    iid = items[0].instance_id
    start = items[0].charges_remaining
    for _ in range(start):
        items = use_charge(items, iid)
    assert items[0].charges_remaining == 0
    with pytest.raises(NoCharges):
        use_charge(items, iid)
    items = reset_charges(items, iid)
    assert items[0].charges_remaining == start


def test_equipped_enchanted_resolves_by_kind():
    from aose.engine.enchant import add_free_enchanted, equip, equipped_enchanted
    d = _lifecycle_data()
    items = add_free_enchanted([], "short_sword", "sword_plus_1", d)
    items = equip(items, items[0].instance_id)
    spec = _minimal_spec(enchanted=items)
    weapons = equipped_enchanted(spec, d, "weapon")
    assert len(weapons) == 1
    assert weapons[0].magic_bonus == 1
    assert equipped_enchanted(spec, d, "armor") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "lifecycle or roundtrip or charges or equipped_enchanted or new_enchanted" -q`
Expected: FAIL — missing functions.

- [ ] **Step 3: Add lifecycle helpers**

Append to `aose/engine/enchant.py`:

```python
def _kind_of_instance(inst: EnchantedInstance, data: GameData) -> str | None:
    ench = data.enchantments.get(inst.enchantment_id)
    return ench.kind if ench else None


def _index(items: list[EnchantedInstance], instance_id: str) -> int:
    for i, m in enumerate(items):
        if m.instance_id == instance_id:
            return i
    raise UnknownEnchantment(f"No enchanted instance {instance_id!r}")


def new_enchanted_instance(base_id: str, enchantment_id: str, data: GameData,
                           rng: random.Random | None = None) -> EnchantedInstance:
    """Create a fresh EnchantedInstance.  Validates the base exists, the
    enchantment exists, and the two are compatible.  Rolls ``charge_dice`` or
    seeds ``max_charges`` (mirrors ``magic.new_magic_instance``)."""
    base = data.items.get(base_id)
    if not isinstance(base, (Weapon, Armor)):
        raise ValueError(f"{base_id!r} is not a base weapon or armour")
    ench = data.enchantments.get(enchantment_id)
    if ench is None:
        raise UnknownEnchantment(f"{enchantment_id!r} is not an enchantment")
    if not is_compatible(base, ench):
        raise IncompatibleBase(f"{base_id!r} is not compatible with {enchantment_id!r}")
    charges_max: int | None = None
    if ench.charge_dice:
        charges_max = roll(ench.charge_dice, rng)
    elif ench.max_charges is not None:
        charges_max = ench.max_charges
    return EnchantedInstance(
        instance_id=uuid.uuid4().hex,
        base_id=base_id,
        enchantment_id=enchantment_id,
        equipped=False,
        charges_max=charges_max,
        charges_remaining=charges_max,
    )


def add_free_enchanted(items: list[EnchantedInstance], base_id: str,
                       enchantment_id: str, data: GameData) -> list[EnchantedInstance]:
    return [*items, new_enchanted_instance(base_id, enchantment_id, data)]


def equip(items: list[EnchantedInstance], instance_id: str) -> list[EnchantedInstance]:
    idx = _index(items, instance_id)
    updated = items[idx].model_copy(update={"equipped": True})
    return [*items[:idx], updated, *items[idx + 1:]]


def unequip(items: list[EnchantedInstance], instance_id: str) -> list[EnchantedInstance]:
    idx = _index(items, instance_id)
    updated = items[idx].model_copy(update={"equipped": False})
    return [*items[:idx], updated, *items[idx + 1:]]


def use_charge(items: list[EnchantedInstance], instance_id: str) -> list[EnchantedInstance]:
    idx = _index(items, instance_id)
    inst = items[idx]
    if inst.charges_remaining is None or inst.charges_remaining <= 0:
        raise NoCharges(f"{inst.enchantment_id!r} has no charges left")
    updated = inst.model_copy(update={"charges_remaining": inst.charges_remaining - 1})
    return [*items[:idx], updated, *items[idx + 1:]]


def reset_charges(items: list[EnchantedInstance], instance_id: str) -> list[EnchantedInstance]:
    idx = _index(items, instance_id)
    updated = items[idx].model_copy(update={"charges_remaining": items[idx].charges_max})
    return [*items[:idx], updated, *items[idx + 1:]]


def remove(items: list[EnchantedInstance], instance_id: str) -> list[EnchantedInstance]:
    idx = _index(items, instance_id)
    return [*items[:idx], *items[idx + 1:]]


def set_note(items: list[EnchantedInstance], instance_id: str, note: str) -> list[EnchantedInstance]:
    idx = _index(items, instance_id)
    updated = items[idx].model_copy(update={"note": note})
    return [*items[:idx], updated, *items[idx + 1:]]


def resolve_instance(inst: EnchantedInstance, data: GameData):
    """Resolve one instance to its synthetic Weapon/Armor, or None if its base
    or enchantment is missing from the catalog."""
    base = data.items.get(inst.base_id)
    ench = data.enchantments.get(inst.enchantment_id)
    if ench is None or not isinstance(base, (Weapon, Armor)):
        return None
    if ench.kind == "weapon":
        return resolve_weapon(base, ench, inst.instance_id)
    return resolve_armor(base, ench, inst.instance_id)


def equipped_enchanted(spec, data: GameData, kind: str) -> list:
    """Resolved synthetic items for every EQUIPPED enchanted instance of the
    given ``kind`` (``weapon`` / ``armor`` / ``shield``)."""
    out = []
    for inst in spec.enchanted:
        if not inst.equipped:
            continue
        if _kind_of_instance(inst, data) != kind:
            continue
        resolved = resolve_instance(inst, data)
        if resolved is not None:
            out.append(resolved)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "lifecycle or roundtrip or charges or equipped_enchanted or new_enchanted" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add aose/engine/enchant.py tests/test_enchantments.py
git commit -m "feat(enchant): instance lifecycle + equipped_enchanted resolver"
```

---

## Task 9: `magic.active_modifiers` collects enchantment passives

**Files:**
- Modify: `aose/engine/magic.py:56-66`
- Test: `tests/test_enchantments.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enchantments.py`:

```python
def test_active_modifiers_collect_enchanted_passives(data):
    from aose.engine.magic import active_modifiers
    from aose.engine.enchant import add_free_enchanted, equip
    from aose.models import Enchantment, Modifier
    d = data
    # inject a Luck-Blade-style enchantment with a passive save:all +1
    d.enchantments["luck_blade"] = Enchantment(
        id="luck_blade", name_template="{base} of Luck", kind="weapon",
        applies_to={"include": ["any_weapon"]}, magic_bonus=1,
        modifiers=[Modifier(target="save:all", op="add", value=1)])
    base_id = "short_sword"
    items = add_free_enchanted([], base_id, "luck_blade", d)
    items = equip(items, items[0].instance_id)
    spec = _minimal_spec(enchanted=items)
    mods = active_modifiers(spec, d)
    assert any(m.target == "save:all" for m in mods)


def test_active_modifiers_ignore_unequipped_enchanted(data):
    from aose.engine.magic import active_modifiers
    from aose.engine.enchant import add_free_enchanted
    from aose.models import Enchantment, Modifier
    d = data
    d.enchantments["luck_blade2"] = Enchantment(
        id="luck_blade2", name_template="{base} of Luck", kind="weapon",
        applies_to={"include": ["any_weapon"]},
        modifiers=[Modifier(target="save:all", op="add", value=1)])
    items = add_free_enchanted([], "short_sword", "luck_blade2", d)  # not equipped
    spec = _minimal_spec(enchanted=items)
    assert active_modifiers(spec, d) == []
```

> The `data` fixture is module-scoped; mutating `d.enchantments` is fine because
> each enchantment id is unique per test.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "active_modifiers_collect_enchanted or ignore_unequipped_enchanted" -q`
Expected: FAIL — enchanted passives not collected.

- [ ] **Step 3: Extend `active_modifiers`**

In `aose/engine/magic.py`, replace the body of `active_modifiers` with:

```python
def active_modifiers(spec: CharacterSpec, data: GameData) -> list[Modifier]:
    """Catalog modifiers + extra_modifiers from every EQUIPPED magic item, plus
    enchantment modifiers + extra_modifiers from every EQUIPPED enchanted
    instance.  ``magic_bonus``/``conditional_bonus`` are NOT modifiers — they
    are consumed directly by attacks/AC."""
    out: list[Modifier] = []
    for inst in spec.magic_items:
        if not inst.equipped:
            continue
        catalog = data.items.get(inst.catalog_id)
        if isinstance(catalog, MagicItem):
            out.extend(catalog.modifiers)
        out.extend(inst.extra_modifiers)
    for inst in spec.enchanted:
        if not inst.equipped:
            continue
        ench = data.enchantments.get(inst.enchantment_id)
        if ench is not None:
            out.extend(ench.modifiers)
        out.extend(inst.extra_modifiers)
    return out
```

> No new import is needed — `data.enchantments` is already on `GameData`, and
> `magic.py` still imports only models + loader + dice (no cycle).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "active_modifiers_collect_enchanted or ignore_unequipped_enchanted" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add aose/engine/magic.py tests/test_enchantments.py
git commit -m "feat(magic): active_modifiers collects equipped-enchantment passives"
```

---

## Task 10: `armor_class.py` — enchanted base + enchanted shield

**Files:**
- Modify: `aose/engine/armor_class.py`
- Test: `tests/test_enchantments.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enchantments.py`:

```python
def _equip_one_enchanted(d, base_id, ench_id, **spec_kwargs):
    from aose.engine.enchant import add_free_enchanted, equip
    spec = _minimal_spec(**spec_kwargs)
    spec.enchanted = add_free_enchanted([], base_id, ench_id, d)
    spec.enchanted = equip(spec.enchanted, spec.enchanted[0].instance_id)
    return spec


def test_ac_enchanted_armour_base(data):
    from aose.engine.armor_class import armor_class
    from aose.models import Enchantment
    d = data
    d.enchantments["armour_plus_1"] = Enchantment(
        id="armour_plus_1", name_template="{base} +1", kind="armor",
        applies_to={"include": ["any_armour"]}, magic_bonus=1)
    spec = _equip_one_enchanted(
        d, "chain_mail", "armour_plus_1",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    desc, _ = armor_class(spec, d)
    assert desc == 4   # chain 5 − 1 magic


def test_ac_enchanted_shield_bonus(data):
    from aose.engine.armor_class import armor_class
    from aose.models import Enchantment
    d = data
    d.enchantments["shield_plus_1"] = Enchantment(
        id="shield_plus_1", name_template="{base} +1", kind="shield",
        applies_to={"include": ["any_shield"]}, magic_bonus=1)
    spec = _equip_one_enchanted(
        d, "shield", "shield_plus_1",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    desc, _ = armor_class(spec, d)
    assert desc == 9 - 2   # unarmoured 9, shield ac_bonus 1 + magic 1


def test_ac_best_base_wins_mundane_vs_enchanted(data):
    """Wearing mundane leather (7) + an enchanted chain (4) → best base 4."""
    from aose.engine.armor_class import armor_class
    from aose.models import Enchantment
    d = data
    d.enchantments.setdefault("armour_plus_1", Enchantment(
        id="armour_plus_1", name_template="{base} +1", kind="armor",
        applies_to={"include": ["any_armour"]}, magic_bonus=1))
    spec = _equip_one_enchanted(
        d, "chain_mail", "armour_plus_1",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    spec.inventory = ["leather_armor"]
    spec.equipped = {"armor": "leather_armor"}   # worse base
    desc, _ = armor_class(spec, d)
    assert desc == 4   # enchanted chain base wins over leather 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "ac_enchanted or best_base_wins" -q`
Expected: FAIL — enchanted base/shield not considered.

- [ ] **Step 3: Wire enchanted AC**

In `aose/engine/armor_class.py`, add the import near the top:

```python
from .enchant import equipped_enchanted
```

After the existing mundane-armour `base` block and before the `ac set` loop,
add an enchanted-armour base candidate (best-AC-wins via `min`):

```python
    for resolved in equipped_enchanted(spec, data, "armor"):
        base = min(base, resolved.ac_descending - resolved.magic_bonus)
```

Replace the shield block so an enchanted shield competes with the mundane one
(best-AC-wins via `max`):

```python
    shield_bonus = 0
    shield_id = spec.equipped.get("shield")
    if shield_id and shield_id in data.items:
        item = data.items[shield_id]
        if isinstance(item, Armor) and item.is_shield:
            shield_bonus = item.ac_bonus + item.magic_bonus
    for resolved in equipped_enchanted(spec, data, "shield"):
        shield_bonus = max(shield_bonus, resolved.ac_bonus + resolved.magic_bonus)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "ac_enchanted or best_base_wins" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add aose/engine/armor_class.py tests/test_enchantments.py
git commit -m "feat(ac): enchanted armour base + enchanted shield bonus (best-AC-wins)"
```

---

## Task 11: `attacks.py` — equipped enchanted weapons

**Files:**
- Modify: `aose/engine/attacks.py:188-199`
- Test: `tests/test_enchantments.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enchantments.py`:

```python
def test_enchanted_weapon_attack_profile(data):
    from aose.engine.attacks import attack_profiles
    from aose.engine.attack_bonus import thac0
    from aose.models import Enchantment
    d = data
    d.enchantments["sword_vs_undead"] = Enchantment(
        id="sword_vs_undead", name_template="{base} +1, +3 vs Undead",
        kind="weapon", applies_to={"include": ["sword"]}, magic_bonus=1,
        conditional_bonus={"vs": "undead", "bonus": 2})
    spec = _equip_one_enchanted(
        d, "short_sword", "sword_vs_undead",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10})
    base_thac0 = thac0(_minimal_spec(), d)
    profiles = attack_profiles(spec, d)
    ench_row = next(p for p in profiles if p.name.startswith("Short Sword +1"))
    assert ench_row.to_hit_thac0 == base_thac0 - 1   # +1 magic, STR 12 mod 0
    assert ench_row.conditional is not None
    assert ench_row.conditional.label == "vs undead"
    assert ench_row.conditional.to_hit_thac0 == base_thac0 - 3
    assert ench_row.damage == "1d6+1"


def test_unequipped_enchanted_weapon_absent_from_attacks(data):
    from aose.engine.attacks import attack_profiles
    from aose.engine.enchant import add_free_enchanted
    from aose.models import Enchantment
    d = data
    d.enchantments.setdefault("sword_plus_1", Enchantment(
        id="sword_plus_1", name_template="{base} +1", kind="weapon",
        applies_to={"include": ["sword"]}, magic_bonus=1))
    spec = _minimal_spec()
    spec.enchanted = add_free_enchanted([], "short_sword", "sword_plus_1", d)  # not equipped
    names = {p.name for p in attack_profiles(spec, d)}
    assert not any(n.startswith("Short Sword +1") for n in names)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "enchanted_weapon_attack or unequipped_enchanted_weapon" -q`
Expected: FAIL — enchanted weapons not in attack profiles.

- [ ] **Step 3: Add the enchanted-weapon loop**

In `aose/engine/attacks.py`, add the import near the existing engine imports:

```python
from aose.engine.enchant import equipped_enchanted
```

In `attack_profiles`, after the mundane `for weapon_id, count in counts.items():`
loop (before `weapon_profiles.sort(...)`), add:

```python
    for resolved in equipped_enchanted(spec, data, "weapon"):
        weapon_profiles.append(
            _profile_for(resolved, spec, data, 1, eff, base_thac0, g_atk, g_dmg)
        )
```

> `_profile_for` already consumes `magic_bonus`, `conditional_bonus`, and
> `base_weapon` (for proficiency). The synthetic `id` (`ench:<instance>`) keeps
> profiles unique; sorting by name is unaffected.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "enchanted_weapon_attack or unequipped_enchanted_weapon" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add aose/engine/attacks.py tests/test_enchantments.py
git commit -m "feat(attacks): equipped enchanted weapons produce attack profiles"
```

---

## Task 12: `encumbrance.py` — enchanted-instance weight

**Files:**
- Modify: `aose/engine/encumbrance.py:118-123`
- Test: `tests/test_enchantments.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enchantments.py`:

```python
def test_enchanted_weapon_weight_counts(data):
    from aose.engine.encumbrance import carried_weight_cn
    from aose.engine.enchant import add_free_enchanted
    from aose.models import Enchantment, RuleSet
    d = data
    d.enchantments.setdefault("sword_plus_1", Enchantment(
        id="sword_plus_1", name_template="{base} +1", kind="weapon",
        applies_to={"include": ["sword"]}, magic_bonus=1))
    spec = _minimal_spec(ruleset=RuleSet(encumbrance="detailed"))
    base_weight = d.items["short_sword"].weight_cn
    spec.enchanted = add_free_enchanted([], "short_sword", "sword_plus_1", d)
    assert carried_weight_cn(spec, d) == base_weight


def test_enchanted_armour_half_weight(data):
    from aose.engine.encumbrance import carried_weight_cn
    from aose.engine.enchant import add_free_enchanted
    from aose.models import Enchantment, RuleSet
    d = data
    d.enchantments.setdefault("armour_plus_1", Enchantment(
        id="armour_plus_1", name_template="{base} +1", kind="armor",
        applies_to={"include": ["any_armour"]}, magic_bonus=1))
    spec = _minimal_spec(ruleset=RuleSet(encumbrance="detailed"))
    spec.enchanted = add_free_enchanted([], "chain_mail", "armour_plus_1", d)
    assert carried_weight_cn(spec, d) == 200   # 400 × 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "enchanted_weapon_weight or enchanted_armour_half_weight" -q`
Expected: FAIL — enchanted weight not counted.

- [ ] **Step 3: Count enchanted weight**

In `aose/engine/encumbrance.py`, add to the top imports:

```python
from aose.engine.enchant import resolve_instance
```

In `carried_weight_cn`, after the `for mi in spec.magic_items:` loop (before
`return total`), add:

```python
    from aose.models import Armor as _Armor
    for inst in spec.enchanted:
        resolved = resolve_instance(inst, data)
        if resolved is None:
            continue
        if isinstance(resolved, _Armor):
            total += int(resolved.weight_cn * resolved.weight_multiplier)
        else:
            total += resolved.weight_cn
```

> Like magic-item instances, enchanted instances count whether equipped or not
> (they have no carried/stashed distinction in Phase 1). Half-weight applies to
> resolved enchanted armour via its `weight_multiplier`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "enchanted_weapon_weight or enchanted_armour_half_weight" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add aose/engine/encumbrance.py tests/test_enchantments.py
git commit -m "feat(encumbrance): count enchanted-instance weight (armour half)"
```

---

## Task 13: Seed `data/enchantments.yaml`

**Files:**
- Create: `data/enchantments.yaml`
- Test: `tests/test_enchantments.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enchantments.py`:

```python
def test_seed_enchantments_load(data):
    e = data.enchantments
    assert "generic_plus_1" in e
    assert e["generic_plus_1"].applies_to.exclude == ["sword"]
    assert "sword_plus_1_vs_undead" in e
    assert e["sword_plus_1_vs_undead"].conditional_bonus.vs == "undead"
    assert "luck_blade" in e
    assert e["luck_blade"].modifiers[0].target == "save:all"
    assert "armour_plus_1" in e and e["armour_plus_1"].kind == "armor"
    assert "shield_plus_1" in e and e["shield_plus_1"].kind == "shield"
    # charged one
    assert e["trident_fish_command"].charge_dice is not None


def test_seed_generic_plus1_excludes_swords(data):
    from aose.engine.enchant import is_compatible
    ench = data.enchantments["generic_plus_1"]
    assert not is_compatible(data.items["short_sword"], ench)   # sword excluded
    # an axe (tagged groups:[axe]) is allowed
    axe = next(i for i in data.items.values()
               if getattr(i, "groups", None) and "axe" in i.groups)
    assert is_compatible(axe, ench)
```

> If no axe carries `groups: [axe]` yet, add the tag in `weapons.yaml` (Task 5
> already covers axes); pick whatever axe id exists (e.g. `battle_axe`,
> `hand_axe`).

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "seed_enchantments or generic_plus1_excludes" -q`
Expected: FAIL — `KeyError: 'generic_plus_1'`.

- [ ] **Step 3: Create the seed**

Create `data/enchantments.yaml`:

```yaml
# Minimal, representative Phase-1 enchantment seed.  Bulk import is Phase 2.

- id: generic_plus_1
  name_template: "{base} +1"
  kind: weapon
  applies_to:
    include: [any_weapon]
    exclude: [sword]          # swords get their own +1 lines; no double-coverage
  magic_bonus: 1
  description: "+1 to attack and damage rolls."

- id: sword_plus_1
  name_template: "{base} +1"
  kind: weapon
  applies_to:
    include: [sword]
  magic_bonus: 1
  description: "+1 to attack and damage rolls."

- id: sword_plus_1_vs_undead
  name_template: "{base} +1, +3 vs Undead"
  kind: weapon
  applies_to:
    include: [sword]
  magic_bonus: 1
  conditional_bonus: {vs: undead, bonus: 2}
  description: "+1 normally; +3 to attack and damage versus undead."

- id: short_sword_of_quickness
  name_template: "{base} of Quickness"
  kind: weapon
  applies_to:
    include: [short_sword]
  magic_bonus: 1
  description: "Always wins initiative; +1 to attack and damage."

- id: luck_blade
  name_template: "{base} of Luck"
  kind: weapon
  applies_to:
    include: [sword]
  magic_bonus: 1
  modifiers:
    - {target: "save:all", op: add, value: 1}
  description: "+1 to attack and damage; +1 to all saving throws while held."

- id: trident_fish_command
  name_template: "{base} of Fish Command"
  kind: weapon
  applies_to:
    include: [trident]
  magic_bonus: 1
  charge_dice: "2d6"
  description: "Commands fish/sea creatures while charges remain."

- id: armour_plus_1
  name_template: "{base} +1"
  kind: armor
  applies_to:
    include: [any_armour]
  magic_bonus: 1
  description: "+1 bonus to Armour Class."

- id: shield_plus_1
  name_template: "{base} +1"
  kind: shield
  applies_to:
    include: [any_shield]
  magic_bonus: 1
  description: "+1 bonus to Armour Class from the shield."
```

> Ensure `weapons.yaml` has a `trident` base tagged `groups: [trident]` (or
> matchable by id `trident`); add it in Task 5's edits if missing.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "seed_enchantments or generic_plus1_excludes" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add data/enchantments.yaml data/equipment/weapons.yaml tests/test_enchantments.py
git commit -m "feat(data): seed representative enchantments.yaml"
```

---

## Task 14: Sheet view — enchanted rows in the Magic Items view

**Files:**
- Modify: `aose/sheet/view.py` (extend the Magic Items view assembly)
- Test: `tests/test_enchantments.py`

The sheet's `MagicItemView` already models an instance row (instance_id, name,
description, equippable, equipped, charges, note, modifier_summary). Enchanted
instances reuse it. Add an `enchanted_items_view(...)` helper and include its
rows in `build_sheet`'s `magic_items`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enchantments.py`:

```python
def test_enchanted_items_view_rows(data):
    from aose.sheet.view import enchanted_items_view
    from aose.engine.enchant import add_free_enchanted, equip
    from aose.models import Enchantment
    d = data
    d.enchantments.setdefault("luck_blade", Enchantment(
        id="luck_blade", name_template="{base} of Luck", kind="weapon",
        applies_to={"include": ["sword"]}, magic_bonus=1,
        modifiers=[{"target": "save:all", "op": "add", "value": 1}],
        description="Lucky."))
    items = add_free_enchanted([], "short_sword", "luck_blade", d)
    items = equip(items, items[0].instance_id)
    rows = enchanted_items_view(items, d)
    assert len(rows) == 1
    row = rows[0]
    assert row.instance_id == items[0].instance_id
    assert row.name == "Short Sword of Luck"
    assert row.equipped is True
    assert row.equippable is True
    assert "+1 all saves" in row.modifier_summary
    assert row.description == "Lucky."


def test_build_sheet_includes_enchanted_rows(data):
    from aose.sheet.view import build_sheet
    from aose.engine.enchant import add_free_enchanted, equip
    from aose.models import Enchantment
    d = data
    d.enchantments.setdefault("sword_plus_1", Enchantment(
        id="sword_plus_1", name_template="{base} +1", kind="weapon",
        applies_to={"include": ["sword"]}, magic_bonus=1))
    spec = _minimal_spec()
    spec.enchanted = add_free_enchanted([], "short_sword", "sword_plus_1", d)
    spec.enchanted = equip(spec.enchanted, spec.enchanted[0].instance_id)
    sheet = build_sheet(spec, d)
    assert any(v.name == "Short Sword +1" for v in sheet.magic_items)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "enchanted_items_view or build_sheet_includes_enchanted" -q`
Expected: FAIL — `ImportError: cannot import name 'enchanted_items_view'`.

- [ ] **Step 3: Add the view helper**

In `aose/sheet/view.py`, add a helper after `magic_items_view` (the
enchantment magic_bonus is summarised inline so swords show their +N):

```python
def enchanted_items_view(enchanted, data: GameData) -> list[MagicItemView]:
    """Build Magic-Items rows for EnchantedInstance items.  Each resolves to a
    synthetic weapon/armour for its display name; the summary combines the
    enchantment's magic_bonus, passive modifiers, and per-instance
    extra_modifiers.  All enchanted items are equippable."""
    from aose.engine.enchant import resolve_instance
    views: list[MagicItemView] = []
    for inst in enchanted:
        ench = data.enchantments.get(inst.enchantment_id)
        resolved = resolve_instance(inst, data)
        name = resolved.name if resolved is not None else inst.enchantment_id
        summary: list[str] = []
        if ench is not None and ench.magic_bonus:
            if ench.kind == "weapon":
                summary.append(f"+{ench.magic_bonus} to hit & damage")
                if ench.conditional_bonus:
                    summary.append(
                        f"+{ench.magic_bonus + ench.conditional_bonus.bonus}"
                        f" vs {ench.conditional_bonus.vs}")
            else:
                summary.append(f"+{ench.magic_bonus} AC")
        if ench is not None:
            summary += [_summarize_modifier(m) for m in ench.modifiers]
        summary += [_summarize_modifier(m) for m in inst.extra_modifiers]
        views.append(MagicItemView(
            instance_id=inst.instance_id,
            catalog_id=inst.base_id,
            name=name,
            description=ench.description if ench is not None else None,
            equippable=True,
            equipped=inst.equipped,
            charges_remaining=inst.charges_remaining,
            charges_max=inst.charges_max,
            note=inst.note,
            modifier_summary=summary,
        ))
    return views
```

In `build_sheet`, change the `magic_items=` argument from
`magic_items=_magic_items(spec, data),` to:

```python
        magic_items=_magic_items(spec, data) + enchanted_items_view(spec.enchanted, data),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "enchanted_items_view or build_sheet_includes_enchanted" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add aose/sheet/view.py tests/test_enchantments.py
git commit -m "feat(sheet): enchanted instances appear in the Magic Items view"
```

---

## Task 15: Sheet routes — enchanted lifecycle + Add picker

**Files:**
- Modify: `aose/web/routes.py`
- Test: `tests/test_enchantments.py`

Mirror the magic-item routes, keyed by `instance_id`, targeting `spec.enchanted`,
plus an `/add-enchanted` route taking `base_id` + `enchantment_id`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enchantments.py`:

```python
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character, save_settings
from aose.web.app import create_app


def _make_client(tmp_path, ruleset=None):
    from aose.models import RuleSet
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True)
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, ruleset or RuleSet())
    app = create_app(data_dir=DATA_DIR, characters_dir=characters_dir,
                     drafts_dir=drafts_dir, examples_dir=examples_dir,
                     settings_path=settings_path)
    client = TestClient(app, follow_redirects=False)
    client._characters_dir = characters_dir
    return client


def _seed(client, **overrides):
    save_character("test", _minimal_spec(**overrides), client._characters_dir)
    return "test"


def test_add_enchanted_creates_instance(tmp_path):
    client = _make_client(tmp_path)
    _seed(client)
    r = client.post("/character/test/equipment/add-enchanted",
                    data={"base_id": "short_sword", "enchantment_id": "sword_plus_1"})
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert len(spec.enchanted) == 1
    assert spec.enchanted[0].base_id == "short_sword"
    assert spec.enchanted[0].enchantment_id == "sword_plus_1"


def test_add_enchanted_incompatible_400(tmp_path):
    client = _make_client(tmp_path)
    _seed(client)
    # a sword-only enchantment on an axe base
    axe = None
    from aose.data.loader import GameData
    d = GameData.load(DATA_DIR)
    axe = next(i.id for i in d.items.values()
               if getattr(i, "groups", None) and "axe" in i.groups)
    r = client.post("/character/test/equipment/add-enchanted",
                    data={"base_id": axe, "enchantment_id": "sword_plus_1"})
    assert r.status_code == 400


def test_enchanted_equip_charge_note_remove_roundtrip(tmp_path):
    client = _make_client(tmp_path)
    _seed(client)
    client.post("/character/test/equipment/add-enchanted",
                data={"base_id": "trident", "enchantment_id": "trident_fish_command"})
    spec = load_character("test", client._characters_dir)
    iid = spec.enchanted[0].instance_id
    client.post("/character/test/equipment/equip-enchanted", data={"instance_id": iid})
    spec = load_character("test", client._characters_dir)
    assert spec.enchanted[0].equipped is True
    start = spec.enchanted[0].charges_remaining
    client.post("/character/test/equipment/enchanted/use-charge", data={"instance_id": iid})
    spec = load_character("test", client._characters_dir)
    assert spec.enchanted[0].charges_remaining == start - 1
    client.post("/character/test/equipment/enchanted/reset-charges", data={"instance_id": iid})
    client.post("/character/test/equipment/enchanted-note",
                data={"instance_id": iid, "note": "from the deep"})
    spec = load_character("test", client._characters_dir)
    assert spec.enchanted[0].note == "from the deep"
    client.post("/character/test/equipment/unequip-enchanted", data={"instance_id": iid})
    client.post("/character/test/equipment/remove-enchanted", data={"instance_id": iid})
    spec = load_character("test", client._characters_dir)
    assert spec.enchanted == []
```

> If `trident` is not a base weapon id in `weapons.yaml`, add it in Task 5 (tag
> `groups: [trident]`), or change the test to use a base the seed
> `trident_fish_command` matches.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "add_enchanted or enchanted_equip_charge" -q`
Expected: FAIL — 404/405 on the new routes.

- [ ] **Step 3: Add the routes**

In `aose/web/routes.py`, add to the imports:

```python
from aose.engine.enchant import (
    IncompatibleBase,
    UnknownEnchantment,
    add_free_enchanted as _add_free_enchanted,
    equip as _equip_enchanted,
    remove as _remove_enchanted,
    reset_charges as _reset_ench_charges,
    set_note as _set_enchanted_note,
    unequip as _unequip_enchanted,
    use_charge as _use_ench_charge,
)
```

After the magic-item routes block (after `equipment_magic_note`, ~line 578) add:

```python
# ── Enchanted item actions (sheet-only) ────────────────────────────────────

@router.post("/character/{character_id}/equipment/add-enchanted")
async def equipment_add_enchanted(request: Request, character_id: str,
                                  base_id: str = Form(...),
                                  enchantment_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.enchanted = _add_free_enchanted(
            spec.enchanted, base_id, enchantment_id, request.app.state.game_data)
    except (UnknownEnchantment, IncompatibleBase, ValueError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/equip-enchanted")
async def equipment_equip_enchanted(request: Request, character_id: str,
                                    instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.enchanted = _equip_enchanted(spec.enchanted, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/unequip-enchanted")
async def equipment_unequip_enchanted(request: Request, character_id: str,
                                      instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.enchanted = _unequip_enchanted(spec.enchanted, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/enchanted/use-charge")
async def equipment_enchanted_use_charge(request: Request, character_id: str,
                                         instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.enchanted = _use_ench_charge(spec.enchanted, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/enchanted/reset-charges")
async def equipment_enchanted_reset_charges(request: Request, character_id: str,
                                            instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.enchanted = _reset_ench_charges(spec.enchanted, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/remove-enchanted")
async def equipment_remove_enchanted(request: Request, character_id: str,
                                     instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.enchanted = _remove_enchanted(spec.enchanted, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/enchanted-note")
async def equipment_enchanted_note(request: Request, character_id: str,
                                   instance_id: str = Form(...),
                                   note: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.enchanted = _set_enchanted_note(spec.enchanted, instance_id, note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "add_enchanted or enchanted_equip_charge" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add aose/web/routes.py tests/test_enchantments.py
git commit -m "feat(web): sheet routes for enchanted item lifecycle + add picker"
```

---

## Task 16: Sheet template — enchanted panel + Add picker

**Files:**
- Modify: `aose/web/routes.py` (pass enchantment picker context + `magic_acquisition` flag)
- Modify: `aose/web/templates/_equipment_ui.html`
- Test: `tests/test_enchantments.py`

The shared partial gains:
1. a `magic_acquisition` flag (sheet=True, wizard=False) that gates all magic +
   enchanted acquisition UI, and
2. an **Add Enchanted Item** picker: pick an enchantment, then a base from its
   compatible bases. Per-row controls for owned enchanted instances reuse the
   existing Magic Items panel — but enchanted rows post to the `*-enchanted`
   routes. To keep the panel logic simple, render a **separate** "Enchanted
   Items" sub-panel whose buttons target the enchanted routes.

Provide a compatibility map for the picker:
`enchant_choices = [{enchantment, bases:[...] }]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enchantments.py`:

```python
def test_sheet_renders_enchanted_add_picker(tmp_path):
    client = _make_client(tmp_path)
    _seed(client)
    page = client.get("/character/test").text
    assert "Add Enchanted Item" in page
    assert "/equipment/add-enchanted" in page
    # enchantment option labels appear
    assert "Sword +1" in page or "+1" in page


def test_sheet_renders_owned_enchanted_controls(tmp_path):
    client = _make_client(tmp_path)
    _seed(client)
    client.post("/character/test/equipment/add-enchanted",
                data={"base_id": "short_sword", "enchantment_id": "sword_plus_1"})
    page = client.get("/character/test").text
    assert "Short Sword +1" in page
    assert "/equipment/equip-enchanted" in page
    assert "/equipment/remove-enchanted" in page
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "renders_enchanted_add_picker or owned_enchanted_controls" -q`
Expected: FAIL — picker markup absent.

- [ ] **Step 3: Pass picker context from the sheet route**

In `aose/web/routes.py`, in `character_sheet`, add to the template context dict
(inside the `TemplateResponse` call):

```python
            "magic_acquisition": True,
            "enchant_choices": _enchant_choices(game_data),
            "enchanted_items_view": sheet.magic_items,  # enchanted rows already inside
```

Add a module-level helper near the other helpers in `routes.py`:

```python
def _enchant_choices(game_data):
    """Picker data: each enchantment with its compatible base items."""
    from aose.engine.enchant import compatible_bases
    out = []
    for ench in sorted(game_data.enchantments.values(), key=lambda e: (e.kind, e.id)):
        bases = compatible_bases(ench, game_data)
        if not bases:
            continue
        out.append({
            "id": ench.id,
            "name_template": ench.name_template,
            "kind": ench.kind,
            "bases": [{"id": b.id, "name": b.name} for b in bases],
        })
    return out
```

> To render owned enchanted instances with the right routes, filter
> `magic_items_view` rows by whether their `catalog_id` corresponds to a base
> item. Simpler: pass the enchanted rows separately. Replace the line above with
> a dedicated list built from `spec.enchanted`:

```python
            "enchanted_rows": [v for v in sheet.magic_items
                               if v.instance_id in {e.instance_id for e in spec.enchanted}],
```

and drop `"enchanted_items_view"`. Keep `magic_items_view` as the magic-only
rows by excluding enchanted ids:

```python
            "magic_items_view": [v for v in sheet.magic_items
                                 if v.instance_id not in {e.instance_id for e in spec.enchanted}],
```

- [ ] **Step 4: Render the picker + owned-enchanted panel**

In `aose/web/templates/_equipment_ui.html`, wrap the existing Magic Items panel
and Shop magic categories in `{% if magic_acquisition %}` … `{% endif %}` so the
wizard (which passes `magic_acquisition=False`) shows neither.

Add, just after the Magic Items panel block (before the Shop heading), the
enchanted panel + picker (only when `magic_acquisition`):

```html
{% if magic_acquisition %}
{% if enchanted_rows %}
<h3 class="subhead">Enchanted Items</h3>
<table class="inventory-table magic-items-table">
  <thead><tr><th>Item</th><th>State</th><th>Charges</th><th>Note</th><th>Actions</th></tr></thead>
  <tbody>
  {% for mi in enchanted_rows %}
    <tr class="magic-item-row">
      <td>
        <strong>{{ mi.name }}</strong>
        {% for chip in mi.modifier_summary %}<span class="modifier-chip">{{ chip }}</span>{% endfor %}
      </td>
      <td>
        {% if mi.equipped %}
        <form method="post" action="{{ target_url_prefix }}/unequip-enchanted" class="inline-form">
          <input type="hidden" name="instance_id" value="{{ mi.instance_id }}">
          <button type="submit">Unequip</button>
        </form>
        {% else %}
        <form method="post" action="{{ target_url_prefix }}/equip-enchanted" class="inline-form">
          <input type="hidden" name="instance_id" value="{{ mi.instance_id }}">
          <button type="submit">Equip</button>
        </form>
        {% endif %}
      </td>
      <td class="charges">
        {% if mi.charges_remaining is not none %}
          {{ mi.charges_remaining }} / {{ mi.charges_max }}
          <form method="post" action="{{ target_url_prefix }}/enchanted/use-charge" class="inline-form">
            <input type="hidden" name="instance_id" value="{{ mi.instance_id }}">
            <button type="submit" {% if mi.charges_remaining == 0 %}disabled{% endif %}>Use</button>
          </form>
          <form method="post" action="{{ target_url_prefix }}/enchanted/reset-charges" class="inline-form">
            <input type="hidden" name="instance_id" value="{{ mi.instance_id }}">
            <button type="submit">Reset</button>
          </form>
        {% else %}<span class="muted small">—</span>{% endif %}
      </td>
      <td>
        <form method="post" action="{{ target_url_prefix }}/enchanted-note" class="inline-form">
          <input type="hidden" name="instance_id" value="{{ mi.instance_id }}">
          <input type="text" name="note" value="{{ mi.note }}" placeholder="note…">
          <button type="submit">Save</button>
        </form>
      </td>
      <td>
        <form method="post" action="{{ target_url_prefix }}/remove-enchanted" class="inline-form">
          <input type="hidden" name="instance_id" value="{{ mi.instance_id }}">
          <button type="submit">Remove</button>
        </form>
      </td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endif %}

{% if enchant_choices %}
<h3 class="subhead">Add Enchanted Item</h3>
<form method="post" action="{{ target_url_prefix }}/add-enchanted" class="enchant-add-form">
  <label>Enchantment
    <select name="enchantment_id" id="ench-select">
      {% for c in enchant_choices %}
      <option value="{{ c.id }}">{{ c.name_template.replace("{base}", "…") }} ({{ c.kind }})</option>
      {% endfor %}
    </select>
  </label>
  <label>Base item
    <select name="base_id" id="ench-base-select">
      {% for c in enchant_choices %}
        {% for b in c.bases %}
        <option value="{{ b.id }}" data-ench="{{ c.id }}"
                {% if not loop.first or not c is sameas enchant_choices[0] %}hidden{% endif %}>{{ b.name }}</option>
        {% endfor %}
      {% endfor %}
    </select>
  </label>
  <button type="submit">Add (GM grant)</button>
</form>
<script>
  // Filter base options to the selected enchantment's compatible bases.
  (function () {
    const ench = document.getElementById('ench-select');
    const base = document.getElementById('ench-base-select');
    if (!ench || !base) return;
    function sync() {
      const id = ench.value;
      let first = null;
      base.querySelectorAll('option').forEach(o => {
        const ok = o.dataset.ench === id;
        o.hidden = !ok;
        if (ok && first === null) first = o;
      });
      if (first) base.value = first.value;
    }
    ench.addEventListener('change', sync);
    sync();
  })();
</script>
{% endif %}
{% endif %}
```

> The picker labels render `name_template` with `{base}` replaced by `…`, so a
> `"{base} +1"` template shows as `… +1 (weapon)`. The JS filters the base
> dropdown to the chosen enchantment. The whole block is gated by
> `magic_acquisition` so the wizard never shows it.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "renders_enchanted_add_picker or owned_enchanted_controls" -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add aose/web/routes.py aose/web/templates/_equipment_ui.html tests/test_enchantments.py
git commit -m "feat(web): enchanted-items panel and Add picker on the sheet"
```

---

## Task 17: Wizard finalize round-trips `enchanted`; equipment is mundane-only

**Files:**
- Modify: `aose/web/wizard.py` (`_draft_to_spec`, `_equipment_context`)
- Test: `tests/test_enchantments.py`

The wizard equipment step must expose **no** magic/enchanted acquisition. Pass
`magic_acquisition=False` and omit `enchant_choices`/`enchanted_rows`. Also make
`_draft_to_spec` carry `enchanted` (default empty) so the field always
round-trips even though the wizard never sets it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enchantments.py`:

```python
from aose.characters import load_draft, save_draft


def _walk_wizard_to_equipment(client):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    client.post(f"/wizard/{draft_id}/rules", data={
        "ability_roll_method": "3d6_in_order", "encumbrance": "basic",
        "separate_race_class": "on", "demihuman_level_limits": "on",
        "demihuman_class_restrictions": "on"})
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.post(f"/wizard/{draft_id}/identity", data={"name": "Tester", "alignment": "law"})
    return draft_id


def test_wizard_equipment_exposes_no_magic_or_enchanted(tmp_path):
    client = _make_client(tmp_path)
    client._drafts_dir = client._characters_dir.parent / "drafts"
    draft_id = _walk_wizard_to_equipment(client)
    page = client.get(f"/wizard/{draft_id}/equipment").text
    assert "Add Enchanted Item" not in page
    assert "/equipment/add-enchanted" not in page
    assert "Magic Items" not in page


def test_wizard_finalize_roundtrips_enchanted_empty(tmp_path):
    client = _make_client(tmp_path)
    client._drafts_dir = client._characters_dir.parent / "drafts"
    draft_id = _walk_wizard_to_equipment(client)
    client.get(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    assert r.status_code == 303
    char_id = r.headers["location"].rsplit("/", 1)[-1]
    spec = load_character(char_id, client._characters_dir)
    assert spec.enchanted == []
```

> `_make_client` here only stored `_characters_dir`; the test sets
> `_drafts_dir`. Confirm `create_app` uses `tmp_path/"drafts"` (it does in
> `test_magic_items.py::_make_client`); align the path accordingly.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "wizard_equipment_exposes_no or finalize_roundtrips_enchanted" -q`
Expected: FAIL — wizard still shows magic UI / `enchanted` not on finalize spec
(it defaults empty, so the second test may already pass; the first fails).

- [ ] **Step 3: Make the wizard mundane-only**

In `aose/web/wizard.py`, in `_equipment_context`, add to the returned dict:

```python
        "magic_acquisition": False,
        "enchant_choices": [],
        "enchanted_rows": [],
```

and change `magic_items_view(...)` so the wizard shows no magic instance panel
either — pass an empty list:

```python
        "magic_items_view": [],
```

> Rationale: after Task 19 deletes `magic_items.yaml` there are no MagicItem
> catalog entries, so the wizard magic panel/shop would be empty anyway; setting
> the flag false makes the intent explicit and satisfies the regression test.

In `_draft_to_spec`, add `enchanted` to the `CharacterSpec(...)` call (defaults
empty; the wizard never grants enchanted items):

```python
        enchanted=[
            EnchantedInstance.model_validate(e) for e in draft.get("enchanted", [])
        ],
```

Add `EnchantedInstance` to the wizard's model imports (find the
`from aose.models import (... MagicItemInstance ...)` block and add it).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -k "wizard_equipment_exposes_no or finalize_roundtrips_enchanted" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add aose/web/wizard.py tests/test_enchantments.py
git commit -m "feat(wizard): mundane-only equipment step; round-trip enchanted field"
```

---

## Task 18: Delete `magic_items.yaml`; rework orphaned tests

Deleting the placeholder catalog removes `gauntlets_of_ogre_power`,
`ring_of_protection`, `ring_of_spell_turning`, `girdle_of_giant_strength`,
`sword_plus_1`*, `sword_plus_2/3`, `sword_plus_1_vs_undead`*, `chain_mail_plus_1`,
`shield_plus_1`, and `potion_of_healing` from `GameData.items`. (* the magic
*weapon/armour* concept now lives only as enchanted instances.)

Unit tests that inject fakes (`_fake_magic_data`, `_with_magic`) keep working —
they don't read these from `DATA_DIR`. The tests that break are **app-level**
(real `DATA_DIR`) and the **yaml-load** tests.

**Files:**
- Delete: `data/equipment/magic_items.yaml`
- Modify: `tests/test_magic_items.py`
- Modify: `tests/test_equip_enforcement.py`
- Modify: `tests/test_weapon_proficiency.py`

- [ ] **Step 1: Delete the placeholder**

```powershell
git rm data/equipment/magic_items.yaml
```

- [ ] **Step 2: Run the full suite to enumerate breakage**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: FAILs in `test_magic_items.py`, `test_equip_enforcement.py`,
`test_weapon_proficiency.py` referencing the deleted ids. Note the exact list.

- [ ] **Step 3: Rework `tests/test_magic_items.py`**

The MagicItem *machinery* (rings/gauntlets/charges/abilities) is still valid
code; only its seed data is gone. Keep the **unit** tests that use
`_fake_magic_data`/`_with_magic` unchanged. **Delete** the seed-dependent tests
that asserted the placeholder catalog and the app-level tests that referenced
deleted ids, since equivalent coverage now lives in `tests/test_enchantments.py`:

Delete these test functions (they assert deleted seed data or exercise magic
acquisition that has moved to enchantments):
- `test_magic_items_yaml_loads`
- `test_ring_of_spell_turning_has_charge_dice`
- `test_sword_vs_undead_conditional`
- `test_magic_categories_appear_in_shop`
- `test_add_worn_item_creates_instance`, `test_add_potion_goes_to_inventory`,
  `test_add_sword_inventory_then_equip`,
  `test_equip_unequip_magic_roundtrip_reflects_on_sheet`,
  `test_use_and_reset_charges`, `test_use_charge_at_zero_400`,
  `test_magic_note_and_remove`
- `test_sheet_html_shows_magic_section_and_markers`,
  `test_sheet_html_shows_conditional_attack`, `test_print_html_lists_magic_items`
- `test_shop_renders_magic_addonly_section`, `test_owned_magic_panel_renders`
- The wizard-mirror tests: `test_wizard_add_worn_item_creates_instance_in_draft`,
  `test_wizard_finalize_roundtrips_magic_items`, `test_wizard_use_charge_roundtrips`
- `test_shop_item_carries_magic_flag` and
  `test_magic_items_view_lists_instance_and_inventory` rely on
  `potion_of_healing`/`ring_of_protection`; update them to inject the item into a
  deep-copied `data` (use the existing `_with_magic`/`_copy.deepcopy` pattern) OR
  delete if redundant.

> Keep `test_equip_magic_non_equippable_400` (uses a bogus id) and all engine
> unit tests using `_fake_magic_data`/`_with_magic`.

- [ ] **Step 4: Rework `tests/test_equip_enforcement.py` magic-variant tests**

Replace the magic *catalog-variant* equip tests with enchanted-instance
equivalents. The tests at lines ~123-157 (`test_equip_allows_magic_weapon_*`,
`test_equip_blocks_magic_weapon_*`, `test_equip_allows_magic_armor_*`,
`test_inventory_view_flags_magic_weapon_*`) referenced `sword_plus_1` /
`chain_mail_plus_1` as plain inventory ids. Those no longer exist.

The class-allowance-by-base-type concern is now covered by `resolve_weapon`’s
`base_weapon` / `resolve_armor`’s `base_armor`. Add a focused test in
`tests/test_enchantments.py` instead and **delete** the now-invalid catalog tests
here:

Add to `tests/test_enchantments.py`:

```python
def test_resolved_enchanted_weapon_keeps_base_for_proficiency(data):
    from aose.engine.enchant import resolve_instance, new_enchanted_instance
    inst = new_enchanted_instance("short_sword", "sword_plus_1", data)
    resolved = resolve_instance(inst, data)
    assert resolved.base_weapon == "short_sword"
```

Delete the four magic-variant tests in `test_equip_enforcement.py` (lines
~123-157) and the section comment above them.

- [ ] **Step 5: Rework `tests/test_weapon_proficiency.py` magic-variant tests**

Lines ~323-347 reference `sword_plus_1` as a catalog item and assert the picker
omits magic variants. Since magic weapons are no longer catalog items, the picker
naturally omits them. Replace:
- `test_magic_variant_uses_base_weapon_proficiency` → rewrite to build an
  enchanted instance and assert its attack profile uses base-weapon proficiency:

```python
def test_enchanted_weapon_uses_base_weapon_proficiency(data):
    from aose.engine.enchant import add_free_enchanted, equip
    from aose.engine.attacks import attack_profiles
    from aose.models import CharacterSpec, ClassEntry, RuleSet
    spec = CharacterSpec(
        name="P", abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12,
                             "CON": 12, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="law",
        ruleset=RuleSet(weapon_proficiency=True),
        weapon_proficiencies=["short_sword"])
    spec.enchanted = add_free_enchanted([], "short_sword", "sword_plus_1", data)
    spec.enchanted = equip(spec.enchanted, spec.enchanted[0].instance_id)
    prof = next(p for p in attack_profiles(spec, data) if p.name.startswith("Short Sword +1"))
    assert prof.proficient is True
```

- Delete `test_picker_omits_magic_weapon_variants` (no magic variants exist to
  omit) and the `variant = data.items["sword_plus_1"]` assertion block.

- [ ] **Step 6: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing `pytest-current` PermissionError).

- [ ] **Step 7: Commit**

```powershell
git add -A
git commit -m "refactor(data,tests): delete placeholder magic_items.yaml; migrate tests to enchantments"
```

---

## Task 19: Full-suite verification + docs note

**Files:**
- Modify: `CLAUDE.md` (Current state note)
- Test: whole suite

- [ ] **Step 1: Run the whole suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: All pass (ignore the `pytest-current` PermissionError).

- [ ] **Step 2: Smoke-run the app**

Run: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app` (Ctrl-C after it
binds). Expected: imports cleanly, no startup error from the deleted yaml or new
loader path. Optionally open `/character/<id>` for a saved character and confirm
the **Add Enchanted Item** picker renders and adding a `Short Sword +1` equips
and shows on the Attacks table + AC.

- [ ] **Step 3: Update `CLAUDE.md`**

Add a bullet under "Current state" summarising the enchantment composition model
(Enchantment registry, `EnchantedInstance`, `aose/engine/enchant.py`, shield
`ac_bonus` refactor, deleted placeholder `magic_items.yaml`, sheet-only Add-only
acquisition) and point to this plan + the design spec.

- [ ] **Step 4: Commit**

```powershell
git add CLAUDE.md
git commit -m "docs: note magic-item enchantment composition model (Phase 1)"
```

---

## Self-review notes (coverage map)

- Spec §1 Enchantment model → Task 1; AppliesTo + matching → Tasks 1, 6.
- Spec §1 Weapon/Armor `groups`/`ac_bonus` → Tasks 2, 5.
- Spec §1 EnchantedInstance + `CharacterSpec.enchanted` → Task 3.
- Spec §2 `enchant.py` matching/resolution/lifecycle → Tasks 6, 7, 8.
- Spec §2 `active_modifiers` extension → Task 9.
- Spec §2 `armor_class.py` shield refactor + enchanted base/shield → Tasks 5, 10.
- Spec §2 `attacks.py` enchanted weapons → Task 11.
- Spec §2 `encumbrance.py` enchanted weight → Task 12.
- Spec §3 Loader → Task 4. Routes → Task 15. Sheet view/template → Tasks 14, 16.
  Wizard mundane-only + regression → Task 17.
- Spec §4 seed enchantments + base tags + delete magic_items.yaml → Tasks 5, 13, 18.
- Spec testing checklist → covered across Tasks 6-18 in `tests/test_enchantments.py`.

**Open items for the executor to confirm against the live data files:**
- Exact mundane base-weapon ids in `weapons.yaml` (e.g. `short_sword`, `sword`,
  `two_handed_sword`, axe id, trident id). Adjust seed `applies_to` tokens and
  test ids to match what exists; add a `trident` base if the
  `trident_fish_command` seed needs one.
- Confirm `create_app` draft dir path used by `_make_client` in the new tests
  matches `test_magic_items.py`.
