# Feature-granted modifiers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let classes and races grant mechanical bonuses (AC / saves / attack, possibly conditional or scaled by level/ability) through YAML data, feeding the same `Modifier` aggregation magic items already feed — with no class/race id hardcoded in any engine.

**Architecture:** A new `GrantedModifier` declaration on `ClassFeature`/`RaceFeature` is resolved by `aose/engine/features.py::feature_modifiers` into concrete `Modifier`s (carrying `condition` + `source`); `all_modifiers = active_modifiers (magic) + feature_modifiers (class/race)` becomes the single list `armor_class`, `saves`, and `attacks` consume. Conditions are honoured at each consumption site; unrecognised conditions are inert-but-carried (never inflate a headline number). The bespoke kineticist AC column is retired onto this path.

**Tech Stack:** Python 3.14, Pydantic v2, PyYAML, pytest. Windows/PowerShell — run Python via `.venv\Scripts\python.exe`.

**Spec:** `docs/superpowers/specs/2026-06-06-feature-granted-modifiers-design.md`

**Test command (used throughout):**
```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```
(The trailing `PermissionError` on `pytest-current` is a known Windows/pytest-9 quirk — ignore it.)

**Key facts established during planning:**
- Only `data/classes/kineticist.yaml` uses the `armor_class` progression column; only `aose/engine/armor_class.py:46` reads `ClassLevelData.armor_class`.
- `wizard.py:794` sets `race_id = cls.race_locked` for race-as-class, so a classic demihuman (e.g. halfling-as-class) **always carries its `Race`** and gets the race features. Therefore **racial grants live on the `Race` only, never on the race-locked `CharClass`'s duplicate feature** — this avoids double-application and satisfies the "halfling class missile bonus" audit item via the race.
- App save category keys: `death` (= death/poison), `wands` (= magic wands/rods/staves), `paralysis`, `breath`, `spells`.
- `effective_abilities` (magic.py) applies magic + temp ability mods only; racial ability mods are baked into `spec.abilities` at creation, so tests set abilities directly.
- Ranged weapon id for tests: `short_bow`. Armour id for tests: `chain_mail`.

---

## Task 1: Data models

**Files:**
- Modify: `aose/models/modifier.py`
- Modify: `aose/models/character_class.py` (ClassFeature)
- Modify: `aose/models/race.py` (RaceFeature)
- Modify: `aose/models/__init__.py`
- Test: `tests/test_feature_modifiers.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_feature_modifiers.py`:

```python
"""Feature-granted modifiers: data-driven class/race bonuses."""
from pathlib import Path

import pytest

from aose.data.loader import GameData

DATA = GameData.load(Path(__file__).parent.parent / "data")


# ── Task 1: models ──────────────────────────────────────────────────────────

def test_granted_modifier_flat_value_ok():
    from aose.models import GrantedModifier
    g = GrantedModifier(target="ac", op="add", value=1)
    assert g.value == 1 and g.scale is None


def test_granted_modifier_scaled_ok():
    from aose.models import GrantedModifier, Scaling
    g = GrantedModifier(target="save:spells", op="add",
                        scale=Scaling(by="ability:CON", table={7: 2, 11: 3}))
    assert g.scale.by == "ability:CON"


def test_granted_modifier_rejects_both_value_and_scale():
    from aose.models import GrantedModifier, Scaling
    with pytest.raises(ValueError):
        GrantedModifier(target="ac", op="add", value=1,
                        scale=Scaling(by="level", table={1: 1}))


def test_granted_modifier_rejects_neither():
    from aose.models import GrantedModifier
    with pytest.raises(ValueError):
        GrantedModifier(target="ac", op="add")


def test_modifier_condition_and_source_default():
    from aose.models import Modifier
    m = Modifier(target="ac", op="add", value=1)
    assert m.condition is None and m.source == ""


def test_features_accept_granted_modifiers():
    from aose.models import ClassFeature, GrantedModifier, RaceFeature
    cf = ClassFeature(id="x", name="X", text="",
                      granted_modifiers=[GrantedModifier(target="ac", op="add", value=1)])
    rf = RaceFeature(id="y", name="Y", text="",
                     granted_modifiers=[GrantedModifier(target="attack", op="add", value=1)])
    assert cf.granted_modifiers[0].target == "ac"
    assert rf.granted_modifiers[0].target == "attack"


def test_features_default_no_granted_modifiers():
    from aose.models import ClassFeature, RaceFeature
    assert ClassFeature(id="x", name="X", text="").granted_modifiers == []
    assert RaceFeature(id="y", name="Y", text="").granted_modifiers == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -q`
Expected: FAIL — `ImportError: cannot import name 'GrantedModifier'`.

- [ ] **Step 3: Add `Scaling` + `GrantedModifier` and extend `Modifier`**

In `aose/models/modifier.py`, change the imports line and append the new models. Full new file content:

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class Modifier(BaseModel):
    """A single mechanical effect from a magic item OR a class/race feature.

    Shared by catalog ``MagicItem.modifiers``, per-instance
    ``MagicItemInstance.extra_modifiers``, and the resolved output of
    ``aose/engine/features.py``.  Lives in its own module so ``item.py``,
    ``character.py``, ``race.py``, and ``character_class.py`` can all import it
    without coupling.

    ``op`` semantics (applied per target): all ``set`` (last wins) → all ``add``
    (summed) → ``set_min`` (``max(result, value)``) → ``set_max``
    (``min(result, value)``).  ``add`` always means *better for the character*
    (the lower-is-better targets negate it at their call site); ``set`` and the
    bounds use literal game-system numbers.

    ``target`` grammar (unknown targets are ignored — forward-compatible):
    ``ability:STR``…``ability:CHA``, ``ac``, ``save:all``,
    ``save:death|wands|paralysis|breath|spells``, ``attack``, ``damage``,
    ``carry_capacity``, ``thac0``.

    ``condition`` is open-ended free text (``None`` = unconditional).  Each
    derivation recognises only the conditions it can evaluate in context
    (``unarmored`` for AC; ``ranged``/``melee`` for attack/damage); any other
    condition is *situational* — carried for display but never folded into a
    headline number.  ``source`` is a human label (e.g. a feature name) for the
    future on-hover conditional-modifier view.
    """
    model_config = ConfigDict(extra="forbid")

    target: str
    op: Literal["add", "set", "set_min", "set_max"]
    value: int
    condition: str | None = None
    source: str = ""


