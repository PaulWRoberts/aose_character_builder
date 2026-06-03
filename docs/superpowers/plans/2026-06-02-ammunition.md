# Ammunition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Model ammunition as a non-weapon item that loads into a ranged launcher, tracks per-stack counts, and — when the loaded ammo is magic (a base ammo + an `Enchantment` of `kind: ammunition`) — confers its bonus additively to the launcher's attack line.

**Architecture:** A new `Ammunition` item variant + per-character `AmmoStack` list and a `loaded_ammo` map on `CharacterSpec`. Magic ammo reuses the existing enchantment-composition engine (extended with an `ammunition` kind). A cycle-free `aose/engine/ammo.py` owns stack/load logic; `aose/engine/attacks.py` adds the loaded bonus and an "Unloaded" flag. Sheet and wizard each get thin routes over the shared engine, mirroring the existing enchanted-item wiring.

**Tech Stack:** Python 3.14, Pydantic v2, PyYAML, FastAPI, Jinja2, pytest. Spec: `docs/superpowers/specs/2026-06-02-ammunition-design.md`.

---

## Pre-flight

- Read the spec: `docs/superpowers/specs/2026-06-02-ammunition-design.md`.
- Read for patterns: `aose/models/item.py` (`ItemBase`, `Weapon`, `ConditionalBonus`, the `Item` union), `aose/models/enchantment.py`, `aose/models/character.py` (`EnchantedInstance`, `CharacterSpec`), `aose/engine/enchant.py`, `aose/engine/ammo.py`-analogue `aose/engine/magic.py`, `aose/engine/attacks.py`.
- **Run tests (Windows; venv is not auto-activated):**
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/ -q
  ```
  Baseline: **834 passing** (835 collected). Ignore the trailing `pytest-current` PermissionError (known Windows pytest-9 quirk).
- No data migration is needed (the app is single-user/local; new `CharacterSpec` fields default empty — see the project "no migrations" rule).

**`weapon_key` convention (used throughout):** the key under which a launcher's loaded ammo is stored is the weapon's resolved `.id` — the catalog id for a mundane weapon (e.g. `short_bow`), or `ench:<instance_id>` for an enchanted launcher (set by `enchant.resolve_weapon`). The sheet's `AttackProfile.weapon_id` already carries exactly this value, so the load form posts it back verbatim.

---

## Task 1: Models — `Ammunition`, `AmmoStack`, `accepts_ammo`, `loaded_ammo`, ammunition enchantment kind

**Files:**
- Modify: `aose/models/item.py`
- Modify: `aose/models/enchantment.py`
- Modify: `aose/models/character.py`
- Modify: `aose/models/__init__.py`
- Test: `tests/test_ammunition.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ammunition.py`:
```python
"""Ammunition model + engine tests."""
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).parent.parent / "data"


def test_ammunition_parses_minimal():
    from aose.models import Ammunition
    a = Ammunition(id="arrow", name="Arrows", category="ammunition",
                   item_type="ammunition", cost_gp=5)
    assert a.weight_cn == 0          # ammo never weighs in
    assert a.bundle_count == 1
    assert a.groups == []


def test_ammunition_full_fields():
    from aose.models import Ammunition
    a = Ammunition(id="arrow", name="Arrows (quiver of 20)", category="ammunition",
                   item_type="ammunition", cost_gp=5, bundle_count=20,
                   groups=["arrow"], description="A quiver of 20 arrows.")
    assert a.bundle_count == 20 and a.groups == ["arrow"]


def test_ammunition_is_in_item_union():
    from pydantic import TypeAdapter
    from aose.models import Ammunition, Item
    parsed = TypeAdapter(Item).validate_python(
        {"id": "arrow", "name": "Arrows", "category": "ammunition",
         "item_type": "ammunition", "cost_gp": 5, "groups": ["arrow"]})
    assert isinstance(parsed, Ammunition)


def test_weapon_accepts_ammo_defaults_empty():
    from aose.models import Weapon, WeaponDamage
    w = Weapon(id="sword", name="Sword", category="weapons", item_type="weapon",
               cost_gp=10, damage=WeaponDamage())
    assert w.accepts_ammo == []


def test_enchantment_kind_allows_ammunition():
    from aose.models import Enchantment
    e = Enchantment(id="arrows_plus_1", name_template="{base} +1",
                    kind="ammunition", applies_to={"include": ["arrow"]},
                    magic_bonus=1)
    assert e.kind == "ammunition"


def test_ammo_stack_and_spec_fields():
    from aose.models import AmmoStack, CharacterSpec, ClassEntry
    s = AmmoStack(instance_id="x", base_id="arrow", count=20)
    assert s.enchantment_id is None and s.count == 20
    spec = CharacterSpec(name="A", abilities={}, race_id="human",
                         classes=[ClassEntry(class_id="fighter")], alignment="law")
    assert spec.ammo == [] and spec.loaded_ammo == {}
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ammunition.py -q`
Expected: FAIL — `ImportError: cannot import name 'Ammunition'`.

- [ ] **Step 3: Add the `Ammunition` variant and `Weapon.accepts_ammo`**

In `aose/models/item.py`, add `accepts_ammo` to `Weapon` (after `groups`):
```python
    accepts_ammo: list[str] = Field(default_factory=list)  # ammo groups this launcher fires
```
Add the new variant (after `AdventuringGear`):
```python
class Ammunition(ItemBase):
    item_type: Literal["ammunition"]
    groups: list[str] = Field(default_factory=list)   # match tags (e.g. [arrow])
    bundle_count: int = 1                              # units granted per purchase
    # weight_cn defaults to 0 (ItemBase) — ammo never contributes encumbrance.
```
Add `Ammunition` to the `Item` union:
```python
Item = Annotated[
    Union[Weapon, Armor, AdventuringGear, Poison, Container, MagicItem, Ammunition],
    Field(discriminator="item_type"),
]
```

- [ ] **Step 4: Extend `Enchantment.kind`**

In `aose/models/enchantment.py`:
```python
    kind: Literal["weapon", "armor", "shield", "ammunition"]
```

- [ ] **Step 5: Add `AmmoStack` and the `CharacterSpec` fields**

In `aose/models/character.py`, add the model (after `EnchantedInstance`):
```python
class AmmoStack(BaseModel):
    """A stack of one kind of ammunition the character owns.  Stacks with the
    same (base_id, enchantment_id) combine; counts are adjusted manually (no
    automatic per-shot consumption).  ``enchantment_id`` set => magic ammo,
    resolved like an EnchantedInstance to confer its bonus to a loaded launcher.
    """
    model_config = ConfigDict(extra="forbid")

    instance_id: str                       # uuid4 hex
    base_id: str                           # references an Ammunition item
    enchantment_id: str | None = None      # references an Enchantment (kind ammunition)
    count: int = 0
```
On `CharacterSpec`, add (after `enchanted`):
```python
    # Ammunition stacks (counts), plus which stack is loaded into each launcher.
    ammo: list[AmmoStack] = Field(default_factory=list)
    loaded_ammo: dict[str, str] = Field(default_factory=dict)  # weapon_key -> AmmoStack.instance_id
