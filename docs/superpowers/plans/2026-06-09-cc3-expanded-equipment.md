# CC3 Expanded Equipment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the weapon `qualities` list the single source of truth for weapon mechanics (Phase 1), then add all Carcass Crawler 3 "Expanded Equipment" content on top of it (Phase 2).

**Architecture:** Phase 1 is a behaviour-preserving refactor: `melee`, `ranged`, `range_*`, `hands`, `versatile`, and the 2H damage become computed properties derived from *parametric* qualities (`{missile: [x,y,z]}`, `{versatile: "1d8+1"}`), with a loader validation guarding drift. Phase 2 adds a new non-core source (`carcass_crawler_3`) of gear, containers, weapons (incl. no-damage and versatile), armour (with `base_armor` wearable categories + tailorable full plate), and a `blunt`→cleric quality-based weapon allowance.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, pytest, YAML data.

**Spec:** `docs/superpowers/specs/2026-06-09-cc3-expanded-equipment-design.md`

**Run tests:** `.venv\Scripts\python.exe -m pytest tests/ -q` (a trailing `pytest-current` PermissionError on Windows is a known pytest-9 tempdir quirk — ignore it). Run a single test with `.venv\Scripts\python.exe -m pytest tests/test_x.py::test_y -v`.

---

## File Structure

