# Magic Items Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a character own magic items. Most are pure flavour; some modify the character (ability score, AC, saves, weapon +N, armour +N, carry capacity, THAC0) and those modifications show on the sheet. The design is data-driven: a bounded `Modifier` vocabulary applied at the natural derivation sites, plus a manual escape hatch (free-text `note` + per-instance `extra_modifiers`) for four genuinely awkward mechanics.

**Architecture:** A `Modifier` value type (new `aose/models/modifier.py`) is shared by catalog `MagicItem.modifiers` and per-instance `MagicItemInstance.extra_modifiers`. `MagicItem` joins the `Item` discriminated union; `MagicItemInstance` lives on `CharacterSpec.magic_items` (mirrors `ContainerInstance`). Magic *weapons/armour* stay native `Weapon`/`Armor` with a `magic_bonus` field. A new pure module `aose/engine/magic.py` computes `active_modifiers` / `effective_abilities` / `carry_capacity_bonus` and owns the instance/charge helpers — it imports only models + loader + dice, so the derivation modules (`armor_class`, `saves`, `attack_bonus`, `attacks`, `encumbrance`) can import it without a cycle.

**Tech Stack:** Python 3.14, Pydantic v2, FastAPI, Jinja2, pytest. Vanilla JS (no framework). YAML for catalog data.

**Spec:** [docs/superpowers/specs/2026-05-28-magic-items-design.md](../specs/2026-05-28-magic-items-design.md)

**Test command:** `.venv\Scripts\python.exe -m pytest tests/ -q`
**Run command:** `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`

---

## Spec deviations (read first)

Two claims in the spec are wrong against the actual code; this plan follows the code, not the spec text:

1. **Loader is a glob, not an `ITEM_FILES` list.** `aose/data/loader.py::_load_items` reads `directory.glob("*.yaml")` over `data/equipment/`. Dropping `data/equipment/magic_items.yaml` is picked up automatically. **No loader edit is needed** (and there is no `ITEM_FILES` symbol to edit). Task 12 verifies this with a load test rather than touching the loader.
2. **`_draft_to_spec` already round-trips `containers`.** The "forgotten field" bug the spec warns about is hypothetical for magic items: this plan's Task 15 adds `magic_items=[...]` to `_draft_to_spec` and guards it with a finalize round-trip test.