class RolledModifier(BaseModel):
    """A modifier whose value is rolled when the item *instance* is created
    (e.g. Bracers of Armour: AC 8 − 1d4).  At acquisition,
    ``new_magic_instance`` rolls ``dice`` and appends a concrete
    ``Modifier{target, op, value}`` to the instance's ``extra_modifiers``.
    """
    model_config = ConfigDict(extra="forbid")

    target: str
    op: Literal["add", "set", "set_min", "set_max"]
    dice: str


class Scaling(BaseModel):
    """Table-driven value for a ``GrantedModifier``.

    ``by`` selects the input: ``"level"`` (the granting class's level; invalid
    on a race feature) or ``"ability:STR"``…``"ability:CHA"`` (the effective,
    magic-adjusted score).  ``table`` is a *banded* lookup: the value is the
    entry for the greatest key ≤ the input; below the lowest key yields 0.
    """
    model_config = ConfigDict(extra="forbid")

    by: str
    table: dict[int, int]


class GrantedModifier(BaseModel):
    """A modifier a class/race *feature* grants, declared in YAML and resolved
    to a concrete :class:`Modifier` by ``aose/engine/features.py``.  Exactly one
    of ``value`` (flat) or ``scale`` (table-driven) must be set.
    """
    model_config = ConfigDict(extra="forbid")

    target: str
    op: Literal["add", "set", "set_min", "set_max"]
    condition: str | None = None
    value: int | None = None
    scale: Scaling | None = None

    @model_validator(mode="after")
    def _exactly_one_value_source(self):
        if (self.value is None) == (self.scale is None):
            raise ValueError("GrantedModifier requires exactly one of value or scale")
        return self
```

- [ ] **Step 4: Add `granted_modifiers` to `ClassFeature`**

In `aose/models/character_class.py`, add the import near the top (after the existing `from .ability import Ability`):

```python
from .modifier import GrantedModifier
```

Then add the field to `ClassFeature` (after `gained_at_level`):

```python
class ClassFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    text: str
    gained_at_level: int = 1
    mechanical: dict[str, Any] | None = None
    granted_modifiers: list[GrantedModifier] = Field(default_factory=list)
```

- [ ] **Step 5: Add `granted_modifiers` to `RaceFeature`**

In `aose/models/race.py`, add the import (after `from .ability import Ability`):

```python
from .modifier import GrantedModifier
```

Then add the field to `RaceFeature`:

```python
class RaceFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    text: str
    mechanical: dict[str, Any] | None = None
    granted_modifiers: list[GrantedModifier] = Field(default_factory=list)
```

- [ ] **Step 6: Export the new models**

In `aose/models/__init__.py`, change the modifier import line to:

```python
from .modifier import GrantedModifier, Modifier, RolledModifier, Scaling
```

and add `"GrantedModifier"` and `"Scaling"` to `__all__` (next to `"Modifier"`).

- [ ] **Step 7: Run the tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -q`
Expected: PASS (7 passed).

- [ ] **Step 8: Run the full suite (no regressions)**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: same pass/fail baseline as before (the 2 pre-existing breadcrumb-label failures in `test_wizard_class_setup` / `test_wizard_identity` are unrelated and expected).

- [ ] **Step 9: Commit**

```powershell
git add aose/models/ tests/test_feature_modifiers.py
git commit -m "feat(models): GrantedModifier + Scaling; Modifier condition/source"
```

---

## Task 2: Resolver engine (`features.py`)

**Files:**
- Create: `aose/engine/features.py`
- Test: `tests/test_feature_modifiers.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_feature_modifiers.py`:

```python
# ── Task 2: resolver ────────────────────────────────────────────────────────

def test_band_lookup():
    from aose.engine.features import _band_lookup
    t = {7: 2, 11: 3, 15: 4, 18: 5}
    assert _band_lookup(t, 6) == 0      # below lowest band
    assert _band_lookup(t, 7) == 2
    assert _band_lookup(t, 10) == 2
    assert _band_lookup(t, 11) == 3
    assert _band_lookup(t, 18) == 5
    assert _band_lookup(t, 20) == 5     # above highest band


def test_resolve_value_flat():
    from aose.engine.features import resolve_value
    from aose.models import GrantedModifier
    g = GrantedModifier(target="attack", op="add", value=1)
    assert resolve_value(g, level=3, eff={}) == 1


def test_resolve_value_by_level():
    from aose.engine.features import resolve_value
    from aose.models import GrantedModifier, Scaling
    g = GrantedModifier(target="ac", op="add",
                        scale=Scaling(by="level", table={4: 1, 6: 2}))
    assert resolve_value(g, level=5, eff={}) == 1
    assert resolve_value(g, level=6, eff={}) == 2


def test_resolve_value_by_ability_uses_effective():
    from aose.engine.features import resolve_value
    from aose.models import Ability, GrantedModifier, Scaling
    g = GrantedModifier(target="save:spells", op="add",
                        scale=Scaling(by="ability:CON", table={7: 2, 11: 3}))
    assert resolve_value(g, level=None, eff={Ability.CON: 13}) == 3


def test_resolve_value_level_scale_on_race_feature_raises():
    from aose.engine.features import resolve_value
    from aose.models import GrantedModifier, Scaling
    g = GrantedModifier(target="ac", op="add",
                        scale=Scaling(by="level", table={1: 1}))
    with pytest.raises(ValueError):
        resolve_value(g, level=None, eff={})


def test_feature_modifiers_empty_for_plain_character():
    # Human fighter has no granted modifiers anywhere → all_modifiers == magic only.
    from aose.engine.features import all_modifiers, feature_modifiers
    from aose.engine.magic import active_modifiers
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="T", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
    )
    assert feature_modifiers(spec, DATA) == []
    assert all_modifiers(spec, DATA) == active_modifiers(spec, DATA)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aose.engine.features'`.