**Phase 1 (refactor):**
- `aose/models/weapon_quality.py` — add `param` schema field.
- `aose/models/item.py` — `QualityRef` model; `Weapon` stores `qualities: list[QualityRef]`, drops `hands/versatile/melee/ranged/range_*`, exposes them as computed properties; `WeaponDamage` drops `variable_two_handed`.
- `aose/models/__init__.py` — export `QualityRef`.
- `aose/data/loader.py` — `_validate_weapon_qualities` pass in `GameData.load`.
- `data/equipment/weapon_qualities.yaml` — `param` on `missile`; new `versatile` definition.
- `data/equipment/weapons.yaml` — rewrite all 20 weapons into parametric form (drop redundant `1d6` defaults, the spear's bogus `versatile`).
- `aose/engine/enchant.py` — simplify `resolve_weapon`.
- `aose/engine/detail.py` — structured-qualities rendering + no-damage `—` + `two_handed_damage`.

**Phase 2 (content):**
- `data/sources.yaml`, `data/equipment/{adventuring_gear,weapon_qualities,weapons,ammunition,armor}.yaml`.
- `aose/models/item.py` — `Armor.tailorable` + `untailored_ac_descending`.
- `aose/models/character.py` — `CharacterSpec.armor_tailored`.
- `aose/models/character_class.py` — `CharClass.weapon_qualities_allowed`.
- `data/classes/{cleric,acolyte}.yaml` — quality-based allowance.
- `aose/engine/attacks.py` — no-damage + versatile split.
- `aose/engine/armor_class.py` — tailored AC.
- `aose/engine/proficiency.py` — quality-based weapon allowance.
- `aose/sheet/view.py` + `aose/web/routes.py` + `aose/web/templates/_equipment_ui.html` — tailored toggle UI.
- `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.

---

# PHASE 1 — Parametric weapon qualities (behaviour-preserving)

## Task 1: Quality `param` schema + parametric `Weapon` model

**Files:**
- Modify: `aose/models/weapon_quality.py`
- Modify: `aose/models/item.py:21-52` (WeaponDamage, Weapon, add QualityRef)
- Modify: `aose/models/__init__.py`
- Test: `tests/test_weapon_qualities.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_weapon_qualities.py`:

```python
"""Parametric weapon qualities: parsing + computed properties on Weapon."""
from aose.models import QualityRef, Weapon, WeaponQuality


def _weapon(**kw):
    base = dict(id="w", name="W", category="weapons", cost_gp=1, item_type="weapon")
    base.update(kw)
    return Weapon.model_validate(base)


def test_bare_string_quality_parses_to_ref():
    w = _weapon(qualities=["melee", "blunt"])
    assert [q.id for q in w.qualities] == ["melee", "blunt"]
    assert all(q.param is None for q in w.qualities)


def test_missile_param_drives_ranged_and_ranges():
    w = _weapon(qualities=[{"missile": [10, 20, 30]}])
    assert w.ranged is True
    assert w.melee is False
    assert (w.range_short, w.range_medium, w.range_long) == (10, 20, 30)


def test_two_handed_quality_drives_hands():
    assert _weapon(qualities=["melee"]).hands == 1
    assert _weapon(qualities=["melee", "two_handed"]).hands == 2


def test_versatile_param_is_two_handed_damage():
    w = _weapon(qualities=["melee", {"versatile": "1d8+1"}])
    assert w.versatile is True
    assert w.two_handed_damage == "1d8+1"


def test_default_damage_is_1d6_when_omitted():
    w = _weapon()
    assert w.damage.default == "1d6"
    assert w.damage.variable == "1d6"
    assert w.deals_damage is True


def test_empty_damage_is_no_damage():
    w = _weapon(damage={"default": "", "variable": ""})
    assert w.deals_damage is False


def test_quality_registry_has_param_field():
    q = WeaponQuality.model_validate(
        {"id": "missile", "name": "Missile", "param": "ranges", "description": "x"})
    assert q.param == "ranges"
    assert WeaponQuality.model_validate(
        {"id": "blunt", "name": "Blunt", "description": "x"}).param == "none"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_qualities.py -q`
Expected: FAIL (`cannot import name 'QualityRef'`).

- [ ] **Step 3: Add `param` to WeaponQuality**

In `aose/models/weapon_quality.py`, add the field and import `Literal`:

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict


class WeaponQuality(BaseModel):
    """A weapon quality definition (Blunt, Brace, Charge, …) — referenceable
    in-game.  Not an ``Item``; loaded into ``GameData.qualities``.

    ``param`` declares whether weapons carry a value for this quality:
    ``ranges`` (the [short, medium, long] of ``missile``), ``damage`` (the
    two-handed die of ``versatile``), or ``none``."""
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    param: Literal["none", "ranges", "damage"] = "none"
```

- [ ] **Step 4: Rewrite the `Weapon`/`WeaponDamage` models**

In `aose/models/item.py`, change the top import line to include `Any` and validator helpers, and replace the `WeaponDamage`/`Weapon` blocks (lines 21–52):

```python
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator
```

```python
class WeaponDamage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # "1d6" is the standard-rule damage for every weapon and the SOLE place 1d6
    # lives — weapon YAML omits both fields unless overriding (a differentiated
    # variable die, or "" for a no-damage weapon like the net/blowgun).
    default: str = "1d6"
    variable: str = "1d6"


class ConditionalBonus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vs: str
    bonus: int


class QualityRef(BaseModel):
    """A weapon's reference to a quality, optionally carrying a parameter.
    Authored in YAML as a bare id (``melee``) or a one-key mapping
    (``{missile: [10, 20, 30]}``, ``{versatile: "1d8+1"}``)."""
    model_config = ConfigDict(extra="forbid")
    id: str
    param: Any = None


class Weapon(ItemBase):
    item_type: Literal["weapon"]
    damage: WeaponDamage = Field(default_factory=WeaponDamage)
    qualities: list[QualityRef] = Field(default_factory=list)
    accepts_ammo: list[str] = Field(default_factory=list)  # ammo groups this launcher fires
    groups: list[str] = Field(default_factory=list)        # enchantment matching tags
    magic_bonus: int = 0
    conditional_bonus: ConditionalBonus | None = None
    base_weapon: str | None = None   # magic/variant: mundane type for proficiency

    @field_validator("qualities", mode="before")
    @classmethod
    def _parse_qualities(cls, v):
        if not v:
            return []
        out: list[dict] = []
        for entry in v:
            if isinstance(entry, str):
                out.append({"id": entry})
            elif isinstance(entry, dict) and set(entry) <= {"id", "param"}:
                out.append(entry)              # already structured (e.g. enchant copy)
            elif isinstance(entry, dict) and len(entry) == 1:
                (key, val), = entry.items()
                out.append({"id": key, "param": val})
            else:
                raise ValueError(f"bad weapon quality entry: {entry!r}")
        return out

    def _q(self, qid: str) -> "QualityRef | None":
        return next((q for q in self.qualities if q.id == qid), None)

    @property
    def quality_ids(self) -> set[str]:
        return {q.id for q in self.qualities}

    @property
    def melee(self) -> bool:
        return "melee" in self.quality_ids

    @property
    def ranged(self) -> bool:
        return "missile" in self.quality_ids

    @property
    def hands(self) -> int:
        return 2 if "two_handed" in self.quality_ids else 1

    @property
    def versatile(self) -> bool:
        return "versatile" in self.quality_ids

    @property
    def _ranges(self) -> "tuple[int, int, int] | None":
        q = self._q("missile")
        return tuple(q.param) if q and q.param else None

    @property
    def range_short(self) -> int | None:
        r = self._ranges
        return r[0] if r else None

    @property
    def range_medium(self) -> int | None:
        r = self._ranges
        return r[1] if r else None

    @property
    def range_long(self) -> int | None:
        r = self._ranges
        return r[2] if r else None

    @property
    def two_handed_damage(self) -> str | None:
        q = self._q("versatile")
        return q.param if q else None

    @property
    def deals_damage(self) -> bool:
        return bool(self.damage.default)
```

- [ ] **Step 5: Export `QualityRef`**

In `aose/models/__init__.py`, add `QualityRef` to the `from .item import (...)` block and to `__all__`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_qualities.py -q`
Expected: PASS (8 passed).

- [ ] **Step 7: Commit**

```bash
git add aose/models/weapon_quality.py aose/models/item.py aose/models/__init__.py tests/test_weapon_qualities.py
git commit -m "refactor(weapons): parametric qualities + computed weapon properties"
```

---

## Task 2: Loader validation for quality params

**Files:**
- Modify: `aose/data/loader.py`
- Test: `tests/test_weapon_qualities.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_weapon_qualities.py`:

```python
import pytest

from aose.data.loader import _validate_weapon_qualities
from aose.models import Armor


def _wq():
    return {
        "melee": WeaponQuality(id="melee", name="Melee", description="x"),
        "missile": WeaponQuality(id="missile", name="Missile", description="x", param="ranges"),
        "versatile": WeaponQuality(id="versatile", name="Versatile", description="x", param="damage"),
    }


def test_validate_rejects_unknown_quality():
    items = {"w": _weapon(qualities=["bogus"])}
    with pytest.raises(ValueError, match="unknown quality"):
        _validate_weapon_qualities(items, _wq())


def test_validate_rejects_missile_without_three_ranges():
    items = {"w": _weapon(qualities=[{"missile": [10, 20]}])}
    with pytest.raises(ValueError, match="three integer ranges"):
        _validate_weapon_qualities(items, _wq())


def test_validate_rejects_versatile_without_damage():
    items = {"w": _weapon(qualities=["versatile"])}
    with pytest.raises(ValueError, match="damage string"):
        _validate_weapon_qualities(items, _wq())


def test_validate_rejects_param_on_plain_quality():
    items = {"w": _weapon(qualities=[{"melee": [1, 2, 3]}])}
    with pytest.raises(ValueError, match="takes no parameter"):
        _validate_weapon_qualities(items, _wq())


def test_validate_accepts_good_weapon():
    items = {"w": _weapon(qualities=["melee", {"missile": [10, 20, 30]}])}
    _validate_weapon_qualities(items, _wq())  # no raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_qualities.py -q`
Expected: FAIL (`cannot import name '_validate_weapon_qualities'`).

- [ ] **Step 3: Add the validator and wire it into `load`**

In `aose/data/loader.py`, add after `_load_weapon_qualities` (around line 195):

```python
def _validate_weapon_qualities(
    items: dict, qualities: dict
) -> None:
    """Every weapon's quality refs must name a known quality and carry the
    param shape that quality's registry entry declares (``ranges`` = three
    ints; ``damage`` = a non-empty string; ``none`` = no param)."""
    from aose.models import Weapon

    for item in items.values():
        if not isinstance(item, Weapon):
            continue
        for ref in item.qualities:
            q = qualities.get(ref.id)
            if q is None:
                raise ValueError(
                    f"weapon {item.id!r} references unknown quality {ref.id!r}")
            if q.param == "ranges":
                ok = (isinstance(ref.param, (list, tuple))
                      and len(ref.param) == 3
                      and all(isinstance(n, int) for n in ref.param))
                if not ok:
                    raise ValueError(
                        f"weapon {item.id!r} quality {ref.id!r} needs three "
                        f"integer ranges, got {ref.param!r}")
            elif q.param == "damage":
                if not (isinstance(ref.param, str) and ref.param):
                    raise ValueError(
                        f"weapon {item.id!r} quality {ref.id!r} needs a damage "
                        f"string, got {ref.param!r}")
            else:  # "none"
                if ref.param is not None:
                    raise ValueError(
                        f"weapon {item.id!r} quality {ref.id!r} takes no "
                        f"parameter, got {ref.param!r}")
```

Then in `GameData.load`, build items + qualities into locals and validate before returning:

```python
    @classmethod
    def load(cls, data_dir: Path) -> "GameData":
        items = _load_items(data_dir / "equipment")
        qualities = _load_weapon_qualities(data_dir)
        _validate_weapon_qualities(items, qualities)
        return cls(
            races=_load_models(data_dir / "races", Race),
            classes=_load_models(data_dir / "classes", CharClass),
            spells=_load_models(data_dir / "spells", Spell),
            spell_lists=_load_spell_lists(data_dir),
            items=items,
            qualities=qualities,
            secondary_skills=_load_secondary_skills(data_dir),
            languages=_load_languages(data_dir),
            enchantments=_load_enchantments(data_dir),
            sources=_load_sources(data_dir),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_qualities.py -q`
Expected: PASS (13 passed). Note: the real data still loads fine because `missile` in YAML isn't yet marked `param: ranges` — Task 3 fixes the data; this validator only enforces what the registry declares. Do NOT run the full suite yet (real `weapons.yaml` is still in the old shape and will fail to parse).

- [ ] **Step 5: Commit**

```bash
git add aose/data/loader.py tests/test_weapon_qualities.py
git commit -m "feat(loader): validate weapon quality params against registry"
```

---

## Task 3: Rewrite weapons.yaml + quality registry into parametric form

**Files:**
- Modify: `data/equipment/weapon_qualities.yaml`
- Modify: `data/equipment/weapons.yaml` (full rewrite)
- Test: `tests/test_weapon_parity.py` (new)

- [ ] **Step 1: Write the failing parity test**

Create `tests/test_weapon_parity.py`:

```python
"""Parametric weapons.yaml derives exactly the pre-refactor stored values."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.models import Weapon

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


# (id, melee, ranged, hands, ranges_or_None, variable_damage, two_handed_damage)
EXPECTED = {
    "battle_axe":      (True,  False, 2, None,            "1d8",  None),
    "club":            (True,  False, 1, None,            "1d4",  None),
    "crossbow":        (False, True,  2, (80, 160, 240),  "1d6",  None),
    "dagger":          (True,  True,  1, (10, 20, 30),    "1d4",  None),
    "hand_axe":        (True,  True,  1, (10, 20, 30),    "1d6",  None),
    "javelin":         (False, True,  1, (30, 60, 90),    "1d4",  None),
    "lance":           (True,  False, 1, None,            "1d6",  None),
    "long_bow":        (False, True,  2, (70, 140, 210),  "1d6",  None),
    "mace":            (True,  False, 1, None,            "1d6",  None),
    "polearm":         (True,  False, 2, None,            "1d10", None),
    "short_bow":       (False, True,  2, (50, 100, 150),  "1d6",  None),
    "short_sword":     (True,  False, 1, None,            "1d6",  None),
    "silver_dagger":   (True,  True,  1, (10, 20, 30),    "1d4",  None),
    "sling":           (False, True,  1, (40, 80, 160),   "1d4",  None),
    "spear":           (True,  True,  1, (20, 40, 60),    "1d6",  None),
    "staff":           (True,  False, 2, None,            "1d4",  None),
    "sword":           (True,  False, 1, None,            "1d8",  None),
    "two_handed_sword":(True,  False, 2, None,            "1d10", None),
    "war_hammer":      (True,  False, 1, None,            "1d6",  None),
    "trident":         (True,  False, 1, None,            "1d6",  None),
}


@pytest.mark.parametrize("wid", sorted(EXPECTED))
def test_weapon_derives_legacy_values(data, wid):
    w = data.items[wid]
    assert isinstance(w, Weapon)
    melee, ranged, hands, ranges, var, two_h = EXPECTED[wid]
    assert w.melee is melee
    assert w.ranged is ranged
    assert w.hands == hands
    got = (w.range_short, w.range_medium, w.range_long) if w.ranged else None
    assert got == ranges
    assert w.damage.default == "1d6"     # standard rule, uniform
    assert w.damage.variable == var
    assert w.two_handed_damage == two_h
    assert w.deals_damage is True


def test_spear_is_not_versatile(data):
    assert data.items["spear"].versatile is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_parity.py -q`
Expected: FAIL (old `weapons.yaml` shape — `extra fields not permitted` / validation error on load).

- [ ] **Step 3: Mark `missile` param + add `versatile` in the quality registry**

In `data/equipment/weapon_qualities.yaml`, add `param: ranges` to the `missile` entry, and append a new `versatile` entry:

```yaml
- id: missile
  name: Missile
  param: ranges
  description: >-
    May be used to make ranged attacks, using the listed ranges.
- id: versatile
  name: Versatile
  param: damage
  description: >-
    May be used with one or two hands. When wielded two-handed, the
    parenthesised damage is used (and a shield may not be employed).
```

- [ ] **Step 4: Rewrite `data/equipment/weapons.yaml`**

Replace the entire file with the parametric form (drop `hands`, `melee`, `ranged`, `range_*`, redundant `1d6` damage; the spear loses `versatile`):

```yaml
# Weapons (AOSE).  Mechanics live in `qualities`: `melee` ⟹ usable in melee,
# `{missile: [s,m,l]}` ⟹ ranged with those ranges, `two_handed` ⟹ two hands,
# `{versatile: "die"}` ⟹ optional two-handed damage.  Standard-rule damage is
# always 1d6 (the model default), so `damage.default` is never written; only a
# differentiated `variable` die (the Variable Weapon Damage optional rule) is.

- id: battle_axe
  item_type: weapon
  name: Battle Axe
  category: weapons
  cost_gp: 7
  weight_cn: 50
  damage: { variable: "1d8" }
  qualities: [melee, slow, two_handed]
  groups: [axe]

- id: club
  item_type: weapon
  name: Club
  category: weapons
  cost_gp: 3
  weight_cn: 50
  damage: { variable: "1d4" }
  qualities: [blunt, melee]

- id: crossbow
  item_type: weapon
  name: Crossbow
  category: weapons
  cost_gp: 30
  weight_cn: 50
  qualities: [reload, slow, two_handed, {missile: [80, 160, 240]}]
  accepts_ammo: [crossbow_bolt]

- id: dagger
  item_type: weapon
  name: Dagger
  category: weapons
  cost_gp: 3
  weight_cn: 10
  damage: { variable: "1d4" }
  qualities: [melee, {missile: [10, 20, 30]}]

- id: hand_axe
  item_type: weapon
  name: Hand Axe
  category: weapons
  cost_gp: 4
  weight_cn: 30
  qualities: [melee, {missile: [10, 20, 30]}]
  groups: [axe]

- id: javelin
  item_type: weapon
  name: Javelin
  category: weapons
  cost_gp: 1
  weight_cn: 20
  damage: { variable: "1d4" }
  qualities: [{missile: [30, 60, 90]}]

- id: lance
  item_type: weapon
  name: Lance
  category: weapons
  cost_gp: 5
  weight_cn: 120
  qualities: [charge, melee]

- id: long_bow
  item_type: weapon
  name: Long Bow
  category: weapons
  cost_gp: 40
  weight_cn: 30
  qualities: [two_handed, {missile: [70, 140, 210]}]
  groups: [bow]
  accepts_ammo: [arrow]

- id: mace
  item_type: weapon
  name: Mace
  category: weapons
  cost_gp: 5
  weight_cn: 30
  qualities: [blunt, melee]

- id: polearm
  item_type: weapon
  name: Pole-arm
  category: weapons
  cost_gp: 7
  weight_cn: 150
  damage: { variable: "1d10" }
  qualities: [brace, melee, slow, two_handed]

- id: short_bow
  item_type: weapon
  name: Short Bow
  category: weapons
  cost_gp: 25
  weight_cn: 30
  qualities: [two_handed, {missile: [50, 100, 150]}]
  groups: [bow]
  accepts_ammo: [arrow]

- id: short_sword
  item_type: weapon
  name: Short Sword
  category: weapons
  cost_gp: 7
  weight_cn: 30
  qualities: [melee]
  groups: [sword]

- id: silver_dagger
  item_type: weapon
  name: Silver Dagger
  category: weapons
  cost_gp: 30
  weight_cn: 10
  damage: { variable: "1d4" }
  qualities: [melee, {missile: [10, 20, 30]}]

- id: sling
  item_type: weapon
  name: Sling
  category: weapons
  cost_gp: 2
  weight_cn: 20
  damage: { variable: "1d4" }
  qualities: [blunt, {missile: [40, 80, 160]}]
  accepts_ammo: [sling_stone]

- id: spear
  item_type: weapon
  name: Spear
  category: weapons
  cost_gp: 4
  weight_cn: 30
  qualities: [brace, melee, {missile: [20, 40, 60]}]

- id: staff
  item_type: weapon
  name: Staff
  category: weapons
  cost_gp: 2
  weight_cn: 40
  damage: { variable: "1d4" }
  qualities: [blunt, melee, slow, two_handed]

- id: sword
  item_type: weapon
  name: Sword
  category: weapons
  cost_gp: 10
  weight_cn: 60
  damage: { variable: "1d8" }
  qualities: [melee]
  groups: [sword]

- id: two_handed_sword
  item_type: weapon
  name: Two-Handed Sword
  category: weapons
  cost_gp: 15
  weight_cn: 150
  damage: { variable: "1d10" }
  qualities: [melee, slow, two_handed]
  groups: [sword]

- id: war_hammer
  item_type: weapon
  name: War Hammer
  category: weapons
  cost_gp: 5
  weight_cn: 30
  qualities: [blunt, melee]

- id: trident
  item_type: weapon
  name: Trident
  category: weapons
  cost_gp: 5
  weight_cn: 50
  qualities: [melee]
  groups: [trident]
```

- [ ] **Step 5: Run the parity test + full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_weapon_parity.py tests/test_weapon_qualities.py -q`
Expected: PASS.
Then run the full suite: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: failures only in `test_detail_cards.py`/`test_detail_views.py`/`test_enchantments.py` referencing removed fields (fixed in Tasks 4–5) and possibly `test_models.py`. Do not fix unrelated failures; note which fail.

- [ ] **Step 6: Commit**

```bash
git add data/equipment/weapon_qualities.yaml data/equipment/weapons.yaml tests/test_weapon_parity.py
git commit -m "refactor(weapons): rewrite weapons.yaml into parametric qualities"
```

---

## Task 4: Simplify enchant.py `resolve_weapon`

**Files:**
- Modify: `aose/engine/enchant.py:105-127`
- Test: `tests/test_enchantments.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_enchantments.py` (it already has a `data` fixture; if not, add `from pathlib import Path` + the standard `GameData.load(Path(__file__).parent.parent / "data")` fixture):

```python
def test_enchanted_weapon_derives_props_from_base(data):
    from aose.engine.enchant import resolve_weapon
    sword = data.items["sword"]
    ench = next(iter(data.enchantments.values()))
    resolved = resolve_weapon(sword, ench, "inst1")
    assert resolved.melee is True
    assert resolved.ranged is False
    assert resolved.hands == 1
    assert resolved.damage.variable == "1d8"
    assert resolved.base_weapon == "sword"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -q`
Expected: FAIL (`Weapon.__init__` got unexpected `versatile`/`melee`/… — because `resolve_weapon` still passes removed fields).

- [ ] **Step 3: Simplify `resolve_weapon`**

In `aose/engine/enchant.py`, replace the `return Weapon(...)` in `resolve_weapon` (drop `hands`, `versatile`, `melee`, `ranged`, `range_*`; forward `qualities` + `damage`):

```python
    return Weapon(
        id=f"ench:{instance_id}",
        name=ench.name_template.format(base=base.name),
        category=base.category,
        cost_gp=0,
        weight_cn=base.weight_cn,
        magic=True,
        item_type="weapon",
        damage=base.damage,
        qualities=[q.model_copy() for q in base.qualities],
        groups=list(base.groups),
        accepts_ammo=list(base.accepts_ammo),
        magic_bonus=ench.magic_bonus,
        conditional_bonus=ench.conditional_bonus,
        base_weapon=base.id,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchantments.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/enchant.py tests/test_enchantments.py
git commit -m "refactor(enchant): derive enchanted-weapon props from base qualities"
```

---

## Task 5: Detail-card rendering (structured qualities + no-damage)

**Files:**
- Modify: `aose/engine/detail.py:49-67`
- Test: `tests/test_detail_cards.py` (extend) — first read the file to see existing weapon assertions and update any that reference `item.qualities` as bare strings.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_detail_cards.py` (reuse its existing `data` fixture / `item_card` import):

```python
def test_weapon_card_formats_parametric_qualities(data):
    from aose.engine.detail import item_card
    card = item_card(data.items["crossbow"])
    labels = {s.label: s.value for s in card.stats}
    assert "Missile" in labels["Qualities"]
    assert labels["Range"] == "80/160/240 ft"


def test_weapon_card_shows_dash_for_no_damage(data):
    from aose.engine.detail import item_card
    # A synthetic no-damage weapon
    from aose.models import Weapon
    w = Weapon.model_validate(dict(
        id="netx", name="Net", category="weapons", cost_gp=1, item_type="weapon",
        damage={"default": "", "variable": ""},
        qualities=["blunt", {"missile": [10, 20, 30]}]))
    card = item_card(w)
    labels = {s.label: s.value for s in card.stats}
    assert labels["Damage"] == "—"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_detail_cards.py -q`
Expected: FAIL (Damage shows `""`, Qualities join raises on `QualityRef`).

- [ ] **Step 3: Update `item_card` weapon branch**

In `aose/engine/detail.py`, replace the `Weapon` branch (lines ~49–67) damage + qualities lines:

```python
    if isinstance(item, Weapon):
        stats.append(StatLine(label="Type", value="Weapon"))
        stats.append(StatLine(label="Damage",
                              value=item.damage.default if item.deals_damage else "—"))
        if item.two_handed_damage:
            stats.append(StatLine(label="Damage (2H)", value=item.two_handed_damage))
        if item.ranged and item.range_short:
            stats.append(StatLine(
                label="Range",
                value=f"{item.range_short}/{item.range_medium}/{item.range_long} ft"))
        stats.append(StatLine(label="Hands", value=str(item.hands)))
        if item.qualities:
            stats.append(StatLine(label="Qualities", value=_format_qualities(item)))
        if item.magic_bonus:
            stats.append(StatLine(label="Magic", value=f"+{item.magic_bonus}"))
        if item.conditional_bonus:
            cb = item.conditional_bonus
            stats.append(StatLine(label="Bonus", value=f"+{cb.bonus} vs {cb.vs}"))
        stats += _cost_weight(item)
```

Add a helper near the top of `detail.py` (after imports):

```python
def _format_qualities(weapon) -> str:
    """Human-readable quality list: bare ids title-cased, params inlined."""
    parts: list[str] = []
    for q in weapon.qualities:
        name = q.id.replace("_", " ").title()
        if q.id == "missile" and q.param:
            parts.append(f"{name} ({q.param[0]}/{q.param[1]}/{q.param[2]} ft)")
        elif q.id == "versatile" and q.param:
            parts.append(f"{name} ({q.param})")
        else:
            parts.append(name)
    return ", ".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass + full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_detail_cards.py tests/test_detail_views.py -q`
Expected: PASS (fix any remaining old-shape assertions in those files inline — e.g. a test asserting `Qualities == "blunt, melee"` becomes `"Blunt, Melee"`).
Then: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (whole suite green — Phase 1 complete).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/detail.py tests/test_detail_cards.py tests/test_detail_views.py
git commit -m "refactor(detail): render parametric qualities and no-damage weapons"
```

---

# PHASE 2 — CC3 content

## Task 6: Register the `carcass_crawler_3` source

**Files:**
- Modify: `data/sources.yaml`
- Test: `tests/test_cc3_content.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_cc3_content.py`:

```python
"""Carcass Crawler 3 expanded equipment content."""
from pathlib import Path

import pytest

from aose.data.loader import GameData

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


def test_source_registered(data):
    assert "carcass_crawler_3" in data.sources
    assert data.sources["carcass_crawler_3"].core is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_content.py -q`
Expected: FAIL (`carcass_crawler_3` not in sources).

- [ ] **Step 3: Add the source**

Append to `data/sources.yaml`:

```yaml
- id: carcass_crawler_3
  name: Carcass Crawler Issue 3
  publisher: Necrotic Gnome
  core: false
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_content.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data/sources.yaml tests/test_cc3_content.py
git commit -m "feat(data): register Carcass Crawler 3 source"
```

---

## Task 7: Adventuring gear + containers

**Files:**
- Modify: `data/equipment/adventuring_gear.yaml`
- Test: `tests/test_cc3_content.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cc3_content.py`:

```python
from aose.models import AdventuringGear, Container

CC3_GEAR_IDS = [
    "barrel", "bedroll", "bell_miniature", "block_and_tackle", "bucket",
    "caltrops", "candles", "chain_10ft", "chalk", "chisel", "cooking_pots",
    "firewood", "fishing_rod", "holy_symbol_gold", "holy_symbol_wooden",
    "ink_vial", "ladder_10ft", "lantern_bullseye", "lock", "magnifying_glass",
    "manacles", "marbles", "mining_pick", "instrument_string", "instrument_wind",
    "paper", "quill", "saw", "scroll_case", "sledgehammer", "spade",
    "tent", "twine", "vial_glass", "whistle",
]
CC3_CONTAINERS = {
    "belt_pouch": 50, "box_iron_small": 250, "box_iron_large": 800,
    "chest_wooden_small": 300, "chest_wooden_large": 1000,
}


@pytest.mark.parametrize("gid", CC3_GEAR_IDS)
def test_cc3_gear_loads(data, gid):
    item = data.items[gid]
    assert isinstance(item, AdventuringGear)
    assert item.source == "carcass_crawler_3"


@pytest.mark.parametrize("cid,cap", sorted(CC3_CONTAINERS.items()))
def test_cc3_containers(data, cid, cap):
    item = data.items[cid]
    assert isinstance(item, Container)
    assert item.capacity_cn == cap
    assert item.source == "carcass_crawler_3"


def test_bundle_counts(data):
    assert data.items["candles"].bundle_count == 10
    assert data.items["chalk"].bundle_count == 10
    assert data.items["paper"].bundle_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_content.py -q`
Expected: FAIL (KeyError on the new ids).

- [ ] **Step 3: Append the gear + containers**

Append to `data/equipment/adventuring_gear.yaml`. Each `gear` row needs `item_type: gear`, `category: adventuring_gear`, `source: carcass_crawler_3`, `cost_gp`, and (where the book sells sets) `bundle_count`. Containers use `item_type: container` + `capacity_cn` + `weight_multiplier: 1.0`. Use these costs (gp) from CC3:

```yaml
# ── Carcass Crawler 3 expanded adventuring gear ──────────────────────────────
- { id: barrel, item_type: gear, name: Barrel, category: adventuring_gear, cost_gp: 1, source: carcass_crawler_3, description: "Holds 40 gallons (320 pints) of liquid." }
- { id: bedroll, item_type: gear, name: Bedroll, category: adventuring_gear, cost_gp: 2, source: carcass_crawler_3, description: "A heavy woollen blanket with a small pillow." }
- { id: bell_miniature, item_type: gear, name: Bell (miniature), category: adventuring_gear, cost_gp: 1, source: carcass_crawler_3, description: "A 1\" brass bell." }
- { id: block_and_tackle, item_type: gear, name: Block and Tackle, category: adventuring_gear, cost_gp: 5, source: carcass_crawler_3, description: "Reduces the effective weight of a hauled object by 75%. Requires 4 times as much rope." }
- { id: bucket, item_type: gear, name: Bucket, category: adventuring_gear, cost_gp: 1, source: carcass_crawler_3, description: "Holds 5 gallons (40 pints)." }
- { id: caltrops, item_type: gear, name: Caltrops (bag of 20), category: adventuring_gear, cost_gp: 1, source: carcass_crawler_3, description: "Cover a 5' x 5' area; 2-in-6 chance to tread on a spike (50% movement reduction for 24 hours)." }
- { id: candles, item_type: gear, name: Candles (10), category: adventuring_gear, cost_gp: 1, bundle_count: 10, source: carcass_crawler_3, description: "Each casts dim light in a 5' radius and burns for 1 hour." }
- { id: chain_10ft, item_type: gear, name: Chain (10'), category: adventuring_gear, cost_gp: 30, source: carcass_crawler_3, description: "A 10' length of heavy iron chain." }
- { id: chalk, item_type: gear, name: Chalk (10 sticks), category: adventuring_gear, cost_gp: 1, bundle_count: 10, source: carcass_crawler_3, description: "Useful for making markings on stone." }
- { id: chisel, item_type: gear, name: Chisel, category: adventuring_gear, cost_gp: 2, source: carcass_crawler_3, description: "Used with a hammer for chipping away stone." }
- { id: cooking_pots, item_type: gear, name: Cooking Pots, category: adventuring_gear, cost_gp: 3, source: carcass_crawler_3, description: "Pots and pans for campfire cooking." }
- { id: firewood, item_type: gear, name: Firewood (bundle), category: adventuring_gear, cost_gp: 1, source: carcass_crawler_3, description: "A bundle of dry wood. Burns for 8 hours." }
- { id: fishing_rod, item_type: gear, name: Fishing Rod and Tackle, category: adventuring_gear, cost_gp: 4, source: carcass_crawler_3, description: "A rod, line, hook, and bait box." }
- { id: holy_symbol_gold, item_type: gear, name: Holy Symbol (gold), category: adventuring_gear, cost_gp: 100, source: carcass_crawler_3, description: "Grants a +1 bonus to the 2d6 turning roll for the affected Hit Dice of undead." }
- { id: holy_symbol_wooden, item_type: gear, name: Holy Symbol (wooden), category: adventuring_gear, cost_gp: 5, source: carcass_crawler_3, description: "Incurs a -1 penalty to the 2d6 turning roll." }
- { id: ink_vial, item_type: gear, name: Ink (vial), category: adventuring_gear, cost_gp: 1, source: carcass_crawler_3, description: "Black ink, enough for ~50 pages. Coloured ink costs double." }
- { id: ladder_10ft, item_type: gear, name: Ladder (wooden, 10'), category: adventuring_gear, cost_gp: 5, source: carcass_crawler_3, description: "Simple wooden construction. Very encumbering." }
- { id: lantern_bullseye, item_type: gear, name: Lantern, Bullseye, category: adventuring_gear, cost_gp: 20, source: carcass_crawler_3, description: "Casts a narrow beam, 60' long and 20' wide at the end. Burns one oil flask every four hours." }
- { id: lock, item_type: gear, name: Lock, category: adventuring_gear, cost_gp: 20, source: carcass_crawler_3, description: "A basic iron lock with a key." }
- { id: magnifying_glass, item_type: gear, name: Magnifying Glass, category: adventuring_gear, cost_gp: 3, source: carcass_crawler_3, description: "Used for studying fine details." }
- { id: manacles, item_type: gear, name: Manacles, category: adventuring_gear, cost_gp: 15, source: carcass_crawler_3, description: "Iron manacles with a chain, for binding hands or feet." }
- { id: marbles, item_type: gear, name: Marbles (bag of 20), category: adventuring_gear, cost_gp: 1, source: carcass_crawler_3, description: "A bag of colourful glass beads." }
- { id: mining_pick, item_type: gear, name: Mining Pick, category: adventuring_gear, cost_gp: 3, source: carcass_crawler_3, description: "For breaking rock." }
- { id: instrument_string, item_type: gear, name: Musical Instrument (string), category: adventuring_gear, cost_gp: 20, source: carcass_crawler_3, description: "A lute, mandolin, or similar. Basic quality." }
- { id: instrument_wind, item_type: gear, name: Musical Instrument (wind), category: adventuring_gear, cost_gp: 5, source: carcass_crawler_3, description: "A flute, pipe, or similar. Basic quality." }
- { id: paper, item_type: gear, name: Paper/Parchment (2 sheets), category: adventuring_gear, cost_gp: 1, bundle_count: 2, source: carcass_crawler_3, description: "Approximately 1'-square sheets." }
- { id: quill, item_type: gear, name: Quill, category: adventuring_gear, cost_gp: 1, source: carcass_crawler_3, description: "A large feather sharpened into a writing point." }
- { id: saw, item_type: gear, name: Saw, category: adventuring_gear, cost_gp: 1, source: carcass_crawler_3, description: "A hand saw for cutting wood." }
- { id: scroll_case, item_type: gear, name: Scroll Case, category: adventuring_gear, cost_gp: 1, source: carcass_crawler_3, description: "An oiled leather tube with a cap. Not completely watertight." }
- { id: sledgehammer, item_type: gear, name: Sledgehammer, category: adventuring_gear, cost_gp: 5, source: carcass_crawler_3, description: "A big heavy hammer for breaking rock." }
- { id: spade, item_type: gear, name: Spade or Shovel, category: adventuring_gear, cost_gp: 2, source: carcass_crawler_3, description: "For excavating earth." }
- { id: tent, item_type: gear, name: Tent, category: adventuring_gear, cost_gp: 20, source: carcass_crawler_3, description: "Large enough for 2 adult humans." }
- { id: twine, item_type: gear, name: Twine (100' ball), category: adventuring_gear, cost_gp: 1, source: carcass_crawler_3, description: "Thin cord; supports up to 300 coins of weight." }
- { id: vial_glass, item_type: gear, name: Vial (glass), category: adventuring_gear, cost_gp: 1, source: carcass_crawler_3, description: "Holds up to half a pint of liquid." }
- { id: whistle, item_type: gear, name: Whistle, category: adventuring_gear, cost_gp: 1, source: carcass_crawler_3, description: "Useful for signalling or faking bird calls." }

- { id: belt_pouch, item_type: container, name: Belt Pouch, category: adventuring_gear, cost_gp: 1, capacity_cn: 50, weight_multiplier: 1.0, source: carcass_crawler_3, description: "A leather pouch that holds up to 50 coins." }
- { id: box_iron_small, item_type: container, name: Box (iron, small), category: adventuring_gear, cost_gp: 10, capacity_cn: 250, weight_multiplier: 1.0, source: carcass_crawler_3, description: "A solid iron casket holding up to 250 coins." }
- { id: box_iron_large, item_type: container, name: Box (iron, large), category: adventuring_gear, cost_gp: 30, capacity_cn: 800, weight_multiplier: 1.0, source: carcass_crawler_3, description: "A solid iron casket holding up to 800 coins." }
- { id: chest_wooden_small, item_type: container, name: Chest (wooden, small), category: adventuring_gear, cost_gp: 1, capacity_cn: 300, weight_multiplier: 1.0, source: carcass_crawler_3, description: "A wooden chest holding up to 300 coins." }
- { id: chest_wooden_large, item_type: container, name: Chest (wooden, large), category: adventuring_gear, cost_gp: 5, capacity_cn: 1000, weight_multiplier: 1.0, source: carcass_crawler_3, description: "A wooden chest holding up to 1,000 coins." }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_content.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data/equipment/adventuring_gear.yaml tests/test_cc3_content.py
git commit -m "feat(data): CC3 adventuring gear and containers"
```

---

## Task 8: New weapon qualities

**Files:**
- Modify: `data/equipment/weapon_qualities.yaml`
- Test: `tests/test_cc3_content.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cc3_content.py`:

```python
@pytest.mark.parametrize("qid", ["knock_out", "entangle", "stealth", "strangle"])
def test_cc3_qualities_loaded(data, qid):
    assert qid in data.qualities
    assert data.qualities[qid].param == "none"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_content.py -k qualities -q`
Expected: FAIL.

- [ ] **Step 3: Append the qualities**

Append to `data/equipment/weapon_qualities.yaml`:

```yaml
- id: knock_out
  name: Knock-out
  description: >-
    On a successful hit, the target must save versus paralysis or be knocked
    out for 1d6 turns.
- id: entangle
  name: Entangle
  description: >-
    On a successful hit, the target must save versus paralysis or be unable to
    move or act. A new save is allowed each round to escape.
- id: stealth
  name: Stealth
  description: >-
    May only be used to attack an unaware person (human/demihuman of any level
    or humanoid monster up to 4+1 HD) from behind. Non-living creatures are immune.
- id: strangle
  name: Strangle
  description: >-
    Following a successful hit, inflicts automatic damage each round; the victim
    cannot move and suffers -2 to attack rolls. A successful hit on the attacker
    lets the victim break free.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_content.py -k qualities -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data/equipment/weapon_qualities.yaml tests/test_cc3_content.py
git commit -m "feat(data): CC3 weapon qualities (knock-out, entangle, stealth, strangle)"
```

---

## Task 9: New weapons + blowgun dart ammo

**Files:**
- Modify: `data/equipment/weapons.yaml`
- Modify: `data/equipment/ammunition.yaml`
- Test: `tests/test_cc3_content.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cc3_content.py`:

```python
from aose.models import Ammunition, Weapon


def test_bastard_sword_versatile(data):
    w = data.items["bastard_sword"]
    assert isinstance(w, Weapon)
    assert w.versatile is True
    assert w.two_handed_damage == "1d8+1"
    assert w.damage.default == "1d6"      # standard rule
    assert w.damage.variable == "1d6+1"   # one-handed variable
    assert w.hands == 1
    assert "sword" in w.groups


@pytest.mark.parametrize("wid", ["blowgun", "net"])
def test_no_damage_weapons(data, wid):
    w = data.items[wid]
    assert w.deals_damage is False
    assert w.damage.default == "" and w.damage.variable == ""


def test_blowgun_accepts_darts(data):
    assert data.items["blowgun"].accepts_ammo == ["blowgun_dart"]
    dart = data.items["blowgun_dart"]
    assert isinstance(dart, Ammunition)
    assert dart.bundle_count == 5
    assert dart.groups == ["blowgun_dart"]


@pytest.mark.parametrize("wid,quals", [
    ("blackjack", {"blunt", "knock_out", "melee", "stealth"}),
    ("bolas", {"blunt", "entangle", "missile"}),
    ("garotte", {"melee", "stealth", "strangle", "two_handed"}),
    ("whip", {"entangle", "melee"}),
])
def test_cc3_weapon_qualities(data, wid, quals):
    assert data.items[wid].quality_ids == quals
    assert data.items[wid].source == "carcass_crawler_3"


def test_garotte_two_handed(data):
    assert data.items["garotte"].hands == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_content.py -k "bastard or no_damage or blowgun or cc3_weapon or garotte" -q`
Expected: FAIL.

- [ ] **Step 3: Append weapons + ammo**

Append to `data/equipment/weapons.yaml`:

```yaml
# ── Carcass Crawler 3 weapons ────────────────────────────────────────────────
- id: bastard_sword
  item_type: weapon
  name: Bastard Sword
  category: weapons
  cost_gp: 15
  weight_cn: 80
  damage: { variable: "1d6+1" }
  qualities: [melee, {versatile: "1d8+1"}]
  groups: [sword]
  source: carcass_crawler_3

- id: blackjack
  item_type: weapon
  name: Blackjack
  category: weapons
  cost_gp: 1
  weight_cn: 10
  damage: { variable: "1d2" }
  qualities: [blunt, knock_out, melee, stealth]
  source: carcass_crawler_3

- id: blowgun
  item_type: weapon
  name: Blowgun
  category: weapons
  cost_gp: 3
  weight_cn: 5
  damage: { default: "", variable: "" }
  qualities: [{missile: [10, 20, 30]}]
  accepts_ammo: [blowgun_dart]
  source: carcass_crawler_3

- id: bolas
  item_type: weapon
  name: Bolas
  category: weapons
  cost_gp: 5
  weight_cn: 40
  damage: { variable: "1d2" }
  qualities: [blunt, entangle, {missile: [20, 40, 60]}]
  source: carcass_crawler_3

- id: garotte
  item_type: weapon
  name: Garotte
  category: weapons
  cost_gp: 1
  weight_cn: 5
  damage: { variable: "1d4" }
  qualities: [melee, stealth, strangle, two_handed]
  source: carcass_crawler_3

- id: net
  item_type: weapon
  name: Net
  category: weapons
  cost_gp: 5
  weight_cn: 100
  damage: { default: "", variable: "" }
  qualities: [blunt, entangle, {missile: [10, 20, 30]}]
  source: carcass_crawler_3

- id: whip
  item_type: weapon
  name: Whip
  category: weapons
  cost_gp: 10
  weight_cn: 50
  damage: { variable: "1d2" }
  qualities: [entangle, melee]
  source: carcass_crawler_3
```

Append to `data/equipment/ammunition.yaml`:

```yaml
- id: blowgun_dart
  item_type: ammunition
  name: Blowgun Darts (pouch of 5)
  category: ammunition
  cost_gp: 1
  weight_cn: 0
  bundle_count: 5
  groups: [blowgun_dart]
  source: carcass_crawler_3
  description: A pouch of 5 darts for a blowgun. The darts inflict no damage but may administer a bloodstream poison.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_content.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data/equipment/weapons.yaml data/equipment/ammunition.yaml tests/test_cc3_content.py
git commit -m "feat(data): CC3 weapons (bastard sword, blowgun, net, etc.) + blowgun darts"
```

---

## Task 10: Attack profiles — no-damage + versatile split

**Files:**
- Modify: `aose/engine/attacks.py` (`_profile_for` damage handling; `attack_profiles` versatile branch)
- Test: `tests/test_cc3_attacks.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_cc3_attacks.py`:

```python
"""Attack profiles for no-damage and versatile CC3 weapons."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine.attacks import attack_profiles
from aose.models import Ability, CharacterSpec, ClassEntry, RuleSet

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


def _fighter(data, equipped_weapons, *, variable):
    return CharacterSpec(
        name="T",
        abilities={a: 10 for a in Ability},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", xp=0)],
        alignment="neutral",
        inventory=list(equipped_weapons),
        equipped_weapons=list(equipped_weapons),
        ruleset=RuleSet(variable_weapon_damage=variable),
    )


def test_net_profile_has_no_damage(data):
    spec = _fighter(data, ["net"], variable=False)
    profs = {p.name: p for p in attack_profiles(spec, data)}
    assert profs["Net"].damage == "—"


def test_versatile_single_profile_under_standard_rule(data):
    spec = _fighter(data, ["bastard_sword"], variable=False)
    names = [p.name for p in attack_profiles(spec, data)]
    assert names.count("Bastard Sword") == 1
    assert not any("Two-handed" in n for n in names)


def test_versatile_splits_under_variable_rule(data):
    spec = _fighter(data, ["bastard_sword"], variable=True)
    profs = {p.name: p for p in attack_profiles(spec, data)}
    assert "Bastard Sword" in profs
    assert "Bastard Sword (Two-handed)" in profs
    # STR 10 → +0; 1H uses variable 1d6+1, 2H uses 1d8+1
    assert profs["Bastard Sword"].damage == "1d6+1"
    assert profs["Bastard Sword (Two-handed)"].damage == "1d8+1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_attacks.py -q`
Expected: FAIL (net damage shows `+0`-style string; no 2H profile).

- [ ] **Step 3: Handle no-damage in `_profile_for`**

In `aose/engine/attacks.py`, inside `_profile_for`, replace the `base_damage` selection and the `dmg()` helper so an empty damage string yields `"—"` with no modifier:

```python
    use_variable = spec.ruleset.variable_weapon_damage
    base_damage = weapon.damage.variable if use_variable else weapon.damage.default
    no_damage = not base_damage

    rng = None
    if weapon.ranged and weapon.range_short is not None:
        rng = (weapon.range_short, weapon.range_medium or 0, weapon.range_long or 0)

    def hit_thac0(extra: int) -> int:
        return base_thac0 - atk_mod - prof_pen - spec_hit - extra - g_atk

    def hit_asc(extra: int) -> int:
        return base_attack + atk_mod + prof_pen + spec_hit + extra + g_atk

    def dmg(extra: int) -> str:
        if no_damage:
            return "—"
        return _format_damage(base_damage, dmg_mod + g_dmg + spec_dmg + extra)
```

(The `conditional` block already calls `dmg(extra)`, so it inherits the `—` automatically.)

- [ ] **Step 4: Add the versatile-split in `attack_profiles`**

In `aose/engine/attacks.py`, add a helper near `_profile_for` that builds a two-handed variant profile, and emit it in the catalog-weapon loop. Add this function after `_profile_for`:

```python
def _two_handed_variant(base: AttackProfile, weapon: Weapon,
                        spec: CharacterSpec) -> AttackProfile | None:
    """For a versatile weapon under the variable-damage rule, a second profile
    using the two-handed die (cannot use a shield). Returns None otherwise."""
    if not (weapon.versatile and weapon.two_handed_damage
            and spec.ruleset.variable_weapon_damage):
        return None
    # Reformat the damage: swap the 1H variable die for the 2H die, keep the
    # same numeric modifier the base row computed.
    one_h = weapon.damage.variable
    two_h = weapon.two_handed_damage
    new_damage = base.damage.replace(one_h, two_h, 1) if one_h in base.damage else two_h
    return base.model_copy(update={
        "name": f"{weapon.name} (Two-handed)",
        "damage": new_damage,
        "manageable_item_id": None,
    })
```

Then in `attack_profiles`, in the `counts.items()` loop, after appending the base profile, append the variant:

```python
    counts = Counter(spec.equipped_weapons)
    weapon_profiles: list[AttackProfile] = []
    for weapon_id, count in counts.items():
        item = data.items.get(weapon_id)
        if not isinstance(item, Weapon):
            continue  # equipped_weapons should only contain weapons, defensive
        g_atk, g_dmg = _atk_dmg(mods, melee=item.melee, ranged=item.ranged)
        base = _profile_for(item, spec, data, count, eff, base_thac0, g_atk, g_dmg,
                            manageable_item_id=item.id, **_ammo_args(item))
        weapon_profiles.append(base)
        variant = _two_handed_variant(base, item, spec)
        if variant is not None:
            weapon_profiles.append(variant)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_attacks.py -q`
Expected: PASS.
Then: `.venv\Scripts\python.exe -m pytest tests/test_equip_attacks.py tests/test_cc3_attacks.py -q`
Expected: PASS (existing attack tests unaffected — no equipped weapon is versatile by default).

- [ ] **Step 6: Commit**

```bash
git add aose/engine/attacks.py tests/test_cc3_attacks.py
git commit -m "feat(attacks): no-damage profiles + versatile two-handed split"
```

---

## Task 11: New armour + wearable categories via `base_armor`

**Files:**
- Modify: `data/equipment/armor.yaml`
- Test: `tests/test_cc3_content.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cc3_content.py`:

```python
from aose.engine.proficiency import allowed_armor_ids
from aose.models import Armor

CC3_ARMOR = {
    # id: (ac_descending, movement_impact, base_armor)
    "padded_armor": (8, "leather", "leather_armor"),
    "furs": (7, "leather", "leather_armor"),
    "studded_leather": (6, "leather", "chain_mail"),
    "banded_mail": (4, "metal", "plate_mail"),
    "full_plate": (2, "metal", "plate_mail"),
}


@pytest.mark.parametrize("aid,expected", sorted(CC3_ARMOR.items()))
def test_cc3_armor_loads(data, aid, expected):
    a = data.items[aid]
    assert isinstance(a, Armor)
    ac, mv, base = expected
    assert a.ac_descending == ac
    assert a.movement_impact == mv
    assert a.base_armor == base
    assert a.source == "carcass_crawler_3"


def test_leather_user_gets_padded_and_furs_not_studded(data):
    thief = data.classes["thief"]   # armor_allowed: leather
    allowed = allowed_armor_ids([thief], data)
    assert {"padded_armor", "furs", "leather_armor"}.issubset(allowed)
    assert "studded_leather" not in allowed
    assert "full_plate" not in allowed


def test_plate_user_gets_banded_and_full_plate(data):
    fighter = data.classes["fighter"]  # armor_allowed: all
    assert allowed_armor_ids([fighter], data) == "all"
    # A plate-restricted class: knight (verify its armor_allowed includes plate)
```

Note: `allowed_armor_ids` for a leather-only class works because `padded_armor`/`furs` declare `base_armor: leather_armor`, and `base_armor_id` is what the equip/allowance check reads. The thief's `armor_allowed: [leather]` resolves to `{leather_armor}`; the new armours are admitted at equip time via `base_armor_id`, but `allowed_armor_ids` itself returns the resolved *class entry* set. **Verify** by reading `equip.py:69` — the check is `base_armor_id(item) not in allowed_armor`, so `padded_armor` (base `leather_armor`) passes. Adjust the test to assert via `equip`:

```python
def test_leather_user_can_equip_padded_not_studded(data):
    from aose.engine.equip import equip
    from aose.engine.proficiency import allowed_armor_ids, shields_allowed
    thief = data.classes["thief"]
    allowed = allowed_armor_ids([thief], data)
    inv = ["padded_armor", "studded_leather"]
    eq, _ = equip(inv, {}, [], "padded_armor", data, allowed_armor=allowed)
    assert eq["armor"] == "padded_armor"
    with pytest.raises(ValueError):
        equip(inv, {}, [], "studded_leather", data, allowed_armor=allowed)
```

Use this `equip`-based test as the authoritative allowance check and drop the brittle subset assertions if they don't hold.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_content.py -k armor -q`
Expected: FAIL (KeyError on new armour ids).

- [ ] **Step 3: Append the armour**

Append to `data/equipment/armor.yaml`:

```yaml
# ── Carcass Crawler 3 armour ─────────────────────────────────────────────────
- id: padded_armor
  item_type: armor
  name: Padded Armour
  category: armor
  cost_gp: 5
  weight_cn: 100
  ac_descending: 8
  movement_impact: leather
  base_armor: leather_armor
  groups: [leather_armour]
  source: carcass_crawler_3
  description: Layers of cloth and quilted padding.

- id: furs
  item_type: armor
  name: Furs
  category: armor
  cost_gp: 10
  weight_cn: 250
  ac_descending: 7
  movement_impact: leather
  base_armor: leather_armor
  groups: [leather_armour]
  source: carcass_crawler_3
  description: Thickly layered furs and pelts of any kind.

- id: studded_leather
  item_type: armor
  name: Studded Leather
  category: armor
  cost_gp: 25
  weight_cn: 300
  ac_descending: 6
  movement_impact: leather
  base_armor: chain_mail
  groups: [leather_armour]
  source: carcass_crawler_3
  description: A suit of flexible leather studded with hundreds of metal rivets.

- id: banded_mail
  item_type: armor
  name: Banded Mail
  category: armor
  cost_gp: 50
  weight_cn: 450
  ac_descending: 4
  movement_impact: metal
  base_armor: plate_mail
  groups: [metal_armour]
  source: carcass_crawler_3
  description: Horizontal bands of metal riveted to a padded leather backing, with chain mail at the joints.

- id: full_plate
  item_type: armor
  name: Full Plate
  category: armor
  cost_gp: 1000
  weight_cn: 700
  ac_descending: 2
  untailored_ac_descending: 3
  tailorable: true
  movement_impact: metal
  base_armor: plate_mail
  groups: [metal_armour]
  source: carcass_crawler_3
  description: Perfectly interlocking plates over chain mail and padding. Crafted and tailored for a specific wearer; another person's full plate grants only AC 3 [16].
```

Note: `full_plate` uses `tailorable`/`untailored_ac_descending` fields added in Task 12 — if running this task first, temporarily omit those two lines and add them in Task 12. (Recommended: do Task 12's model change first, then this step won't error.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_content.py -k armor -q`
Expected: PASS (after Task 12's model fields exist).

- [ ] **Step 5: Commit**

```bash
git add data/equipment/armor.yaml tests/test_cc3_content.py
git commit -m "feat(data): CC3 armour with base_armor wearable categories"
```

---

## Task 12: Tailorable full plate (model + AC engine)

**Files:**
- Modify: `aose/models/item.py` (`Armor`)
- Modify: `aose/models/character.py` (`CharacterSpec.armor_tailored`)
- Modify: `aose/engine/armor_class.py:81-93` (`_compute_ac`)
- Test: `tests/test_cc3_armor_ac.py` (new)

> Do this task BEFORE Task 11's data step so the `full_plate` fields validate.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cc3_armor_ac.py`:

```python
"""Full plate AC: tailored (2 [17]) vs untailored (3 [16])."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine.armor_class import armor_class
from aose.models import Ability, CharacterSpec, ClassEntry

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


def _knight_in_plate(tailored):
    return CharacterSpec(
        name="T",
        abilities={a: 10 for a in Ability},   # DEX 10 → +0
        race_id="human",
        classes=[ClassEntry(class_id="fighter", xp=0)],
        alignment="neutral",
        inventory=["full_plate"],
        equipped={"armor": "full_plate"},
        armor_tailored=tailored,
    )


def test_full_plate_tailored_is_ac2(data):
    desc, asc = armor_class(_knight_in_plate(True), data, use_shield=False)
    assert desc == 2 and asc == 17


def test_full_plate_untailored_is_ac3(data):
    desc, asc = armor_class(_knight_in_plate(False), data, use_shield=False)
    assert desc == 3 and asc == 16


def test_default_armor_tailored_is_true(data):
    spec = _knight_in_plate(True)
    assert spec.armor_tailored is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_armor_ac.py -q`
Expected: FAIL (`armor_tailored` not a field / full_plate missing).

- [ ] **Step 3: Add model fields**

In `aose/models/item.py`, extend `Armor`:

```python
class Armor(ItemBase):
    item_type: Literal["armor"]
    ac_descending: int
    movement_impact: Literal["none", "leather", "metal"] = "metal"
    is_shield: bool = False
    groups: list[str] = Field(default_factory=list)
    ac_bonus: int = 0
    magic_bonus: int = 0
    weight_multiplier: float = 1.0
    base_armor: str | None = None
    # Tailorable armour (full plate): worn by its fitted owner it grants
    # ``ac_descending``; worn by anyone else, the worse ``untailored_ac_descending``.
    tailorable: bool = False
    untailored_ac_descending: int | None = None
```

In `aose/models/character.py`, add to `CharacterSpec` (near `equipped`, ~line 193):

```python
    # Whether the equipped tailorable body armour (full plate) is fitted to this
    # character. Inert unless the worn armour is `tailorable`; a single toggle
    # (one body-armour slot), remembered across re-equips.
    armor_tailored: bool = True
```

- [ ] **Step 4: Apply the AC adjustment**

In `aose/engine/armor_class.py`, in `_compute_ac`, replace the mundane-armour base block (lines ~82-88):

```python
        armor_id = spec.equipped.get("armor")
        if armor_id and armor_id in data.items:
            item = data.items[armor_id]
            if isinstance(item, Armor) and not item.is_shield:
                ac_desc = item.ac_descending
                if (item.tailorable and not spec.armor_tailored
                        and item.untailored_ac_descending is not None):
                    ac_desc = item.untailored_ac_descending
                cand = ac_desc - item.magic_bonus
                if cand < base:
                    base, base_source = cand, item.name
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_armor_ac.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/models/item.py aose/models/character.py aose/engine/armor_class.py tests/test_cc3_armor_ac.py
git commit -m "feat(armor): tailorable full plate AC adjustment"
```

---

## Task 13: Cleric blunt allowance (quality-based weapon allowance)

**Files:**
- Modify: `aose/models/character_class.py` (`CharClass.weapon_qualities_allowed`)
- Modify: `aose/engine/proficiency.py:182-198` (`allowed_weapon_ids`)
- Modify: `data/classes/cleric.yaml`, `data/classes/acolyte.yaml`
- Test: `tests/test_cc3_content.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cc3_content.py`:

```python
from aose.engine.proficiency import allowed_weapon_ids


def test_cleric_can_use_all_blunt_weapons(data):
    cleric = data.classes["cleric"]
    allowed = allowed_weapon_ids([cleric], data)
    assert allowed != "all"
    # core blunt
    assert {"club", "mace", "sling", "staff", "war_hammer"}.issubset(allowed)
    # CC3 blunt picked up automatically
    assert {"blackjack", "bolas", "net"}.issubset(allowed)
    # non-blunt excluded
    assert "sword" not in allowed and "dagger" not in allowed


def test_acolyte_also_blunt_only(data):
    allowed = allowed_weapon_ids([data.classes["acolyte"]], data)
    assert "blackjack" in allowed and "sword" not in allowed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_content.py -k "cleric or acolyte" -q`
Expected: FAIL (blackjack not in cleric's explicit list).

- [ ] **Step 3: Add the class field**

In `aose/models/character_class.py`, add to `CharClass` (after `optional_weapons_allowed`):

```python
    # Weapon qualities that grant usage of EVERY weapon bearing them (data-driven
    # class restriction). Cleric/acolyte use [blunt] — "May be used by clerics".
    weapon_qualities_allowed: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Expand allowances by quality**

In `aose/engine/proficiency.py`, in `allowed_weapon_ids`, after the optional-weapons union and before `per_class.append(resolved)`:

```python
        if cls.weapon_qualities_allowed and resolved != "all":
            wanted = set(cls.weapon_qualities_allowed)
            by_quality = {w.id for w in weapons if w.quality_ids & wanted}
            resolved = resolved | by_quality
        per_class.append(resolved)
```

- [ ] **Step 5: Update cleric and acolyte data**

In `data/classes/cleric.yaml`, replace the `weapons_allowed` block (lines 9-14) with:

```yaml
weapons_allowed: []   # blunt-only — see weapon_qualities_allowed
weapon_qualities_allowed:
- blunt
```

In `data/classes/acolyte.yaml`, replace its `weapons_allowed` block (lines 10-15) with the same two keys.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_content.py -k "cleric or acolyte" tests/test_equip_enforcement.py -q`
Expected: PASS (the existing `test_cleric_weapon_list_resolved_with_spaces` uses `.issubset`, so it stays green; the new set is a superset).

- [ ] **Step 7: Commit**

```bash
git add aose/models/character_class.py aose/engine/proficiency.py data/classes/cleric.yaml data/classes/acolyte.yaml tests/test_cc3_content.py
git commit -m "feat(allowance): blunt quality grants cleric/acolyte weapon usage"
```

---

## Task 14: Tailored toggle UI (sheet view + route + template)

**Files:**
- Modify: `aose/sheet/view.py` (CharacterSheet field + build_sheet)
- Modify: `aose/web/routes.py` (new route)
- Modify: `aose/web/templates/_equipment_ui.html` (checkbox)
- Test: `tests/test_rest_routes.py` pattern → `tests/test_cc3_armor_ac.py` (extend with a route test)

- [ ] **Step 1: Write the failing route test**

Append to `tests/test_cc3_armor_ac.py`:

```python
def test_tailored_route_flips_flag(tmp_path):
    from fastapi.testclient import TestClient
    from aose.web.app import app
    from aose.characters.storage import save_character
    import aose.web.app as appmod

    data = GameData.load(DATA_DIR)
    app.state.game_data = data
    app.state.characters_dir = tmp_path
    spec = _knight_in_plate(True)
    save_character("c1", spec, tmp_path)

    client = TestClient(app)
    r = client.post("/character/c1/equipment/tailored",
                    data={"value": "false"}, follow_redirects=False)
    assert r.status_code == 303
    from aose.characters.storage import load_character
    assert load_character("c1", tmp_path).armor_tailored is False
```

(If the existing route tests use a different client/fixture wiring, mirror `tests/test_rest_routes.py` exactly instead of the above.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_armor_ac.py -k tailored -q`
Expected: FAIL (404 — route missing).

- [ ] **Step 3: Add the route**

In `aose/web/routes.py`, after `set_carrying_treasure` (line ~321), add:

```python
@router.post("/character/{character_id}/equipment/tailored")
async def set_armor_tailored(request: Request, character_id: str,
                             value: str = Form(...)):
    """Flip whether the equipped tailorable body armour is fitted to the wearer."""
    spec = _load_spec_or_404(request, character_id)
    spec.armor_tailored = value.lower() in ("true", "1", "on", "yes")
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Expose the flag on the sheet view**

In `aose/sheet/view.py`, add two fields to the `CharacterSheet` model (near `armor_movement_class`, line ~387):

```python
    armor_tailorable: bool = False   # equipped body armour can be tailored (full plate)
    armor_tailored: bool = True      # and is currently fitted to this wearer
```

In `build_sheet` (before the `CharacterSheet(...)` return, ~line 1249), compute:

```python
    _armor_id = spec.equipped.get("armor")
    _armor_item = data.items.get(_armor_id) if _armor_id else None
    _armor_tailorable = bool(getattr(_armor_item, "tailorable", False))
```

and pass `armor_tailorable=_armor_tailorable, armor_tailored=spec.armor_tailored` into the `CharacterSheet(...)` constructor.

- [ ] **Step 5: Add the checkbox to the equipment drawer**

In `aose/web/templates/_equipment_ui.html`, after the equipped `inv_table` (line ~160), add a guarded toggle (the wizard context doesn't define `sheet`, so guard on it):

```html
{% if sheet is defined and sheet.armor_tailorable %}
<form method="post"
      action="/character/{{ character_id }}/equipment/tailored"
      class="tailored-toggle">
  <input type="hidden" name="value" value="{{ 'false' if sheet.armor_tailored else 'true' }}">
  <label>
    <input type="checkbox" disabled {{ 'checked' if sheet.armor_tailored else '' }}>
    Tailored to wearer
  </label>
  <button type="submit" class="link-button">
    {{ 'Mark as another’s plate (AC 3)' if sheet.armor_tailored else 'Mark as tailored (AC 2)' }}
  </button>
</form>
{% endif %}
```

Confirm the template receives `sheet` and `character_id` in the sheet render context (grep `_equipment_ui.html` include site in `sheet.html`); if `character_id` is named differently, use the existing variable.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_armor_ac.py -q`
Expected: PASS.

- [ ] **Step 7: Manually verify in the app**

Run the server: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`, create/open a character with full plate equipped, confirm the toggle appears and flipping it changes the AC headline 2 ↔ 3.

- [ ] **Step 8: Commit**

```bash
git add aose/sheet/view.py aose/web/routes.py aose/web/templates/_equipment_ui.html tests/test_cc3_armor_ac.py
git commit -m "feat(sheet): tailored-full-plate toggle in equipment drawer"
```

---

## Task 15: Docs (architecture + changelog)

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: Update ARCHITECTURE.md**

Under "## Attacks & ammunition", add a paragraph documenting that weapon qualities are the source of truth (parametric `{missile:[…]}` / `{versatile:"die"}`, `two_handed`⟹hands, `melee`/`missile` presence ⟹ melee/ranged, all as computed `Weapon` properties; loader validation; no-damage = empty `damage`; versatile splits into a 2H profile under the variable rule). Update the inventory/armour section to note `tailorable`/`untailored_ac_descending` + `CharacterSpec.armor_tailored`. Update the content-sources / allowances note to mention `CharClass.weapon_qualities_allowed` (cleric/acolyte = `[blunt]`) and the `carcass_crawler_3` source.

- [ ] **Step 2: Update CHANGELOG.md**

Add one row at the top:

```
| 2026-06-09 | CC3 expanded equipment + parametric weapon qualities | main | 2026-06-09-cc3-expanded-equipment |
```

(Match the existing column format in the file.)

- [ ] **Step 3: Run the full suite one final time**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing `pytest-current` PermissionError).

- [ ] **Step 4: Commit**

```bash
git add docs/ARCHITECTURE.md docs/CHANGELOG.md
git commit -m "docs: record CC3 equipment + parametric weapon qualities"
```

---

## Self-review notes (for the implementer)

- **Task ordering caveat:** Do **Task 12** (model fields) before **Task 11 Step 3** (full_plate data uses `tailorable`/`untailored_ac_descending`), or temporarily omit those two YAML lines. The plan flags this inline.
- **Existing tests to watch:** `test_detail_cards.py` / `test_detail_views.py` may assert old lowercase quality strings — update to the new `_format_qualities` output (Task 5). `test_models.py` may construct a `Weapon` with `hands=`/`melee=` kwargs — update to `qualities=`. `test_cleric_weapon_list_resolved_with_spaces` stays green (subset check).
- **No-damage + variable rule:** `dmg()` keys off the rule-selected `base_damage`; both `default` and `variable` are `""` for net/blowgun, so `—` shows in either mode.
- **Versatile variant** reuses the base profile's computed to-hit and only swaps the damage die — proficiency, specialisation, and global mods carry over correctly.