Sign-convention resolution (the spec is internally inconsistent here): `apply_modifiers` implements **literal** op semantics (`set` last-wins → `add` summed → `set_min` = `max` → `set_max` = `min`). It is called directly only for `ability:*` (where literal `add` = a higher score = improvement) and for `thac0` (where the only realistic modifier is `set_max`, a literal cap — the Girdle). The "lower-is-better" targets `ac` and `save:*` are applied at their call sites, which negate `add` into the descending/target direction manually (matching the spec's `armor_class` / `saves` pseudocode). Seed data uses no `thac0 add`, so the literal-add-worsens-thac0 edge never fires; it is documented in `apply_modifiers`.

---

## Task 1: Add the `Modifier` value type

**Files:**
- Create: `aose/models/modifier.py`
- Modify: `aose/models/__init__.py`
- Create: `tests/test_magic_items.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_magic_items.py`:

```python
"""Tests for magic items: Modifier value type, MagicItem catalog variant,
magic Weapon/Armor enchantment fields, MagicItemInstance runtime model, the
magic engine (active_modifiers / effective_abilities / charge helpers), the
derivation hooks (AC / saves / THAC0 / attacks / encumbrance), acquisition
routing, and the sheet + wizard HTTP routes."""
from pathlib import Path

import pytest

from aose.models import Modifier

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def test_modifier_parses_and_defaults():
    m = Modifier(target="ability:STR", op="set", value=18)
    assert m.target == "ability:STR"
    assert m.op == "set"
    assert m.value == 18


def test_modifier_rejects_unknown_op():
    with pytest.raises(ValueError):
        Modifier(target="ac", op="multiply", value=2)


def test_modifier_forbids_extra_fields():
    with pytest.raises(ValueError):
        Modifier(target="ac", op="add", value=1, bogus=True)
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -q
```
Expected: `ImportError: cannot import name 'Modifier' from 'aose.models'`.

- [ ] **Step 3: Create the module**

`aose/models/modifier.py`:

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Modifier(BaseModel):
    """A single mechanical effect from a magic item.

    Shared by catalog ``MagicItem.modifiers`` and per-instance
    ``MagicItemInstance.extra_modifiers``.  Lives in its own module so
    ``item.py`` and ``character.py`` can both import it without coupling.

    ``op`` semantics (applied per target): all ``set`` (last wins) → all
    ``add`` (summed) → ``set_min`` (``max(result, value)``) → ``set_max``
    (``min(result, value)``).  ``add`` always means *better for the character*
    (the lower-is-better targets negate it at their call site); ``set`` and the
    bounds use literal game-system numbers.

    ``target`` grammar (unknown targets are ignored — forward-compatible):
    ``ability:STR``…``ability:CHA``, ``ac``, ``save:all``,
    ``save:death|wands|paralysis|breath|spells``, ``attack``, ``damage``,
    ``carry_capacity``, ``thac0``.
    """
    model_config = ConfigDict(extra="forbid")

    target: str
    op: Literal["add", "set", "set_min", "set_max"]
    value: int
```

- [ ] **Step 4: Export `Modifier`**

In `aose/models/__init__.py`, add the import and `__all__` entry:

```python
from .modifier import Modifier
```

Add `"Modifier"` to `__all__`. Place the import after `from .item import (...)` so item.py's own import of `.modifier` (Task 2) is unaffected.

- [ ] **Step 5: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -q
```
Expected: 3 passed.

- [ ] **Step 6: Commit**

```
git add aose/models/modifier.py aose/models/__init__.py tests/test_magic_items.py
git commit -m "Add Modifier value type for magic items"
```

---

## Task 2: Add `description` + `magic` to `ItemBase` and the `MagicItem` variant

**Files:**
- Modify: `aose/models/item.py`
- Modify: `aose/models/__init__.py`
- Modify: `tests/test_magic_items.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_magic_items.py`:

```python
from aose.models import AdventuringGear, MagicItem


def test_itembase_new_fields_default_safely():
    gear = AdventuringGear(
        id="torch", name="Torch", category="adventuring_gear",
        item_type="gear", cost_gp=1, weight_cn=20,
    )
    assert gear.description is None
    assert gear.magic is False


def test_magic_item_parses_with_modifiers():
    ring = MagicItem(
        id="ring_of_protection", name="Ring of Protection",
        category="magic_rings", item_type="magic", cost_gp=0, weight_cn=0,
        magic=True, equippable=True,
        description="+1 AC and saves.",
        modifiers=[
            {"target": "ac", "op": "add", "value": 1},
            {"target": "save:all", "op": "add", "value": 1},
        ],
    )
    assert ring.equippable is True
    assert ring.magic is True
    assert len(ring.modifiers) == 2
    assert ring.modifiers[0].target == "ac"
    assert ring.max_charges is None
    assert ring.charge_dice is None


def test_magic_item_charge_fields():
    wand = MagicItem(
        id="ring_of_spell_turning", name="Ring of Spell Turning",
        category="magic_rings", item_type="magic", cost_gp=0, weight_cn=0,
        magic=True, equippable=True, charge_dice="2d6",
    )
    assert wand.charge_dice == "2d6"
    assert wand.modifiers == []
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "itembase or magic_item" -q
```
Expected: `ImportError: cannot import name 'MagicItem'` (and the ItemBase test fails on the missing `description` attribute once the import is fixed).

- [ ] **Step 3: Edit `aose/models/item.py`**

Add the import at the top:

```python
from .modifier import Modifier
```

Add the two new fields to `ItemBase`:

```python
class ItemBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    category: str
    cost_gp: float
    weight_cn: int = 0
    description: str | None = None   # long flavour / rules text
    magic: bool = False              # drives Magic Items section + Add-only acquisition
```

Add the `MagicItem` variant after `Container`:

```python
class MagicItem(ItemBase):
    item_type: Literal["magic"]
    equippable: bool = False
    modifiers: list[Modifier] = Field(default_factory=list)
    max_charges: int | None = None     # fixed charge ceiling, OR…
    charge_dice: str | None = None     # …rolled at acquisition (e.g. "2d6")
```

Add it to the `Item` union:

```python
Item = Annotated[
    Union[Weapon, Armor, AdventuringGear, Poison, Container, MagicItem],
    Field(discriminator="item_type"),
]
```

- [ ] **Step 4: Export `MagicItem`**

In `aose/models/__init__.py`, add `MagicItem` to the `from .item import (...)` block and to `__all__`.

- [ ] **Step 5: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: new tests pass; full suite green (new `ItemBase` fields default safely, so existing item YAML and models are unaffected).

- [ ] **Step 6: Commit**

```
git add aose/models/item.py aose/models/__init__.py tests/test_magic_items.py
git commit -m "Add description/magic to ItemBase and MagicItem catalog variant"
```

---

## Task 3: Add enchantment fields to `Weapon` and `Armor`

**Files:**
- Modify: `aose/models/item.py`
- Modify: `aose/models/__init__.py`
- Modify: `tests/test_magic_items.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_magic_items.py`:

```python
from aose.models import Armor, ConditionalBonus, Weapon, WeaponDamage


def test_weapon_magic_fields_default_off():
    w = Weapon(
        id="dagger", name="Dagger", category="weapons", item_type="weapon",
        cost_gp=3, weight_cn=10, damage=WeaponDamage(default="1d6", variable="1d4"),
        proficiency_group="dagger",
    )
    assert w.magic_bonus == 0
    assert w.conditional_bonus is None


def test_magic_weapon_with_conditional():
    w = Weapon(
        id="sword_plus_1_vs_undead", name="Sword +1, +3 vs Undead",
        category="magic_swords", item_type="weapon", cost_gp=0, weight_cn=60,
        damage=WeaponDamage(default="1d6", variable="1d8"),
        proficiency_group="sword", magic=True, magic_bonus=1,
        conditional_bonus=ConditionalBonus(vs="undead", bonus=2),
    )
    assert w.magic_bonus == 1
    assert w.conditional_bonus.vs == "undead"
    assert w.conditional_bonus.bonus == 2


def test_armor_magic_and_weight_multiplier():
    a = Armor(
        id="chain_mail_plus_1", name="Chain Mail +1", category="magic_armour",
        item_type="armor", cost_gp=0, weight_cn=400, ac_descending=5,
        movement_impact="metal", magic=True, magic_bonus=1, weight_multiplier=0.5,
    )
    assert a.magic_bonus == 1
    assert a.weight_multiplier == 0.5
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "weapon_magic or magic_weapon or armor_magic" -q
```
Expected: `ImportError: cannot import name 'ConditionalBonus'`.

- [ ] **Step 3: Edit `aose/models/item.py`**

Add `ConditionalBonus` above `Weapon`, and the new fields to `Weapon` and `Armor`:

```python
class ConditionalBonus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vs: str          # creature-category label, e.g. "undead"
    bonus: int       # ADDITIONAL bonus on top of magic_bonus when it applies


class Weapon(ItemBase):
    item_type: Literal["weapon"]
    damage: WeaponDamage
    hands: int = 1
    versatile: bool = False
    melee: bool = True
    ranged: bool = False
    range_short: int | None = None
    range_medium: int | None = None
    range_long: int | None = None
    qualities: list[str] = Field(default_factory=list)
    proficiency_group: str | None = None
    magic_bonus: int = 0
    conditional_bonus: ConditionalBonus | None = None


class Armor(ItemBase):
    item_type: Literal["armor"]
    ac_descending: int
    movement_impact: Literal["none", "leather", "metal"] = "metal"
    is_shield: bool = False
    magic_bonus: int = 0
    weight_multiplier: float = 1.0   # 0.5 for enchanted armour
```

- [ ] **Step 4: Export `ConditionalBonus`**

In `aose/models/__init__.py`, add `ConditionalBonus` to the `from .item import (...)` block and `__all__`.

- [ ] **Step 5: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: new tests pass; full suite green.

- [ ] **Step 6: Commit**

```
git add aose/models/item.py aose/models/__init__.py tests/test_magic_items.py
git commit -m "Add magic_bonus / conditional_bonus / weight_multiplier to Weapon and Armor"
```

---

## Task 4: Add `MagicItemInstance` and `CharacterSpec.magic_items`

**Files:**
- Modify: `aose/models/character.py`
- Modify: `aose/models/__init__.py`
- Modify: `tests/test_magic_items.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_magic_items.py`:

```python
from aose.models import CharacterSpec, ClassEntry, MagicItemInstance, RuleSet


def _minimal_spec(**overrides):
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


def test_magic_item_instance_construct():
    inst = MagicItemInstance(
        instance_id="abc123", catalog_id="ring_of_protection", equipped=True,
    )
    assert inst.equipped is True
    assert inst.charges_remaining is None
    assert inst.extra_modifiers == []
    assert inst.note == ""


def test_character_spec_defaults_magic_items_empty():
    spec = _minimal_spec()
    assert spec.magic_items == []
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "instance_construct or defaults_magic_items" -q
```
Expected: `ImportError: cannot import name 'MagicItemInstance'`.

- [ ] **Step 3: Edit `aose/models/character.py`**

Add the import and the model (above `ClassEntry`):

```python
from .modifier import Modifier
```

```python
class MagicItemInstance(BaseModel):
    """A specific magic item the character owns — per-instance state separate
    from the catalog ``MagicItem``.  Tracked here (not in ``inventory``) only
    when the catalog item is ``equippable`` or has charges; stateless magic
    items (potions, magic weapons/armour) stay plain inventory ids.

    Modifiers apply only while ``equipped`` is True.
    """
    model_config = ConfigDict(extra="forbid")

    instance_id: str                         # uuid4 hex
    catalog_id: str                          # references a MagicItem
    equipped: bool = False
    charges_max: int | None = None
    charges_remaining: int | None = None
    extra_modifiers: list[Modifier] = Field(default_factory=list)  # escape hatch
    note: str = ""                                                 # escape hatch
```

Add the field to `CharacterSpec`, after `containers`:

```python
    magic_items: list[MagicItemInstance] = Field(default_factory=list)
```

- [ ] **Step 4: Export `MagicItemInstance`**

In `aose/models/__init__.py`, add `MagicItemInstance` to the `from .character import (...)` line and `__all__`.

- [ ] **Step 5: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: new tests pass; full suite green (the new `CharacterSpec` field has a default, satisfying `extra="forbid"` and old saves).

- [ ] **Step 6: Commit**

```
git add aose/models/character.py aose/models/__init__.py tests/test_magic_items.py
git commit -m "Add MagicItemInstance and CharacterSpec.magic_items"
```

---

## Task 5: Create `aose/engine/magic.py` — modifier engine

**Files:**
- Create: `aose/engine/magic.py`
- Modify: `tests/test_magic_items.py`

This module is the cycle-free core: it imports only `aose.models`, `aose.data.loader`, and `aose.engine.dice`. The derivation modules import *from* it in later tasks.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_magic_items.py`:

```python
from aose.data.loader import GameData
from aose.models import MagicItem


def _fake_magic_data():
    """In-memory GameData with the magic items the engine tests need."""
    return GameData(items={
        "gauntlets": MagicItem(
            id="gauntlets", name="Gauntlets of Ogre Power",
            category="miscellaneous_magic_items", item_type="magic",
            cost_gp=0, weight_cn=0, magic=True, equippable=True,
            modifiers=[
                {"target": "ability:STR", "op": "set", "value": 18},
                {"target": "carry_capacity", "op": "add", "value": 1000},
            ],
        ),
        "ring_prot": MagicItem(
            id="ring_prot", name="Ring of Protection", category="magic_rings",
            item_type="magic", cost_gp=0, weight_cn=0, magic=True, equippable=True,
            modifiers=[
                {"target": "ac", "op": "add", "value": 1},
                {"target": "save:all", "op": "add", "value": 1},
            ],
        ),
    })


def test_apply_modifiers_order_set_then_add_then_bounds():
    from aose.engine.magic import apply_modifiers
    from aose.models import Modifier
    mods = [
        Modifier(target="x", op="add", value=2),
        Modifier(target="x", op="set", value=10),
        Modifier(target="x", op="set_max", value=11),
        Modifier(target="x", op="set_min", value=12),
        Modifier(target="other", op="add", value=99),  # filtered out
    ]
    # set→10, add→12, set_min(max(12,12))→12, set_max(min(12,11))→11
    assert apply_modifiers(0, mods, "x") == 11


def test_active_modifiers_empty_when_none_equipped():
    from aose.engine.magic import active_modifiers
    from aose.models import MagicItemInstance
    fake = _fake_magic_data()
    spec = _minimal_spec(magic_items=[
        MagicItemInstance(instance_id="i1", catalog_id="ring_prot", equipped=False),
    ])
    assert active_modifiers(spec, fake) == []


def test_active_modifiers_collects_equipped_catalog_and_extra():
    from aose.engine.magic import active_modifiers
    from aose.models import MagicItemInstance, Modifier
    fake = _fake_magic_data()
    spec = _minimal_spec(magic_items=[
        MagicItemInstance(
            instance_id="i1", catalog_id="ring_prot", equipped=True,
            extra_modifiers=[Modifier(target="thac0", op="set_max", value=15)],
        ),
    ])
    mods = active_modifiers(spec, fake)
    targets = sorted(m.target for m in mods)
    assert targets == ["ac", "save:all", "thac0"]


def test_effective_abilities_applies_set_and_leaves_rest():
    from aose.engine.magic import effective_abilities
    from aose.models import Ability, MagicItemInstance
    fake = _fake_magic_data()
    spec = _minimal_spec(
        abilities={"STR": 9, "INT": 12, "WIS": 11, "DEX": 13, "CON": 12, "CHA": 10},
        magic_items=[MagicItemInstance(instance_id="i", catalog_id="gauntlets", equipped=True)],
    )
    eff = effective_abilities(spec, fake)
    assert eff[Ability.STR] == 18
    assert eff[Ability.DEX] == 13  # untouched


def test_effective_abilities_base_when_unequipped():
    from aose.engine.magic import effective_abilities
    from aose.models import Ability, MagicItemInstance
    fake = _fake_magic_data()
    spec = _minimal_spec(
        abilities={"STR": 9, "INT": 12, "WIS": 11, "DEX": 13, "CON": 12, "CHA": 10},
        magic_items=[MagicItemInstance(instance_id="i", catalog_id="gauntlets", equipped=False)],
    )
    assert effective_abilities(spec, fake)[Ability.STR] == 9


def test_carry_capacity_bonus_sums_active():
    from aose.engine.magic import carry_capacity_bonus
    from aose.models import MagicItemInstance
    fake = _fake_magic_data()
    spec = _minimal_spec(magic_items=[
        MagicItemInstance(instance_id="i", catalog_id="gauntlets", equipped=True),
    ])
    assert carry_capacity_bonus(spec, fake) == 1000
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "apply_modifiers or active_modifiers or effective_abilities or carry_capacity_bonus" -q
```
Expected: `ModuleNotFoundError: No module named 'aose.engine.magic'`.

- [ ] **Step 3: Create `aose/engine/magic.py`**

```python
"""Magic-item engine — the cycle-free core.

Imports only models, the data loader, and dice.  The derivation modules
(``armor_class``, ``saves``, ``attack_bonus``, ``attacks``, ``encumbrance``)
import *from here*, never the other way round.

``apply_modifiers`` is literal: ``set`` (last wins) → ``add`` (summed) →
``set_min`` (``max``) → ``set_max`` (``min``).  Callers for lower-is-better
targets (``ac``, ``save:*``) negate ``add`` into the descending/target
direction themselves.
"""
from __future__ import annotations

import random
import uuid

from aose.data.loader import GameData
from aose.engine.dice import roll
from aose.models import Ability, CharacterSpec, MagicItem, MagicItemInstance, Modifier


class UnknownMagicItem(ValueError):
    pass


class NotEquippable(ValueError):
    pass


class NoCharges(ValueError):
    pass


def apply_modifiers(base: int, mods: list[Modifier], target: str) -> int:
    """Literal op semantics for one target.  See module docstring.

    NOTE: this is only used directly for ``ability:*`` (literal add = higher
    score = improvement) and ``thac0`` (realistic modifier is ``set_max``).  A
    ``thac0 add`` would literally *raise* THAC0; no seed data uses it.
    """
    relevant = [m for m in mods if m.target == target]
    result = base
    sets = [m.value for m in relevant if m.op == "set"]
    if sets:
        result = sets[-1]
    result += sum(m.value for m in relevant if m.op == "add")
    for m in relevant:
        if m.op == "set_min":
            result = max(result, m.value)
    for m in relevant:
        if m.op == "set_max":
            result = min(result, m.value)
    return result


def active_modifiers(spec: CharacterSpec, data: GameData) -> list[Modifier]:
    """Catalog modifiers + extra_modifiers from every EQUIPPED magic item."""
    out: list[Modifier] = []
    for inst in spec.magic_items:
        if not inst.equipped:
            continue
        catalog = data.items.get(inst.catalog_id)
        if isinstance(catalog, MagicItem):
            out.extend(catalog.modifiers)
        out.extend(inst.extra_modifiers)
    return out


def effective_abilities(spec: CharacterSpec, data: GameData) -> dict[Ability, int]:
    """``spec.abilities`` with every ``ability:*`` modifier applied."""
    mods = active_modifiers(spec, data)
    scores = dict(spec.abilities)
    for ab in Ability:
        target = f"ability:{ab.value}"
        if any(m.target == target for m in mods):
            scores[ab] = apply_modifiers(scores[ab], mods, target)
    return scores


def carry_capacity_bonus(spec: CharacterSpec, data: GameData) -> int:
    """Effective bonus carrying capacity in cn from active modifiers.

    ``add`` accumulates; a literal ``set`` (rare) overrides the running total.
    """
    return apply_modifiers(0, active_modifiers(spec, data), "carry_capacity")


def needs_instance(item) -> bool:
    """Whether a catalog item must be tracked as a MagicItemInstance (because
    it carries mutable per-instance state: equippable or charged)."""
    return isinstance(item, MagicItem) and (
        item.equippable or item.max_charges is not None or item.charge_dice is not None
    )
```

- [ ] **Step 4: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "apply_modifiers or active_modifiers or effective_abilities or carry_capacity_bonus" -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: new tests pass; full suite green.

- [ ] **Step 5: Commit**

```
git add aose/engine/magic.py tests/test_magic_items.py
git commit -m "Add magic engine core: apply/active modifiers, effective abilities, carry capacity"
```

---

## Task 6: Magic-item instance & charge helpers

**Files:**
- Modify: `aose/engine/magic.py`
- Modify: `tests/test_magic_items.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_magic_items.py`:

```python
import random as _random


def _charged_fake():
    fake = _fake_magic_data()
    fake.items["wand"] = MagicItem(
        id="wand", name="Wand", category="magic_wands", item_type="magic",
        cost_gp=0, weight_cn=10, magic=True, equippable=True, charge_dice="2d6",
    )
    fake.items["staff"] = MagicItem(
        id="staff", name="Staff", category="magic_staves", item_type="magic",
        cost_gp=0, weight_cn=40, magic=True, equippable=True, max_charges=10,
    )
    return fake


def test_new_magic_instance_rolls_charge_dice():
    from aose.engine.magic import new_magic_instance
    fake = _charged_fake()
    inst = new_magic_instance("wand", fake, rng=_random.Random(1))
    assert inst.charges_max == inst.charges_remaining
    assert 2 <= inst.charges_max <= 12
    assert len(inst.instance_id) >= 16
    assert inst.equipped is False


def test_new_magic_instance_uses_max_charges():
    from aose.engine.magic import new_magic_instance
    fake = _charged_fake()
    inst = new_magic_instance("staff", fake)
    assert inst.charges_max == 10
    assert inst.charges_remaining == 10


def test_new_magic_instance_no_charges_when_neither():
    from aose.engine.magic import new_magic_instance
    fake = _fake_magic_data()
    inst = new_magic_instance("ring_prot", fake)
    assert inst.charges_max is None
    assert inst.charges_remaining is None


def test_new_magic_instance_rejects_unknown_and_non_magic():
    from aose.engine.magic import UnknownMagicItem, new_magic_instance
    fake = _fake_magic_data()
    fake.items["torch"] = __import__("aose.models", fromlist=["AdventuringGear"]).AdventuringGear(
        id="torch", name="Torch", category="gear", item_type="gear", cost_gp=1, weight_cn=20,
    )
    with pytest.raises(UnknownMagicItem):
        new_magic_instance("missing", fake)
    with pytest.raises(UnknownMagicItem):
        new_magic_instance("torch", fake)  # exists but not a MagicItem


def test_add_free_then_equip_unequip():
    from aose.engine.magic import add_free_magic_item, equip_magic, unequip_magic, NotEquippable
    fake = _charged_fake()
    items = add_free_magic_item([], "ring_prot", fake)
    assert len(items) == 1 and items[0].equipped is False
    iid = items[0].instance_id
    items = equip_magic(items, iid, fake)
    assert items[0].equipped is True
    items = unequip_magic(items, iid)
    assert items[0].equipped is False


def test_equip_magic_rejects_non_equippable():
    from aose.engine.magic import add_free_magic_item, equip_magic, NotEquippable
    fake = _charged_fake()
    fake.items["amulet"] = MagicItem(
        id="amulet", name="Amulet", category="misc", item_type="magic",
        cost_gp=0, weight_cn=0, magic=True, equippable=False, max_charges=3,
    )
    items = add_free_magic_item([], "amulet", fake)
    with pytest.raises(NotEquippable):
        equip_magic(items, items[0].instance_id, fake)


def test_use_charge_decrements_and_raises_at_zero():
    from aose.engine.magic import add_free_magic_item, use_charge, reset_charges, NoCharges
    fake = _charged_fake()
    items = add_free_magic_item([], "staff", fake)   # 10 charges
    iid = items[0].instance_id
    for _ in range(10):
        items = use_charge(items, iid)
    assert items[0].charges_remaining == 0
    with pytest.raises(NoCharges):
        use_charge(items, iid)
    items = reset_charges(items, iid)
    assert items[0].charges_remaining == 10


def test_use_charge_on_uncharged_raises():
    from aose.engine.magic import add_free_magic_item, use_charge, NoCharges
    fake = _fake_magic_data()
    items = add_free_magic_item([], "ring_prot", fake)
    with pytest.raises(NoCharges):
        use_charge(items, items[0].instance_id)


def test_remove_magic_drop_removes_instance():
    from aose.engine.magic import add_free_magic_item, remove_magic
    fake = _fake_magic_data()
    items = add_free_magic_item([], "ring_prot", fake)
    new_items, gold = remove_magic(items, 5, items[0].instance_id, "drop", fake)
    assert new_items == []
    assert gold == 5  # cost_gp 0 → no refund regardless of mode


def test_set_magic_note_persists():
    from aose.engine.magic import add_free_magic_item, set_magic_note
    fake = _fake_magic_data()
    items = add_free_magic_item([], "ring_prot", fake)
    items = set_magic_note(items, items[0].instance_id, "found in dragon hoard")
    assert items[0].note == "found in dragon hoard"
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "new_magic_instance or add_free_then_equip or equip_magic or use_charge or remove_magic or set_magic_note" -q
```
Expected: ImportError on the new helpers.

- [ ] **Step 3: Implement the helpers in `aose/engine/magic.py`**

Append:

```python
REMOVE_MODES = ("drop", "sell", "refund")


def _index(magic_items: list[MagicItemInstance], instance_id: str) -> int:
    for i, m in enumerate(magic_items):
        if m.instance_id == instance_id:
            return i
    raise UnknownMagicItem(f"No magic item instance {instance_id!r}")


def new_magic_instance(catalog_id: str, data: GameData,
                       rng: random.Random | None = None) -> MagicItemInstance:
    """Create a fresh MagicItemInstance.  Validates the catalog is a MagicItem.
    Rolls ``charge_dice`` (via engine.dice) or uses ``max_charges`` to seed
    ``charges_max == charges_remaining``; ``uuid4`` hex id."""
    item = data.items.get(catalog_id)
    if not isinstance(item, MagicItem):
        raise UnknownMagicItem(f"{catalog_id!r} is not a magic item")
    charges_max: int | None = None
    if item.charge_dice:
        charges_max = roll(item.charge_dice, rng)
    elif item.max_charges is not None:
        charges_max = item.max_charges
    return MagicItemInstance(
        instance_id=uuid.uuid4().hex,
        catalog_id=catalog_id,
        equipped=False,
        charges_max=charges_max,
        charges_remaining=charges_max,
    )


def add_free_magic_item(magic_items: list[MagicItemInstance], catalog_id: str,
                        data: GameData) -> list[MagicItemInstance]:
    return [*magic_items, new_magic_instance(catalog_id, data)]


def equip_magic(magic_items: list[MagicItemInstance], instance_id: str,
                data: GameData) -> list[MagicItemInstance]:
    idx = _index(magic_items, instance_id)
    catalog = data.items.get(magic_items[idx].catalog_id)
    if not (isinstance(catalog, MagicItem) and catalog.equippable):
        raise NotEquippable(f"{magic_items[idx].catalog_id!r} is not equippable")
    updated = magic_items[idx].model_copy(update={"equipped": True})
    return [*magic_items[:idx], updated, *magic_items[idx + 1:]]


def unequip_magic(magic_items: list[MagicItemInstance],
                  instance_id: str) -> list[MagicItemInstance]:
    idx = _index(magic_items, instance_id)
    updated = magic_items[idx].model_copy(update={"equipped": False})
    return [*magic_items[:idx], updated, *magic_items[idx + 1:]]


def use_charge(magic_items: list[MagicItemInstance],
               instance_id: str) -> list[MagicItemInstance]:
    idx = _index(magic_items, instance_id)
    inst = magic_items[idx]
    if inst.charges_remaining is None or inst.charges_remaining <= 0:
        raise NoCharges(f"{inst.catalog_id!r} has no charges left")
    updated = inst.model_copy(update={"charges_remaining": inst.charges_remaining - 1})
    return [*magic_items[:idx], updated, *magic_items[idx + 1:]]


def reset_charges(magic_items: list[MagicItemInstance],
                  instance_id: str) -> list[MagicItemInstance]:
    idx = _index(magic_items, instance_id)
    inst = magic_items[idx]
    updated = inst.model_copy(update={"charges_remaining": inst.charges_max})
    return [*magic_items[:idx], updated, *magic_items[idx + 1:]]


def remove_magic(magic_items: list[MagicItemInstance], gold: int,
                 instance_id: str, mode: str,
                 data: GameData) -> tuple[list[MagicItemInstance], int]:
    """drop = discard, no refund.  sell/refund refund only when cost_gp > 0
    (seed magic items are cost 0, so this is effectively drop for them)."""
    if mode not in REMOVE_MODES:
        raise ValueError(f"Unknown remove mode {mode!r}; want one of {REMOVE_MODES}")
    idx = _index(magic_items, instance_id)
    catalog = data.items.get(magic_items[idx].catalog_id)
    cost = int(catalog.cost_gp) if catalog else 0
    refund = 0
    if cost > 0 and mode == "sell":
        refund = cost // 2
    elif cost > 0 and mode == "refund":
        refund = cost
    return [*magic_items[:idx], *magic_items[idx + 1:]], gold + refund


def set_magic_note(magic_items: list[MagicItemInstance], instance_id: str,
                   note: str) -> list[MagicItemInstance]:
    idx = _index(magic_items, instance_id)
    updated = magic_items[idx].model_copy(update={"note": note})
    return [*magic_items[:idx], updated, *magic_items[idx + 1:]]
```

- [ ] **Step 4: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: all pass.

- [ ] **Step 5: Commit**

```
git add aose/engine/magic.py tests/test_magic_items.py
git commit -m "Add magic-item instance and charge helpers"
```

---

## Task 7: Wire magic into Armour Class

**Files:**
- Modify: `aose/engine/armor_class.py`
- Modify: `tests/test_magic_items.py`

- [ ] **Step 1: Write the failing tests**

These use real data, so the magic-armour catalog must exist. Task 12 seeds the YAML; to keep this task self-contained, build a data fixture that deep-copies real data and injects the magic items inline.

Append to `tests/test_magic_items.py`:

```python
import copy as _copy


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def _with_magic(data):
    """Deep-copy real GameData and inject the magic catalog items the AC /
    saves / attacks tests need (so these tasks don't depend on Task 12)."""
    from aose.models import Armor, MagicItem, Weapon, WeaponDamage, ConditionalBonus
    d = _copy.deepcopy(data)
    d.items["ring_of_protection"] = MagicItem(
        id="ring_of_protection", name="Ring of Protection", category="magic_rings",
        item_type="magic", cost_gp=0, weight_cn=0, magic=True, equippable=True,
        modifiers=[
            {"target": "ac", "op": "add", "value": 1},
            {"target": "save:all", "op": "add", "value": 1},
        ],
    )
    d.items["gauntlets_of_ogre_power"] = MagicItem(
        id="gauntlets_of_ogre_power", name="Gauntlets of Ogre Power",
        category="miscellaneous_magic_items", item_type="magic", cost_gp=0,
        weight_cn=0, magic=True, equippable=True,
        modifiers=[
            {"target": "ability:STR", "op": "set", "value": 18},
            {"target": "carry_capacity", "op": "add", "value": 1000},
        ],
    )
    d.items["girdle_of_giant_strength"] = MagicItem(
        id="girdle_of_giant_strength", name="Girdle of Giant Strength",
        category="miscellaneous_magic_items", item_type="magic", cost_gp=0,
        weight_cn=0, magic=True, equippable=True,
        modifiers=[{"target": "thac0", "op": "set_max", "value": 14}],
    )
    d.items["chain_mail_plus_1"] = Armor(
        id="chain_mail_plus_1", name="Chain Mail +1", category="magic_armour",
        item_type="armor", cost_gp=0, weight_cn=400, ac_descending=5,
        movement_impact="metal", magic=True, magic_bonus=1, weight_multiplier=0.5,
    )
    d.items["shield_plus_1"] = Armor(
        id="shield_plus_1", name="Shield +1", category="magic_armour",
        item_type="armor", cost_gp=0, weight_cn=100, ac_descending=9,
        is_shield=True, magic=True, magic_bonus=1, weight_multiplier=0.5,
    )
    d.items["sword_plus_1"] = Weapon(
        id="sword_plus_1", name="Sword +1", category="magic_swords",
        item_type="weapon", cost_gp=0, weight_cn=60,
        damage=WeaponDamage(default="1d6", variable="1d8"), melee=True,
        proficiency_group="sword", magic=True, magic_bonus=1,
    )
    d.items["sword_plus_1_vs_undead"] = Weapon(
        id="sword_plus_1_vs_undead", name="Sword +1, +3 vs Undead",
        category="magic_swords", item_type="weapon", cost_gp=0, weight_cn=60,
        damage=WeaponDamage(default="1d6", variable="1d8"), melee=True,
        proficiency_group="sword", magic=True, magic_bonus=1,
        conditional_bonus=ConditionalBonus(vs="undead", bonus=2),
    )
    return d


def _equip_magic_spec(data, catalog_id, **spec_kwargs):
    from aose.engine.magic import add_free_magic_item, equip_magic
    spec = _minimal_spec(**spec_kwargs)
    spec.magic_items = add_free_magic_item([], catalog_id, data)
    spec.magic_items = equip_magic(spec.magic_items, spec.magic_items[0].instance_id, data)
    return spec


def test_ac_ring_of_protection(data):
    from aose.engine.armor_class import armor_class
    d = _with_magic(data)
    spec = _minimal_spec(abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    base_desc, base_asc = armor_class(spec, d)
    spec = _equip_magic_spec(d, "ring_of_protection",
                             abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    desc, asc = armor_class(spec, d)
    assert desc == base_desc - 1
    assert asc == base_asc + 1


def test_ac_chain_mail_plus_1(data):
    from aose.engine.armor_class import armor_class
    d = _with_magic(data)
    spec = _minimal_spec(abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    spec.inventory = ["chain_mail_plus_1"]
    spec.equipped = {"armor": "chain_mail_plus_1"}
    desc, asc = armor_class(spec, d)
    assert desc == 4   # 5 - 1
    assert asc == 15


def test_ac_shield_plus_1_two_points(data):
    from aose.engine.armor_class import armor_class
    d = _with_magic(data)
    spec = _minimal_spec(abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    spec.inventory = ["shield_plus_1"]
    spec.equipped = {"shield": "shield_plus_1"}
    desc, _ = armor_class(spec, d)
    assert desc == 9 - 2  # unarmored 9, shield bonus 1 + magic 1


def test_ac_chain_and_ring_stack(data):
    from aose.engine.armor_class import armor_class
    d = _with_magic(data)
    spec = _equip_magic_spec(d, "ring_of_protection",
                             abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    spec.inventory = ["chain_mail_plus_1"]
    spec.equipped = {"armor": "chain_mail_plus_1"}
    desc, _ = armor_class(spec, d)
    assert desc == 4 - 1  # chain+1 base 4, ring -1


def test_ac_set_takes_better_base(data):
    """ad-hoc bracers-style 'ac set 4' base candidate via extra_modifiers."""
    from aose.engine.armor_class import armor_class
    from aose.engine.magic import add_free_magic_item, equip_magic
    from aose.models import Modifier
    d = _with_magic(data)
    spec = _minimal_spec(abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    spec.magic_items = add_free_magic_item([], "ring_of_protection", d)
    iid = spec.magic_items[0].instance_id
    spec.magic_items[0].extra_modifiers = [Modifier(target="ac", op="set", value=4)]
    spec.magic_items = equip_magic(spec.magic_items, iid, d)
    desc, _ = armor_class(spec, d)
    # base min(9, 4) = 4, then ring -1 (add) → 3
    assert desc == 3
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "test_ac_" -q
```
Expected: assertion failures (current `armor_class` ignores `magic_bonus` and modifiers).

- [ ] **Step 3: Rewrite `aose/engine/armor_class.py`**

```python
from aose.data.loader import GameData
from aose.models import Ability, Armor, CharacterSpec

from .ability_mods import ability_modifier
from .magic import active_modifiers, effective_abilities

UNARMORED_AC_DESCENDING = 9
SHIELD_AC_BONUS = 1


def armor_class(spec: CharacterSpec, data: GameData) -> tuple[int, int]:
    """Return (descending_ac, ascending_ac). Sheet renders one based on ruleset."""
    eff = effective_abilities(spec, data)
    dex_mod = ability_modifier(eff[Ability.DEX])
    mods = active_modifiers(spec, data)

    base = UNARMORED_AC_DESCENDING
    armor_id = spec.equipped.get("armor")
    if armor_id and armor_id in data.items:
        item = data.items[armor_id]
        if isinstance(item, Armor) and not item.is_shield:
            base = item.ac_descending - item.magic_bonus

    # `ac set N` = literal descending base candidate (bracers-style); keep the better.
    for m in mods:
        if m.target == "ac" and m.op == "set":
            base = min(base, m.value)

    shield_bonus = 0
    shield_id = spec.equipped.get("shield")
    if shield_id and shield_id in data.items:
        item = data.items[shield_id]
        if isinstance(item, Armor) and item.is_shield:
            shield_bonus = SHIELD_AC_BONUS + item.magic_bonus

    ac_add = sum(m.value for m in mods if m.target == "ac" and m.op == "add")
    descending = base - dex_mod - shield_bonus - ac_add
    ascending = 19 - descending
    return descending, ascending
```

- [ ] **Step 4: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "test_ac_" -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: AC tests pass; full suite green (mundane characters have no modifiers and `magic_bonus` defaults to 0, so AC is unchanged for them — `tests/test_derivation.py` etc. stay green).

- [ ] **Step 5: Commit**

```
git add aose/engine/armor_class.py tests/test_magic_items.py
git commit -m "Armour Class picks up magic_bonus and ac modifiers"
```

---

## Task 8: Wire magic into Saving Throws

**Files:**
- Modify: `aose/engine/saves.py`
- Modify: `tests/test_magic_items.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_magic_items.py`:

```python
def test_saves_ring_improves_all_by_one(data):
    from aose.engine.saves import saving_throws
    d = _with_magic(data)
    base = saving_throws(_minimal_spec(), d)
    spec = _equip_magic_spec(d, "ring_of_protection")
    improved = saving_throws(spec, d)
    for cat, val in base.items():
        assert improved[cat] == max(2, val - 1)


def test_saves_single_category(data):
    from aose.engine.saves import saving_throws
    from aose.engine.magic import add_free_magic_item, equip_magic
    from aose.models import MagicItem, Modifier
    d = _copy.deepcopy(data)
    d.items["cloak_death"] = MagicItem(
        id="cloak_death", name="Cloak vs Death", category="misc",
        item_type="magic", cost_gp=0, weight_cn=0, magic=True, equippable=True,
        modifiers=[Modifier(target="save:death", op="add", value=2)],
    )
    base = saving_throws(_minimal_spec(), d)
    spec = _minimal_spec()
    spec.magic_items = add_free_magic_item([], "cloak_death", d)
    spec.magic_items = equip_magic(spec.magic_items, spec.magic_items[0].instance_id, d)
    improved = saving_throws(spec, d)
    assert improved["death"] == max(2, base["death"] - 2)
    assert improved["wands"] == base["wands"]  # untouched


def test_saves_clamp_floor(data):
    from aose.engine.saves import saving_throws
    from aose.engine.magic import add_free_magic_item, equip_magic
    from aose.models import MagicItem, Modifier
    d = _copy.deepcopy(data)
    d.items["overkill"] = MagicItem(
        id="overkill", name="Overkill Amulet", category="misc",
        item_type="magic", cost_gp=0, weight_cn=0, magic=True, equippable=True,
        modifiers=[Modifier(target="save:all", op="add", value=99)],
    )
    spec = _minimal_spec()
    spec.magic_items = add_free_magic_item([], "overkill", d)
    spec.magic_items = equip_magic(spec.magic_items, spec.magic_items[0].instance_id, d)
    improved = saving_throws(spec, d)
    assert all(v == 2 for v in improved.values())
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "test_saves_" -q
```
Expected: assertion failures.

- [ ] **Step 3: Edit `aose/engine/saves.py`**

Add the magic import and apply modifiers after the best-per-category pass:

```python
from aose.data.loader import GameData
from aose.models import CharacterSpec

from .magic import active_modifiers

SAVE_FLOOR = 2


def _level_data(cls, level: int):
    ...  # unchanged


def saving_throws(spec: CharacterSpec, data: GameData) -> dict[str, int]:
    """Best (lowest) save in each category across all classes, then magic
    modifiers.  ``add`` improves (target -= value); ``set`` / bounds use literal
    save numbers.  Targets clamp at ``SAVE_FLOOR``."""
    best: dict[str, int] = {}
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        ld = _level_data(cls, entry.level)
        for name, value in ld.saves.items():
            if name not in best or value < best[name]:
                best[name] = value

    mods = active_modifiers(spec, data)
    for name in list(best):
        wanted = ("save:all", f"save:{name}")
        target = best[name]
        sets = [m.value for m in mods if m.op == "set" and m.target in wanted]
        if sets:
            target = sets[-1]
        target -= sum(m.value for m in mods if m.op == "add" and m.target in wanted)
        for m in mods:
            if m.target in wanted and m.op == "set_min":
                target = max(target, m.value)
            elif m.target in wanted and m.op == "set_max":
                target = min(target, m.value)
        best[name] = max(SAVE_FLOOR, target)
    return best
```

- [ ] **Step 4: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "test_saves_" -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: save tests pass; full suite green.

- [ ] **Step 5: Commit**

```
git add aose/engine/saves.py tests/test_magic_items.py
git commit -m "Saving throws pick up save modifiers with a floor clamp"
```

---

## Task 9: Wire magic into THAC0

**Files:**
- Modify: `aose/engine/attack_bonus.py`
- Modify: `tests/test_magic_items.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_magic_items.py`:

```python
def test_thac0_girdle_set_max_lowers_worse(data):
    """A class with a worse (higher) THAC0 is capped at 14 by the Girdle."""
    from aose.engine.attack_bonus import thac0
    d = _with_magic(data)
    spec = _minimal_spec()  # fighter L1 → THAC0 19
    base = thac0(spec, d)
    assert base > 14
    spec = _equip_magic_spec(d, "girdle_of_giant_strength")
    assert thac0(spec, d) == 14


def test_thac0_set_max_leaves_better_untouched(data):
    """A natural THAC0 already better than 14 is not worsened by set_max 14."""
    from aose.engine.attack_bonus import thac0
    from aose.engine.magic import add_free_magic_item, equip_magic
    from aose.models import MagicItem, Modifier
    d = _copy.deepcopy(data)
    d.items["girdle"] = MagicItem(
        id="girdle", name="Girdle", category="misc", item_type="magic",
        cost_gp=0, weight_cn=0, magic=True, equippable=True,
        modifiers=[Modifier(target="thac0", op="set_max", value=14)],
    )
    # Force a better base THAC0 by monkey-injecting via a higher-level class is
    # awkward; instead assert the literal min() semantics directly:
    from aose.engine.magic import apply_modifiers
    assert apply_modifiers(11, [Modifier(target="thac0", op="set_max", value=14)], "thac0") == 11
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "test_thac0_" -q
```
Expected: the Girdle test fails (current `thac0` ignores modifiers).

- [ ] **Step 3: Edit `aose/engine/attack_bonus.py`**

```python
from aose.data.loader import GameData
from aose.models import CharacterSpec

from .magic import active_modifiers, apply_modifiers
from .saves import _level_data


def thac0(spec: CharacterSpec, data: GameData) -> int:
    best = 20
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        ld = _level_data(cls, entry.level)
        if ld.thac0 < best:
            best = ld.thac0
    return apply_modifiers(best, active_modifiers(spec, data), "thac0")


def attack_bonus(spec: CharacterSpec, data: GameData) -> int:
    return 19 - thac0(spec, data)
```

- [ ] **Step 4: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "test_thac0_" -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: THAC0 tests pass; full suite green.

- [ ] **Step 5: Commit**

```
git add aose/engine/attack_bonus.py tests/test_magic_items.py
git commit -m "THAC0 picks up thac0 modifiers (Girdle set_max override)"
```

---

## Task 10: Weapons, the unarmed strike, and conditional attacks

**Files:**
- Modify: `aose/engine/attacks.py`
- Modify: `tests/test_magic_items.py`

This is the largest engine task. `attack_profiles` now: (1) reads abilities via `effective_abilities`; (2) adds `weapon.magic_bonus` and global `attack`/`damage` modifiers to every profile; (3) attaches a `conditional` variant for any weapon with `conditional_bonus`; (4) **prepends a synthetic Unarmed profile** (1d2, STR, always proficient, first).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_magic_items.py`:

```python
def _weapon_spec(data, weapon_id, **kwargs):
    spec = _minimal_spec(**kwargs)
    spec.inventory = [weapon_id]
    spec.equipped_weapons = [weapon_id]
    return spec


def test_unarmed_profile_always_present_and_first(data):
    from aose.engine.attacks import attack_profiles
    spec = _minimal_spec(abilities={"STR": 13, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10})
    profiles = attack_profiles(spec, data)
    assert profiles[0].unarmed is True
    assert profiles[0].name == "Unarmed"
    assert profiles[0].proficient is True
    assert profiles[0].damage == "1d2+1"  # STR 13 → +1


def test_gauntlets_buff_unarmed_and_melee(data):
    from aose.engine.attacks import attack_profiles
    d = _with_magic(data)
    # base STR 9 (mod 0); gauntlets set STR 18 (mod +3)
    spec = _weapon_spec(d, "sword_plus_1",
                        abilities={"STR": 9, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10})
    from aose.engine.magic import add_free_magic_item, equip_magic
    spec.magic_items = add_free_magic_item([], "gauntlets_of_ogre_power", d)
    spec.magic_items = equip_magic(spec.magic_items, spec.magic_items[0].instance_id, d)
    profiles = attack_profiles(spec, d)
    unarmed = next(p for p in profiles if p.unarmed)
    assert unarmed.damage == "1d2+3"
    sword = next(p for p in profiles if p.weapon_id == "sword_plus_1")
    # variable_weapon_damage off → base 1d6; +3 STR, +1 magic = +4
    assert sword.damage == "1d6+4"


def test_magic_bonus_to_hit_and_damage(data):
    from aose.engine.attacks import attack_profiles
    from aose.engine.attack_bonus import thac0
    d = _with_magic(data)
    spec = _weapon_spec(d, "sword_plus_1",
                        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10})
    base_thac0 = thac0(_minimal_spec(), d)
    sword = next(p for p in attack_profiles(spec, d) if p.weapon_id == "sword_plus_1")
    assert sword.to_hit_thac0 == base_thac0 - 1   # STR 12 mod 0, +1 magic
    assert sword.to_hit_ascending == (19 - base_thac0) + 1
    assert sword.damage == "1d6+1"


def test_conditional_attack_profile(data):
    from aose.engine.attacks import attack_profiles
    from aose.engine.attack_bonus import thac0
    d = _with_magic(data)
    spec = _weapon_spec(d, "sword_plus_1_vs_undead",
                        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10})
    base_thac0 = thac0(_minimal_spec(), d)
    sword = next(p for p in attack_profiles(spec, d) if p.weapon_id == "sword_plus_1_vs_undead")
    assert sword.to_hit_thac0 == base_thac0 - 1   # normal: +1
    assert sword.conditional is not None
    assert sword.conditional.label == "vs undead"
    assert sword.conditional.to_hit_thac0 == base_thac0 - 3  # +1 base +2 extra
    assert sword.conditional.damage == "1d6+3"


def test_variable_weapon_damage_with_magic(data):
    from aose.engine.attacks import attack_profiles
    d = _with_magic(data)
    spec = _weapon_spec(d, "sword_plus_1",
                        abilities={"STR": 9, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10},
                        ruleset=RuleSet(variable_weapon_damage=True))
    sword = next(p for p in attack_profiles(spec, d) if p.weapon_id == "sword_plus_1")
    assert sword.damage == "1d8+1"  # variable 1d8, STR 0, +1 magic
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "unarmed or gauntlets_buff or magic_bonus_to_hit or conditional_attack or variable_weapon_damage_with_magic" -q
```
Expected: `AttributeError` on `.unarmed` / `.conditional`, plus assertion failures.

- [ ] **Step 3: Rewrite `aose/engine/attacks.py`**

Add `ConditionalAttack`, the new `AttackProfile` fields, the global-modifier helper, magic-bonus arithmetic, the conditional variant, and the synthetic unarmed profile. Key shape:

```python
from aose.engine.magic import active_modifiers, effective_abilities
from aose.models import Ability, CharacterSpec, ConditionalBonus, Weapon

UNARMED_DAMAGE = "1d2"


class ConditionalAttack(BaseModel):
    label: str
    to_hit_thac0: int
    to_hit_ascending: int
    damage: str


class AttackProfile(BaseModel):
    weapon_id: str
    name: str
    count: int
    melee: bool
    ranged: bool
    proficient: bool
    to_hit_thac0: int
    to_hit_ascending: int
    damage: str
    range_ft: tuple[int, int, int] | None
    conditional: ConditionalAttack | None = None
    unarmed: bool = False


def _format_damage(base: str, mod: int) -> str:
    if mod == 0:
        return base
    sign = "+" if mod > 0 else "-"
    return f"{base}{sign}{abs(mod)}"


def _global_atk_dmg(spec, data) -> tuple[int, int]:
    mods = active_modifiers(spec, data)
    atk = sum(m.value for m in mods if m.target == "attack" and m.op == "add")
    dmg = sum(m.value for m in mods if m.target == "damage" and m.op == "add")
    return atk, dmg


def _profile_for(weapon, spec, data, count, eff, base_thac0, g_atk, g_dmg):
    str_mod = ability_modifier(eff[Ability.STR])
    dex_mod = ability_modifier(eff[Ability.DEX])
    base_attack = 19 - base_thac0

    if weapon.melee:
        atk_mod, dmg_mod = str_mod, str_mod
    else:
        atk_mod, dmg_mod = dex_mod, 0

    proficient = True
    prof_pen = 0
    if spec.ruleset.weapon_proficiency:
        proficient = is_proficient_with(weapon, spec.chosen_proficiencies)
        if not proficient:
            prof_pen = -2

    base_damage = weapon.damage.variable if spec.ruleset.variable_weapon_damage else weapon.damage.default

    rng = None
    if weapon.ranged and weapon.range_short is not None:
        rng = (weapon.range_short, weapon.range_medium or 0, weapon.range_long or 0)

    def hit_thac0(extra):
        return base_thac0 - atk_mod - prof_pen - extra - g_atk

    def hit_asc(extra):
        return base_attack + atk_mod + prof_pen + extra + g_atk

    def dmg(extra):
        return _format_damage(base_damage, dmg_mod + g_dmg + extra)

    conditional = None
    if weapon.conditional_bonus is not None:
        extra = weapon.magic_bonus + weapon.conditional_bonus.bonus
        conditional = ConditionalAttack(
            label=f"vs {weapon.conditional_bonus.vs}",
            to_hit_thac0=hit_thac0(extra),
            to_hit_ascending=hit_asc(extra),
            damage=dmg(extra),
        )

    return AttackProfile(
        weapon_id=weapon.id, name=weapon.name, count=count,
        melee=weapon.melee, ranged=weapon.ranged, proficient=proficient,
        to_hit_thac0=hit_thac0(weapon.magic_bonus),
        to_hit_ascending=hit_asc(weapon.magic_bonus),
        damage=dmg(weapon.magic_bonus),
        range_ft=rng, conditional=conditional, unarmed=False,
    )


def _unarmed_profile(spec, eff, base_thac0, g_atk, g_dmg) -> AttackProfile:
    str_mod = ability_modifier(eff[Ability.STR])
    return AttackProfile(
        weapon_id="unarmed", name="Unarmed", count=1, melee=True, ranged=False,
        proficient=True,
        to_hit_thac0=base_thac0 - str_mod - g_atk,
        to_hit_ascending=(19 - base_thac0) + str_mod + g_atk,
        damage=_format_damage(UNARMED_DAMAGE, str_mod + g_dmg),
        range_ft=None, conditional=None, unarmed=True,
    )


def attack_profiles(spec, data):
    eff = effective_abilities(spec, data)
    base_thac0 = thac0(spec, data)
    g_atk, g_dmg = _global_atk_dmg(spec, data)

    counts = Counter(spec.equipped_weapons)
    weapon_profiles = []
    for weapon_id, count in counts.items():
        item = data.items.get(weapon_id)
        if not isinstance(item, Weapon):
            continue
        weapon_profiles.append(
            _profile_for(item, spec, data, count, eff, base_thac0, g_atk, g_dmg)
        )
    weapon_profiles.sort(key=lambda p: p.name)
    return [_unarmed_profile(spec, eff, base_thac0, g_atk, g_dmg), *weapon_profiles]
```

Keep the module docstring; add a note that Unarmed is synthetic and always first.

- [ ] **Step 4: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "unarmed or gauntlets_buff or magic_bonus_to_hit or conditional_attack or variable_weapon_damage_with_magic" -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: attack tests pass. **`tests/test_equip_attacks.py` will likely need updating** — it asserts on `attack_profiles` output that no longer omits Unarmed. Read that file; where a test asserts `len(profiles) == N` or `profiles[0]`, update it to account for the leading Unarmed row (e.g. filter `[p for p in profiles if not p.unarmed]` or index from the weapon). Adjust those assertions, re-run, and confirm the whole suite is green. This is expected churn, not a regression.

- [ ] **Step 5: Commit**

```
git add aose/engine/attacks.py tests/test_magic_items.py tests/test_equip_attacks.py
git commit -m "Attacks: effective abilities, magic_bonus, conditional + unarmed profiles"
```

---

## Task 11: Encumbrance — half-weight armour, instance weight, capacity banding

**Files:**
- Modify: `aose/engine/encumbrance.py`
- Modify: `tests/test_magic_items.py`

Three changes to `carried_weight_cn`: inventory `Armor` contributes `int(weight_cn * weight_multiplier)`; each `MagicItemInstance` contributes its catalog `weight_cn`; containers unchanged. Then add `banding_weight_cn` (raw − `carry_capacity_bonus`, floored at 0) and band on it in `effective_movement` + `encumbrance_table`. Displayed carried weight stays raw.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_magic_items.py`:

```python
def test_magic_armour_half_weight(data):
    from aose.engine.encumbrance import carried_weight_cn
    d = _with_magic(data)
    spec = _minimal_spec(ruleset=RuleSet(encumbrance="detailed"))
    spec.inventory = ["chain_mail_plus_1"]   # 400 cn × 0.5
    assert carried_weight_cn(spec, d) == 200


def test_magic_instance_contributes_weight(data):
    from aose.engine.encumbrance import carried_weight_cn
    from aose.engine.magic import add_free_magic_item
    from aose.models import MagicItem
    d = _copy.deepcopy(data)
    d.items["heavy_orb"] = MagicItem(
        id="heavy_orb", name="Heavy Orb", category="misc", item_type="magic",
        cost_gp=0, weight_cn=120, magic=True, equippable=True,
    )
    spec = _minimal_spec(ruleset=RuleSet(encumbrance="detailed"))
    spec.magic_items = add_free_magic_item([], "heavy_orb", d)
    assert carried_weight_cn(spec, d) == 120  # on-person whether worn or not


def test_carry_capacity_keeps_band_0(data):
    """Gauntlets +1000: 1400 cn raw → bands at 400 → still band 0 (move 120')."""
    from aose.engine.encumbrance import banding_weight_cn, weight_band, carried_weight_cn
    from aose.engine.magic import add_free_magic_item, equip_magic
    d = _with_magic(data)
    spec = _minimal_spec(race_id="human", ruleset=RuleSet(encumbrance="detailed"))
    # Pile 1400 cn of loose weight (use a mundane heavy item from real data, or torches).
    spec.inventory = ["torch"] * 70  # 70 × 20 = 1400 cn  (adjust id/qty to real data)
    spec.magic_items = add_free_magic_item([], "gauntlets_of_ogre_power", d)
    spec.magic_items = equip_magic(spec.magic_items, spec.magic_items[0].instance_id, d)
    assert carried_weight_cn(spec, d) == 1400          # displayed raw
    assert banding_weight_cn(spec, d) == 400           # 1400 - 1000
    assert weight_band(banding_weight_cn(spec, d)) == 0
```

> When writing Step 1, confirm a real 20-cn item id (Task 12 has `torch`-like gear; check `data/equipment/adventuring_gear.yaml` for an actual id and quantity that lands on 1400 cn). Adjust the filler item/qty so `carried_weight_cn == 1400` exactly.

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "magic_armour_half or magic_instance_contributes or carry_capacity_keeps_band" -q
```
Expected: ImportError on `banding_weight_cn`, plus assertion failures.

- [ ] **Step 3: Edit `aose/engine/encumbrance.py`**

Update `carried_weight_cn`'s inventory loop and add the instance loop:

```python
def carried_weight_cn(spec: CharacterSpec, data: GameData) -> int:
    from aose.models import Armor, Container

    total = 0
    for item_id in spec.inventory:
        item = data.items.get(item_id)
        if item is None:
            continue
        if isinstance(item, Armor):
            total += int(item.weight_cn * item.weight_multiplier)
        else:
            total += item.weight_cn

    for c in spec.containers:
        if c.state != "carried":
            continue
        catalog = data.items.get(c.catalog_id)
        if not isinstance(catalog, Container):
            continue
        total += catalog.weight_cn
        raw = sum(
            (data.items[x].weight_cn if x in data.items else 0)
            for x in c.contents
        )
        total += int(catalog.weight_multiplier * raw)

    for mi in spec.magic_items:
        catalog = data.items.get(mi.catalog_id)
        if catalog is not None:
            total += catalog.weight_cn

    return total


def banding_weight_cn(spec: CharacterSpec, data: GameData) -> int:
    """Weight used for movement banding: raw carried weight minus the active
    carry-capacity bonus, floored at zero.  The *displayed* carried weight stays
    raw — only the band/movement improves."""
    from aose.engine.magic import carry_capacity_bonus
    return max(0, carried_weight_cn(spec, data) - carry_capacity_bonus(spec, data))
```

In `effective_movement`, change the detailed-mode band line:

```python
    band = weight_band(banding_weight_cn(spec, data))
    return _scale(_TABLE_HUMAN[(armor_cls, band)], base)
```

In `encumbrance_table`, change the `current_band` computation:

```python
    if mode == "detailed":
        current_band = weight_band(banding_weight_cn(spec, data))
```

> Import note: `encumbrance` now imports `carry_capacity_bonus` from `magic` (lazily, inside `banding_weight_cn`, to keep the module-load order robust). `magic` does not import `encumbrance`, so there is no cycle.

- [ ] **Step 4: Update the sheet view's band display (Task 13 finalises this, but fix it now to keep the suite green)**

`aose/sheet/view.py::build_sheet` computes `current_weight_band` with `weight_band(carried_weight_cn(...))`. Change it to band on `banding_weight_cn`:

```python
from aose.engine.encumbrance import (..., banding_weight_cn, ...)
...
current_weight_band=(
    band_label(weight_band(banding_weight_cn(spec, data)))
    if spec.ruleset.encumbrance == "detailed" else None
),
```

(`carried_weight_cn` is still used, unchanged, for the displayed `carried_weight_cn` field — that stays raw.)

- [ ] **Step 5: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "magic_armour_half or magic_instance_contributes or carry_capacity_keeps_band" -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: encumbrance tests pass; full suite green. Watch `tests/test_encumbrance.py` — mundane characters have `weight_multiplier 1.0` armour and zero capacity bonus, so `banding_weight_cn == carried_weight_cn` and nothing changes.

- [ ] **Step 6: Commit**

```
git add aose/engine/encumbrance.py aose/sheet/view.py tests/test_magic_items.py
git commit -m "Encumbrance: half-weight armour, instance weight, capacity-adjusted banding"
```

---

## Task 12: Seed `data/equipment/magic_items.yaml`

**Files:**
- Create: `data/equipment/magic_items.yaml`
- Modify: `tests/test_magic_items.py`

The loader globs `data/equipment/*.yaml`, so the new file is auto-loaded — **no loader change**. (The spec's `ITEM_FILES` claim is wrong; see "Spec deviations".)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_magic_items.py`:

```python
def test_magic_items_yaml_loads(data):
    from aose.models import MagicItem, Weapon, Armor
    assert isinstance(data.items["gauntlets_of_ogre_power"], MagicItem)
    assert isinstance(data.items["ring_of_protection"], MagicItem)
    assert isinstance(data.items["sword_plus_1"], Weapon)
    assert data.items["sword_plus_1"].magic_bonus == 1
    assert isinstance(data.items["chain_mail_plus_1"], Armor)
    assert data.items["chain_mail_plus_1"].weight_multiplier == 0.5
    assert data.items["potion_of_healing"].magic is True


def test_ring_of_spell_turning_has_charge_dice(data):
    assert data.items["ring_of_spell_turning"].charge_dice == "2d6"


def test_sword_vs_undead_conditional(data):
    w = data.items["sword_plus_1_vs_undead"]
    assert w.conditional_bonus.vs == "undead"
    assert w.conditional_bonus.bonus == 2


def test_magic_categories_appear_in_shop(data):
    from aose.engine.shop import shop_categories
    cats = {c.id for c in shop_categories(data)}
    assert "magic_swords" in cats
    assert "magic_rings" in cats
    assert "miscellaneous_magic_items" in cats
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "yaml_loads or spell_turning or vs_undead or magic_categories" -q
```
Expected: KeyError on the missing ids.

- [ ] **Step 3: Create `data/equipment/magic_items.yaml`**

Copy the seed block verbatim from the spec's "Seed Data" section (lines 383–527): the four worn misc items (Gauntlets, Ring of Protection, Ring of Spell Turning, Girdle), four magic swords (+1/+2/+3 and +1/+3 vs undead), Chain Mail +1, Shield +1, and Potion of Healing. Every entry has `cost_gp: 0` and `magic: true`.

> Sanity checks while transcribing: `item_type` is `magic` for the worn items, `weapon` for swords, `armor` for armour, `gear` for the potion. The Girdle's `thac0 set_max 14` carries the inline comment to confirm the value against the AOSE monster attack matrix.

- [ ] **Step 4: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: all pass. `tests/test_data_loading.py` should still pass (the new file parses into the `Item` union).

- [ ] **Step 5: Commit**

```
git add data/equipment/magic_items.yaml tests/test_magic_items.py
git commit -m "Seed magic_items.yaml (worn items, magic swords, magic armour, potion)"
```

---

## Task 13: Sheet view — effective abilities marker + Magic Items view + ShopItem.magic

**Files:**
- Modify: `aose/sheet/view.py`
- Modify: `aose/engine/shop.py`
- Modify: `tests/test_magic_items.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_magic_items.py`:

```python
def test_ability_row_marks_modified(data):
    from aose.sheet.view import build_sheet
    from aose.engine.magic import add_free_magic_item, equip_magic
    d = _with_magic(data)
    spec = _minimal_spec(abilities={"STR": 9, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10})
    spec.magic_items = add_free_magic_item([], "gauntlets_of_ogre_power", d)
    spec.magic_items = equip_magic(spec.magic_items, spec.magic_items[0].instance_id, d)
    sheet = build_sheet(spec, d)
    str_row = next(r for r in sheet.abilities if r.ability == "STR")
    assert str_row.score == 18
    assert str_row.modified is True
    dex_row = next(r for r in sheet.abilities if r.ability == "DEX")
    assert dex_row.modified is False


def test_magic_items_view_lists_instance_and_inventory(data):
    from aose.sheet.view import build_sheet
    from aose.engine.magic import add_free_magic_item, equip_magic
    d = _with_magic(data)
    d.items["potion_of_healing"] = __import__("aose.models", fromlist=["AdventuringGear"]).AdventuringGear(
        id="potion_of_healing", name="Potion of Healing", category="magic_potions",
        item_type="gear", cost_gp=0, weight_cn=10, magic=True,
        description="Restores HP.",
    )
    spec = _minimal_spec()
    spec.inventory = ["potion_of_healing"]
    spec.magic_items = add_free_magic_item([], "ring_of_protection", d)
    spec.magic_items = equip_magic(spec.magic_items, spec.magic_items[0].instance_id, d)
    sheet = build_sheet(spec, d)
    names = {v.name for v in sheet.magic_items}
    assert "Ring of Protection" in names
    assert "Potion of Healing" in names
    ring = next(v for v in sheet.magic_items if v.name == "Ring of Protection")
    assert ring.instance_id is not None
    assert ring.equipped is True
    assert ring.modifier_summary  # non-empty human-readable list
    potion = next(v for v in sheet.magic_items if v.name == "Potion of Healing")
    assert potion.instance_id is None


def test_shop_item_carries_magic_flag(data):
    from aose.engine.shop import shop_categories
    flat = {i.id: i for c in shop_categories(data) for i in c.items}
    assert flat["ring_of_protection"].magic is True
    # a mundane item is not magic
    some_mundane = next(i for i in flat.values() if not i.magic)
    assert some_mundane.magic is False
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "ability_row_marks or magic_items_view or shop_item_carries" -q
```
Expected: `AttributeError`/validation errors on missing `modified`, `sheet.magic_items`, `ShopItem.magic`.

- [ ] **Step 3: `ShopItem.magic` in `aose/engine/shop.py`**

Add the field and populate it:

```python
class ShopItem(BaseModel):
    id: str
    name: str
    category: str
    cost_gp: float
    weight_cn: int = 0
    magic: bool = False
```

In `shop_categories`, pass `magic=i.magic` when building each `ShopItem`.

- [ ] **Step 4: Sheet view changes in `aose/sheet/view.py`**

Add imports:

```python
from aose.engine.magic import active_modifiers, effective_abilities
from aose.models import Ability, CharacterSpec, MagicItem, MagicItemInstance, RuleSet
```

Extend `AbilityRow`:

```python
class AbilityRow(BaseModel):
    ability: str
    score: int
    modifier: int
    modified: bool = False
```

Add the view model and `CharacterSheet.magic_items`:

```python
class MagicItemView(BaseModel):
    instance_id: str | None
    catalog_id: str
    name: str
    description: str | None
    equippable: bool
    equipped: bool
    charges_remaining: int | None
    charges_max: int | None
    note: str
    modifier_summary: list[str]
```

Add `magic_items: list[MagicItemView]` to `CharacterSheet`.

Add a human-readable summariser and the builder:

```python
_ABILITY_LABELS = {a.value: a.value for a in Ability}


def _summarize_modifier(m) -> str:
    t = m.target
    if t.startswith("ability:"):
        ab = t.split(":", 1)[1]
        return f"{ab} → {m.value}" if m.op in ("set", "set_min", "set_max") else f"{ab} {'+' if m.value >= 0 else ''}{m.value}"
    if t == "ac":
        return f"+{m.value} AC" if m.op == "add" else f"AC {m.value}"
    if t == "save:all":
        return f"+{m.value} all saves" if m.op == "add" else f"saves {m.value}"
    if t.startswith("save:"):
        cat = t.split(":", 1)[1]
        return f"+{m.value} {cat} save" if m.op == "add" else f"{cat} save {m.value}"
    if t == "attack":
        return f"+{m.value} to hit"
    if t == "damage":
        return f"+{m.value} damage"
    if t == "carry_capacity":
        return f"+{m.value} cn capacity"
    if t == "thac0":
        return f"THAC0 {m.value}" if m.op != "add" else f"+{m.value} THAC0"
    return f"{t} {m.op} {m.value}"


def _magic_bonus_summary(item) -> list[str]:
    from aose.models import Armor, Weapon
    out: list[str] = []
    if isinstance(item, Weapon) and item.magic_bonus:
        out.append(f"+{item.magic_bonus} to hit & damage")
        if item.conditional_bonus:
            out.append(f"+{item.magic_bonus + item.conditional_bonus.bonus} vs {item.conditional_bonus.vs}")
    if isinstance(item, Armor) and item.magic_bonus:
        out.append(f"+{item.magic_bonus} AC")
    return out


def _magic_items(spec: CharacterSpec, data: GameData) -> list[MagicItemView]:
    views: list[MagicItemView] = []
    # Instance-tracked magic items
    for inst in spec.magic_items:
        catalog = data.items.get(inst.catalog_id)
        is_magic = isinstance(catalog, MagicItem)
        summary = (
            [_summarize_modifier(m) for m in catalog.modifiers] if is_magic else []
        ) + [_summarize_modifier(m) for m in inst.extra_modifiers]
        views.append(MagicItemView(
            instance_id=inst.instance_id,
            catalog_id=inst.catalog_id,
            name=catalog.name if catalog else inst.catalog_id,
            description=catalog.description if catalog else None,
            equippable=bool(is_magic and catalog.equippable),
            equipped=inst.equipped,
            charges_remaining=inst.charges_remaining,
            charges_max=inst.charges_max,
            note=inst.note,
            modifier_summary=summary,
        ))
    # Plain-inventory magic items (deduped by catalog id; V1 has no count field)
    seen: set[str] = set()
    for item_id in spec.inventory:
        if item_id in seen:
            continue
        item = data.items.get(item_id)
        if item is None or not getattr(item, "magic", False):
            continue
        seen.add(item_id)
        views.append(MagicItemView(
            instance_id=None,
            catalog_id=item_id,
            name=item.name,
            description=item.description,
            equippable=False,
            equipped=False,
            charges_remaining=None,
            charges_max=None,
            note="",
            modifier_summary=_magic_bonus_summary(item),
        ))
    return views
```

In `build_sheet`, build abilities from effective scores and add `magic_items`:

```python
eff = effective_abilities(spec, data)
abilities = [
    AbilityRow(
        ability=ab.value,
        score=eff[ab],
        modifier=ability_mods.ability_modifier(eff[ab]),
        modified=(eff[ab] != spec.abilities[ab]),
    )
    for ab in ABILITY_ORDER
]
...
return CharacterSheet(
    ...,
    magic_items=_magic_items(spec, data),
)
```

- [ ] **Step 5: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "ability_row_marks or magic_items_view or shop_item_carries" -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: view tests pass; full suite green (`tests/test_sheet.py` should be fine — `modified` defaults False; if it constructs `AbilityRow` directly anywhere, the default covers it).

- [ ] **Step 6: Commit**

```
git add aose/sheet/view.py aose/engine/shop.py tests/test_magic_items.py
git commit -m "Sheet view: effective-ability marker, Magic Items view, ShopItem.magic flag"
```

---

## Task 14: Sheet HTTP routes — acquisition routing + magic actions

**Files:**
- Modify: `aose/web/routes.py`
- Modify: `tests/test_magic_items.py`

`/add` routes a `needs_instance` magic item to `add_free_magic_item`; otherwise the existing inventory/container paths. `/buy` is **not** extended (the UI offers no Buy for magic items). Six new POST routes mirror the engine helpers.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_magic_items.py` (TestClient harness mirrors `tests/test_containers.py`):

```python
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character, save_settings
from aose.web.app import create_app


def _make_client(tmp_path, ruleset=None):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True)
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, ruleset or RuleSet())
    app = create_app(
        data_dir=DATA_DIR, characters_dir=characters_dir, drafts_dir=drafts_dir,
        examples_dir=examples_dir, settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._characters_dir = characters_dir
    client._drafts_dir = drafts_dir
    return client


def _seed_character(client, **overrides):
    spec = _minimal_spec(**overrides)
    save_character("test", spec, client._characters_dir)
    return "test"


def test_add_worn_item_creates_instance(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    r = client.post("/character/test/equipment/add", data={"item_id": "ring_of_protection"})
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.inventory == []
    assert len(spec.magic_items) == 1
    assert spec.magic_items[0].catalog_id == "ring_of_protection"


def test_add_potion_goes_to_inventory(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "potion_of_healing"})
    spec = load_character("test", client._characters_dir)
    assert "potion_of_healing" in spec.inventory
    assert spec.magic_items == []


def test_add_sword_inventory_then_equip(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "sword_plus_1"})
    spec = load_character("test", client._characters_dir)
    assert "sword_plus_1" in spec.inventory
    client.post("/character/test/equipment/equip", data={"item_id": "sword_plus_1"})
    spec = load_character("test", client._characters_dir)
    assert "sword_plus_1" in spec.equipped_weapons


def test_equip_unequip_magic_roundtrip_reflects_on_sheet(tmp_path):
    client = _make_client(tmp_path, RuleSet(ascending_ac=True))
    _seed_character(client, abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    client.post("/character/test/equipment/add", data={"item_id": "ring_of_protection"})
    spec = load_character("test", client._characters_dir)
    iid = spec.magic_items[0].instance_id
    r = client.post("/character/test/equipment/equip-magic", data={"instance_id": iid})
    assert r.status_code == 303
    page = client.get("/character/test").text
    assert "Ring of Protection" in page
    spec = load_character("test", client._characters_dir)
    assert spec.magic_items[0].equipped is True
    client.post("/character/test/equipment/unequip-magic", data={"instance_id": iid})
    spec = load_character("test", client._characters_dir)
    assert spec.magic_items[0].equipped is False


def test_equip_magic_non_equippable_400(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    # Potion is not an instance at all; craft an instance that points at a
    # non-equippable magic item via the charged amulet path is overkill here —
    # instead assert a bogus instance id 400s.
    r = client.post("/character/test/equipment/equip-magic", data={"instance_id": "nope"})
    assert r.status_code == 400


def test_use_and_reset_charges(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "ring_of_spell_turning"})
    spec = load_character("test", client._characters_dir)
    iid = spec.magic_items[0].instance_id
    start = spec.magic_items[0].charges_remaining
    assert start is not None and start >= 1
    client.post("/character/test/equipment/use-charge", data={"instance_id": iid})
    spec = load_character("test", client._characters_dir)
    assert spec.magic_items[0].charges_remaining == start - 1
    client.post("/character/test/equipment/reset-charges", data={"instance_id": iid})
    spec = load_character("test", client._characters_dir)
    assert spec.magic_items[0].charges_remaining == start


def test_use_charge_at_zero_400(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "ring_of_spell_turning"})
    spec = load_character("test", client._characters_dir)
    iid = spec.magic_items[0].instance_id
    for _ in range(spec.magic_items[0].charges_remaining):
        client.post("/character/test/equipment/use-charge", data={"instance_id": iid})
    r = client.post("/character/test/equipment/use-charge", data={"instance_id": iid})
    assert r.status_code == 400


def test_magic_note_and_remove(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "ring_of_protection"})
    spec = load_character("test", client._characters_dir)
    iid = spec.magic_items[0].instance_id
    client.post("/character/test/equipment/magic-note", data={"instance_id": iid, "note": "cursed?"})
    spec = load_character("test", client._characters_dir)
    assert spec.magic_items[0].note == "cursed?"
    client.post("/character/test/equipment/remove-magic", data={"instance_id": iid, "mode": "drop"})
    spec = load_character("test", client._characters_dir)
    assert spec.magic_items == []
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "add_worn or add_potion or add_sword or equip_unequip_magic or equip_magic_non or use_and_reset or use_charge_at_zero or magic_note_and_remove" -q
```
Expected: 404/405 on the missing routes; the `/add` instance test fails.

- [ ] **Step 3: Edit `aose/web/routes.py`**

Augment the import block:

```python
from aose.engine.magic import (
    NoCharges,
    NotEquippable,
    UnknownMagicItem,
    add_free_magic_item,
    equip_magic as _equip_magic,
    needs_instance,
    remove_magic as _remove_magic,
    reset_charges as _reset_charges,
    set_magic_note as _set_magic_note,
    unequip_magic as _unequip_magic,
    use_charge as _use_charge,
)
```

In `equipment_add`, branch on `needs_instance` first (before the Container branch, since a `MagicItem` is never a `Container`):

```python
    item = game_data.items.get(item_id)
    from aose.models import Container
    try:
        if needs_instance(item):
            spec.magic_items = add_free_magic_item(spec.magic_items, item_id, game_data)
        elif isinstance(item, Container):
            spec.containers = add_free_container(spec.containers, item_id, game_data)
        else:
            spec.inventory = shop_add_free(spec.inventory, item_id, game_data)
    except (UnknownItem, UnknownMagicItem, ValueError) as e:
        raise HTTPException(400, str(e))
```

Add the six routes (each: load spec → call helper → save → 303; `ValueError`/`NotEquippable`/`NoCharges`/`UnknownMagicItem` → 400):

```python
@router.post("/character/{character_id}/equipment/equip-magic")
async def equipment_equip_magic(request: Request, character_id: str, instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.magic_items = _equip_magic(spec.magic_items, instance_id, request.app.state.game_data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/unequip-magic")
async def equipment_unequip_magic(request: Request, character_id: str, instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.magic_items = _unequip_magic(spec.magic_items, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/use-charge")
async def equipment_use_charge(request: Request, character_id: str, instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.magic_items = _use_charge(spec.magic_items, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/reset-charges")
async def equipment_reset_charges(request: Request, character_id: str, instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.magic_items = _reset_charges(spec.magic_items, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/remove-magic")
async def equipment_remove_magic(request: Request, character_id: str,
                                 instance_id: str = Form(...), mode: str = Form("drop")):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.magic_items, spec.gold = _remove_magic(
            spec.magic_items, spec.gold, instance_id, mode, request.app.state.game_data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/magic-note")
async def equipment_magic_note(request: Request, character_id: str,
                               instance_id: str = Form(...), note: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.magic_items = _set_magic_note(spec.magic_items, instance_id, note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: route tests pass; full suite green.

- [ ] **Step 5: Commit**

```
git add aose/web/routes.py tests/test_magic_items.py
git commit -m "Sheet routes: magic acquisition routing + equip/charge/note/remove actions"
```

---

## Task 15: Wizard mirror — `_draft_to_spec`, equipment context, magic routes

**Files:**
- Modify: `aose/web/wizard.py`
- Modify: `tests/test_magic_items.py`

The wizard stores `magic_items` in the draft JSON as a list of dicts (`model_dump()`), mirroring how `containers` are handled. `_draft_to_spec` must round-trip them.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_magic_items.py`:

```python
def _start_wizard_to_equipment(client):
    """Drive a fresh wizard draft up to the equipment step. Reuse the helper
    pattern from tests/test_containers.py / test_wizard.py — POST through rules,
    abilities (name), race, class, alignment, hp/roll — then return draft_id."""
    # Implementation note: copy the working flow from tests/test_containers.py's
    # wizard tests (they already reach the equipment step). Keep it minimal.
    ...


def test_wizard_add_worn_item_creates_instance_in_draft(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _start_wizard_to_equipment(client)
    client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "ring_of_protection"})
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft.get("inventory", []) == []
    assert len(draft["magic_items"]) == 1
    assert draft["magic_items"][0]["catalog_id"] == "ring_of_protection"


def test_wizard_finalize_roundtrips_magic_items(tmp_path):
    """Regression guard: _draft_to_spec must include magic_items."""
    client = _make_client(tmp_path)
    draft_id = _start_wizard_to_equipment(client)
    client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "ring_of_protection"})
    draft = load_draft(draft_id, client._drafts_dir)
    iid = draft["magic_items"][0]["instance_id"]
    client.post(f"/wizard/{draft_id}/equipment/equip-magic", data={"instance_id": iid})
    r = client.post(f"/wizard/{draft_id}/finalize")
    assert r.status_code == 303
    char_id = r.headers["location"].rsplit("/", 1)[-1]
    spec = load_character(char_id, client._characters_dir)
    assert len(spec.magic_items) == 1
    assert spec.magic_items[0].equipped is True
```

Add `from aose.characters import load_draft` to the test imports.

> When writing `_start_wizard_to_equipment`, lift the exact working sequence from the wizard equipment tests in `tests/test_containers.py` (search for `/wizard/` POSTs there) so it stays in sync with the real step order and gating.

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "wizard_add_worn or wizard_finalize_roundtrips" -q
```
Expected: 404 on `/equipment/add` magic routing not creating an instance; finalize missing magic_items.

- [ ] **Step 3: Edit `aose/web/wizard.py`**

Add imports:

```python
from aose.engine.magic import (
    add_free_magic_item,
    equip_magic as _equip_magic,
    needs_instance,
    remove_magic as _remove_magic,
    reset_charges as _reset_charges,
    set_magic_note as _set_magic_note,
    unequip_magic as _unequip_magic,
    use_charge as _use_charge,
)
from aose.models import (Ability, CharacterSpec, ClassEntry, ContainerInstance,
                         MagicItemInstance, RuleSet)
```

In `post_equipment_add`, branch on `needs_instance` first:

```python
    item = data.items.get(item_id)
    from aose.models import Container
    try:
        if needs_instance(item):
            magic_items = [MagicItemInstance.model_validate(m) for m in draft.get("magic_items", [])]
            magic_items = add_free_magic_item(magic_items, item_id, data)
            draft["magic_items"] = [m.model_dump() for m in magic_items]
        elif isinstance(item, Container):
            ...  # unchanged
        else:
            draft["inventory"] = shop_add_free(draft.get("inventory", []), item_id, data)
    except (UnknownItem, ValueError) as e:
        raise HTTPException(400, str(e))
```

Add a small helper for the magic routes to cut repetition:

```python
def _draft_magic(draft):
    return [MagicItemInstance.model_validate(m) for m in draft.get("magic_items", [])]
```

Add the six wizard magic routes mirroring the sheet (each loads the draft, validates `magic_items`, calls the helper, dumps back, redirects to `/wizard/{id}/equipment`). For example:

```python
@router.post("/{draft_id}/equipment/equip-magic")
async def wiz_equip_magic(request: Request, draft_id: str, instance_id: str = Form(...)):
    draft = _load(request, draft_id)
    try:
        items = _equip_magic(_draft_magic(draft), instance_id, request.app.state.game_data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["magic_items"] = [m.model_dump() for m in items]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")
```

…and analogous `unequip-magic`, `use-charge`, `reset-charges`, `remove-magic` (takes `mode`, returns `(items, gold)` → also set `draft["gold"]`), `magic-note` (takes `note`).

Extend `_equipment_context` to surface a magic-items view for the partial. The simplest faithful approach: build a `CharacterSpec`-free view by reusing the sheet builder's `_magic_items`. Since `_equipment_context` only has a draft, construct the pieces directly:

```python
from aose.sheet.view import _magic_items as _magic_items_view  # reuse summariser

def _equipment_context(draft, game_data):
    ...
    magic_items = [MagicItemInstance.model_validate(m) for m in draft.get("magic_items", [])]
    # Build a lightweight spec-like shim for the view builder, OR inline the
    # MagicItemView construction. Inlining avoids a fake spec:
    magic_view = _magic_items_for(magic_items, draft.get("inventory", []), game_data)
    return {
        ...,
        "magic_items_view": magic_view,
    }
```

> Decision for the implementer: rather than importing the private `_magic_items` (which takes a `CharacterSpec`), add a small public helper in `aose/sheet/view.py` — `magic_items_view(magic_items: list[MagicItemInstance], inventory: list[str], data) -> list[MagicItemView]` — and have `_magic_items(spec, data)` delegate to it. Then both the sheet route (`spec.magic_items, spec.inventory`) and the wizard (`draft` lists) call the same public helper. Update Task 13's `_magic_items` to delegate; if you do this in Task 15, re-run the Task 13 tests too.

Add `magic_items` to `_draft_to_spec`:

```python
        magic_items=[
            MagicItemInstance.model_validate(m) for m in draft.get("magic_items", [])
        ],
```

The sheet route (`character_sheet` in routes.py) already passes `sheet` (which now carries `magic_items`) to the template; for the equipment partial it must also pass `magic_items_view`. Update **both** callers (`routes.py::character_sheet` and `wizard.py::get_equipment`) to include `"magic_items_view": <built view>` in the template context. On the sheet side reuse `build_sheet(...).magic_items` or call the new public helper with `spec.magic_items, spec.inventory`.

- [ ] **Step 4: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: wizard tests pass; full suite green.

- [ ] **Step 5: Commit**

```
git add aose/web/wizard.py aose/sheet/view.py aose/web/routes.py tests/test_magic_items.py
git commit -m "Wizard mirror: magic acquisition + actions; _draft_to_spec round-trips magic_items"
```

---

## Task 16: Equipment editor UI — magic shop section + owned-items panel

**Files:**
- Modify: `aose/web/templates/_equipment_ui.html`
- Modify: `tests/test_magic_items.py`

The partial gains: (1) an **Owned Magic Items** panel (one row per instance: Equip/Unequip toggle, charges `n / max` with Use/Reset, editable note, Remove); (2) the shop renders magic rows **Add-only** (no Buy, cost "—"), with magic categories collapsed in a `<details>`. Magic categories are detected via `ShopItem.magic`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_magic_items.py`:

```python
def test_shop_renders_magic_addonly_section(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    page = client.get("/character/test").text
    # Magic categories appear (label title-cased) and offer Add, not Buy.
    assert "Magic Swords" in page or "Magic Rings" in page
    assert "/equipment/add" in page  # add form present for magic items


def test_owned_magic_panel_renders(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "ring_of_spell_turning"})
    page = client.get("/character/test").text
    assert "Ring of Spell Turning" in page
    assert "/equipment/equip-magic" in page
    assert "/equipment/use-charge" in page
    assert "/equipment/magic-note" in page
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "shop_renders_magic or owned_magic_panel" -q
```
Expected: failures (no magic panel, no equip-magic form).

- [ ] **Step 3: Edit `_equipment_ui.html`**

Update the header comment to document the new required context: `magic_items_view` (list of `MagicItemView`).

Add an **Owned Magic Items** panel above (or below) the Inventory subhead, rendered only when `magic_items_view` has instance rows. One block per `mi` where `mi.instance_id` is set:

```jinja
{% set owned_instances = magic_items_view | selectattr("instance_id") | list %}
{% if owned_instances %}
<h3 class="subhead">Magic Items</h3>
<table class="inventory-table magic-items-table">
  <thead><tr><th>Item</th><th>State</th><th>Charges</th><th>Note</th><th>Actions</th></tr></thead>
  <tbody>
  {% for mi in owned_instances %}
    <tr class="magic-item-row">
      <td>
        <strong>{{ mi.name }}</strong>
        {% if mi.modifier_summary %}
          {% for chip in mi.modifier_summary %}<span class="modifier-chip">{{ chip }}</span>{% endfor %}
        {% endif %}
      </td>
      <td>
        {% if mi.equippable %}
          {% if mi.equipped %}
          <form method="post" action="{{ target_url_prefix }}/unequip-magic" class="inline-form">
            <input type="hidden" name="instance_id" value="{{ mi.instance_id }}">
            <button type="submit">Unequip</button>
          </form>
          {% else %}
          <form method="post" action="{{ target_url_prefix }}/equip-magic" class="inline-form">
            <input type="hidden" name="instance_id" value="{{ mi.instance_id }}">
            <button type="submit">Equip</button>
          </form>
          {% endif %}
        {% else %}<span class="muted small">—</span>{% endif %}
      </td>
      <td class="charges">
        {% if mi.charges_remaining is not none %}
          {{ mi.charges_remaining }} / {{ mi.charges_max }}
          <form method="post" action="{{ target_url_prefix }}/use-charge" class="inline-form">
            <input type="hidden" name="instance_id" value="{{ mi.instance_id }}">
            <button type="submit" {% if mi.charges_remaining == 0 %}disabled{% endif %}>Use</button>
          </form>
          <form method="post" action="{{ target_url_prefix }}/reset-charges" class="inline-form">
            <input type="hidden" name="instance_id" value="{{ mi.instance_id }}">
            <button type="submit">Reset</button>
          </form>
        {% else %}<span class="muted small">—</span>{% endif %}
      </td>
      <td>
        <form method="post" action="{{ target_url_prefix }}/magic-note" class="inline-form">
          <input type="hidden" name="instance_id" value="{{ mi.instance_id }}">
          <input type="text" name="note" value="{{ mi.note }}" placeholder="note…">
          <button type="submit">Save</button>
        </form>
      </td>
      <td>
        <form method="post" action="{{ target_url_prefix }}/remove-magic" class="inline-form">
          <input type="hidden" name="instance_id" value="{{ mi.instance_id }}">
          <button type="submit" name="mode" value="drop">Remove</button>
        </form>
      </td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endif %}
```

In the shop loop, branch on whether a category is all-magic (or per-row `item.magic`). Per-row branching is simplest: replace the Actions cell with a conditional — magic items show only Add and a "—" cost:

```jinja
<td class="num">{% if item.magic %}—{% else %}{{ item.cost_gp | int }} gp{% endif %}</td>
...
<td>
  {% if not item.magic %}
  <form method="post" action="{{ target_url_prefix }}/buy" class="inline-form">
    <input type="hidden" name="item_id" value="{{ item.id }}">
    <button type="submit" {% if item.cost_gp > gold %}disabled{% endif %}>Buy</button>
  </form>
  {% endif %}
  <form method="post" action="{{ target_url_prefix }}/add" class="inline-form">
    <input type="hidden" name="item_id" value="{{ item.id }}">
    <button type="submit" title="Add without spending gold (GM gift / found loot)">Add</button>
  </form>
</td>
```

For "collapsed by default", wrap each shop category whose items are all magic in `<details>` instead of the bare `<h4>` + `<table>`. Detect with a Jinja test: `{% set is_magic_cat = category.items | selectattr("magic") | list | length == category.items | length %}`. When `is_magic_cat`, render `<details><summary class="shop-category">{{ category.name }}</summary> ...table... </details>`; otherwise the existing `<h4>` + table. Keep the `data-shop-category` attributes so the search filter still works.

- [ ] **Step 4: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "shop_renders_magic or owned_magic_panel" -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: UI tests pass; full suite green.

- [ ] **Step 5: Manually verify in the browser**

```
.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload
```
Open a character sheet → Equipment. Add a Ring of Protection (instance appears in the Magic Items panel), Equip it, confirm AC drops by 1 on the sheet above. Add a Ring of Spell Turning, Use a charge, Reset. Add a Potion of Healing → it lands in the normal Carried table. Confirm the shop's magic categories are collapsed and Add-only with "—" cost. Also drive the wizard's Equipment step through the same actions.

- [ ] **Step 6: Commit**

```
git add aose/web/templates/_equipment_ui.html tests/test_magic_items.py
git commit -m "Equipment editor: owned magic-items panel + Add-only magic shop section"
```

---

## Task 17: Sheet & print display — Magic Items section, ability marker, unarmed + conditional

**Files:**
- Modify: `aose/web/templates/sheet.html`
- Modify: `aose/web/templates/sheet_print.html`
- Modify: `tests/test_magic_items.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_magic_items.py`:

```python
def test_sheet_html_shows_magic_section_and_markers(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, abilities={"STR": 9, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10})
    client.post("/character/test/equipment/add", data={"item_id": "gauntlets_of_ogre_power"})
    spec = load_character("test", client._characters_dir)
    iid = spec.magic_items[0].instance_id
    client.post("/character/test/equipment/equip-magic", data={"instance_id": iid})
    page = client.get("/character/test").text
    assert "Magic Items" in page
    assert "Gauntlets of Ogre Power" in page
    assert "18" in page          # effective STR
    assert "*" in page           # modified marker on the ability row
    assert "Unarmed" in page     # always-present attack row


def test_sheet_html_shows_conditional_attack(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "sword_plus_1_vs_undead"})
    client.post("/character/test/equipment/equip", data={"item_id": "sword_plus_1_vs_undead"})
    page = client.get("/character/test").text
    assert "vs undead" in page


def test_print_html_lists_magic_items(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "ring_of_protection"})
    spec = load_character("test", client._characters_dir)
    client.post("/character/test/equipment/equip-magic",
                data={"instance_id": spec.magic_items[0].instance_id})
    page = client.get("/character/test/print").text
    assert "Ring of Protection" in page
    assert "+1 AC" in page  # one-line modifier summary
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -k "sheet_html_shows or print_html_lists" -q
```
Expected: failures.

- [ ] **Step 3: Edit `sheet.html`**

Abilities table — mark modified rows and add a footnote:

```jinja
<td class="num">{{ ab.score }}{% if ab.modified %}<span class="ability-modified" title="Modified by a magic item">*</span>{% endif %}</td>
...
{% if sheet.abilities | selectattr("modified") | list %}
<p class="small muted">* modified by a magic item</p>
{% endif %}
```

Attacks table — the Unarmed row is already first (engine prepends it). Add the conditional sub-line under any weapon with `atk.conditional`, and an `unarmed-row` class:

```jinja
<tr class="{% if atk.unarmed %}unarmed-row{% endif %}">
  ... existing cells ...
</tr>
{% if atk.conditional %}
<tr class="attack-conditional">
  <td class="small muted">&nbsp;&nbsp;({{ atk.conditional.label }})</td>
  <td class="num">{% if sheet.use_ascending %}{{ "%+d"|format(atk.conditional.to_hit_ascending) }}{% else %}{{ atk.conditional.to_hit_thac0 }}{% endif %}</td>
  <td>{{ atk.conditional.damage }}</td>
  <td class="small">&mdash;</td>
</tr>
{% endif %}
```

(The "No weapons equipped" branch can stay; Unarmed now means `sheet.attacks` is never empty, so that branch effectively becomes dead — leave it or drop the `{% else %}`.)

Add a **Magic Items** section in the right column (after Equipment or as its own section), with collapsible descriptions:

```jinja
{% if sheet.magic_items %}
<section class="section">
  <h2>Magic Items</h2>
  {% for mi in sheet.magic_items %}
  <div class="magic-item-row">
    <div class="feature-name">
      {{ mi.name }}
      {% if mi.instance_id and mi.equippable %}<span class="small muted">({{ "worn" if mi.equipped else "not worn" }})</span>{% endif %}
      {% if mi.charges_remaining is not none %}<span class="small muted">[{{ mi.charges_remaining }}/{{ mi.charges_max }} charges]</span>{% endif %}
    </div>
    {% if mi.modifier_summary %}
      <div>{% for chip in mi.modifier_summary %}<span class="modifier-chip">{{ chip }}</span>{% endfor %}</div>
    {% endif %}
    {% if mi.description %}
    <details class="magic-desc">
      <summary class="small muted">Description</summary>
      <div class="feature-text">{{ mi.description }}</div>
    </details>
    {% endif %}
    {% if mi.note %}<div class="small muted">Note: {{ mi.note }}</div>{% endif %}
  </div>
  {% endfor %}
</section>
{% endif %}
```

- [ ] **Step 4: Edit `sheet_print.html`**

Add a compact owned-magic-items block (name + one-line modifier summary, no descriptions) in the right column near Equipment:

```jinja
{% if sheet.magic_items %}
<section class="section">
  <h2>Magic Items</h2>
  <ul>
    {% for mi in sheet.magic_items %}
    <li><strong>{{ mi.name }}</strong>{% if mi.modifier_summary %} — {{ mi.modifier_summary | join(", ") }}{% endif %}</li>
    {% endfor %}
  </ul>
</section>
{% endif %}
```

The print sheet also reads `sheet.abilities`; add the `*` marker there too if desired (optional — keep print clean; a footnote is enough). AC/saves/THAC0 already reflect modifiers numerically.

- [ ] **Step 5: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_magic_items.py -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: display tests pass; full suite green. Note `tests/test_pdf.py` / `tests/test_web.py` may assert on the print/sheet HTML — re-run and adjust only if a genuine assertion conflicts.

- [ ] **Step 6: Commit**

```
git add aose/web/templates/sheet.html aose/web/templates/sheet_print.html tests/test_magic_items.py
git commit -m "Sheet + print: Magic Items section, ability marker, unarmed + conditional attacks"
```

---

## Task 18: CSS, full-suite green, and CLAUDE.md current-state

**Files:**
- Modify: `aose/web/static/sheet.css`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add CSS**

Append to `aose/web/static/sheet.css` (match the existing visual language — muted greys, subtle accents):

```css
/* ── Magic items ─────────────────────────────────────────── */
.magic-item-row { margin: 6px 0; padding: 4px 0; border-bottom: 1px dashed #ddd; }
.magic-desc { margin-top: 3px; }
.modifier-chip {
    display: inline-block; font-size: 0.78rem; padding: 1px 7px; margin: 1px 3px 1px 0;
    background: #eef2ff; color: #3344aa; border-radius: 10px; white-space: nowrap;
}
.charges { white-space: nowrap; }
.ability-modified { color: #b8860b; font-weight: bold; margin-left: 1px; }
.attack-conditional td { padding-top: 0; border-top: none; }
.attack-conditional { color: #666; }
.unarmed-row { color: #555; }
.magic-items-table input[type="text"] { width: 9rem; }
```

- [ ] **Step 2: Run the full suite**

```
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: all green. (Ignore the trailing `pytest-current` PermissionError — known Windows quirk.)

- [ ] **Step 3: Final manual smoke in the browser**

```
.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload
```
Verify end-to-end on a fresh character: equip Gauntlets (STR 18*, unarmed `1d2+3`, melee +3), Ring of Protection (AC −1), Chain Mail +1 (AC), Girdle (THAC0 capped), Sword +1, +3 vs Undead (conditional line), Ring of Spell Turning (charges Use/Reset), a note, Remove. Confirm carry-capacity banding only changes the band in detailed mode while the displayed carried weight stays raw. Print preview lists magic items compactly.

- [ ] **Step 4: Update `CLAUDE.md` current-state**

Replace the "Current state" section with a magic-items summary: the `Modifier`/`MagicItem`/`MagicItemInstance` models, `aose/engine/magic.py` as the cycle-free core, the derivation hooks (effective abilities, AC `magic_bonus` + `ac` mods, save mods, THAC0 `set_max`, magic_bonus/conditional/unarmed attacks, half-weight armour + capacity banding), Add-only acquisition + the magic routes, the sheet Magic Items section, and `data/equipment/magic_items.yaml`. Note the spec/plan paths. Update the date and the passing-test count.

- [ ] **Step 5: Commit**

```
git add aose/web/static/sheet.css CLAUDE.md
git commit -m "Magic-item CSS and CLAUDE.md current-state refresh"
```

---

## Out of scope (per spec — do NOT build)

- Damage-die overrides (Girdle's 2d8 / "twice normal") — note only.
- Spell-turning reflection automation — text + charge counter only.
- Multiple / non-weapon conditional bonuses — one flat `{vs, bonus}` only.
- Slot limits / attunement — GM trust, no enforcement.
- Editing `extra_modifiers` via UI — note-only in V1; `extra_modifiers` is settable via homebrew catalog data / direct JSON.
- Stashing magic-item instances — always on-person in V1.
- Non-stacking rules for like bonuses — additive only.
- Magic-item drag-and-drop — buttons/forms only (magic weapons/armour still DnD via the existing inventory path, since they're plain inventory ids).
- Custom item creation UI — homebrew goes in YAML / `extra_modifiers`.

## Notes for the implementer

- **HP and XP keep base abilities.** Only the abilities table, AC, saves, and attacks use `effective_abilities` in V1. A CON-buffing item does not retroactively change max HP, and prime-requisite XP multipliers use the rolled scores. The spec only mandates AC/saves/attacks/abilities — don't touch `hp.py` or `leveling.py`.
- **No import cycles.** `aose/engine/magic.py` imports only models + loader + dice. Everything else imports *from* magic. `encumbrance.banding_weight_cn` imports `carry_capacity_bonus` lazily inside the function for safety.
- **`/buy` is intentionally not extended.** The UI hides Buy for magic items; leave the buy route alone. If a magic instance item is ever POSTed to `/buy` it would wrongly land in inventory — acceptable for V1 since the UI never offers it, but do not add a Buy button for magic rows.
- After each task, run the **whole** suite, not just the new tests — the engine rewrites (Tasks 7–11, 13) touch shared derivations and the most likely regressions are in `tests/test_derivation.py`, `tests/test_equip_attacks.py`, `tests/test_encumbrance.py`, and `tests/test_sheet.py`.