- [ ] **Step 3: Create the resolver**

Create `aose/engine/features.py`:

```python
"""Feature-granted modifiers — resolves class/race feature grants into the same
``Modifier`` objects magic items emit.

Cycle-free: imports only models, the data loader, and ``magic`` (for
``active_modifiers`` + ``effective_abilities``).  The derivation modules
(``armor_class``, ``saves``, ``attacks``) import ``all_modifiers`` *from here*;
this module never imports them.
"""
from __future__ import annotations

from aose.data.loader import GameData
from aose.models import Ability, CharacterSpec, Modifier
from aose.engine.magic import active_modifiers, effective_abilities


def _band_lookup(table: dict[int, int], key: int) -> int:
    """Value for the greatest table key ≤ ``key``; 0 below the lowest band."""
    candidates = [k for k in table if k <= key]
    return table[max(candidates)] if candidates else 0


def resolve_value(g, *, level: int | None, eff: dict) -> int:
    """Concrete value for a ``GrantedModifier`` given the granting class's
    ``level`` (None on a race feature) and effective ability scores ``eff``."""
    if g.scale is None:
        return g.value
    by = g.scale.by
    if by == "level":
        if level is None:
            raise ValueError("level scaling is not valid on a race feature")
        return _band_lookup(g.scale.table, level)
    if by.startswith("ability:"):
        ability = Ability(by.split(":", 1)[1])
        return _band_lookup(g.scale.table, eff[ability])
    raise ValueError(f"Unknown scale.by {by!r}")


def feature_modifiers(spec: CharacterSpec, data: GameData) -> list[Modifier]:
    """Concrete ``Modifier``s from every reached class feature (per the class's
    level) and every race feature.  Each carries the grant's ``condition`` and
    the feature's name as ``source``."""
    eff = effective_abilities(spec, data)
    out: list[Modifier] = []
    for entry in spec.classes:
        cls = data.classes.get(entry.class_id)
        if cls is None:
            continue
        for feat in cls.features:
            if feat.gained_at_level > entry.level:
                continue
            for g in feat.granted_modifiers:
                out.append(Modifier(
                    target=g.target, op=g.op,
                    value=resolve_value(g, level=entry.level, eff=eff),
                    condition=g.condition, source=feat.name,
                ))
    race = data.races.get(spec.race_id)
    if race is not None:
        for feat in race.features:
            for g in feat.granted_modifiers:
                out.append(Modifier(
                    target=g.target, op=g.op,
                    value=resolve_value(g, level=None, eff=eff),
                    condition=g.condition, source=feat.name,
                ))
    return out


def all_modifiers(spec: CharacterSpec, data: GameData) -> list[Modifier]:
    """The single modifier list every derivation consumes: equipped magic items
    plus class/race feature grants."""
    return active_modifiers(spec, data) + feature_modifiers(spec, data)
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -q`
Expected: PASS (all Task 1 + Task 2 tests).

- [ ] **Step 5: Commit**

```powershell
git add aose/engine/features.py tests/test_feature_modifiers.py
git commit -m "feat(engine): feature_modifiers resolver + all_modifiers merge"
```

---

## Task 3: Wire consumers to `all_modifiers` + condition handling

This task makes `armor_class`, `saves`, and `attacks` consume `all_modifiers`, adds condition handling, and moves `ac set` outside the worn-armour gate. **Behaviour is unchanged for all existing data** (no feature has grants yet) **except** Bracers-of-Armour-style `ac set` items now also show in the unarmoured display (the intended, more-correct change). The legacy kineticist AC column block is **kept** here and retired in Task 7.

**Files:**
- Modify: `aose/engine/armor_class.py`
- Modify: `aose/engine/saves.py`
- Modify: `aose/engine/attacks.py`
- Test: `tests/test_feature_modifiers.py` (append)

- [ ] **Step 1: Write the failing test (bracers unarmoured display)**

Append to `tests/test_feature_modifiers.py`:

```python
# ── Task 3: consumer wiring + conditions ────────────────────────────────────

def test_ac_set_modifier_shows_in_unarmored_display():
    # An `ac set 6` magic item now reflects in the unarmoured value (was ignored
    # when ac-set lived inside the worn-armour gate). DEX 10 -> +0 -> descending 6.
    from aose.engine.armor_class import unarmored_ac
    from aose.models import CharacterSpec, ClassEntry, MagicItemInstance, Modifier
    spec = CharacterSpec(
        name="T", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        magic_items=[MagicItemInstance(
            instance_id="i1", catalog_id="bracers_of_armour", equipped=True,
            extra_modifiers=[Modifier(target="ac", op="set", value=6)],
        )],
    )
    assert unarmored_ac(spec, DATA) == (6, 13)
```