```

- [ ] **Step 6: Export the new names**

In `aose/models/__init__.py`, add `Ammunition` to the item imports/`__all__` and `AmmoStack` to the character imports/`__all__` (follow the existing alphabetical-ish grouping; mirror how `MagicItem`/`EnchantedInstance` are exported).

- [ ] **Step 7: Run the tests, verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ammunition.py -q`
Expected: PASS (6 tests).

- [ ] **Step 8: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: 840 passing (834 + 6). No regressions (new fields are optional with defaults).

- [ ] **Step 9: Commit**
```powershell
git add aose/models tests/test_ammunition.py
git commit -m "feat(models): Ammunition item, AmmoStack, accepts_ammo, ammunition enchantment kind"
```

---

## Task 2: `enchant.py` — ammunition matching + preserve `accepts_ammo`

**Files:**
- Modify: `aose/engine/enchant.py`
- Test: `tests/test_ammunition.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ammunition.py`:
```python
def _ammo(id, groups=()):
    from aose.models import Ammunition
    return Ammunition(id=id, name=id.title(), category="ammunition",
                      item_type="ammunition", cost_gp=1, groups=list(groups))


def _ammo_ench(id, include, exclude=()):
    from aose.models import Enchantment
    return Enchantment(id=id, name_template="{base} +1", kind="ammunition",
                       applies_to={"include": list(include), "exclude": list(exclude)})


def test_ammunition_nature_and_wildcard():
    from aose.engine.enchant import matches, is_compatible
    arrow = _ammo("arrow", groups=["arrow"])
    assert matches(arrow, "any_ammunition")
    assert matches(arrow, "arrow")
    assert is_compatible(arrow, _ammo_ench("arrows_plus_1", ["arrow"]))


def test_silver_arrow_takes_arrow_slaying():
    from aose.engine.enchant import is_compatible
    silver = _ammo("silver_arrow", groups=["arrow"])
    assert is_compatible(silver, _ammo_ench("arrow_slaying", ["arrow"]))


def test_ammo_enchantment_not_compatible_with_weapon():
    from aose.engine.enchant import is_compatible
    from aose.models import Weapon, WeaponDamage
    bow = Weapon(id="short_bow", name="Short Bow", category="weapons",
                 item_type="weapon", cost_gp=25, damage=WeaponDamage(), ranged=True)
    assert not is_compatible(bow, _ammo_ench("arrows_plus_1", ["arrow"]))


def test_resolve_weapon_preserves_accepts_ammo():
    from aose.engine.enchant import resolve_weapon
    from aose.models import Enchantment, Weapon, WeaponDamage
    bow = Weapon(id="short_bow", name="Short Bow", category="weapons",
                 item_type="weapon", cost_gp=25, damage=WeaponDamage(),
                 ranged=True, groups=["bow"], accepts_ammo=["arrow"])
    ench = Enchantment(id="bow_plus_1", name_template="{base} +1", kind="weapon",
                       applies_to={"include": ["bow"]}, magic_bonus=1)
    resolved = resolve_weapon(bow, ench, "iid")
    assert resolved.accepts_ammo == ["arrow"]
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ammunition.py -k "ammunition_nature or silver_arrow or ammo_enchantment_not or resolve_weapon_preserves" -q`
Expected: FAIL — `matches(arrow, "any_ammunition")` is False (and `resolved.accepts_ammo` empty).

- [ ] **Step 3: Add the ammunition nature to `enchant.py`**

Add the wildcard to the set:
```python
_WILDCARDS = {"any_weapon", "any_armour", "any_shield", "any_ammunition"}
```
Add the nature predicate (near `_is_weapon`):
```python
def _is_ammunition(base) -> bool:
    from aose.models import Ammunition
    return isinstance(base, Ammunition)
```
Extend `matches` (add the wildcard branch alongside the others):
```python
    if token == "any_ammunition":
        return _is_ammunition(base)
```
Extend `_nature_matches_kind`:
```python
def _nature_matches_kind(base, kind: str) -> bool:
    return (
        (kind == "weapon" and _is_weapon(base))
        or (kind == "armor" and _is_armour(base))
        or (kind == "shield" and _is_shield(base))
        or (kind == "ammunition" and _is_ammunition(base))
    )
```

- [ ] **Step 4: Preserve `accepts_ammo` in `resolve_weapon`**

In `resolve_weapon`, add to the returned `Weapon(...)`:
```python
        accepts_ammo=list(base.accepts_ammo),
```

- [ ] **Step 5: Run the tests, verify pass** → the four targeted tests PASS.
- [ ] **Step 6: Full suite** → green (840).
- [ ] **Step 7: Commit**
```powershell
git add aose/engine/enchant.py tests/test_ammunition.py
git commit -m "feat(enchant): ammunition matching kind + preserve accepts_ammo on resolve"
```

---

## Task 3: `aose/engine/ammo.py` — stacks, loading, bonus