(Catalog id `bracers_of_armour` must exist in `data/equipment/magic_items.yaml`; if the exact id differs, use any real equippable magic item id — the `extra_modifiers` drive the assertion, not the catalog.)

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py::test_ac_set_modifier_shows_in_unarmored_display -q`
Expected: FAIL — returns `(9, 10)` (ac set still inside the gate).

- [ ] **Step 3: Rewrite `armor_class.py`**

Replace the whole file `aose/engine/armor_class.py` with:

```python
from aose.data.loader import GameData
from aose.models import Ability, Armor, CharacterSpec

from .ability_mods import ability_modifier
from .enchant import equipped_enchanted
from .features import all_modifiers
from .magic import effective_abilities

UNARMORED_AC_DESCENDING = 9


def _has_worn_armor(spec: CharacterSpec, data: GameData) -> bool:
    """True when a body-armour item (not a shield) is equipped — mundane or
    enchanted.  Used to drop ``unarmored``-conditioned AC bonuses."""
    armor_id = spec.equipped.get("armor")
    item = data.items.get(armor_id) if armor_id else None
    if isinstance(item, Armor) and not item.is_shield:
        return True
    return any(True for _ in equipped_enchanted(spec, data, "armor"))


def armor_class(spec: CharacterSpec, data: GameData, *,
                use_armor: bool = True, use_shield: bool = True) -> tuple[int, int]:
    """Return (descending_ac, ascending_ac). Sheet renders one based on ruleset.

    use_armor / use_shield = False computes the unarmoured value (DEX + magic/
    feature AC mods only), used for the sheet's armoured-vs-unarmoured display.
    """
    eff = effective_abilities(spec, data)
    dex_mod = ability_modifier(eff[Ability.DEX])
    mods = all_modifiers(spec, data)

    base = UNARMORED_AC_DESCENDING
    if use_armor:
        armor_id = spec.equipped.get("armor")
        if armor_id and armor_id in data.items:
            item = data.items[armor_id]
            if isinstance(item, Armor) and not item.is_shield:
                base = item.ac_descending - item.magic_bonus
        # Enchanted armour: best-AC-wins (min descending) over mundane equipped.
        for resolved in equipped_enchanted(spec, data, "armor"):
            base = min(base, resolved.ac_descending - resolved.magic_bonus)

    # `ac set N` from ANY source (class/race feature OR magic item) is a literal
    # descending base candidate; best (lowest) wins. Evaluated OUTSIDE the
    # use_armor gate so class-granted AC (e.g. Kineticist) and bracers-style
    # items show in the unarmoured display and still beat worn armour.
    for m in mods:
        if m.target == "ac" and m.op == "set":
            base = min(base, m.value)

    # Legacy class-granted level AC column. Retired in the kineticist-migration
    # task once the data moves to a granted `ac set` modifier; kept here so this
    # task is behaviour-preserving for the kineticist.
    class_acs = []
    for entry in spec.classes:
        cls_obj = data.classes.get(entry.class_id)
        if cls_obj is not None and entry.level in cls_obj.progression:
            col = cls_obj.progression[entry.level].armor_class
            if col is not None:
                class_acs.append(col)
    if class_acs:
        base = min(base, min(class_acs))

    shield_bonus = 0
    if use_shield:
        shield_id = spec.equipped.get("shield")
        if shield_id and shield_id in data.items:
            item = data.items[shield_id]
            if isinstance(item, Armor) and item.is_shield:
                shield_bonus = item.ac_bonus + item.magic_bonus
        for resolved in equipped_enchanted(spec, data, "shield"):
            shield_bonus = max(shield_bonus, resolved.ac_bonus + resolved.magic_bonus)

    armor_worn = use_armor and _has_worn_armor(spec, data)

    def ac_add_applies(m) -> bool:
        if m.condition is None:
            return True
        if m.condition == "unarmored":
            return not armor_worn
        return False  # unrecognised condition: situational, never in the headline

    ac_add = sum(m.value for m in mods
                 if m.target == "ac" and m.op == "add" and ac_add_applies(m))
    descending = base - dex_mod - shield_bonus - ac_add
    ascending = 19 - descending
    return descending, ascending


def unarmored_ac(spec: CharacterSpec, data: GameData) -> tuple[int, int]:
    """AC with worn armour & shield ignored (DEX + magic/feature AC mods kept)."""
    return armor_class(spec, data, use_armor=False, use_shield=False)
```

- [ ] **Step 4: Switch `saves.py` to `all_modifiers` + condition filter**

In `aose/engine/saves.py`, change the import:

```python
from .features import all_modifiers
```
(remove `from .magic import active_modifiers`).

Then in `saving_throws`, change the modifiers line from `mods = active_modifiers(spec, data)` to:

```python
    # Saves recognise no V1 conditions; situational (conditioned) save mods are
    # excluded from the number until a derivation learns to evaluate them.
    mods = [m for m in all_modifiers(spec, data) if m.condition is None]
```

(Leave `_level_data` and everything else unchanged — `attack_bonus.py` still imports `_level_data` from here.)

- [ ] **Step 5: Switch `attacks.py` to `all_modifiers` + per-weapon conditions**

In `aose/engine/attacks.py`:

(a) Change the imports:
```python
from aose.engine.features import all_modifiers
from aose.engine.magic import effective_abilities
```
(remove `active_modifiers` from the magic import.)

(b) Replace the `_global_atk_dmg` function with:
```python
def _atk_dmg(mods, *, melee: bool, ranged: bool) -> tuple[int, int]:
    """Sum global ``attack``/``damage`` add-modifiers that apply to a weapon of
    this kind.  Unconditional always; ``ranged``/``melee`` gated by the weapon;
    any other condition is situational and excluded from the number."""
    def applies(m) -> bool:
        if m.condition is None:
            return True
        if m.condition == "ranged":
            return ranged
        if m.condition == "melee":
            return melee
        return False
    atk = sum(m.value for m in mods if m.target == "attack" and m.op == "add" and applies(m))
    dmg = sum(m.value for m in mods if m.target == "damage" and m.op == "add" and applies(m))
    return atk, dmg
```

(c) In `attack_profiles`, replace `g_atk, g_dmg = _global_atk_dmg(spec, data)` with `mods = all_modifiers(spec, data)`, then compute per-weapon/per-unarmed bonuses. The end of the function becomes:

```python
    eff = effective_abilities(spec, data)
    base_thac0 = thac0(spec, data)
    mods = all_modifiers(spec, data)

    def _ammo_args(weapon):
        if not weapon.accepts_ammo:
            return {}
        a_bonus, a_cond = loaded_bonus(weapon.id, spec, data)
        stack = loaded_stack(weapon.id, spec, data)
        name = resolve_ammo(stack, data)["name"] if stack else None
        return {"ammo_bonus": a_bonus, "ammo_conditional": a_cond,
                "ammo_name": name,
                "unloaded": is_unloaded(weapon.id, weapon, spec, data)}

    counts = Counter(spec.equipped_weapons)
    weapon_profiles: list[AttackProfile] = []
    for weapon_id, count in counts.items():
        item = data.items.get(weapon_id)
        if not isinstance(item, Weapon):
            continue  # equipped_weapons should only contain weapons, defensive
        g_atk, g_dmg = _atk_dmg(mods, melee=item.melee, ranged=item.ranged)
        weapon_profiles.append(
            _profile_for(item, spec, data, count, eff, base_thac0, g_atk, g_dmg,
                         manageable_item_id=item.id, **_ammo_args(item))
        )
    for resolved in equipped_enchanted(spec, data, "weapon"):
        g_atk, g_dmg = _atk_dmg(mods, melee=resolved.melee, ranged=resolved.ranged)
        weapon_profiles.append(
            _profile_for(resolved, spec, data, 1, eff, base_thac0, g_atk, g_dmg,
                         **_ammo_args(resolved))
        )
    weapon_profiles.sort(key=lambda p: p.name)
    u_atk, u_dmg = _atk_dmg(mods, melee=True, ranged=False)
    return [_unarmed_profile(spec, eff, base_thac0, u_atk, u_dmg), *weapon_profiles]
```

(`_profile_for` and `_unarmed_profile` signatures are unchanged — they still take integer `g_atk`/`g_dmg`.)

- [ ] **Step 6: Run the new test + full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -q`
Expected: PASS.

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: baseline pass/fail. **If a pre-existing test asserts that a Bracers-of-Armour (or any `ac set`) item is *ignored* in the unarmoured display, update it to the new value** (ac set now applies unarmoured). Search to be sure:

Run: `.venv\Scripts\python.exe -m pytest tests/test_magic_items.py tests/test_magic_item_import.py tests/test_unarmored_ac.py -q`
Expected: PASS (after any such update).

- [ ] **Step 7: Commit**

```powershell
git add aose/engine/armor_class.py aose/engine/saves.py aose/engine/attacks.py tests/
git commit -m "feat(engine): consume all_modifiers; honour conditions; ac-set outside armour gate"
```

---

## Task 4: Barbarian Agile Fighting (level-scaled, unarmored AC)

**Files:**
- Modify: `data/classes/barbarian.yaml` (the `agile_fighting` feature)
- Test: `tests/test_feature_modifiers.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_feature_modifiers.py`:

```python
# ── Task 4: barbarian agile AC ──────────────────────────────────────────────

def _barbarian(level, *, dex=10, **kw):
    from aose.models import CharacterSpec, ClassEntry
    base = dict(
        name="B", abilities={"STR": 13, "INT": 10, "WIS": 10, "DEX": dex, "CON": 13, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="barbarian", level=level, hp_rolls=[8])],
        alignment="neutral",
    )
    base.update(kw)
    return CharacterSpec(**base)


def test_barbarian_agile_ac_unarmored_at_l4():
    from aose.engine.armor_class import armor_class
    # L4, no armour, DEX 10 -> +0: descending 9 - 1 (agile) = 8.
    assert armor_class(_barbarian(4), DATA)[0] == 8


def test_barbarian_agile_ac_absent_before_l4():
    from aose.engine.armor_class import armor_class
    # gained_at_level 4: L3 has no bonus -> descending 9.
    assert armor_class(_barbarian(3), DATA)[0] == 9


def test_barbarian_agile_ac_dropped_when_armoured():
    from aose.engine.armor_class import armor_class
    # With chain_mail worn, the unarmored-conditioned bonus drops: a barbarian
    # L4 in chainmail has the same AC as a fighter L1 in the same chainmail.
    from aose.models import CharacterSpec, ClassEntry
    barb = _barbarian(4, equipped={"armor": "chain_mail"})
    fighter = CharacterSpec(
        name="F", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral", equipped={"armor": "chain_mail"},
    )
    assert armor_class(barb, DATA)[0] == armor_class(fighter, DATA)[0]


def test_barbarian_agile_ac_shows_in_unarmored_display_even_when_armoured():
    from aose.engine.armor_class import unarmored_ac
    # The unarmoured display reflects the no-armour scenario -> bonus applies.
    barb = _barbarian(4, equipped={"armor": "chain_mail"})
    assert unarmored_ac(barb, DATA)[0] == 8
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -k barbarian -q`
Expected: FAIL (`armor_class(_barbarian(4))[0] == 9`, not 8 — no grant yet).