**Files:**
- Create: `aose/engine/ammo.py`
- Test: `tests/test_ammunition.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ammunition.py`:
```python
import random as _random

from aose.data.loader import GameData
from aose.models import AmmoStack, Ammunition, Enchantment, Weapon, WeaponDamage


def _data_with_ammo():
    """In-memory GameData: a bow launcher, arrow + silver arrow bases, two ammo
    enchantments."""
    d = GameData()
    d.items["short_bow"] = Weapon(id="short_bow", name="Short Bow",
        category="weapons", item_type="weapon", cost_gp=25, damage=WeaponDamage(),
        ranged=True, groups=["bow"], accepts_ammo=["arrow"])
    d.items["arrow"] = Ammunition(id="arrow", name="Arrows (quiver of 20)",
        category="ammunition", item_type="ammunition", cost_gp=5, bundle_count=20,
        groups=["arrow"])
    d.items["silver_arrow"] = Ammunition(id="silver_arrow", name="Silver Arrow",
        category="ammunition", item_type="ammunition", cost_gp=5, bundle_count=1,
        groups=["arrow"])
    d.enchantments["arrows_plus_1"] = Enchantment(id="arrows_plus_1",
        name_template="{base} +1", kind="ammunition",
        applies_to={"include": ["arrow"]}, magic_bonus=1)
    return d


def test_accepts():
    from aose.engine.ammo import accepts
    d = _data_with_ammo()
    assert accepts(d.items["short_bow"], d.items["arrow"]) is True


def test_buy_ammo_adds_bundle_and_combines():
    from aose.engine.ammo import buy_ammo
    d = _data_with_ammo()
    stacks, gold = buy_ammo([], 10, "arrow", d)
    assert gold == 5 and stacks[0].count == 20 and stacks[0].enchantment_id is None
    stacks, gold = buy_ammo(stacks, gold, "arrow", d)   # second quiver combines
    assert gold == 0 and len(stacks) == 1 and stacks[0].count == 40


def test_buy_ammo_insufficient_gold():
    from aose.engine.ammo import buy_ammo, InsufficientGold
    d = _data_with_ammo()
    with pytest.raises(InsufficientGold):
        buy_ammo([], 2, "arrow", d)


def test_add_free_magic_ammo_validates_compat():
    from aose.engine.ammo import add_free_ammo, IncompatibleAmmo
    d = _data_with_ammo()
    stacks = add_free_ammo([], "arrow", "arrows_plus_1", d)
    assert stacks[0].enchantment_id == "arrows_plus_1" and stacks[0].count == 1
    d.enchantments["bolts"] = Enchantment(id="bolts", name_template="{base}",
        kind="ammunition", applies_to={"include": ["crossbow_bolt"]})
    with pytest.raises(IncompatibleAmmo):
        add_free_ammo([], "arrow", "bolts", d)


def test_adjust_count_clamps_and_removes_at_zero():
    from aose.engine.ammo import adjust_count
    s = [AmmoStack(instance_id="a", base_id="arrow", count=3)]
    s = adjust_count(s, "a", -1)
    assert s[0].count == 2
    s = adjust_count(s, "a", -5)        # clamps to 0 → stack removed
    assert s == []


def test_load_unload_and_loaded_stack():
    from aose.engine.ammo import load, unload, loaded_stack
    d = _data_with_ammo()
    stacks = [AmmoStack(instance_id="a", base_id="arrow",
                        enchantment_id="arrows_plus_1", count=20)]

    class _Spec:  # minimal stand-in
        ammo = stacks
        loaded_ammo = {}
    spec = _Spec()
    spec.loaded_ammo = load(spec.loaded_ammo, "short_bow", "a")
    assert loaded_stack("short_bow", spec, d).instance_id == "a"
    spec.loaded_ammo = unload(spec.loaded_ammo, "short_bow")
    assert loaded_stack("short_bow", spec, d) is None


def test_loaded_bonus_from_magic_ammo():
    from aose.engine.ammo import load, loaded_bonus
    d = _data_with_ammo()
    stacks = [AmmoStack(instance_id="a", base_id="arrow",
                        enchantment_id="arrows_plus_1", count=20)]

    class _Spec:
        ammo = stacks
        loaded_ammo = {}
    spec = _Spec()
    spec.loaded_ammo = load(spec.loaded_ammo, "short_bow", "a")
    bonus, cond = loaded_bonus("short_bow", spec, d)
    assert bonus == 1 and cond is None


def test_is_unloaded_flag():
    from aose.engine.ammo import is_unloaded
    d = _data_with_ammo()

    class _Spec:
        ammo = []
        loaded_ammo = {}
    assert is_unloaded("short_bow", d.items["short_bow"], _Spec(), d) is True
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ammunition.py -k "accepts or buy_ammo or add_free_magic or adjust_count or load_unload or loaded_bonus or is_unloaded" -q`
Expected: FAIL — `ModuleNotFoundError: aose.engine.ammo`.

- [ ] **Step 3: Create `aose/engine/ammo.py`**
```python
"""Ammunition engine — cycle-free core for ammo stacks, loading, and the
magic-ammo bonus a loaded stack confers to its launcher.

Imports only models, the loader, dice, and ``enchant`` (for compatibility +
display name).  Mutators return a new list/dict (the ``enchant``/``magic`` style).
"""
from __future__ import annotations

import uuid

from aose.data.loader import GameData
from aose.engine.enchant import is_compatible
from aose.models import Ammunition, AmmoStack, ConditionalBonus, Weapon


class UnknownAmmo(ValueError):
    pass


class IncompatibleAmmo(ValueError):
    pass


class InsufficientGold(ValueError):
    pass


def accepts(weapon: Weapon, ammo_base: Ammunition) -> bool:
    """True when the launcher fires this ammo (a group/id token overlaps)."""
    tokens = {ammo_base.id, *ammo_base.groups}
    return any(t in weapon.accepts_ammo for t in tokens)


def _ammo_base(base_id: str, data: GameData) -> Ammunition:
    base = data.items.get(base_id)
    if not isinstance(base, Ammunition):
        raise UnknownAmmo(f"{base_id!r} is not ammunition")
    return base


def _find(stacks: list[AmmoStack], instance_id: str) -> int:
    for i, s in enumerate(stacks):
        if s.instance_id == instance_id:
            return i
    raise UnknownAmmo(f"No ammo stack {instance_id!r}")


def _combine(stacks: list[AmmoStack], base_id: str, enchantment_id: str | None,
             count: int) -> list[AmmoStack]:
    """Add ``count`` to an existing (base_id, enchantment_id) stack, or append a
    fresh one."""
    for i, s in enumerate(stacks):
        if s.base_id == base_id and s.enchantment_id == enchantment_id:
            merged = s.model_copy(update={"count": s.count + count})
            return [*stacks[:i], merged, *stacks[i + 1:]]
    fresh = AmmoStack(instance_id=uuid.uuid4().hex, base_id=base_id,
                      enchantment_id=enchantment_id, count=count)
    return [*stacks, fresh]


def buy_ammo(stacks: list[AmmoStack], gold: int, base_id: str,
             data: GameData) -> tuple[list[AmmoStack], int]:
    """Purchase one bundle of mundane ammo: subtract cost, add ``bundle_count``."""
    base = _ammo_base(base_id, data)
    cost = int(base.cost_gp)
    if gold < cost:
        raise InsufficientGold(f"Need {cost} gp, have {gold}")
    return _combine(stacks, base_id, None, base.bundle_count), gold - cost


def add_free_ammo(stacks: list[AmmoStack], base_id: str,
                  enchantment_id: str | None, data: GameData) -> list[AmmoStack]:
    """GM grant.  Mundane (enchantment_id None) adds one bundle; magic adds 1
    unit (count is adjusted up manually).  Validates compatibility."""
    base = _ammo_base(base_id, data)
    if enchantment_id is None:
        return _combine(stacks, base_id, None, base.bundle_count)
    ench = data.enchantments.get(enchantment_id)
    if ench is None or ench.kind != "ammunition":
        raise IncompatibleAmmo(f"{enchantment_id!r} is not an ammunition enchantment")
    if not is_compatible(base, ench):
        raise IncompatibleAmmo(f"{base_id!r} is not compatible with {enchantment_id!r}")
    return _combine(stacks, base_id, enchantment_id, 1)


def adjust_count(stacks: list[AmmoStack], instance_id: str, delta: int) -> list[AmmoStack]:
    """Change a stack's count (clamped ≥ 0).  Count 0 removes the stack."""
    idx = _find(stacks, instance_id)
    new_count = max(0, stacks[idx].count + delta)
    if new_count == 0:
        return [*stacks[:idx], *stacks[idx + 1:]]
    updated = stacks[idx].model_copy(update={"count": new_count})
    return [*stacks[:idx], updated, *stacks[idx + 1:]]


def remove_ammo(stacks: list[AmmoStack], instance_id: str) -> list[AmmoStack]:
    idx = _find(stacks, instance_id)
    return [*stacks[:idx], *stacks[idx + 1:]]


def load(loaded: dict[str, str], weapon_key: str, instance_id: str) -> dict[str, str]:
    return {**loaded, weapon_key: instance_id}


def unload(loaded: dict[str, str], weapon_key: str) -> dict[str, str]:
    return {k: v for k, v in loaded.items() if k != weapon_key}


def loaded_stack(weapon_key: str, spec, data: GameData) -> AmmoStack | None:
    """The AmmoStack loaded into ``weapon_key``, or None if nothing valid."""
    iid = spec.loaded_ammo.get(weapon_key)
    if iid is None:
        return None
    for s in spec.ammo:
        if s.instance_id == iid and s.count > 0:
            return s
    return None


def loaded_bonus(weapon_key: str, spec, data: GameData) -> tuple[int, ConditionalBonus | None]:
    """The flat magic_bonus + conditional_bonus the loaded ammo confers."""
    stack = loaded_stack(weapon_key, spec, data)
    if stack is None or stack.enchantment_id is None:
        return 0, None
    ench = data.enchantments.get(stack.enchantment_id)
    if ench is None:
        return 0, None
    return ench.magic_bonus, ench.conditional_bonus


def is_unloaded(weapon_key: str, weapon: Weapon, spec, data: GameData) -> bool:
    """True for a launcher (accepts_ammo non-empty) with no valid loaded ammo."""
    if not weapon.accepts_ammo:
        return False
    return loaded_stack(weapon_key, spec, data) is None


def resolve_ammo(stack: AmmoStack, data: GameData) -> dict:
    """Display view: name (+ enchantment), magic_bonus, conditional_bonus."""
    base = data.items.get(stack.base_id)
    name = base.name if base else stack.base_id
    magic_bonus, conditional = 0, None
    if stack.enchantment_id:
        ench = data.enchantments.get(stack.enchantment_id)
        if ench:
            name = ench.name_template.format(base=name)
            magic_bonus, conditional = ench.magic_bonus, ench.conditional_bonus
    return {"instance_id": stack.instance_id, "name": name, "count": stack.count,
            "magic_bonus": magic_bonus, "conditional": conditional,
            "base_id": stack.base_id, "enchantment_id": stack.enchantment_id}
```