- [ ] **Step 3: Add the grant to the data**

In `data/classes/barbarian.yaml`, find the `agile_fighting` feature (id `agile_fighting`, `gained_at_level: 4`) and add `granted_modifiers` to it:

```yaml
- id: agile_fighting
  name: Agile Fighting
  text: |-
    Upon reaching 4th level, a barbarian gains a +1 AC bonus. This increases to +2 at 6th level, +3 at 8th level, and +4 at 10th level.
  gained_at_level: 4
  granted_modifiers:
  - target: ac
    op: add
    condition: unarmored
    scale:
      by: level
      table:
        4: 1
        6: 2
        8: 3
        10: 4
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -k barbarian -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```powershell
git add data/classes/barbarian.yaml tests/test_feature_modifiers.py
git commit -m "feat(data): barbarian Agile Fighting AC via granted modifier"
```

---

## Task 5: Halfling Missile Attack Bonus (ranged-only attack)

Grant lives on the **race** `missile_attack_bonus` feature only. The classic halfling **class** keeps its descriptive duplicate feature with *no* grant — a race-as-class halfling always has `race_id="halfling"`, so the race grant covers it (and prevents double-application).

**Files:**
- Modify: `data/races/halfling.yaml` (the `missile_attack_bonus` feature)
- Test: `tests/test_feature_modifiers.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_feature_modifiers.py`:

```python
# ── Task 5: halfling missile bonus ──────────────────────────────────────────

def _profiles(spec):
    from aose.engine.attacks import attack_profiles
    return {p.weapon_id: p for p in attack_profiles(spec, DATA)}


def test_halfling_missile_bonus_applies_to_ranged_only():
    from aose.models import CharacterSpec, ClassEntry
    # Halfling fighter, STR/DEX 10 (+0). short_bow is ranged; unarmed is melee.
    spec = CharacterSpec(
        name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="halfling", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral", equipped_weapons=["short_bow"],
    )
    profs = _profiles(spec)
    assert profs["short_bow"].to_hit_ascending == 1   # +1 missile bonus
    assert profs["unarmed"].to_hit_ascending == 0     # melee: no bonus


def test_non_halfling_has_no_missile_bonus():
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="Hu", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral", equipped_weapons=["short_bow"],
    )
    assert _profiles(spec)["short_bow"].to_hit_ascending == 0


def test_classic_halfling_missile_bonus_not_doubled():
    # Race-as-class halfling: race_id == "halfling" AND class == halfling.
    # The bonus must apply exactly once (race grant only).
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="Hc", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="halfling", classes=[ClassEntry(class_id="halfling", level=1, hp_rolls=[6])],
        alignment="neutral", equipped_weapons=["short_bow"],
    )
    assert _profiles(spec)["short_bow"].to_hit_ascending == 1   # +1, not +2
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -k missile_bonus -q`
Expected: FAIL (`short_bow.to_hit_ascending == 0` for halfling — no grant yet).

- [ ] **Step 3: Add the grant to the race data**

In `data/races/halfling.yaml`, find the `missile_attack_bonus` feature and add `granted_modifiers`:

```yaml
- id: missile_attack_bonus
  name: Missile Attack Bonus
  text: Gains a +1 bonus to attack rolls with all missile weapons.
  mechanical:
    attack_roll_bonus: 1
    weapon_category: missile
  granted_modifiers:
  - target: attack
    op: add
    value: 1
    condition: ranged
```

(Do **not** touch `data/classes/halfling.yaml` — its `missile_attack_bonus` feature stays grant-free.)

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -k "missile_bonus or halfling" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add data/races/halfling.yaml tests/test_feature_modifiers.py
git commit -m "feat(data): halfling missile attack bonus via granted modifier (race-only)"
```

---

## Task 6: Resilience / Magic Resistance (CON-scaled saves)

CON-banded save bonuses on the **race** features for dwarf, duergar, gnome, halfling. Save-category mapping: poison → `save:death`, magic wands/rods/staves → `save:wands`, spells → `save:spells`, paralysis → `save:paralysis`. CON band table (all four): `{7: 2, 11: 3, 15: 4, 18: 5}` (CON ≤ 6 → 0). Each affected category is its own `GrantedModifier` (same table).

**Files:**
- Modify: `data/races/dwarf.yaml` (`resilience`)
- Modify: `data/races/duergar.yaml` (`resilience` — includes paralysis)
- Modify: `data/races/gnome.yaml` (`magic_resistance` — spells + wands only)
- Modify: `data/races/halfling.yaml` (`resilience`)
- Test: `tests/test_feature_modifiers.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_feature_modifiers.py`:

```python
# ── Task 6: CON-scaled resilience saves ─────────────────────────────────────

def _saves(race_id, class_id, con, *, level=1, hp=8):
    from aose.engine.saves import saving_throws
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="R", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": con, "CHA": 10},
        race_id=race_id, classes=[ClassEntry(class_id=class_id, level=level, hp_rolls=[hp])],
        alignment="neutral",
    )
    return saving_throws(spec, DATA)


def test_dwarf_resilience_plus3_at_con13():
    base = _saves("human", "fighter", 13)
    dwarf = _saves("dwarf", "fighter", 13)
    assert dwarf["death"] == base["death"] - 3      # poison/death
    assert dwarf["spells"] == base["spells"] - 3
    assert dwarf["wands"] == base["wands"] - 3
    assert dwarf["paralysis"] == base["paralysis"]  # unaffected
    assert dwarf["breath"] == base["breath"]


def test_dwarf_resilience_zero_at_low_con():
    base = _saves("human", "fighter", 6)
    dwarf = _saves("dwarf", "fighter", 6)
    assert dwarf["death"] == base["death"]          # +0 below band


def test_dwarf_resilience_plus5_at_con18():
    base = _saves("human", "fighter", 18)
    dwarf = _saves("dwarf", "fighter", 18)
    assert dwarf["death"] == base["death"] - 5


def test_gnome_magic_resistance_excludes_poison():
    base = _saves("human", "fighter", 13)
    gnome = _saves("gnome", "fighter", 13)
    assert gnome["spells"] == base["spells"] - 3
    assert gnome["wands"] == base["wands"] - 3
    assert gnome["death"] == base["death"]          # no poison bonus for gnomes


def test_duergar_resilience_includes_paralysis():
    base = _saves("human", "fighter", 13)
    duergar = _saves("duergar", "fighter", 13)
    assert duergar["paralysis"] == base["paralysis"] - 3
    assert duergar["death"] == base["death"] - 3


def test_classic_dwarf_resilience_not_doubled():
    # Race-as-class dwarf: race_id == "dwarf" AND class == dwarf. Bonus once.
    high = _saves("dwarf", "dwarf", 13, hp=8)   # +3
    low = _saves("dwarf", "dwarf", 6, hp=8)     # +0
    assert low["death"] - high["death"] == 3    # exactly 3 (not 6)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -k "resilience or magic_resistance" -q`
Expected: FAIL (no bonus applied yet).

- [ ] **Step 3: Add grants to dwarf**

In `data/races/dwarf.yaml`, add `granted_modifiers` to the `resilience` feature (keep its existing `text` and `mechanical`):

```yaml
  granted_modifiers:
  - target: save:death
    op: add
    scale:
      by: ability:CON
      table:
        7: 2
        11: 3
        15: 4
        18: 5
  - target: save:spells
    op: add
    scale:
      by: ability:CON
      table:
        7: 2
        11: 3
        15: 4
        18: 5
  - target: save:wands
    op: add
    scale:
      by: ability:CON
      table:
        7: 2
        11: 3
        15: 4
        18: 5
```

- [ ] **Step 4: Add grants to halfling**

In `data/races/halfling.yaml`, add the **same three** `granted_modifiers` (death/spells/wands) to the `resilience` feature (identical block to Step 3).

- [ ] **Step 5: Add grants to duergar (adds paralysis)**

In `data/races/duergar.yaml`, add `granted_modifiers` to the `resilience` feature — the same three (death/spells/wands) **plus** a fourth for paralysis:

```yaml
  - target: save:paralysis
    op: add
    scale:
      by: ability:CON
      table:
        7: 2
        11: 3
        15: 4
        18: 5
```

- [ ] **Step 6: Add grants to gnome (spells + wands only)**

In `data/races/gnome.yaml`, add `granted_modifiers` to the `magic_resistance` feature — **only** `save:spells` and `save:wands` (no `save:death`):

```yaml
  granted_modifiers:
  - target: save:spells
    op: add
    scale:
      by: ability:CON
      table:
        7: 2
        11: 3
        15: 4
        18: 5
  - target: save:wands
    op: add
    scale:
      by: ability:CON
      table:
        7: 2
        11: 3
        15: 4
        18: 5
```

- [ ] **Step 7: Run the tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -k "resilience or magic_resistance" -q`
Expected: PASS (6 passed).

- [ ] **Step 8: Commit**

```powershell
git add data/races/dwarf.yaml data/races/duergar.yaml data/races/gnome.yaml data/races/halfling.yaml tests/test_feature_modifiers.py
git commit -m "feat(data): CON-scaled resilience/magic-resistance saves for demihuman races"
```

---

## Task 7: Retire the kineticist AC column onto the modifier path

Move kineticist level-AC from the bespoke `ClassLevelData.armor_class` column to a level-scaled `ac`/`set` `GrantedModifier`, then delete the column field, the YAML column, and the engine block that reads it. The AC engine already evaluates `ac set` outside the armour gate (Task 3), so behaviour is preserved.

**Files:**
- Modify: `aose/models/character_class.py` (remove `armor_class` field)
- Modify: `aose/engine/armor_class.py` (remove legacy column block)
- Modify: `data/classes/kineticist.yaml` (remove `armor_class:` rows; add grant)
- Modify: `tests/test_mental_powers.py` (drop column-field/data assertions)
- Test: `tests/test_feature_modifiers.py` (append regression)

- [ ] **Step 1: Write the failing regression test**

Append to `tests/test_feature_modifiers.py`:

```python
# ── Task 7: kineticist AC migrated off the column ───────────────────────────

KINETICIST_AC = {1: 9, 2: 8, 3: 7, 4: 6, 5: 5, 6: 4, 7: 3, 8: 2,
                 9: 1, 10: 0, 11: -1, 12: -2, 13: -3, 14: -3}


@pytest.mark.parametrize("level,expected", KINETICIST_AC.items())
def test_kineticist_ac_matches_old_column(level, expected):
    # DEX 10 (+0) -> unarmoured descending AC == the granted `ac set` value.
    from aose.engine.armor_class import unarmored_ac
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="K", abilities={"STR": 10, "INT": 10, "WIS": 13, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="kineticist", level=level, hp_rolls=[6])],
        alignment="neutral",
    )
    assert unarmored_ac(spec, DATA)[0] == expected


def test_class_level_data_no_longer_has_armor_class_field():
    from aose.models import ClassLevelData
    with pytest.raises(Exception):
        ClassLevelData(xp_required=0, thac0=19, saves={"death": 13}, armor_class=5)
```

- [ ] **Step 2: Run to verify the field-removal test fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -k "armor_class_field" -q`
Expected: FAIL — `ClassLevelData(... armor_class=5)` currently succeeds (no error raised).