- [ ] **Step 4: Run the targeted tests, verify pass.**
- [ ] **Step 5: Full suite** → green.
- [ ] **Step 6: Commit**
```powershell
git add aose/engine/ammo.py tests/test_ammunition.py
git commit -m "feat(engine): ammunition stacks, loading, and magic-ammo bonus"
```

---

## Task 4: `attacks.py` — loaded bonus + Unloaded flag on launchers

**Files:**
- Modify: `aose/engine/attacks.py`
- Test: `tests/test_ammunition.py`

The launcher's attack line must add the loaded ammo's `magic_bonus` to to-hit and damage (additive with `weapon.magic_bonus`), expose the loaded ammo name, and flag an empty launcher.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ammunition.py`:
```python
def _bow_spec(loaded=True, ench=True):
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="B", abilities={"STR": 12, "INT": 10, "WIS": 10,
                             "DEX": 12, "CON": 12, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter")], alignment="law")
    spec.inventory = ["short_bow"]
    spec.equipped_weapons = ["short_bow"]
    eid = "arrows_plus_1" if ench else None
    spec.ammo = [AmmoStack(instance_id="a", base_id="arrow",
                           enchantment_id=eid, count=20)]
    if loaded:
        spec.loaded_ammo = {"short_bow": "a"}
    return spec


def _real_data():
    return GameData.load(DATA_DIR)


def _bow_profile(profiles):
    return next(p for p in profiles if p.weapon_id == "short_bow")


def test_plus1_arrow_in_plus0_bow_is_plus1():
    from aose.engine.attacks import attack_profiles
    d = _real_data()
    p = _bow_profile(attack_profiles(_bow_spec(loaded=True, ench=True), d))
    base = _bow_profile(attack_profiles(_bow_spec(loaded=True, ench=False), d))
    assert p.to_hit_ascending == base.to_hit_ascending + 1


def test_unloaded_bow_flagged():
    from aose.engine.attacks import attack_profiles
    d = _real_data()
    p = _bow_profile(attack_profiles(_bow_spec(loaded=False), d))
    assert p.unloaded is True
    p2 = _bow_profile(attack_profiles(_bow_spec(loaded=True, ench=True), d))
    assert p2.unloaded is False
    assert p2.loaded_ammo_name and "+1" in p2.loaded_ammo_name
```
> These load the real `data/` dir, so they pass only after Task 5 ships `short_bow` with `accepts_ammo: [arrow]` and the `arrows_plus_1` enchantment. Run them at the end of Task 5; here, assert the engine wiring compiles via the unit path below.

Add an engine-only test that doesn't need real data:
```python
def test_profile_adds_ammo_bonus_unit():
    from aose.engine.attacks import attack_profiles
    d = _data_with_ammo()
    from aose.models import CharacterSpec, ClassEntry
    # Minimal class so thac0() resolves; reuse fighter from real data.
    rd = _real_data()
    d.classes = rd.classes
    spec = CharacterSpec(name="U", abilities={"STR": 10, "INT": 10, "WIS": 10,
                         "DEX": 10, "CON": 10, "CHA": 10}, race_id="human",
                         classes=[ClassEntry(class_id="fighter")], alignment="law")
    spec.equipped_weapons = ["short_bow"]
    spec.ammo = [AmmoStack(instance_id="a", base_id="arrow",
                           enchantment_id="arrows_plus_1", count=5)]
    spec.loaded_ammo = {"short_bow": "a"}
    p = _bow_profile(attack_profiles(spec, d))
    assert p.unloaded is False and "+1" in (p.loaded_ammo_name or "")
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ammunition.py -k "profile_adds_ammo_bonus_unit" -q`
Expected: FAIL — `AttackProfile` has no `unloaded`/`loaded_ammo_name`.

- [ ] **Step 3: Extend `AttackProfile`**

In `aose/engine/attacks.py`, add fields to `AttackProfile`:
```python
    unloaded: bool = False           # launcher with no ammo loaded
    loaded_ammo_name: str | None = None
```

- [ ] **Step 4: Thread the ammo bonus through `_profile_for`**

Change `_profile_for`'s signature to accept the loaded ammo info:
```python
def _profile_for(weapon: Weapon, spec: CharacterSpec, data: GameData,
                 count: int, eff: dict, base_thac0: int,
                 g_atk: int, g_dmg: int,
                 ammo_bonus: int = 0, ammo_conditional=None,
                 ammo_name: str | None = None, unloaded: bool = False) -> AttackProfile:
```
Inside, fold `ammo_bonus` into the magic bonus everywhere `weapon.magic_bonus` is used for the main line, and prefer the weapon's own conditional but fall back to the ammo's:
```python
    flat = weapon.magic_bonus + ammo_bonus

    conditional = None
    if weapon.conditional_bonus is not None:
        extra = weapon.magic_bonus + weapon.conditional_bonus.bonus + ammo_bonus
        conditional = ConditionalAttack(
            label=f"vs {weapon.conditional_bonus.vs}",
            to_hit_thac0=hit_thac0(extra),
            to_hit_ascending=hit_asc(extra),
            damage=dmg(extra),
        )
    elif ammo_conditional is not None:
        extra = flat + ammo_conditional.bonus
        conditional = ConditionalAttack(
            label=f"vs {ammo_conditional.vs}",
            to_hit_thac0=hit_thac0(extra),
            to_hit_ascending=hit_asc(extra),
            damage=dmg(extra),
        )

    return AttackProfile(
        weapon_id=weapon.id,
        name=weapon.name,
        count=count,
        melee=weapon.melee,
        ranged=weapon.ranged,
        proficient=proficient,
        specialised=specialised,
        to_hit_thac0=hit_thac0(flat),
        to_hit_ascending=hit_asc(flat),
        damage=dmg(flat),
        range_ft=rng,
        conditional=conditional,
        unarmed=False,
        unloaded=unloaded,
        loaded_ammo_name=ammo_name,
    )
```
> Replace the three previous `hit_thac0(weapon.magic_bonus)` / `hit_asc(...)` / `dmg(...)` calls in the `return` with the `flat` versions above.

- [ ] **Step 5: Compute the ammo info in `attack_profiles`**

Add the import at the top:
```python
from aose.engine.ammo import is_unloaded, loaded_bonus, loaded_stack, resolve_ammo
```
In both loops (plain equipped weapons and `equipped_enchanted`), compute and pass the ammo info. Helper, defined inside `attack_profiles`:
```python
    def _ammo_args(weapon):
        if not weapon.accepts_ammo:
            return {}
        a_bonus, a_cond = loaded_bonus(weapon.id, spec, data)
        stack = loaded_stack(weapon.id, spec, data)
        name = resolve_ammo(stack, data)["name"] if stack else None
        return {"ammo_bonus": a_bonus, "ammo_conditional": a_cond,
                "ammo_name": name,
                "unloaded": is_unloaded(weapon.id, weapon, spec, data)}
```
Then:
```python
        weapon_profiles.append(
            _profile_for(item, spec, data, count, eff, base_thac0, g_atk, g_dmg,
                         **_ammo_args(item)))
    ...
        weapon_profiles.append(
            _profile_for(resolved, spec, data, 1, eff, base_thac0, g_atk, g_dmg,
                         **_ammo_args(resolved)))
```

- [ ] **Step 6: Run the unit test, verify pass.**
- [ ] **Step 7: Full suite** → green (the real-data tests `test_plus1_arrow_*`/`test_unloaded_bow_flagged` still fail until Task 5 — leave them; they're in the same file and will pass after Task 5. To keep the suite green between commits, mark those two with `@pytest.mark.xfail(reason="needs Task 5 data", strict=True)` now and remove the marker in Task 5.)
- [ ] **Step 8: Commit**
```powershell
git add aose/engine/attacks.py tests/test_ammunition.py
git commit -m "feat(attacks): add loaded-ammo bonus and Unloaded flag to launcher profiles"
```

---

## Task 5: Data — ammunition catalog, ammo enchantments, launcher `accepts_ammo`

**Files:**
- Create: `data/equipment/ammunition.yaml`
- Modify: `data/equipment/weapons.yaml`
- Modify: `data/enchantments.yaml`
- Test: `tests/test_ammunition.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ammunition.py`:
```python
def test_data_ammunition_loads():
    d = GameData.load(DATA_DIR)
    arrow = d.items["arrow"]
    assert isinstance(arrow, Ammunition)
    assert arrow.bundle_count == 20 and arrow.weight_cn == 0
    assert "arrow" in arrow.groups
    assert d.items["sling_stone"].cost_gp == 0


def test_launchers_accept_ammo():
    d = GameData.load(DATA_DIR)
    assert d.items["short_bow"].accepts_ammo == ["arrow"]
    assert d.items["long_bow"].accepts_ammo == ["arrow"]
    assert d.items["crossbow"].accepts_ammo == ["crossbow_bolt"]
    assert d.items["sling"].accepts_ammo == ["sling_stone"]


def test_ammo_enchantments_load():
    d = GameData.load(DATA_DIR)
    assert d.enchantments["arrows_plus_1"].kind == "ammunition"
    assert d.enchantments["arrows_plus_1"].magic_bonus == 1
    assert d.enchantments["crossbow_bolts_plus_2"].magic_bonus == 2
    assert d.enchantments["sling_bullet_impact"].applies_to.include == ["sling_stone"]
```

- [ ] **Step 2: Run, verify failure** → `KeyError: 'arrow'` / `accepts_ammo == []`.

- [ ] **Step 3: Create `data/equipment/ammunition.yaml`**
```yaml
# Mundane ammunition.  weight_cn is always 0 — the listed weight of a missile
# weapon already includes its ammunition and container.  bundle_count is how
# many units one purchase grants.

- id: arrow
  item_type: ammunition
  name: Arrows (quiver of 20)
  category: ammunition
  cost_gp: 5
  weight_cn: 0
  bundle_count: 20
  groups: [arrow]
  description: A quiver of 20 arrows for short or long bows.

- id: crossbow_bolt
  item_type: ammunition
  name: Crossbow Bolts (case of 30)
  category: ammunition
  cost_gp: 10
  weight_cn: 0
  bundle_count: 30
  groups: [crossbow_bolt]
  description: A case of 30 bolts (quarrels) for crossbows.

- id: silver_arrow
  item_type: ammunition
  name: Silver-Tipped Arrow
  category: ammunition
  cost_gp: 5
  weight_cn: 0
  bundle_count: 1
  groups: [arrow]
  description: A single arrow with a silver tip.

- id: sling_stone
  item_type: ammunition
  name: Sling Stones
  category: ammunition
  cost_gp: 0
  weight_cn: 0
  bundle_count: 20
  groups: [sling_stone]
  description: Stones for a sling — freely gathered.
```

- [ ] **Step 4: Add `accepts_ammo` (and bow `groups`) to launchers**

In `data/equipment/weapons.yaml`:
- `short_bow` and `long_bow`: add `groups: [bow]` and `accepts_ammo: [arrow]`.
- `crossbow`: add `accepts_ammo: [crossbow_bolt]`.
- `sling`: add `accepts_ammo: [sling_stone]`.

Example (short_bow):
```yaml
  qualities: [missile, two_handed]
  groups: [bow]
  accepts_ammo: [arrow]
```

- [ ] **Step 5: Add ammo enchantments to `data/enchantments.yaml`**
```yaml
- id: arrows_plus_1
  name_template: "{base} +1"
  kind: ammunition
  applies_to: {include: [arrow]}
  magic_bonus: 1
  description: "+1 to attack and damage rolls while these arrows are loaded."

- id: arrows_plus_2
  name_template: "{base} +2"
  kind: ammunition
  applies_to: {include: [arrow]}
  magic_bonus: 2
  description: "+2 to attack and damage rolls while these arrows are loaded."

- id: arrow_slaying
  name_template: "{base} of Slaying"
  kind: ammunition
  applies_to: {include: [arrow]}
  magic_bonus: 1
  description: |-
    Enchanted to kill a certain type of foe (chosen by the referee). Acts as a
    +3 arrow against that foe and slays it instantly on a hit; otherwise a
    +1 arrow.

- id: crossbow_bolts_plus_1
  name_template: "{base} +1"
  kind: ammunition
  applies_to: {include: [crossbow_bolt]}
  magic_bonus: 1
  description: "+1 to attack and damage rolls while these bolts are loaded."

- id: crossbow_bolts_plus_2
  name_template: "{base} +2"
  kind: ammunition
  applies_to: {include: [crossbow_bolt]}
  magic_bonus: 2
  description: "+2 to attack and damage rolls while these bolts are loaded."

- id: sling_bullet_impact
  name_template: "{base} +1, Impact"
  kind: ammunition
  applies_to: {include: [sling_stone]}
  magic_bonus: 1
  description: |-
    A cast metal bullet engraved with runes. +1 to attack and damage; on a
    hit that beats the required roll, inflicts extra damage equal to the
    margin of success.
```

- [ ] **Step 6: Remove the xfail markers** added in Task 4 from `test_plus1_arrow_in_plus0_bow_is_plus1` and `test_unloaded_bow_flagged`.

- [ ] **Step 7: Run the data + real-data attack tests, verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ammunition.py -q`
Expected: PASS (all).

- [ ] **Step 8: Full suite** — green. **Note:** the `bow` group + ammunition enchantments make these arrows compose; verify no existing data-load test counts items/enchantments by a hard total (search `tests/` for `len(data.items)`/`len(data.enchantments)` and update any exact count).

- [ ] **Step 9: Commit**
```powershell
git add data/equipment/ammunition.yaml data/equipment/weapons.yaml data/enchantments.yaml tests/test_ammunition.py
git commit -m "feat(data): ammunition catalog, ammo enchantments, launcher accepts_ammo"
```

---

## Task 6: Sheet view — ammunition section + launcher load options

**Files:**
- Modify: `aose/sheet/view.py`
- Test: `tests/test_ammunition.py`

The sheet must surface (a) the owned ammo stacks (name, count, magic flag) and (b) per equipped launcher, the compatible stacks for a load dropdown + current load. Attack rows already carry `unloaded`/`loaded_ammo_name` from Task 4.

- [ ] **Step 1: Read `aose/sheet/view.py`** to find the `CharacterSheet` model and where `attack_profiles` is assembled into the sheet (search for `attack_profiles(` and the section-building pattern used for `magic_items`).

- [ ] **Step 2: Write the failing test**

Append to `tests/test_ammunition.py`:
```python
def test_sheet_exposes_ammo_section():
    from aose.sheet.view import build_sheet
    d = GameData.load(DATA_DIR)
    spec = _bow_spec(loaded=True, ench=True)
    sheet = build_sheet(spec, d)
    names = [row.name for row in sheet.ammo]
    assert any("+1" in n for n in names)
    assert sheet.ammo[0].count == 20
    # the bow launcher offers the loaded stack as an option
    opts = sheet.ammo_load_options["short_bow"]
    assert any(o.instance_id == "a" for o in opts)
```

- [ ] **Step 3: Run, verify failure** → `CharacterSheet` has no `ammo`/`ammo_load_options`.

- [ ] **Step 4: Add view models + populate them**

In `aose/sheet/view.py`, define small rendering models near the others:
```python
class AmmoRow(BaseModel):
    instance_id: str
    name: str
    count: int
    magic: bool


class AmmoOption(BaseModel):
    instance_id: str
    name: str
    count: int
```
Add to `CharacterSheet`:
```python
    ammo: list[AmmoRow] = Field(default_factory=list)
    ammo_load_options: dict[str, list[AmmoOption]] = Field(default_factory=dict)
```
In `build_sheet`, after the attack profiles are built, populate them:
```python
    from aose.engine.ammo import accepts, resolve_ammo
    from aose.models import Ammunition, Weapon

    ammo_rows = []
    for s in spec.ammo:
        view = resolve_ammo(s, data)
        ammo_rows.append(AmmoRow(instance_id=s.instance_id, name=view["name"],
                                 count=s.count, magic=s.enchantment_id is not None))

    load_options: dict[str, list[AmmoOption]] = {}
    for prof in attacks:                      # `attacks` = the attack_profiles list
        weapon = data.items.get(prof.weapon_id)
        # resolved enchanted launchers won't be in data.items; recover via base.
        if weapon is None or not isinstance(weapon, Weapon) or not weapon.accepts_ammo:
            # enchanted launcher: look up its base for accepts_ammo
            continue
        opts = []
        for s in spec.ammo:
            base = data.items.get(s.base_id)
            if isinstance(base, Ammunition) and accepts(weapon, base):
                v = resolve_ammo(s, data)
                opts.append(AmmoOption(instance_id=s.instance_id, name=v["name"],
                                       count=s.count))
        if opts:
            load_options[prof.weapon_id] = opts
```
Set them on the returned `CharacterSheet(... ammo=ammo_rows, ammo_load_options=load_options ...)`.
> Use the actual local variable name for the profiles list (read it in Step 1). If enchanted launchers also need load options, resolve their base via `prof.weapon_id` → strip the `ench:` prefix is not reliable; instead iterate `enchant.equipped_enchanted(spec, data, "weapon")` to map each resolved `.id` to its `accepts_ammo`. Keep the mundane path above; add the enchanted path only if a test requires it (YAGNI).

- [ ] **Step 5: Run the test, verify pass.**
- [ ] **Step 6: Full suite** → green.
- [ ] **Step 7: Commit**
```powershell
git add aose/sheet/view.py tests/test_ammunition.py
git commit -m "feat(sheet): ammunition section + per-launcher load options in build_sheet"
```

---

## Task 7: Sheet routes + template — buy/add/adjust/remove/load/unload

**Files:**
- Modify: `aose/web/routes.py`
- Modify: `aose/web/templates/_equipment_ui.html` (and/or `sheet.html`)
- Test: `tests/test_ammunition.py`

- [ ] **Step 1: Write the failing tests** (FastAPI `TestClient` round-trips, mirroring `tests/test_enchantments.py`'s `_make_client`/`_seed` style — read that file for the exact fixture)

Append to `tests/test_ammunition.py`:
```python
def _client(tmp_path):
    # Mirror tests/test_enchantments.py: build the app with a temp characters dir,
    # create one fighter character via the wizard or a saved fixture, return
    # (client, character_id, characters_dir). Reuse that file's helper verbatim.
    from tests.helpers import make_sheet_client   # if a shared helper exists
    return make_sheet_client(tmp_path)


def test_buy_then_load_then_adjust(tmp_path):
    client, cid, cdir = _client(tmp_path)
    from aose.characters.storage import load_character
    # give gold + a bow
    client.post(f"/character/{cid}/gold", data={"amount": 50})
    client.post(f"/character/{cid}/equipment/add", data={"item_id": "short_bow"})
    client.post(f"/character/{cid}/equipment/equip", data={"item_id": "short_bow"})
    # buy a quiver → ammo stack of 20, gold -5
    client.post(f"/character/{cid}/equipment/buy", data={"item_id": "arrow"})
    spec = load_character(cid, cdir)
    assert spec.ammo[0].count == 20 and spec.ammo[0].base_id == "arrow"
    iid = spec.ammo[0].instance_id
    # load + adjust
    client.post(f"/character/{cid}/ammo/load",
                data={"weapon_key": "short_bow", "instance_id": iid})
    client.post(f"/character/{cid}/ammo/adjust",
                data={"instance_id": iid, "delta": -1})
    spec = load_character(cid, cdir)
    assert spec.loaded_ammo["short_bow"] == iid and spec.ammo[0].count == 19


def test_add_magic_ammo_and_remove(tmp_path):
    client, cid, cdir = _client(tmp_path)
    from aose.characters.storage import load_character
    client.post(f"/character/{cid}/ammo/add",
                data={"base_id": "arrow", "enchantment_id": "arrows_plus_1"})
    spec = load_character(cid, cdir)
    assert spec.ammo[0].enchantment_id == "arrows_plus_1"
    iid = spec.ammo[0].instance_id
    client.post(f"/character/{cid}/ammo/remove", data={"instance_id": iid})
    spec = load_character(cid, cdir)
    assert spec.ammo == []
```
> If `tests/` has no shared sheet-client helper, copy `_make_client`/`_seed` from `tests/test_enchantments.py` into this file (don't invent `tests.helpers`).

- [ ] **Step 2: Run, verify failure** → 404/405 on `/ammo/...`.

- [ ] **Step 3: Route mundane ammo purchases to `buy_ammo`**

In `aose/web/routes.py`, import the engine:
```python
from aose.engine.ammo import (
    add_free_ammo as _add_free_ammo,
    adjust_count as _adjust_ammo,
    buy_ammo as _buy_ammo,
    load as _load_ammo,
    remove_ammo as _remove_ammo,
    unload as _unload_ammo,
    InsufficientGold as _AmmoInsufficientGold,
    IncompatibleAmmo as _IncompatibleAmmo,
    UnknownAmmo as _UnknownAmmo,
)
from aose.models import Ammunition
```
In `equipment_buy`, special-case `Ammunition` (alongside the existing `Container` branch):
```python
        if isinstance(item, Ammunition):
            spec.ammo, spec.gold = _buy_ammo(spec.ammo, spec.gold, item_id, game_data)
        elif isinstance(item, Container):
            ...
```
In `equipment_add`, special-case `Ammunition` (mundane add gives a bundle):
```python
        if isinstance(item, Ammunition):
            spec.ammo = _add_free_ammo(spec.ammo, item_id, None, game_data)
        elif needs_instance(item):
            ...
```

- [ ] **Step 4: Add the six ammo routes**

Append to `aose/web/routes.py` (after the enchanted routes):
```python
@router.post("/character/{character_id}/ammo/add")
async def ammo_add(request: Request, character_id: str,
                   base_id: str = Form(...), enchantment_id: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.ammo = _add_free_ammo(spec.ammo, base_id,
                                   enchantment_id or None, request.app.state.game_data)
    except (_UnknownAmmo, _IncompatibleAmmo, ValueError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/ammo/adjust")
async def ammo_adjust(request: Request, character_id: str,
                      instance_id: str = Form(...), delta: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.ammo = _adjust_ammo(spec.ammo, instance_id, delta)
    except _UnknownAmmo as e:
        raise HTTPException(400, str(e))
    # drop any load pointing at a now-removed stack
    live = {s.instance_id for s in spec.ammo}
    spec.loaded_ammo = {k: v for k, v in spec.loaded_ammo.items() if v in live}
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/ammo/remove")
async def ammo_remove(request: Request, character_id: str,
                      instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.ammo = _remove_ammo(spec.ammo, instance_id)
    except _UnknownAmmo as e:
        raise HTTPException(400, str(e))
    live = {s.instance_id for s in spec.ammo}
    spec.loaded_ammo = {k: v for k, v in spec.loaded_ammo.items() if v in live}
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/ammo/load")
async def ammo_load(request: Request, character_id: str,
                    weapon_key: str = Form(...), instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    spec.loaded_ammo = _load_ammo(spec.loaded_ammo, weapon_key, instance_id)
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/ammo/unload")
async def ammo_unload(request: Request, character_id: str,
                      weapon_key: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    spec.loaded_ammo = _unload_ammo(spec.loaded_ammo, weapon_key)
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```
(Mundane buy uses the existing `/equipment/buy`; the `ammo/add` route is for GM-granted magic ammo and takes an optional `enchantment_id`.)

- [ ] **Step 5: Template — render the ammo section**

In `aose/web/templates/_equipment_ui.html` (the shared partial), add an **Ammunition** block that:
- lists `sheet.ammo` rows: name, count, `+`/`−` buttons posting to `{{ target_url_prefix-or-/character/{id} }}/ammo/adjust` with `delta` 1/-1, and a remove button to `/ammo/remove`;
- for each attack row that is a launcher, shows the loaded ammo name or an **"Unloaded"** badge (`{% if profile.unloaded %}`), plus a `<select>` of `sheet.ammo_load_options[profile.weapon_id]` submitting to `/ammo/load` (`weapon_key=profile.weapon_id`) and an Unload button to `/ammo/unload`.

Follow the existing magic-items/enchanted blocks in this partial for markup, the `target_url_prefix` variable (sheet vs wizard), and button styling. The attack table lives in `sheet.html`; add the Unloaded badge / loaded-ammo name to the launcher row there using `profile.unloaded` and `profile.loaded_ammo_name`.

- [ ] **Step 6: Run the route tests, verify pass.**
- [ ] **Step 7: Full suite** → green.
- [ ] **Step 8: Commit**
```powershell
git add aose/web/routes.py aose/web/templates tests/test_ammunition.py
git commit -m "feat(web): sheet ammo routes + ammunition UI (buy/add/adjust/load/unload)"
```

---

## Task 8: Wizard integration — buy/load ammo + carry into the finalized character

**Files:**
- Modify: `aose/web/wizard.py`
- Test: `tests/test_ammunition.py`

The wizard equipment step is mundane-only: buy ammo (via the existing wizard `/equipment/buy`, special-cased) and load it. Magic ammo stays sheet-only. Ammo + loaded_ammo must round-trip from the draft into the finalized `CharacterSpec`.

- [ ] **Step 1: Write the failing test**
```python
def test_wizard_ammo_carries_into_character(tmp_path):
    # Build a draft through to equipment, buy a bow + quiver, load it, finalize,
    # assert the saved CharacterSpec has the ammo stack and loaded_ammo.
    # Reuse the wizard-driving helper from tests/test_enchantments.py or
    # tests/test_wizard*.py (read those for the exact step-posting helper).
    ...
```
> Read `tests/` for an existing wizard-completion helper (e.g. in `tests/test_wizard_equipment.py` or similar) and model this test on it rather than re-deriving the full step sequence.

- [ ] **Step 2: Run, verify failure.**

- [ ] **Step 3: Add a `_draft_ammo` helper + special-case the wizard buy**

In `aose/web/wizard.py`, near `_draft_magic`:
```python
def _draft_ammo(draft: dict[str, Any]) -> list[AmmoStack]:
    return [AmmoStack.model_validate(a) for a in draft.get("ammo", [])]
```
(import `AmmoStack` and `Ammunition` at the top). In `post_equipment_buy`, special-case ammo before the generic shop buy:
```python
        if isinstance(item, Ammunition):
            ammo, new_gold = buy_ammo(_draft_ammo(draft), draft.get("gold", 0),
                                      item_id, data)
            draft["ammo"] = [a.model_dump() for a in ammo]
            draft["gold"] = new_gold
        elif isinstance(item, Container):
            ...
```
(import `buy_ammo`, and `load`/`adjust_count`/`remove_ammo`/`unload` as needed.)

- [ ] **Step 4: Add wizard ammo routes** (`/wizard/{draft_id}/ammo/{adjust,remove,load,unload}`) mirroring the sheet routes but mutating the draft dict (model_dump round-trip) and redirecting to `/wizard/{draft_id}/equipment`. Magic `/ammo/add` is **not** added to the wizard (mundane-only). Pattern after the existing wizard container routes (`post_equipment_stash_container` etc.).

- [ ] **Step 5: Carry ammo into the finalized spec**

In `_draft_to_spec`, add to the `CharacterSpec(...)` construction:
```python
        ammo=[AmmoStack.model_validate(a) for a in draft.get("ammo", [])],
        loaded_ammo=dict(draft.get("loaded_ammo", {})),
```

- [ ] **Step 6: Render the ammo section in the wizard**

In `_equipment_context` (wizard), pass the ammo view so the shared partial renders. Reuse the sheet's view builders or compute `ammo`/`ammo_load_options` from the draft the same way `build_sheet` does (extract the Task-6 population into a small shared helper in `aose/sheet/view.py`, e.g. `ammo_view(spec, data) -> (rows, options)`, and call it from both `build_sheet` and `_equipment_context`). Magic-acquisition stays off (`magic_acquisition=False`).

- [ ] **Step 7: Run the wizard test, verify pass.**
- [ ] **Step 8: Full suite** → green.
- [ ] **Step 9: Commit**
```powershell
git add aose/web/wizard.py aose/sheet/view.py tests/test_ammunition.py
git commit -m "feat(wizard): buy/load mundane ammo; carry ammo into finalized character"
```

---

## Task 9: End-to-end verification + docs

**Files:**
- Test: `tests/test_ammunition.py`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add the spec's verification spot-checks** (one combined test)
```python
def test_spec_verification_spotchecks():
    d = GameData.load(DATA_DIR)
    from aose.engine.ammo import buy_ammo, accepts
    from aose.engine.enchant import is_compatible
    # silver_arrow + arrow_slaying compatible
    assert is_compatible(d.items["silver_arrow"], d.enchantments["arrow_slaying"])
    # buying two quivers combines to 40 for 10 gp
    stacks, gold = buy_ammo([], 100, "arrow", d)
    stacks, gold = buy_ammo(stacks, gold, "arrow", d)
    assert len(stacks) == 1 and stacks[0].count == 40 and gold == 90
    # a launcher accepts its ammo
    assert accepts(d.items["crossbow"], d.items["crossbow_bolt"])
```

- [ ] **Step 2: Run the whole ammo file + full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all green (≈ 834 baseline + the ammo tests). Ignore the `pytest-current` PermissionError.

- [ ] **Step 3: Manual smoke (optional but recommended)**

Launch the app and confirm: buy a quiver in the shop, load it into an equipped bow, the bow's attack line shows the loaded ammo (and the +N when magic ammo is loaded), and an unloaded bow shows the **Unloaded** badge.
```powershell
.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload
```

- [ ] **Step 4: Update `CLAUDE.md` "Current state"**

Add a bullet describing the ammunition model (new `Ammunition` item variant, `AmmoStack`/`loaded_ammo` on `CharacterSpec`, `Enchantment kind: ammunition`, `aose/engine/ammo.py`, launcher `accepts_ammo`, zero ammo encumbrance, magic-ammo bonus conferral in `attacks.py`), mirroring the existing enchantment bullet. Link the spec/plan.

- [ ] **Step 5: Commit**
```powershell
git add tests/test_ammunition.py CLAUDE.md
git commit -m "test(ammo): end-to-end verification; doc ammunition feature"
```

---

## Self-Review (completed by plan author)

**Spec coverage:** purchasable mundane catalog (Task 5 data + Task 7/8 buy) ✓; per-character stacks with counts + combine + manual adjust (Tasks 1, 3, 7) ✓; loading + Unloaded flag (Tasks 3, 4, 6, 7) ✓; magic ammo via enchantment composition `kind: ammunition` (Tasks 1, 2, 5) ✓; additive bonus conferral, +1 bow + +1 arrow = +2 (Task 4 with explicit test) ✓; silver_arrow + arrow_slaying (Tasks 2, 9) ✓; zero ammo encumbrance (Task 1 default `weight_cn 0`; ammo lives in `spec.ammo`, never in `inventory`, so `encumbrance.py` never sees it) ✓; wizard buy/load + finalize round-trip (Task 8) ✓; sheet UI + routes (Tasks 6, 7) ✓; no migration (stated) ✓.

**Non-goals honoured:** no rate-of-fire, no auto-decrement (only manual `adjust`), no ammo recovery, silver stays narrative, whole-bundle purchases only.

**Placeholder scan:** the two test bodies that say "reuse the existing helper" (route/wizard clients) point at concrete existing files (`tests/test_enchantments.py`) to copy from rather than inventing an API — this is deliberate (the harness's exact client fixture must be read at execution time), not a hidden TODO. All engine/model/data/route code is given in full.

**Type consistency:** `AmmoStack{instance_id,base_id,enchantment_id,count}`, `loaded_ammo: dict[str,str]`, `accepts_ammo: list[str]`, and the `ammo.py` function names (`accepts`, `buy_ammo`, `add_free_ammo`, `adjust_count`, `remove_ammo`, `load`, `unload`, `loaded_stack`, `loaded_bonus`, `is_unloaded`, `resolve_ammo`) are used identically across Tasks 1–9. `weapon_key == weapon.id == AttackProfile.weapon_id` is consistent end to end. `AttackProfile` gains `unloaded`/`loaded_ammo_name` (Task 4) and both are read by the view (Task 6) and templates (Task 7).
```