- [ ] **Step 3: Remove the `armor_class` field from the model**

In `aose/models/character_class.py`, delete these lines from `ClassLevelData`:

```python
    # Descending Armour Class granted by the class at this level (e.g. a class
    # whose honed reactions improve AC as it advances). Read generically by the
    # AC engine (best/lowest across classes); None for classes without it.
    armor_class: int | None = None
```

(Keep `powers_known` and everything else.)

- [ ] **Step 4: Remove the legacy column block from the AC engine**

In `aose/engine/armor_class.py`, delete the entire "Legacy class-granted level AC column" block (the `class_acs = []` loop through `if class_acs: base = min(base, min(class_acs))`). Nothing else in the function changes — `ac set` handling already covers it.

- [ ] **Step 5: Migrate the kineticist YAML**

In `data/classes/kineticist.yaml`:

(a) Remove the `armor_class: N` line from **every** one of the 14 `progression` entries (levels 1–14).

(b) Add `granted_modifiers` to the `armour_class` feature (id `armour_class`):

```yaml
- id: armour_class
  name: Armour Class
  text: |-
    As a kineticist advances in level, their honed reactions and ability to deflect attacks grant them an improved Armour Class, as shown on the class table.
  gained_at_level: 1
  granted_modifiers:
  - target: ac
    op: set
    scale:
      by: level
      table:
        1: 9
        2: 8
        3: 7
        4: 6
        5: 5
        6: 4
        7: 3
        8: 2
        9: 1
        10: 0
        11: -1
        12: -2
        13: -3
```

(Level 14 falls back to the level-13 band → −3, matching the old column.)

- [ ] **Step 6: Update `tests/test_mental_powers.py`**

(a) Replace `test_class_level_data_new_columns_default_none` (the test asserting `ld.armor_class is None` and constructing `ClassLevelData(... armor_class=5, powers_known=4)`) with a `powers_known`-only version:

```python
def test_class_level_data_powers_known_defaults_none():
    from aose.models.character_class import ClassLevelData
    ld = ClassLevelData(xp_required=0, thac0=19, saves={"death": 13})
    assert ld.powers_known is None
    ld2 = ClassLevelData(xp_required=0, thac0=19, saves={"death": 13}, powers_known=4)
    assert ld2.powers_known == 4
```

(b) Remove the two data-column assertions that read the retired column (around the Task-3 data test): the lines

```python
    assert cls.progression[1].armor_class == 9
    assert cls.progression[14].armor_class == -3
```

Delete just those two `assert` lines (keep the rest of that test — e.g. `powers_known` assertions). If removing them empties the test body, replace them with `assert cls.progression[1].powers_known == 3`.

(c) The behaviour tests `test_class_granted_ac_drives_unarmored_ac`, `test_class_granted_ac_still_applies_dex`, `test_class_granted_ac_applies_in_armored_call_too`, and `test_class_with_no_ac_column_unaffected` should pass **unchanged** (kineticist AC now comes from the granted modifier, same numbers). Do not edit them.

- [ ] **Step 7: Run the affected suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py tests/test_mental_powers.py -q`
Expected: PASS (the 14 parametrised kineticist-AC cases + field-removal test + mental-powers tests).

- [ ] **Step 8: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: baseline pass/fail (only the 2 unrelated pre-existing breadcrumb failures remain).

- [ ] **Step 9: Commit**

```powershell
git add aose/models/character_class.py aose/engine/armor_class.py data/classes/kineticist.yaml tests/
git commit -m "refactor: retire kineticist AC column onto granted-modifier path"
```

---

## Final verification

- [ ] **Run the whole suite once more**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all green except the 2 known pre-existing breadcrumb-label failures (`test_wizard_class_setup`, `test_wizard_identity`).

- [ ] **Grep for hardcoded class/race ids in engines (should find none)**

```powershell
rg -n "barbarian|halfling|kineticist|dwarf|gnome|duergar" aose/engine/
```
Expected: **no matches** in `aose/engine/`. Any match means a derivation keyed on an id — the design is violated; fix before finishing.

- [ ] **Update `CLAUDE.md` "Current state"**

Add a short "Current state (2026-06-06, feature-granted modifiers)" section summarising: `GrantedModifier`/`Scaling` models, `Modifier.condition`/`source`, `engine/features.py` (`feature_modifiers`/`all_modifiers`), condition handling at AC/saves/attacks, the kineticist AC-column retirement, and the encoded data (barbarian/halfling/dwarf/duergar/gnome). Commit:

```powershell
git add CLAUDE.md
git commit -m "docs: note feature-granted modifiers in CLAUDE.md"
```

---

## Self-review notes (planner)

- **Spec coverage:** §1 models → Task 1; §3 resolver/merge → Task 2; §4 condition handling → Task 3; §5 kineticist retirement + ac-set-outside-gate + bracers consequence → Tasks 3 (engine move) & 7 (column removal); §6 data deliverables → Tasks 4–7; §7 testing → tests in every task incl. kineticist regression + bracers + no-double-application; §2 grant placement on features → Tasks 1, 4–7.
- **Race-as-class wrinkle (§6):** resolved by placing racial grants on the `Race` only and asserting no double-application (Tasks 5 & 6) — verified against `wizard.py:794`.
- **Green at every task:** the legacy AC column is retained through Task 6 and removed in Task 7 together with its replacement grant, so the kineticist AC never regresses mid-plan.
- **Type consistency:** `GrantedModifier`/`Scaling` (Task 1) ↔ `resolve_value`/`feature_modifiers`/`all_modifiers` (Task 2) ↔ consumer imports of `all_modifiers` (Task 3) ↔ `Modifier.condition`/`source` used throughout.
