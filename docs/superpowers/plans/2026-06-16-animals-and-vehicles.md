# Animals & Vehicles (Companions & Holdings — Phase A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a character buy animals and vehicles (official OSE Classic Fantasy content) and use each owned one as a top-level storage location with its own load capacity, including a mundane animal-armour slot.

**Architecture:** Animals/vehicles are new `Item` discriminated-union variants bought through the existing shop into per-instance roster lists on `CharacterSpec` (mirroring `ContainerInstance`). Each instance is a storage location; loaded gear checks against the carrier's capacity and never touches the PC's encumbrance. Combat stats (ascending AC, THAC0/attack bonus, saves) are derived from HD by table lookup in a new cycle-free `monster_stats` engine; only descending AC + HD are stored.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, pytest. Tests run with `.venv\Scripts\python.exe -m pytest`. App runs with `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`.

**Spec:** [`docs/superpowers/specs/2026-06-16-animals-and-vehicles-design.md`](../specs/2026-06-16-animals-and-vehicles-design.md)

**Conventions to honour:**
- No migrations — new `CharacterSpec` fields default empty so old saves load.
- Data, not code — no engine module references a specific animal/vehicle id.
- Keep engine modules cycle-free (`monster_stats` imports models/loader only).
- All routes mutate by URL: load spec → mutate → `save_character` → 303 redirect.
- The trailing `pytest-current` PermissionError on Windows is a known quirk; ignore it.

---

## Checkpoint 1 — Models & data foundation

### Task 1: Animal / Vehicle / AnimalArmor item variants

**Files:**
- Modify: `aose/models/item.py`
- Modify: `aose/models/__init__.py`
- Test: `tests/test_animal_vehicle_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_animal_vehicle_models.py
from pydantic import TypeAdapter
from aose.models import Animal, Vehicle, AnimalArmor, AnimalAttack, Item


def test_animal_parses_via_item_union():
    raw = {
        "item_type": "animal", "id": "mule", "name": "Mule",
        "category": "animals", "cost_gp": 30, "hd": "2", "save_as_hd": "NH",
        "hp": 9, "ac": 7, "morale": 8, "alignment": "neutral", "xp": 20,
        "movement": "120' (40')",
        "attacks": [{"name": "kick", "damage": "1d4"},
                    {"name": "bite", "damage": "1d3", "note": "or"}],
        "max_load_unencumbered_cn": 2000, "max_load_encumbered_cn": 4000,
        "traits": ["Tenacious", "Defensive"],
    }
    animal = TypeAdapter(Item).validate_python(raw)
    assert isinstance(animal, Animal)
    assert animal.hd == "2"
    assert animal.save_as_hd == "NH"
    assert animal.attacks[0] == AnimalAttack(name="kick", damage="1d4")
    assert animal.source == "ose_classic_fantasy"  # default


def test_vehicle_parses_via_item_union():
    raw = {
        "item_type": "vehicle", "id": "cart", "name": "Cart",
        "category": "vehicles", "cost_gp": 100, "vehicle_category": "land_vehicle",
        "ac": 9, "hull_points": "1d4", "cargo_capacity_cn": 4000,
        "cargo_capacity_extra_cn": 8000, "required_animals": "1 draft horse or 2 mules",
        "movement": "60' (20')", "traits": [],
    }
    vehicle = TypeAdapter(Item).validate_python(raw)
    assert isinstance(vehicle, Vehicle)
    assert vehicle.hull_points == "1d4"
    assert vehicle.cargo_capacity_extra_cn == 8000


def test_animal_armor_parses_via_item_union():
    raw = {
        "item_type": "animal_armor", "id": "horse_barding", "name": "Horse barding",
        "category": "tack_and_harness", "cost_gp": 150, "weight_cn": 600,
        "sets_ac": 5, "fits": ["draft_horse", "riding_horse", "war_horse"],
    }
    armor = TypeAdapter(Item).validate_python(raw)
    assert isinstance(armor, AnimalArmor)
    assert armor.sets_ac == 5
    assert "war_horse" in armor.fits
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_animal_vehicle_models.py -q`
Expected: FAIL with `ImportError: cannot import name 'Animal'`.

- [ ] **Step 3: Add the models**

In `aose/models/item.py`, after the `Ammunition` class and before the `Item =` union, add:

```python
class AnimalAttack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str                       # "bite", "hoof", "kick"
    count: int = 1                  # attacks per round of this kind
    damage: str                     # "1d4", "1", "2d4"
    note: str | None = None         # e.g. "or" to flag an alternative routine


class Animal(ItemBase):
    item_type: Literal["animal"]
    hd: str                         # HD rating, e.g. "2", "1+2", "½" → THAC0/XP
    save_as_hd: int | str           # parenthesised save-as ("NH" or int) → saves
    hp: int                         # average hp (the parenthesised value)
    ac: int                         # descending; ascending derived (19 - ac)
    attacks: list[AnimalAttack] = Field(default_factory=list)
    morale: int
    alignment: Literal["law", "neutral", "chaos", "any"] = "neutral"
    xp: int = 0
    movement: str                   # "150' (50')" base (encounter)
    miles_per_day: int | None = None
    max_load_unencumbered_cn: int | None = None
    max_load_encumbered_cn: int | None = None
    movement_encumbered: str | None = None
    miles_per_day_encumbered: int | None = None
    armor_fits: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)


class Vehicle(ItemBase):
    item_type: Literal["vehicle"]
    vehicle_category: Literal["land_vehicle", "water_vessel"]
    ac: int                         # descending; ascending derived
    hull_points: str                # dice ("1d4") OR range ("60-90")
    cargo_capacity_cn: int
    cargo_capacity_extra_cn: int | None = None
    required_animals: str | None = None
    required_crew: str | None = None
    miles_per_day: str | None = None
    movement: str | None = None
    max_mercenaries: int | None = None
    seaworthy: bool | None = None
    requires_captain: bool | None = None
    passengers: str | None = None
    dimensions: str | None = None
    traits: list[str] = Field(default_factory=list)


class AnimalArmor(ItemBase):
    item_type: Literal["animal_armor"]
    sets_ac: int                    # descending; replaces natural AC
    fits: list[str] = Field(default_factory=list)
```

Then extend the union at the bottom of the file:

```python
Item = Annotated[
    Union[Weapon, Armor, AdventuringGear, Poison, Container, MagicItem,
          Ammunition, Animal, Vehicle, AnimalArmor],
    Field(discriminator="item_type"),
]
```

In `aose/models/__init__.py`, add `Animal, AnimalArmor, AnimalAttack, Vehicle` to the `from .item import (...)` block and to `__all__`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_animal_vehicle_models.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/models/item.py aose/models/__init__.py tests/test_animal_vehicle_models.py
git commit -m "feat(models): Animal/Vehicle/AnimalArmor item variants"
```

---

### Task 2: Roster instances + container location

**Files:**
- Modify: `aose/models/character.py`
- Modify: `aose/models/__init__.py`
- Test: `tests/test_companion_instances.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_companion_instances.py
from aose.models import (
    CharacterSpec, AnimalInstance, VehicleInstance, ContainerInstance,
)


def _bare_spec(**kw):
    return CharacterSpec(
        name="Hero", abilities={"str": 10, "int": 10, "wis": 10,
                                "dex": 10, "con": 10, "cha": 10},
        race_id="human", classes=[{"class_id": "fighter"}],
        alignment="neutral", **kw,
    )


def test_spec_defaults_have_empty_companions():
    spec = _bare_spec()
    assert spec.animals == []
    assert spec.vehicles == []


def test_animal_and_vehicle_instances_round_trip():
    spec = _bare_spec(
        animals=[AnimalInstance(instance_id="a1", catalog_id="mule")],
        vehicles=[VehicleInstance(instance_id="v1", catalog_id="cart", hull_max=4)],
    )
    again = CharacterSpec.model_validate(spec.model_dump())
    assert again.animals[0].catalog_id == "mule"
    assert again.vehicles[0].hull_max == 4
    assert again.animals[0].hp_damage == 0
    assert again.animals[0].armor_id is None


def test_container_location_defaults_to_person():
    c = ContainerInstance(instance_id="c1", catalog_id="backpack", state="carried")
    assert c.location == "person"
    assert c.location_id is None


def test_old_save_without_companions_still_loads():
    # A dict shaped like a pre-feature save (no animals/vehicles keys).
    raw = _bare_spec().model_dump()
    raw.pop("animals"); raw.pop("vehicles")
    spec = CharacterSpec.model_validate(raw)
    assert spec.animals == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companion_instances.py -q`
Expected: FAIL with `ImportError: cannot import name 'AnimalInstance'`.

- [ ] **Step 3: Add the models**

In `aose/models/character.py`, add `location`/`location_id` to `ContainerInstance` (after `state`):

```python
    # A container is normally on the person (carried/stashed via ``state``).
    # When loaded onto an animal/vehicle, ``location`` names the carrier kind
    # and ``location_id`` its instance_id; its weight then counts toward that
    # carrier, not the PC. Defaults keep old saves valid.
    location: Literal["person", "animal", "vehicle"] = "person"
    location_id: str | None = None
```

Add two new models (before `CharacterSpec`):

```python
class AnimalInstance(BaseModel):
    """A specific animal the character owns — per-instance state separate from
    the catalog ``Animal``.  Acts as a top-level storage location: ``contents``
    are loose item ids loaded onto the animal, never in ``inventory``."""
    model_config = ConfigDict(extra="forbid")

    instance_id: str                 # uuid4 hex
    catalog_id: str                  # references an Animal
    name: str = ""                   # optional label
    hp_damage: int = 0               # current hp = max(0, catalog.hp - hp_damage)
    armor_id: str | None = None      # references an AnimalArmor in catalog.armor_fits
    contents: list[str] = Field(default_factory=list)
    magic_note: str = ""             # free-text placeholder until magic items land


class VehicleInstance(BaseModel):
    """A specific vehicle the character owns.  Acts as a top-level storage
    location; ``contents`` are loose cargo ids."""
    model_config = ConfigDict(extra="forbid")

    instance_id: str
    catalog_id: str                  # references a Vehicle
    name: str = ""
    hull_max: int                    # resolved from catalog.hull_points at purchase
    hull_damage: int = 0
    contents: list[str] = Field(default_factory=list)
    extra_animals: bool = False      # raises cap to cargo_capacity_extra_cn
    note: str = ""
```

Add fields to `CharacterSpec` (next to `containers`):

```python
    animals: list[AnimalInstance] = Field(default_factory=list)
    vehicles: list[VehicleInstance] = Field(default_factory=list)
```

In `aose/models/__init__.py`, add `AnimalInstance, VehicleInstance` to the `from .character import (...)` block and `__all__`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companion_instances.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/models/character.py aose/models/__init__.py tests/test_companion_instances.py
git commit -m "feat(models): animal/vehicle roster instances + container location"
```

---

### Task 3: `monster_stats` engine + lookup tables

**Files:**
- Create: `data/monster_attack_matrix.yaml`
- Create: `data/monster_saves.yaml`
- Create: `aose/engine/monster_stats.py`
- Modify: `aose/data/loader.py`
- Test: `tests/test_monster_stats.py`

- [ ] **Step 1: Create the data tables**

`data/monster_attack_matrix.yaml`:

```yaml
nh:          {thac0: 20, attack_bonus: -1}
up_to_1:     {thac0: 19, attack_bonus: 0}
"1+_to_2":   {thac0: 18, attack_bonus: 1}
"2+_to_3":   {thac0: 17, attack_bonus: 2}
"3+_to_4":   {thac0: 16, attack_bonus: 3}
"4+_to_5":   {thac0: 15, attack_bonus: 4}
"5+_to_6":   {thac0: 14, attack_bonus: 5}
"6+_to_7":   {thac0: 13, attack_bonus: 6}
"7+_to_9":   {thac0: 12, attack_bonus: 7}
"9+_to_11":  {thac0: 11, attack_bonus: 8}
"11+_to_13": {thac0: 10, attack_bonus: 9}
"13+_to_15": {thac0: 9,  attack_bonus: 10}
"15+_to_17": {thac0: 8,  attack_bonus: 11}
"17+_to_19": {thac0: 7,  attack_bonus: 12}
"19+_to_21": {thac0: 6,  attack_bonus: 13}
"21+":       {thac0: 5,  attack_bonus: 14}
```

`data/monster_saves.yaml`:

```yaml
nh:      {death: 14, wands: 15, paralysis: 16, breath: 17, spells: 18}
"1-3":   {death: 12, wands: 13, paralysis: 14, breath: 15, spells: 16}
"4-6":   {death: 10, wands: 11, paralysis: 12, breath: 13, spells: 14}
"7-9":   {death: 8,  wands: 9,  paralysis: 10, breath: 10, spells: 12}
"10-12": {death: 6,  wands: 7,  paralysis: 8,  breath: 8,  spells: 10}
"13-15": {death: 4,  wands: 5,  paralysis: 6,  breath: 5,  spells: 8}
"16-18": {death: 2,  wands: 3,  paralysis: 4,  breath: 3,  spells: 6}
"19-21": {death: 2,  wands: 2,  paralysis: 2,  breath: 2,  spells: 4}
"22+":   {death: 2,  wands: 2,  paralysis: 2,  breath: 2,  spells: 2}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_monster_stats.py
import pytest
from pathlib import Path
from aose.data.loader import GameData
from aose.engine import monster_stats as ms

DATA = GameData.load(Path("data"))


@pytest.mark.parametrize("hd,thac0,ab", [
    ("½", 19, 0), ("1", 19, 0), ("2", 18, 1), ("3", 17, 2),
    ("1+2", 18, 1), ("2+2", 17, 2), ("NH", 20, -1),
])
def test_attack_for_hd(hd, thac0, ab):
    stats = ms.attack_for_hd(hd, DATA)
    assert stats.thac0 == thac0
    assert stats.attack_bonus == ab


@pytest.mark.parametrize("save_as,expected", [
    ("NH", {"death": 14, "wands": 15, "paralysis": 16, "breath": 17, "spells": 18}),
    (1, {"death": 12, "wands": 13, "paralysis": 14, "breath": 15, "spells": 16}),
    (2, {"death": 12, "wands": 13, "paralysis": 14, "breath": 15, "spells": 16}),
    (5, {"death": 10, "wands": 11, "paralysis": 12, "breath": 13, "spells": 14}),
])
def test_saves_for_hd(save_as, expected):
    assert ms.saves_for_hd(save_as, DATA) == expected


@pytest.mark.parametrize("desc,asc", [(7, 12), (9, 10), (8, 11)])
def test_ascending_ac(desc, asc):
    assert ms.ascending_ac(desc) == asc
```

- [ ] **Step 3: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_monster_stats.py -q`
Expected: FAIL — `monster_attack_matrix`/`monster_saves` not loaded and module missing.

- [ ] **Step 4: Load the tables in `GameData`**

In `aose/data/loader.py`, add a generic table loader after `_load_sources`:

```python
def _load_table(data_dir: Path, filename: str) -> dict:
    """Read a flat mapping table (band -> values). Empty dict if absent."""
    path = data_dir / filename
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{filename} must be a YAML mapping")
    return raw
```

Add two fields to the `GameData` dataclass:

```python
    monster_attack_matrix: dict = field(default_factory=dict)
    monster_saves: dict = field(default_factory=dict)
```

And populate them in `GameData.load(...)`'s returned `cls(...)`:

```python
            monster_attack_matrix=_load_table(data_dir, "monster_attack_matrix.yaml"),
            monster_saves=_load_table(data_dir, "monster_saves.yaml"),
```

- [ ] **Step 5: Write the engine module**

`aose/engine/monster_stats.py`:

```python
"""Derive monster / normal-human combat stats from Hit Dice via table lookup.

Cycle-free: imports only the loader's GameData type. The single home for
"given HD, what are the THAC0 / attack bonus / saving throws". AC is stored
descending; ascending is the 19-minus convention used across the app.
"""
from __future__ import annotations

from pydantic import BaseModel

from aose.data.loader import GameData


class AttackStats(BaseModel):
    thac0: int
    attack_bonus: int


def ascending_ac(descending: int) -> int:
    """AOSE descending→ascending AC: AAC = 19 − descending (AC 9 → 10, 7 → 12)."""
    return 19 - descending


# Attack-matrix bands in ascending order, each as (lower_exclusive, key).
# A band covers HD strictly greater than `lower` up to the next band's lower.
_ATTACK_BANDS = [
    (1, "1+_to_2"), (2, "2+_to_3"), (3, "3+_to_4"), (4, "4+_to_5"),
    (5, "5+_to_6"), (6, "6+_to_7"), (7, "7+_to_9"), (9, "9+_to_11"),
    (11, "11+_to_13"), (13, "13+_to_15"), (15, "15+_to_17"),
    (17, "17+_to_19"), (19, "19+_to_21"), (21, "21+"),
]


def hd_to_attack_band(hd: str) -> str:
    """Map an HD-rating string to an attack-matrix band key.

    "NH" → nh; "½"/"0"/"1" → up_to_1; "N+x" (any plus) → band starting at N;
    a plain integer N ≥ 2 → band whose top is N.
    """
    s = str(hd).strip()
    if s.upper() == "NH":
        return "nh"
    if s in ("½", "1/2", "0", "1"):
        return "up_to_1"
    has_plus = "+" in s
    base = int(s.split("+", 1)[0])
    if base <= 1 and not has_plus:
        return "up_to_1"
    # "N+x" sits in the band whose lower bound is N; a plain "N" sits in the
    # band whose lower bound is N-1. Normalise to a "lower exclusive" value.
    lower = base if has_plus else base - 1
    for lo, key in _ATTACK_BANDS:
        if lower < lo or (lower == lo):
            if lower <= lo:
                return key
    return "21+"


def attack_for_hd(hd: str, data: GameData) -> AttackStats:
    row = data.monster_attack_matrix[hd_to_attack_band(hd)]
    return AttackStats(thac0=row["thac0"], attack_bonus=row["attack_bonus"])


# Save bands: (inclusive_upper, key). "NH" handled separately.
_SAVE_BANDS = [
    (3, "1-3"), (6, "4-6"), (9, "7-9"), (12, "10-12"),
    (15, "13-15"), (18, "16-18"), (21, "19-21"),
]


def _save_band(save_as_hd: int | str) -> str:
    if str(save_as_hd).upper() == "NH":
        return "nh"
    n = int(save_as_hd)
    for upper, key in _SAVE_BANDS:
        if n <= upper:
            return key
    return "22+"


def saves_for_hd(save_as_hd: int | str, data: GameData) -> dict[str, int]:
    return dict(data.monster_saves[_save_band(save_as_hd)])
```

> Note: the `hd_to_attack_band` loop is simpler than it looks — fix it to the
> minimal correct form in Step 6 if any parametrized case fails; the test set
> (`½,1,2,3,1+2,2+2,NH`) is the contract.

- [ ] **Step 6: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_monster_stats.py -q`
Expected: PASS. If `hd_to_attack_band` mis-bands a plain integer, replace its loop with:

```python
    for lo, key in _ATTACK_BANDS:
        if lower <= lo:
            return key
    return "21+"
```

(and delete the nested `if` above it). Re-run until green.

- [ ] **Step 7: Commit**

```bash
git add data/monster_attack_matrix.yaml data/monster_saves.yaml aose/engine/monster_stats.py aose/data/loader.py tests/test_monster_stats.py
git commit -m "feat(engine): monster_stats — HD→THAC0/saves table lookup + AC conversion"
```

---

### Task 4: Import the catalog data (animals, vehicles, tack)

**Files:**
- Create: `data/equipment/animals.yaml`
- Create: `data/equipment/vehicles.yaml`
- Create: `data/equipment/tack.yaml`
- Test: `tests/test_companion_data.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_companion_data.py
from pathlib import Path
from aose.data.loader import GameData
from aose.models import Animal, Vehicle, AnimalArmor, Container
from aose.engine import monster_stats as ms

DATA = GameData.load(Path("data"))

ANIMAL_IDS = {"camel", "draft_horse", "riding_horse", "war_horse", "mule",
              "hunting_dog", "war_dog"}
LAND_VEHICLE_IDS = {"cart", "wagon"}


def test_all_animals_load():
    for aid in ANIMAL_IDS:
        assert isinstance(DATA.items[aid], Animal), aid


def test_land_vehicles_load():
    for vid in LAND_VEHICLE_IDS:
        v = DATA.items[vid]
        assert isinstance(v, Vehicle) and v.vehicle_category == "land_vehicle"


def test_tack_loads_and_armor_fits_resolve():
    assert isinstance(DATA.items["horse_barding"], AnimalArmor)
    assert isinstance(DATA.items["dog_armour"], AnimalArmor)
    assert isinstance(DATA.items["saddle_bags"], Container)
    assert DATA.items["saddle_bags"].capacity_cn == 300
    # every armor_fits / fits cross-reference resolves to a real catalog id
    for a in (i for i in DATA.items.values() if isinstance(i, Animal)):
        for armor_id in a.armor_fits:
            assert armor_id in DATA.items, f"{a.id} fits unknown {armor_id}"


def test_every_animal_hd_resolves_in_tables():
    for a in (i for i in DATA.items.values() if isinstance(i, Animal)):
        ms.attack_for_hd(a.hd, DATA)        # raises KeyError if a band is missing
        ms.saves_for_hd(a.save_as_hd, DATA)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companion_data.py -q`
Expected: FAIL with `KeyError: 'camel'`.

- [ ] **Step 3: Create `data/equipment/animals.yaml`**

```yaml
- item_type: animal
  id: camel
  name: Camel
  category: animals
  cost_gp: 100
  hd: "2"
  save_as_hd: 1
  hp: 9
  ac: 7
  attacks:
    - {name: bite, damage: "1"}
    - {name: hoof, damage: "1d4"}
  morale: 7
  alignment: neutral
  xp: 20
  movement: "150' (50')"
  miles_per_day: 30
  max_load_unencumbered_cn: 3000
  max_load_encumbered_cn: 6000
  movement_encumbered: "75' (25')"
  miles_per_day_encumbered: 15
  description: >-
    Irascible animals that are adapted to life in dry climates. Often used for
    transportation in deserts.
  traits:
    - "Ill-tempered: Bite or kick creatures in their way, including owners."
    - "Water: After drinking well, can survive 2 weeks without water."
    - "Desert travel: Move at full speed through broken lands and deserts."

- item_type: animal
  id: draft_horse
  name: Draft horse
  category: animals
  cost_gp: 40
  hd: "3"
  save_as_hd: 2
  hp: 13
  ac: 7
  attacks: []
  morale: 6
  alignment: neutral
  xp: 35
  movement: "90' (30')"
  miles_per_day: 18
  max_load_unencumbered_cn: 4500
  max_load_encumbered_cn: 9000
  movement_encumbered: "45' (15')"
  miles_per_day_encumbered: 9
  armor_fits: [horse_barding]
  description: >-
    Bred for great strength and endurance. Used to pull vehicles and ploughs or
    as beasts of burden.
  traits:
    - "Non-combatants: Flee, if attacked."

- item_type: animal
  id: riding_horse
  name: Riding horse
  category: animals
  cost_gp: 75
  hd: "2"
  save_as_hd: 1
  hp: 9
  ac: 7
  attacks:
    - {name: hoof, count: 2, damage: "1d4"}
  morale: 7
  alignment: neutral
  xp: 20
  movement: "240' (80')"
  miles_per_day: 48
  max_load_unencumbered_cn: 3000
  max_load_encumbered_cn: 6000
  movement_encumbered: "120' (40')"
  miles_per_day_encumbered: 24
  armor_fits: [horse_barding]
  description: >-
    Lightly built horses adapted to run at high speed. Can survive purely on
    grass, wherever available.

- item_type: animal
  id: war_horse
  name: War horse
  category: animals
  cost_gp: 250
  hd: "3"
  save_as_hd: 2
  hp: 13
  ac: 7
  attacks:
    - {name: hoof, count: 2, damage: "1d6"}
  morale: 9
  alignment: neutral
  xp: 35
  movement: "120' (40')"
  miles_per_day: 24
  max_load_unencumbered_cn: 4000
  max_load_encumbered_cn: 8000
  movement_encumbered: "60' (20')"
  miles_per_day_encumbered: 12
  armor_fits: [horse_barding]
  description: >-
    Bred for strength and courage in battle. Adapted to short bursts of speed;
    not suited to long-distance riding.
  traits:
    - "Charge: When not in melee. Requires a clear run of at least 20 yards. Rider's lance inflicts double damage. Horse cannot attack when charging."
    - "Melee: When in melee, both rider and horse can attack."

- item_type: animal
  id: mule
  name: Mule
  category: animals
  cost_gp: 30
  hd: "2"
  save_as_hd: "NH"
  hp: 9
  ac: 7
  attacks:
    - {name: kick, damage: "1d4"}
    - {name: bite, damage: "1d3", note: "or"}
  morale: 8
  alignment: neutral
  xp: 20
  movement: "120' (40')"
  miles_per_day: 24
  max_load_unencumbered_cn: 2000
  max_load_encumbered_cn: 4000
  movement_encumbered: "60' (20')"
  miles_per_day_encumbered: 12
  description: >-
    Stubborn horse/donkey cross-breeds used as beasts of burden.
  traits:
    - "Tenacious: Can be taken underground, if the referee allows it."
    - "Defensive: May attack if threatened, but cannot be trained to attack on command."

- item_type: animal
  id: hunting_dog
  name: Hunting dog
  category: animals
  cost_gp: 17
  hd: "1+2"
  save_as_hd: 1
  hp: 6
  ac: 7
  attacks:
    - {name: bite, damage: "1d6"}
  morale: 10
  alignment: neutral
  xp: 15
  movement: "180' (60')"
  miles_per_day: 36
  description: >-
    Domestic breeds selected for their intelligence and excellent sense of smell.
  traits:
    - "Tracking: By scent. Once started, very difficult to put off the trail."
    - "Command: Trained to attack on owner's command."

- item_type: animal
  id: war_dog
  name: War dog
  category: animals
  cost_gp: 25
  hd: "2+2"
  save_as_hd: 1
  hp: 11
  ac: 8
  attacks:
    - {name: bite, damage: "2d4"}
  morale: 11
  alignment: neutral
  xp: 25
  movement: "120' (40')"
  miles_per_day: 24
  armor_fits: [dog_armour]
  description: >-
    Large domestic breeds selected for their bulk and ferocious nature.
  traits:
    - "Armour: Trained to wear armour (see Tack and Harness)."
    - "Command: Trained to attack on owner's command."
```

- [ ] **Step 4: Create `data/equipment/vehicles.yaml`**

```yaml
- item_type: vehicle
  id: cart
  name: Cart
  category: vehicles
  vehicle_category: land_vehicle
  cost_gp: 100
  ac: 9
  hull_points: "1d4"
  cargo_capacity_cn: 4000
  cargo_capacity_extra_cn: 8000
  required_animals: "1 draft horse or 2 mules"
  movement: "60' (20')"
  miles_per_day: "12"
  description: >-
    A two-wheeled vehicle.
  traits:
    - "Difficult terrain: Can only travel on maintained roads through desert, forest, mountains, or swamp."

- item_type: vehicle
  id: wagon
  name: Wagon
  category: vehicles
  vehicle_category: land_vehicle
  cost_gp: 200
  ac: 9
  hull_points: "2d4"
  cargo_capacity_cn: 15000
  cargo_capacity_extra_cn: 25000
  required_animals: "2 draft horses or 4 mules"
  movement: "60' (20')"
  miles_per_day: "12"
  description: >-
    A four-wheeled, open vehicle.
  traits:
    - "Difficult terrain: Can only travel on maintained roads through desert, forest, mountains, or swamp."

# --- Water vessels (seaworthy) ---
- item_type: vehicle
  id: lifeboat
  name: Lifeboat
  category: vehicles
  vehicle_category: water_vessel
  cost_gp: 1000
  ac: 9
  hull_points: "10-20"
  cargo_capacity_cn: 15000
  seaworthy: true
  requires_captain: false
  required_crew: "1 sailor (may be piloted by an unskilled character)"
  movement: "90' (30')"
  miles_per_day: "18"
  dimensions: "20' / 4'-5' / 1'-2'"
  description: >-
    A small boat with a mast that folds down for storage. Usually equipped with
    rations to feed ten human-sized beings for one week. Weighs 5,000 coins.

- item_type: vehicle
  id: longship
  name: Longship
  category: vehicles
  vehicle_category: water_vessel
  cost_gp: 15000
  ac: 8
  hull_points: "60-80"
  cargo_capacity_cn: 40000
  seaworthy: true
  requires_captain: true
  max_mercenaries: 75
  required_crew: "60 oarsmen or 75 sailors (crew act as rowers, sailors, and fighters)"
  movement: "90' (90') rowed / 450' (150') sailed"
  miles_per_day: "18 rowed / 90 sailed"
  dimensions: "60'-80' / 10'-15' / 2'-3'"
  description: >-
    A narrow ship which may be used in rivers, coastal waters, or the open seas.
    May be rowed or sailed, depending on the conditions.

- item_type: vehicle
  id: sailing_ship_large
  name: Sailing ship, large
  category: vehicles
  vehicle_category: water_vessel
  cost_gp: 20000
  ac: 7
  hull_points: "120-180"
  cargo_capacity_cn: 300000
  seaworthy: true
  requires_captain: true
  required_crew: "20 sailors"
  movement: "360' (120')"
  miles_per_day: "72"
  dimensions: "100'-150' / 25'-30' / 10'-12'"
  description: >-
    A large, seaworthy vessel with up to three masts. Usually has multiple decks
    and raised "castles" at the bow and stern.

- item_type: vehicle
  id: sailing_ship_small
  name: Sailing ship, small
  category: vehicles
  vehicle_category: water_vessel
  cost_gp: 5000
  ac: 8
  hull_points: "60-90"
  cargo_capacity_cn: 100000
  seaworthy: true
  requires_captain: true
  required_crew: "10 sailors"
  movement: "450' (150')"
  miles_per_day: "90"
  dimensions: "60'-80' / 20'-30' / 5'-8'"
  description: >-
    A small, seaworthy vessel with a single mast.

- item_type: vehicle
  id: troop_transport_large
  name: Troop transport, large
  category: vehicles
  vehicle_category: water_vessel
  cost_gp: 26600
  ac: 7
  hull_points: "160-240"
  cargo_capacity_cn: 300000
  seaworthy: true
  requires_captain: true
  max_mercenaries: 100
  required_crew: "20 sailors"
  movement: "360' (120')"
  miles_per_day: "72"
  dimensions: "100'-150' / 25'-30' / 10'-12'"
  description: >-
    Similar to a large sailing ship, specially designed to carry troops, mounts,
    and equipment of war as cargo.

- item_type: vehicle
  id: troop_transport_small
  name: Troop transport, small
  category: vehicles
  vehicle_category: water_vessel
  cost_gp: 6600
  ac: 8
  hull_points: "80-120"
  cargo_capacity_cn: 100000
  seaworthy: true
  requires_captain: true
  max_mercenaries: 50
  required_crew: "10 sailors"
  movement: "450' (150')"
  miles_per_day: "90"
  dimensions: "60'-80' / 20'-30' / 5'-8'"
  description: >-
    Similar to a small sailing ship, specially designed to carry troops, mounts,
    and equipment of war as cargo.

- item_type: vehicle
  id: warship_large
  name: Warship, large
  category: vehicles
  vehicle_category: water_vessel
  cost_gp: 26600
  ac: 7
  hull_points: "120-180"
  cargo_capacity_cn: 300000
  seaworthy: true
  requires_captain: true
  max_mercenaries: 50
  required_crew: "20 sailors"
  movement: "360' (120')"
  miles_per_day: "72"
  dimensions: "100'-150' / 25'-30' / 10'-12'"
  description: >-
    Similar to a large sailing ship, specially designed to carry mercenaries and
    war gear.

- item_type: vehicle
  id: warship_small
  name: Warship, small
  category: vehicles
  vehicle_category: water_vessel
  cost_gp: 6600
  ac: 8
  hull_points: "60-90"
  cargo_capacity_cn: 100000
  seaworthy: true
  requires_captain: true
  max_mercenaries: 25
  required_crew: "10 sailors"
  movement: "450' (150')"
  miles_per_day: "90"
  dimensions: "60'-80' / 20'-30' / 5'-8'"
  description: >-
    Similar to a small sailing ship, specially designed to carry mercenaries and
    war gear.

# --- Water vessels (unseaworthy) ---
- item_type: vehicle
  id: boat_river
  name: Boat, river
  category: vehicles
  vehicle_category: water_vessel
  cost_gp: 4000
  ac: 8
  hull_points: "20-40"
  cargo_capacity_cn: 30000
  seaworthy: false
  requires_captain: false
  required_crew: "8 oarsmen"
  movement: "180' (60')"
  miles_per_day: "36"
  dimensions: "20'-30' / 10' / 2'-3'"
  description: >-
    Rowed or pushed with poles. Cost increases by 1,000gp if it has a roof.

- item_type: vehicle
  id: boat_sailing
  name: Boat, sailing
  category: vehicles
  vehicle_category: water_vessel
  cost_gp: 2000
  ac: 8
  hull_points: "20-40"
  cargo_capacity_cn: 20000
  seaworthy: false
  requires_captain: false
  required_crew: "1 sailor"
  movement: "360' (120')"
  miles_per_day: "72"
  dimensions: "20'-40' / 10'-15' / 2'-3'"
  description: >-
    A small boat typically used for fishing in lakes or coastal waters.

- item_type: vehicle
  id: canoe
  name: Canoe
  category: vehicles
  vehicle_category: water_vessel
  cost_gp: 50
  ac: 9
  hull_points: "5-10"
  cargo_capacity_cn: 6000
  seaworthy: false
  requires_captain: false
  required_crew: "1 (may be piloted by an unskilled character)"
  movement: "90' (60')"
  miles_per_day: "18"
  dimensions: "15' / 3' / 1'"
  description: >-
    A small boat made of hide or canvas over a wooden frame. May be carried by
    two people (weighing 500 coins).

- item_type: vehicle
  id: galley_large
  name: Galley, large
  category: vehicles
  vehicle_category: water_vessel
  cost_gp: 30000
  ac: 7
  hull_points: "100-120"
  cargo_capacity_cn: 40000
  seaworthy: false
  requires_captain: true
  max_mercenaries: 50
  required_crew: "180 oarsmen or 20 sailors"
  movement: "90' (90') rowed / 360' (120') sailed"
  miles_per_day: "18 rowed / 72 sailed"
  dimensions: "120'-150' / 15'-20' / 3'"
  description: >-
    A long ship with a shallow draft and a single, square-sailed mast.

- item_type: vehicle
  id: galley_small
  name: Galley, small
  category: vehicles
  vehicle_category: water_vessel
  cost_gp: 10000
  ac: 8
  hull_points: "80-100"
  cargo_capacity_cn: 20000
  seaworthy: false
  requires_captain: true
  max_mercenaries: 20
  required_crew: "60 oarsmen or 10 sailors"
  movement: "90' (90') rowed / 450' (150') sailed"
  miles_per_day: "18 rowed / 90 sailed"
  dimensions: "60'-100' / 10'-15' / 2'-3'"
  description: >-
    A ship with a shallow draft and a single, square-sailed mast.

- item_type: vehicle
  id: galley_war
  name: Galley, war
  category: vehicles
  vehicle_category: water_vessel
  cost_gp: 60000
  ac: 7
  hull_points: "120-150"
  cargo_capacity_cn: 60000
  seaworthy: false
  requires_captain: true
  max_mercenaries: 75
  required_crew: "300 oarsmen or 30 sailors"
  movement: "60' (60') rowed / 360' (120') sailed"
  miles_per_day: "12 rowed / 72 sailed"
  dimensions: "120'-150' / 20'-30' / 4'-6'"
  description: >-
    A large, specially constructed galley, generally a fleet's flagship. Always
    fitted with a ram and a full deck above the rowers; two masts and bow/stern
    towers.

- item_type: vehicle
  id: raft_professional
  name: Raft, professional
  category: vehicles
  vehicle_category: water_vessel
  cost_gp: 0
  ac: 9
  hull_points: "5-10"
  cargo_capacity_cn: 100
  seaworthy: false
  requires_captain: false
  required_crew: "1 (may be piloted by an unskilled character)"
  movement: "60' (30')"
  miles_per_day: "12"
  description: >-
    A professionally built raft with raised sides, a basic steering oar, and
    shelter. Up to 30' x 40'. Costs 1gp per square foot; capacity is per square
    foot.
```

> Note: `raft_makeshift` (no purchase cost) and ship weaponry/rams/catapults are intentionally omitted (out of scope).

- [ ] **Step 5: Create `data/equipment/tack.yaml`**

```yaml
- item_type: animal_armor
  id: dog_armour
  name: Dog armour
  category: tack_and_harness
  cost_gp: 25
  sets_ac: 6
  fits: [war_dog]
  description: >-
    Light leather armour with a spiked collar. Provides the animal with an AC of
    6 [13].

- item_type: animal_armor
  id: horse_barding
  name: Horse barding
  category: tack_and_harness
  cost_gp: 150
  weight_cn: 600
  sets_ac: 5
  fits: [draft_horse, riding_horse, war_horse]
  description: >-
    Armour made of leather and plates of metal. Provides the animal with an AC
    of 5 [14] and weighs 600 coins.

- item_type: gear
  id: saddle_and_bridle
  name: Saddle and bridle
  category: tack_and_harness
  cost_gp: 25

- item_type: container
  id: saddle_bags
  name: Saddle bags
  category: tack_and_harness
  cost_gp: 5
  capacity_cn: 300
  description: "Hold up to 300 coins weight."
```

- [ ] **Step 6: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companion_data.py -q`
Expected: PASS (4 passed). Also run the full suite to confirm no loader regression:
`.venv\Scripts\python.exe -m pytest tests/ -q`

- [ ] **Step 7: Commit**

```bash
git add data/equipment/animals.yaml data/equipment/vehicles.yaml data/equipment/tack.yaml tests/test_companion_data.py
git commit -m "feat(data): import OSE animals, vehicles, tack catalog"
```

**CHECKPOINT 1 complete** — data loads, stats derive. Stop for review.

---

## Checkpoint 2 — Acquisition & topology

### Task 5: Buy / add / remove animals & vehicles

**Files:**
- Create: `aose/engine/companions.py`
- Test: `tests/test_companions_shop.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_companions_shop.py
from pathlib import Path
import random
import pytest
from aose.data.loader import GameData
from aose.engine import companions
from aose.engine.shop import InsufficientGold, UnknownItem

DATA = GameData.load(Path("data"))


def test_buy_animal_creates_instance_and_deducts_gold():
    animals, gold = companions.buy_animal([], 100, "mule", DATA)
    assert gold == 70
    assert len(animals) == 1 and animals[0].catalog_id == "mule"
    assert animals[0].instance_id  # uuid assigned


def test_buy_animal_insufficient_gold():
    with pytest.raises(InsufficientGold):
        companions.buy_animal([], 10, "war_horse", DATA)


def test_buy_animal_rejects_non_animal():
    with pytest.raises(ValueError):
        companions.buy_animal([], 1000, "cart", DATA)


def test_buy_vehicle_resolves_hull_from_dice():
    rng = random.Random(1)
    vehicles, gold = companions.buy_vehicle([], 100, "cart", DATA, rng=rng)
    assert gold == 0
    assert 1 <= vehicles[0].hull_max <= 4


def test_buy_vehicle_resolves_hull_from_range_to_max():
    vehicles, _ = companions.buy_vehicle([], 99999, "longship", DATA)
    assert vehicles[0].hull_max == 80   # max of "60-80"


def test_remove_animal_refund_returns_full_cost():
    animals, gold = companions.buy_animal([], 100, "mule", DATA)
    iid = animals[0].instance_id
    animals, gold = companions.remove_animal(animals, gold, iid, "refund", DATA)
    assert animals == [] and gold == 100


def test_remove_animal_sell_returns_half():
    animals, gold = companions.buy_animal([], 100, "mule", DATA)
    iid = animals[0].instance_id
    animals, gold = companions.remove_animal(animals, gold, iid, "sell", DATA)
    assert gold == 70 + 15
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companions_shop.py -q`
Expected: FAIL with `ModuleNotFoundError: aose.engine.companions`.

- [ ] **Step 3: Write `aose/engine/companions.py`**

```python
"""Acquisition + storage-location helpers for owned animals and vehicles.

Mirrors aose/engine/shop.py's container helpers: each buy creates a per-instance
roster entry rather than a flat inventory id, and load/unload move loose gear
between the PC's inventory and a carrier's contents (capacity-checked). The PC's
encumbrance is never affected — carrier contents live in their own lists.
"""
from __future__ import annotations

import random
import uuid
from typing import Optional

from aose.data.loader import GameData
from aose.engine.dice import roll
from aose.engine.shop import InsufficientGold, REMOVE_MODES, UnknownItem
from aose.models import (
    Animal, AnimalInstance, AnimalArmor, CharacterSpec, Container,
    Vehicle, VehicleInstance,
)


class LoadError(ValueError):
    pass


class AnimalOverloaded(LoadError):
    pass


class VehicleOverloaded(LoadError):
    pass


def _require(data: GameData, item_id: str, kind: type, label: str):
    item = data.items.get(item_id)
    if item is None:
        raise UnknownItem(f"No item with id {item_id!r}")
    if not isinstance(item, kind):
        raise ValueError(f"{item_id!r} is not {label}")
    return item


def resolve_hull_max(hull_points: str, rng: Optional[random.Random] = None) -> int:
    """A dice expression ("1d4") is rolled; a range ("60-80") takes its maximum
    (a sound, newly-built vessel). Editable afterward by the player."""
    s = hull_points.strip()
    if "d" in s:
        return roll(s, rng)
    if "-" in s:
        return int(s.split("-")[-1])
    return int(s)


# ── Animals ────────────────────────────────────────────────────────────────

def buy_animal(animals: list[AnimalInstance], gold: int, catalog_id: str,
               data: GameData) -> tuple[list[AnimalInstance], int]:
    item = _require(data, catalog_id, Animal, "an animal")
    cost = int(item.cost_gp)
    if gold < cost:
        raise InsufficientGold(
            f"Cannot afford {item.name}: {cost} gp required, {gold} on hand")
    inst = AnimalInstance(instance_id=uuid.uuid4().hex, catalog_id=catalog_id)
    return [*animals, inst], gold - cost


def add_free_animal(animals: list[AnimalInstance], catalog_id: str,
                    data: GameData) -> list[AnimalInstance]:
    _require(data, catalog_id, Animal, "an animal")
    return [*animals, AnimalInstance(instance_id=uuid.uuid4().hex,
                                     catalog_id=catalog_id)]


def remove_animal(animals: list[AnimalInstance], gold: int, instance_id: str,
                  mode: str, data: GameData) -> tuple[list[AnimalInstance], int]:
    if mode not in REMOVE_MODES:
        raise ValueError(f"Unknown remove mode {mode!r}")
    idx = next((i for i, a in enumerate(animals)
                if a.instance_id == instance_id), None)
    if idx is None:
        raise ValueError(f"No animal with id {instance_id!r}")
    catalog = data.items.get(animals[idx].catalog_id)
    cost = int(catalog.cost_gp) if catalog else 0
    refund = cost if mode == "refund" else (cost // 2 if mode == "sell" else 0)
    return [*animals[:idx], *animals[idx + 1:]], gold + refund


# ── Vehicles ───────────────────────────────────────────────────────────────

def buy_vehicle(vehicles: list[VehicleInstance], gold: int, catalog_id: str,
                data: GameData, rng: Optional[random.Random] = None
                ) -> tuple[list[VehicleInstance], int]:
    item = _require(data, catalog_id, Vehicle, "a vehicle")
    cost = int(item.cost_gp)
    if gold < cost:
        raise InsufficientGold(
            f"Cannot afford {item.name}: {cost} gp required, {gold} on hand")
    inst = VehicleInstance(instance_id=uuid.uuid4().hex, catalog_id=catalog_id,
                           hull_max=resolve_hull_max(item.hull_points, rng))
    return [*vehicles, inst], gold - cost


def add_free_vehicle(vehicles: list[VehicleInstance], catalog_id: str,
                     data: GameData, rng: Optional[random.Random] = None
                     ) -> list[VehicleInstance]:
    item = _require(data, catalog_id, Vehicle, "a vehicle")
    return [*vehicles, VehicleInstance(
        instance_id=uuid.uuid4().hex, catalog_id=catalog_id,
        hull_max=resolve_hull_max(item.hull_points, rng))]


def remove_vehicle(vehicles: list[VehicleInstance], gold: int, instance_id: str,
                   mode: str, data: GameData
                   ) -> tuple[list[VehicleInstance], int]:
    if mode not in REMOVE_MODES:
        raise ValueError(f"Unknown remove mode {mode!r}")
    idx = next((i for i, v in enumerate(vehicles)
                if v.instance_id == instance_id), None)
    if idx is None:
        raise ValueError(f"No vehicle with id {instance_id!r}")
    catalog = data.items.get(vehicles[idx].catalog_id)
    cost = int(catalog.cost_gp) if catalog else 0
    refund = cost if mode == "refund" else (cost // 2 if mode == "sell" else 0)
    return [*vehicles[:idx], *vehicles[idx + 1:]], gold + refund
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companions_shop.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/companions.py tests/test_companions_shop.py
git commit -m "feat(engine): buy/add/remove animals & vehicles"
```

---

### Task 6: Animal-armour assign / clear

**Files:**
- Modify: `aose/engine/companions.py`
- Test: `tests/test_companions_armor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_companions_armor.py
from pathlib import Path
import pytest
from aose.data.loader import GameData
from aose.engine import companions
from aose.models import AnimalInstance

DATA = GameData.load(Path("data"))


def test_assign_armor_moves_from_inventory_to_animal():
    animals = [AnimalInstance(instance_id="a1", catalog_id="war_horse")]
    inv = ["horse_barding"]
    inv, animals = companions.assign_armor(inv, animals, "a1", "horse_barding", DATA)
    assert inv == []
    assert animals[0].armor_id == "horse_barding"


def test_assign_armor_rejects_unfitting():
    animals = [AnimalInstance(instance_id="a1", catalog_id="war_horse")]
    with pytest.raises(ValueError):
        companions.assign_armor(["dog_armour"], animals, "a1", "dog_armour", DATA)


def test_clear_armor_returns_it_to_inventory():
    animals = [AnimalInstance(instance_id="a1", catalog_id="war_horse",
                              armor_id="horse_barding")]
    inv, animals = companions.clear_armor([], animals, "a1", DATA)
    assert inv == ["horse_barding"]
    assert animals[0].armor_id is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companions_armor.py -q`
Expected: FAIL — `assign_armor` not defined.

- [ ] **Step 3: Add the helpers to `aose/engine/companions.py`**

```python
def _find_animal(animals, instance_id):
    idx = next((i for i, a in enumerate(animals)
                if a.instance_id == instance_id), None)
    if idx is None:
        raise ValueError(f"No animal with id {instance_id!r}")
    return idx


def assign_armor(inventory: list[str], animals: list[AnimalInstance],
                 instance_id: str, armor_id: str, data: GameData
                 ) -> tuple[list[str], list[AnimalInstance]]:
    """Move an AnimalArmor from inventory onto the animal. Validates fit."""
    idx = _find_animal(animals, instance_id)
    animal = animals[idx]
    armor = _require(data, armor_id, AnimalArmor, "animal armour")
    catalog = data.items[animal.catalog_id]
    if armor_id not in catalog.armor_fits:
        raise ValueError(f"{armor.name} does not fit {catalog.name}")
    if armor_id not in inventory:
        raise ValueError(f"{armor_id!r} is not in inventory")
    new_inv = list(inventory)
    new_inv.remove(armor_id)
    # return any previously worn armour to inventory first
    if animal.armor_id:
        new_inv.append(animal.armor_id)
    updated = animal.model_copy(update={"armor_id": armor_id})
    return new_inv, [*animals[:idx], updated, *animals[idx + 1:]]


def clear_armor(inventory: list[str], animals: list[AnimalInstance],
                instance_id: str, data: GameData
                ) -> tuple[list[str], list[AnimalInstance]]:
    idx = _find_animal(animals, instance_id)
    animal = animals[idx]
    new_inv = list(inventory)
    if animal.armor_id:
        new_inv.append(animal.armor_id)
    updated = animal.model_copy(update={"armor_id": None})
    return new_inv, [*animals[:idx], updated, *animals[idx + 1:]]
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companions_armor.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/companions.py tests/test_companions_armor.py
git commit -m "feat(engine): assign/clear animal armour"
```

---

### Task 7: Load / unload loose gear onto a carrier (capacity-checked)

**Files:**
- Modify: `aose/engine/companions.py`
- Test: `tests/test_companions_load.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_companions_load.py
from pathlib import Path
import pytest
from aose.data.loader import GameData
from aose.engine import companions
from aose.engine.companions import AnimalOverloaded, VehicleOverloaded
from aose.models import AnimalInstance, VehicleInstance

DATA = GameData.load(Path("data"))
# a heavy item to test capacity: use a real weapon weight from the catalog.
HEAVY = next(i.id for i in DATA.items.values()
             if getattr(i, "weight_cn", 0) >= 80)


def test_load_onto_animal_moves_from_inventory():
    animals = [AnimalInstance(instance_id="a1", catalog_id="mule")]
    inv, animals = companions.load_onto_animal([HEAVY], animals, "a1", HEAVY, DATA)
    assert inv == []
    assert animals[0].contents == [HEAVY]


def test_unload_from_animal_returns_to_inventory():
    animals = [AnimalInstance(instance_id="a1", catalog_id="mule",
                              contents=[HEAVY])]
    inv, animals = companions.unload_from_animal([], animals, "a1", HEAVY, DATA)
    assert inv == [HEAVY]
    assert animals[0].contents == []


def test_dog_has_no_load_capacity():
    animals = [AnimalInstance(instance_id="d1", catalog_id="war_dog")]
    with pytest.raises(AnimalOverloaded):
        companions.load_onto_animal([HEAVY], animals, "d1", HEAVY, DATA)


def test_barding_weight_counts_against_animal_load():
    # mule encumbered cap 4000; load near cap then ensure barding+load rejects.
    cap = DATA.items["mule"].max_load_encumbered_cn  # 4000
    assert cap == 4000


def test_load_onto_vehicle_capacity_uses_extra_when_toggled():
    v = VehicleInstance(instance_id="v1", catalog_id="cart", hull_max=4)
    # cart base 4000, extra 8000 — a single light item always fits; assert toggle path runs
    inv, vehicles = companions.load_onto_vehicle([HEAVY], [v], "v1", HEAVY, DATA)
    assert vehicles[0].contents == [HEAVY]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companions_load.py -q`
Expected: FAIL — `load_onto_animal` not defined.

- [ ] **Step 3: Add load/unload + capacity helpers to `companions.py`**

```python
def _items_weight(item_ids: list[str], data: GameData) -> int:
    return sum((data.items[i].weight_cn if i in data.items else 0)
               for i in item_ids)


def animal_capacity(animal: AnimalInstance, data: GameData) -> int | None:
    """Encumbered max-load cap (the hard ceiling). None when the animal is not
    a beast of burden (dogs) — meaning it carries nothing."""
    catalog = data.items[animal.catalog_id]
    return catalog.max_load_encumbered_cn


def animal_load_cn(animal: AnimalInstance, data: GameData) -> int:
    """Worn barding weight + loaded contents weight."""
    worn = data.items[animal.armor_id].weight_cn if animal.armor_id else 0
    return worn + _items_weight(animal.contents, data)


def load_onto_animal(inventory: list[str], animals: list[AnimalInstance],
                     instance_id: str, item_id: str, data: GameData
                     ) -> tuple[list[str], list[AnimalInstance]]:
    idx = _find_animal(animals, instance_id)
    animal = animals[idx]
    if item_id not in inventory:
        raise ValueError(f"{item_id!r} is not in inventory")
    cap = animal_capacity(animal, data)
    add = data.items[item_id].weight_cn if item_id in data.items else 0
    if cap is None or animal_load_cn(animal, data) + add > cap:
        raise AnimalOverloaded(
            f"{data.items[animal.catalog_id].name} cannot carry that much")
    new_inv = list(inventory); new_inv.remove(item_id)
    updated = animal.model_copy(update={"contents": [*animal.contents, item_id]})
    return new_inv, [*animals[:idx], updated, *animals[idx + 1:]]


def unload_from_animal(inventory: list[str], animals: list[AnimalInstance],
                       instance_id: str, item_id: str, data: GameData
                       ) -> tuple[list[str], list[AnimalInstance]]:
    idx = _find_animal(animals, instance_id)
    animal = animals[idx]
    if item_id not in animal.contents:
        raise ValueError(f"{item_id!r} not loaded on this animal")
    new_contents = list(animal.contents); new_contents.remove(item_id)
    updated = animal.model_copy(update={"contents": new_contents})
    return [*inventory, item_id], [*animals[:idx], updated, *animals[idx + 1:]]


def _find_vehicle(vehicles, instance_id):
    idx = next((i for i, v in enumerate(vehicles)
                if v.instance_id == instance_id), None)
    if idx is None:
        raise ValueError(f"No vehicle with id {instance_id!r}")
    return idx


def vehicle_capacity(vehicle: VehicleInstance, data: GameData) -> int:
    catalog = data.items[vehicle.catalog_id]
    if vehicle.extra_animals and catalog.cargo_capacity_extra_cn is not None:
        return catalog.cargo_capacity_extra_cn
    return catalog.cargo_capacity_cn


def vehicle_load_cn(vehicle: VehicleInstance, data: GameData) -> int:
    return _items_weight(vehicle.contents, data)


def load_onto_vehicle(inventory: list[str], vehicles: list[VehicleInstance],
                      instance_id: str, item_id: str, data: GameData
                      ) -> tuple[list[str], list[VehicleInstance]]:
    idx = _find_vehicle(vehicles, instance_id)
    vehicle = vehicles[idx]
    if item_id not in inventory:
        raise ValueError(f"{item_id!r} is not in inventory")
    add = data.items[item_id].weight_cn if item_id in data.items else 0
    if vehicle_load_cn(vehicle, data) + add > vehicle_capacity(vehicle, data):
        raise VehicleOverloaded(
            f"{data.items[vehicle.catalog_id].name} is over capacity")
    new_inv = list(inventory); new_inv.remove(item_id)
    updated = vehicle.model_copy(update={"contents": [*vehicle.contents, item_id]})
    return new_inv, [*vehicles[:idx], updated, *vehicles[idx + 1:]]


def unload_from_vehicle(inventory: list[str], vehicles: list[VehicleInstance],
                        instance_id: str, item_id: str, data: GameData
                        ) -> tuple[list[str], list[VehicleInstance]]:
    idx = _find_vehicle(vehicles, instance_id)
    vehicle = vehicles[idx]
    if item_id not in vehicle.contents:
        raise ValueError(f"{item_id!r} not loaded on this vehicle")
    new_contents = list(vehicle.contents); new_contents.remove(item_id)
    updated = vehicle.model_copy(update={"contents": new_contents})
    return [*inventory, item_id], [*vehicles[:idx], updated, *vehicles[idx + 1:]]
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companions_load.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/companions.py tests/test_companions_load.py
git commit -m "feat(engine): load/unload loose gear onto animals & vehicles"
```

---

### Task 8: Container-on-carrier + encumbrance exclusion

**Files:**
- Modify: `aose/engine/companions.py`
- Modify: `aose/engine/encumbrance.py:159-171`
- Modify: `aose/engine/shop.py` (`inventory_view` container loop)
- Test: `tests/test_container_on_carrier.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_container_on_carrier.py
from pathlib import Path
from aose.data.loader import GameData
from aose.engine import companions, encumbrance
from aose.models import (
    CharacterSpec, AnimalInstance, ContainerInstance,
)

DATA = GameData.load(Path("data"))


def _spec(**kw):
    return CharacterSpec(
        name="H", abilities={"str": 10, "int": 10, "wis": 10, "dex": 10,
                             "con": 10, "cha": 10},
        race_id="human", classes=[{"class_id": "fighter"}],
        alignment="neutral", ruleset={"encumbrance": "detailed"}, **kw)


def test_move_container_onto_animal_sets_location():
    spec = _spec(
        animals=[AnimalInstance(instance_id="a1", catalog_id="mule")],
        containers=[ContainerInstance(instance_id="c1", catalog_id="saddle_bags",
                                      state="carried")],
    )
    companions.move_container_to_animal(spec, "c1", "a1", DATA)
    c = spec.containers[0]
    assert c.location == "animal" and c.location_id == "a1"


def test_carrier_container_excluded_from_pc_weight():
    # A carried saddle-bag on the person would add its own weight; once on the
    # mule it must not count toward the PC's carried weight.
    spec = _spec(
        animals=[AnimalInstance(instance_id="a1", catalog_id="mule")],
        containers=[ContainerInstance(instance_id="c1", catalog_id="saddle_bags",
                                      state="carried")],
    )
    before = encumbrance.equipment_weight_cn(spec, DATA)
    companions.move_container_to_animal(spec, "c1", "a1", DATA)
    after = encumbrance.equipment_weight_cn(spec, DATA)
    assert after <= before  # carrier container no longer in PC total
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_container_on_carrier.py -q`
Expected: FAIL — `move_container_to_animal` not defined.

- [ ] **Step 3: Add carrier-container mutators to `companions.py`**

```python
def _set_container_location(spec: CharacterSpec, container_id: str,
                            location: str, location_id: str | None) -> None:
    for i, c in enumerate(spec.containers):
        if c.instance_id == container_id:
            spec.containers[i] = c.model_copy(
                update={"location": location, "location_id": location_id})
            return
    raise ValueError(f"No container with id {container_id!r}")


def move_container_to_animal(spec: CharacterSpec, container_id: str,
                            animal_id: str, data: GameData) -> None:
    _find_animal(spec.animals, animal_id)
    _set_container_location(spec, container_id, "animal", animal_id)


def move_container_to_vehicle(spec: CharacterSpec, container_id: str,
                             vehicle_id: str, data: GameData) -> None:
    _find_vehicle(spec.vehicles, vehicle_id)
    _set_container_location(spec, container_id, "vehicle", vehicle_id)


def move_container_to_person(spec: CharacterSpec, container_id: str) -> None:
    _set_container_location(spec, container_id, "person", None)
```

- [ ] **Step 4: Exclude carrier containers from PC weight**

In `aose/engine/encumbrance.py`, the carried-container loop (around line 160) currently reads:

```python
    for c in spec.containers:
        if c.state != "carried":
            continue
```

Change the guard to also skip containers that aren't on the person:

```python
    for c in spec.containers:
        if c.state != "carried" or c.location != "person":
            continue
```

- [ ] **Step 5: Hide carrier containers from the loose inventory view**

In `aose/engine/shop.py`, `inventory_view`'s container loop begins `for c in containers:`. Add at the top of that loop body:

```python
        if getattr(c, "location", "person") != "person":
            continue   # rendered inside its carrier's card, not the loose list
```

- [ ] **Step 6: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_container_on_carrier.py tests/test_encumbrance*.py -q`
Expected: PASS, and no encumbrance regression.

- [ ] **Step 7: Commit**

```bash
git add aose/engine/companions.py aose/engine/encumbrance.py aose/engine/shop.py tests/test_container_on_carrier.py
git commit -m "feat(engine): containers ride animals/vehicles; excluded from PC weight"
```

**CHECKPOINT 2 complete** — acquisition + topology fully tested. Stop for review.

---

## Checkpoint 3 — Derivation & detail

### Task 9: Detail cards for the new item variants

**Files:**
- Modify: `aose/engine/detail.py`
- Test: `tests/test_companion_detail.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_companion_detail.py
from pathlib import Path
from aose.data.loader import GameData
from aose.engine.detail import item_card

DATA = GameData.load(Path("data"))


def test_animal_card_shows_derived_ac_and_attacks():
    card = item_card(DATA.items["camel"])
    labels = {s.label: s.value for s in card.stats}
    assert labels["Type"] == "Animal"
    assert labels["AC"] == "7 [12]"      # 19 - 7
    assert labels["HD"] == "2"
    assert "bite" in labels["Attacks"].lower()
    assert card.description


def test_vehicle_card_shows_hull_and_cargo():
    card = item_card(DATA.items["cart"])
    labels = {s.label: s.value for s in card.stats}
    assert labels["Type"] == "Vehicle"
    assert labels["Hull Points"] == "1d4"
    assert "4000" in labels["Cargo"]


def test_animal_armor_card():
    card = item_card(DATA.items["horse_barding"])
    labels = {s.label: s.value for s in card.stats}
    assert labels["Type"] == "Animal Armour"
    assert labels["AC"] == "5 [14]"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companion_detail.py -q`
Expected: FAIL — animals fall through to the "Gear" branch.

- [ ] **Step 3: Extend `item_card` in `aose/engine/detail.py`**

Add to the imports: `Animal, AnimalArmor, Vehicle`. Insert these branches **before** the final `else` (the AdventuringGear catch-all):

```python
    elif isinstance(item, Animal):
        stats.append(StatLine(label="Type", value="Animal"))
        stats.append(StatLine(label="AC", value=f"{item.ac} [{19 - item.ac}]"))
        stats.append(StatLine(label="HD", value=item.hd))
        if item.attacks:
            stats.append(StatLine(
                label="Attacks",
                value=", ".join(
                    (f"{a.note} " if a.note else "")
                    + (f"{a.count}× " if a.count > 1 else "")
                    + f"{a.name} ({a.damage})"
                    for a in item.attacks)))
        stats.append(StatLine(label="Move", value=item.movement))
        if item.max_load_unencumbered_cn:
            stats.append(StatLine(
                label="Max Load",
                value=f"{item.max_load_unencumbered_cn} / "
                      f"{item.max_load_encumbered_cn} cn"))
        stats.append(StatLine(label="Morale", value=str(item.morale)))
        stats += _cost_weight(item)

    elif isinstance(item, Vehicle):
        stats.append(StatLine(label="Type", value="Vehicle"))
        stats.append(StatLine(label="AC", value=f"{item.ac} [{19 - item.ac}]"))
        stats.append(StatLine(label="Hull Points", value=item.hull_points))
        cargo = f"{item.cargo_capacity_cn} cn"
        if item.cargo_capacity_extra_cn:
            cargo += f" ({item.cargo_capacity_extra_cn} with extra animals)"
        stats.append(StatLine(label="Cargo", value=cargo))
        if item.required_animals:
            stats.append(StatLine(label="Animals", value=item.required_animals))
        if item.required_crew:
            stats.append(StatLine(label="Crew", value=item.required_crew))
        if item.max_mercenaries:
            stats.append(StatLine(label="Mercenaries", value=str(item.max_mercenaries)))
        stats += _cost_weight(item)

    elif isinstance(item, AnimalArmor):
        stats.append(StatLine(label="Type", value="Animal Armour"))
        stats.append(StatLine(label="AC", value=f"{item.sets_ac} [{19 - item.sets_ac}]"))
        if item.fits:
            stats.append(StatLine(label="Fits", value=", ".join(item.fits)))
        stats += _cost_weight(item)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companion_detail.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/detail.py tests/test_companion_detail.py
git commit -m "feat(detail): item cards for animals, vehicles, animal armour"
```

---

### Task 10: Companions view builder for the sheet

**Files:**
- Create: `aose/sheet/companions_view.py`
- Modify: `aose/sheet/view.py` (`CharacterSheet` + `build_sheet`)
- Test: `tests/test_companions_view.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_companions_view.py
from pathlib import Path
from aose.data.loader import GameData
from aose.sheet.companions_view import companions_block
from aose.models import CharacterSpec, AnimalInstance, VehicleInstance

DATA = GameData.load(Path("data"))


def _spec(**kw):
    return CharacterSpec(
        name="H", abilities={"str": 10, "int": 10, "wis": 10, "dex": 10,
                             "con": 10, "cha": 10},
        race_id="human", classes=[{"class_id": "fighter"}],
        alignment="neutral", **kw)


def test_empty_when_no_companions():
    assert companions_block(_spec(), DATA) is None


def test_animal_card_derives_stats():
    spec = _spec(animals=[AnimalInstance(instance_id="a1", catalog_id="war_horse",
                                         armor_id="horse_barding")])
    block = companions_block(spec, DATA)
    card = block.animals[0]
    assert card.name == "War horse"
    assert card.ac_descending == 5         # barding overrides natural 7
    assert card.thac0 == 17                # HD 3
    assert card.saves["death"] == 12       # save-as 2 → band 1-3
    assert card.hp_current == 13 and card.hp_max == 13


def test_vehicle_card_capacity_meter():
    spec = _spec(vehicles=[VehicleInstance(instance_id="v1", catalog_id="cart",
                                           hull_max=4)])
    block = companions_block(spec, DATA)
    card = block.vehicles[0]
    assert card.cargo_capacity == 4000
    assert card.cargo_used == 0
    assert card.hull_current == 4
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companions_view.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `aose/sheet/companions_view.py`**

```python
"""Assemble the read-model for the sheet's Companions & Holdings section.

Pure view assembly: derives display stats (AC from armour or natural, THAC0 and
saves via monster_stats) and resolves contents into inventory rows. Reuses
shop.InventoryRow / detail.item_card; imports only models + engine helpers.
"""
from __future__ import annotations

from collections import Counter

from pydantic import BaseModel

from aose.data.loader import GameData
from aose.engine import companions, monster_stats as ms
from aose.engine.detail import DetailCard, item_card
from aose.engine.shop import InventoryRow, _build_row
from aose.models import Animal, AnimalArmor, CharacterSpec, Vehicle


class AnimalCard(BaseModel):
    instance_id: str
    catalog_id: str
    name: str            # label or species name
    species: str
    ac_descending: int
    ac_ascending: int
    thac0: int
    attack_bonus: int
    saves: dict[str, int]
    hp_current: int
    hp_max: int
    movement: str
    morale: int
    traits: list[str]
    armor_id: str | None
    armor_options: list[tuple[str, str]]    # (id, name) of owned fitting armour
    load_used: int
    load_capacity: int | None
    contents: list[InventoryRow]
    magic_note: str
    detail: DetailCard


class VehicleCard(BaseModel):
    instance_id: str
    catalog_id: str
    name: str
    kind: str            # species/type name
    ac_descending: int
    ac_ascending: int
    hull_current: int
    hull_max: int
    cargo_used: int
    cargo_capacity: int
    extra_animals: bool
    has_extra: bool
    contents: list[InventoryRow]
    detail: DetailCard


class CompanionsBlock(BaseModel):
    animals: list[AnimalCard] = []
    vehicles: list[VehicleCard] = []


def _content_rows(item_ids: list[str], data: GameData) -> list[InventoryRow]:
    rows = [_build_row(i, n, data) for i, n in Counter(item_ids).items()]
    rows.sort(key=lambda r: r.name)
    return rows


def _armor_options(catalog: Animal, inventory: list[str],
                   data: GameData) -> list[tuple[str, str]]:
    out = []
    for aid in catalog.armor_fits:
        if aid in inventory and aid in data.items:
            out.append((aid, data.items[aid].name))
    return out


def companions_block(spec: CharacterSpec, data: GameData) -> CompanionsBlock | None:
    if not spec.animals and not spec.vehicles:
        return None

    animal_cards: list[AnimalCard] = []
    for inst in spec.animals:
        catalog = data.items.get(inst.catalog_id)
        if not isinstance(catalog, Animal):
            continue
        ac = catalog.ac
        if inst.armor_id and isinstance(data.items.get(inst.armor_id), AnimalArmor):
            ac = data.items[inst.armor_id].sets_ac
        atk = ms.attack_for_hd(catalog.hd, data)
        animal_cards.append(AnimalCard(
            instance_id=inst.instance_id, catalog_id=inst.catalog_id,
            name=inst.name or catalog.name, species=catalog.name,
            ac_descending=ac, ac_ascending=ms.ascending_ac(ac),
            thac0=atk.thac0, attack_bonus=atk.attack_bonus,
            saves=ms.saves_for_hd(catalog.save_as_hd, data),
            hp_current=max(0, catalog.hp - inst.hp_damage), hp_max=catalog.hp,
            movement=catalog.movement, morale=catalog.morale,
            traits=catalog.traits, armor_id=inst.armor_id,
            armor_options=_armor_options(catalog, spec.inventory, data),
            load_used=companions.animal_load_cn(inst, data),
            load_capacity=companions.animal_capacity(inst, data),
            contents=_content_rows(inst.contents, data),
            magic_note=inst.magic_note, detail=item_card(catalog),
        ))

    vehicle_cards: list[VehicleCard] = []
    for inst in spec.vehicles:
        catalog = data.items.get(inst.catalog_id)
        if not isinstance(catalog, Vehicle):
            continue
        vehicle_cards.append(VehicleCard(
            instance_id=inst.instance_id, catalog_id=inst.catalog_id,
            name=inst.name or catalog.name, kind=catalog.name,
            ac_descending=catalog.ac, ac_ascending=ms.ascending_ac(catalog.ac),
            hull_current=max(0, inst.hull_max - inst.hull_damage),
            hull_max=inst.hull_max,
            cargo_used=companions.vehicle_load_cn(inst, data),
            cargo_capacity=companions.vehicle_capacity(inst, data),
            extra_animals=inst.extra_animals,
            has_extra=catalog.cargo_capacity_extra_cn is not None,
            contents=_content_rows(inst.contents, data),
            detail=item_card(catalog),
        ))

    return CompanionsBlock(animals=animal_cards, vehicles=vehicle_cards)
```

- [ ] **Step 4: Wire into `build_sheet`**

In `aose/sheet/view.py`, add `companions: CompanionsBlock | None = None` to the `CharacterSheet` model (import `CompanionsBlock` and `companions_block` at the top). In `build_sheet`, before the final `CharacterSheet(...)` construction, compute `companions=companions_block(spec, data)` and pass it through.

- [ ] **Step 5: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companions_view.py -q`
Expected: PASS (3 passed). Also run `.venv\Scripts\python.exe -m pytest tests/ -q` to confirm `build_sheet` still constructs.

- [ ] **Step 6: Commit**

```bash
git add aose/sheet/companions_view.py aose/sheet/view.py tests/test_companions_view.py
git commit -m "feat(sheet): companions view block (derived animal/vehicle cards)"
```

**CHECKPOINT 3 complete** — derivations ready for rendering. Stop for review.

---

## Checkpoint 4 — Routes & UI

### Task 11: Animal routes

**Files:**
- Modify: `aose/web/routes.py`
- Test: `tests/test_companion_routes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_companion_routes.py
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from aose.web.app import create_app
from aose.characters.storage import save_character
from aose.models import CharacterSpec


@pytest.fixture
def client(tmp_path, monkeypatch):
    app = create_app()
    app.state.game_data = __import__(
        "aose.data.loader", fromlist=["GameData"]).GameData.load(Path("data"))
    c = TestClient(app)
    # the app resolves dirs from request.state; the default (auth-off) middleware
    # points them at the repo roots — write the fixture char into that dir.
    return c


def _make_char(client) -> str:
    spec = CharacterSpec(
        name="Rider", abilities={"str": 10, "int": 10, "wis": 10, "dex": 10,
                                 "con": 10, "cha": 10},
        race_id="human", classes=[{"class_id": "fighter"}],
        alignment="neutral", gold=500)
    # Use the import endpoint to persist through the app's own workspace.
    import io, json
    resp = client.post("/import", files={
        "file": ("c.json", io.BytesIO(spec.model_dump_json().encode()), "application/json")})
    assert resp.status_code in (200, 303)
    return resp.headers["location"].rsplit("/", 1)[-1]


def test_buy_animal_route(client):
    cid = _make_char(client)
    resp = client.post(f"/character/{cid}/animal/buy", data={"item_id": "mule"},
                       follow_redirects=False)
    assert resp.status_code == 303
    from aose.characters.storage import load_character
    # reload through the same dir the app used:
    # (helper: hit the sheet and assert the animal name shows)
    sheet = client.get(f"/character/{cid}")
    assert "Mule" in sheet.text
```

> Note: if the import-endpoint round-trip is awkward in your harness, follow the
> pattern already used by `tests/test_hp_state.py` / existing route tests for
> persisting a fixture character, and assert the same observable outcome.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companion_routes.py -q`
Expected: FAIL — route 404.

- [ ] **Step 3: Add animal routes to `aose/web/routes.py`**

Add `from aose.engine import companions` to the imports. Append (mirroring the `hp/damage` route exactly — `_load_spec_or_404`, mutate, `save_character`, 303):

```python
@router.post("/character/{character_id}/animal/buy")
async def animal_buy(request: Request, character_id: str, item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.animals, spec.gold = companions.buy_animal(
            spec.animals, spec.gold, item_id, data)
    except (ValueError,) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/animal/remove")
async def animal_remove(request: Request, character_id: str,
                        instance_id: str = Form(...), mode: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.animals, spec.gold = companions.remove_animal(
            spec.animals, spec.gold, instance_id, mode, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/animal/{instance_id}/rename")
async def animal_rename(request: Request, character_id: str, instance_id: str,
                        name: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    for i, a in enumerate(spec.animals):
        if a.instance_id == instance_id:
            spec.animals[i] = a.model_copy(update={"name": name})
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/animal/{instance_id}/hp")
async def animal_hp(request: Request, character_id: str, instance_id: str,
                    delta: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    for i, a in enumerate(spec.animals):
        if a.instance_id == instance_id:
            catalog = data.items.get(a.catalog_id)
            cap = catalog.hp if catalog else 0
            new_dmg = min(max(0, a.hp_damage - delta), cap)
            spec.animals[i] = a.model_copy(update={"hp_damage": new_dmg})
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/animal/{instance_id}/armor")
async def animal_armor(request: Request, character_id: str, instance_id: str,
                       armor_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        if armor_id == "":
            spec.inventory, spec.animals = companions.clear_armor(
                spec.inventory, spec.animals, instance_id, data)
        else:
            spec.inventory, spec.animals = companions.assign_armor(
                spec.inventory, spec.animals, instance_id, armor_id, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/animal/{instance_id}/load")
async def animal_load(request: Request, character_id: str, instance_id: str,
                      item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.inventory, spec.animals = companions.load_onto_animal(
            spec.inventory, spec.animals, instance_id, item_id, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/animal/{instance_id}/unload")
async def animal_unload(request: Request, character_id: str, instance_id: str,
                        item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.inventory, spec.animals = companions.unload_from_animal(
            spec.inventory, spec.animals, instance_id, item_id, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companion_routes.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_companion_routes.py
git commit -m "feat(routes): animal buy/remove/rename/hp/armor/load/unload"
```

---

### Task 12: Vehicle routes

**Files:**
- Modify: `aose/web/routes.py`
- Test: `tests/test_companion_routes.py` (extend)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_companion_routes.py`:

```python
def test_buy_vehicle_route(client):
    cid = _make_char(client)
    resp = client.post(f"/character/{cid}/vehicle/buy", data={"item_id": "cart"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert "Cart" in client.get(f"/character/{cid}").text


def test_vehicle_extra_animals_toggle(client):
    cid = _make_char(client)
    client.post(f"/character/{cid}/vehicle/buy", data={"item_id": "wagon"})
    # toggle should not 500
    sheet = client.get(f"/character/{cid}").text
    assert "Wagon" in sheet
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companion_routes.py -q`
Expected: FAIL — vehicle routes 404.

- [ ] **Step 3: Add vehicle routes to `aose/web/routes.py`**

```python
@router.post("/character/{character_id}/vehicle/buy")
async def vehicle_buy(request: Request, character_id: str, item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.vehicles, spec.gold = companions.buy_vehicle(
            spec.vehicles, spec.gold, item_id, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/vehicle/remove")
async def vehicle_remove(request: Request, character_id: str,
                         instance_id: str = Form(...), mode: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.vehicles, spec.gold = companions.remove_vehicle(
            spec.vehicles, spec.gold, instance_id, mode, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/vehicle/{instance_id}/rename")
async def vehicle_rename(request: Request, character_id: str, instance_id: str,
                         name: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    for i, v in enumerate(spec.vehicles):
        if v.instance_id == instance_id:
            spec.vehicles[i] = v.model_copy(update={"name": name})
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/vehicle/{instance_id}/hull")
async def vehicle_hull(request: Request, character_id: str, instance_id: str,
                       delta: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    for i, v in enumerate(spec.vehicles):
        if v.instance_id == instance_id:
            new_dmg = min(max(0, v.hull_damage - delta), v.hull_max)
            spec.vehicles[i] = v.model_copy(update={"hull_damage": new_dmg})
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/vehicle/{instance_id}/extra-animals")
async def vehicle_extra_animals(request: Request, character_id: str,
                                instance_id: str, on: bool = Form(False)):
    spec = _load_spec_or_404(request, character_id)
    for i, v in enumerate(spec.vehicles):
        if v.instance_id == instance_id:
            spec.vehicles[i] = v.model_copy(update={"extra_animals": on})
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/vehicle/{instance_id}/load")
async def vehicle_load(request: Request, character_id: str, instance_id: str,
                       item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.inventory, spec.vehicles = companions.load_onto_vehicle(
            spec.inventory, spec.vehicles, instance_id, item_id, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/vehicle/{instance_id}/unload")
async def vehicle_unload(request: Request, character_id: str, instance_id: str,
                         item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.inventory, spec.vehicles = companions.unload_from_vehicle(
            spec.inventory, spec.vehicles, instance_id, item_id, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companion_routes.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_companion_routes.py
git commit -m "feat(routes): vehicle buy/remove/rename/hull/extra-animals/load/unload"
```

---

### Task 13: Sheet UI — Companions & Holdings section

**Files:**
- Read first: `docs/STYLE-GUIDE.md`
- Create: `aose/web/templates/_companions.html`
- Modify: `aose/web/templates/sheet.html`
- Modify: `aose/web/templates/_equipment_ui.html` (add Animals/Vehicles shop categories already auto-appear; add a "load onto carrier" affordance is optional — see note)

- [ ] **Step 1: Read the style guide**

Run (read, don't edit): open `docs/STYLE-GUIDE.md`. Note the group/inked-bar pattern, the overlay model, and that destructive actions belong in the management drawer, not sheet modals.

- [ ] **Step 2: Create `aose/web/templates/_companions.html`**

A partial rendering `sheet.companions`. Match the existing inventory group's structure (inked bar + internal scroll). Each card shows derived stats and a collapsible contents list. Forms POST to the Task 11/12 routes.

```html
{% if sheet.companions %}
<section class="group companions-group">
  <h2 class="group-bar">Companions &amp; Holdings</h2>
  <div class="group-body">

    {% for a in sheet.companions.animals %}
    <article class="companion-card" data-kind="animal">
      <header class="companion-head">
        <span class="companion-name">{{ a.name }}</span>
        <span class="companion-sub">{{ a.species }}</span>
        <span class="companion-stat">AC {{ a.ac_descending }} [{{ a.ac_ascending }}]</span>
        <span class="companion-stat">THAC0 {{ a.thac0 }} [{{ '%+d' % a.attack_bonus }}]</span>
        <span class="companion-stat">HP {{ a.hp_current }}/{{ a.hp_max }}</span>
      </header>

      <div class="companion-saves">
        D {{ a.saves.death }} · W {{ a.saves.wands }} · P {{ a.saves.paralysis }}
        · B {{ a.saves.breath }} · S {{ a.saves.spells }}
        · Move {{ a.movement }} · ML {{ a.morale }}
      </div>

      {% if a.traits %}
      <ul class="companion-traits">
        {% for t in a.traits %}<li>{{ t }}</li>{% endfor %}
      </ul>
      {% endif %}

      <form method="post"
            action="/character/{{ cid }}/animal/{{ a.instance_id }}/hp"
            class="inline-form">
        <button name="delta" value="-1" class="chip">−1 HP</button>
        <button name="delta" value="1" class="chip">+1 HP</button>
      </form>

      {% if a.armor_options or a.armor_id %}
      <form method="post"
            action="/character/{{ cid }}/animal/{{ a.instance_id }}/armor"
            class="inline-form">
        <label>Armour
          <select name="armor_id" onchange="this.form.submit()">
            <option value="">— none —</option>
            {% for aid, aname in a.armor_options %}
              <option value="{{ aid }}">{{ aname }}</option>
            {% endfor %}
            {% if a.armor_id %}
              <option value="{{ a.armor_id }}" selected>
                {{ a.armor_id }} (worn)</option>
            {% endif %}
          </select>
        </label>
      </form>
      {% endif %}

      {% if a.load_capacity %}
      <details class="companion-load">
        <summary>Load {{ a.load_used }} / {{ a.load_capacity }} cn</summary>
        <ul class="contents-list">
          {% for row in a.contents %}
          <li>
            {{ row.name }} ×{{ row.count }}
            <form method="post"
                  action="/character/{{ cid }}/animal/{{ a.instance_id }}/unload"
                  class="inline-form">
              <input type="hidden" name="item_id" value="{{ row.id }}">
              <button class="chip">Unload</button>
            </form>
          </li>
          {% endfor %}
        </ul>
      </details>
      {% endif %}
    </article>
    {% endfor %}

    {% for v in sheet.companions.vehicles %}
    <article class="companion-card" data-kind="vehicle">
      <header class="companion-head">
        <span class="companion-name">{{ v.name }}</span>
        <span class="companion-sub">{{ v.kind }}</span>
        <span class="companion-stat">AC {{ v.ac_descending }} [{{ v.ac_ascending }}]</span>
        <span class="companion-stat">Hull {{ v.hull_current }}/{{ v.hull_max }}</span>
        <span class="companion-stat">Cargo {{ v.cargo_used }}/{{ v.cargo_capacity }} cn</span>
      </header>

      <form method="post"
            action="/character/{{ cid }}/vehicle/{{ v.instance_id }}/hull"
            class="inline-form">
        <button name="delta" value="-1" class="chip">−1 Hull</button>
        <button name="delta" value="1" class="chip">+1 Hull</button>
      </form>

      {% if v.has_extra %}
      <form method="post"
            action="/character/{{ cid }}/vehicle/{{ v.instance_id }}/extra-animals"
            class="inline-form">
        <label><input type="checkbox" name="on" value="true"
               {% if v.extra_animals %}checked{% endif %}
               onchange="this.form.submit()"> Extra animals</label>
      </form>
      {% endif %}

      <details class="companion-load">
        <summary>Cargo {{ v.cargo_used }} / {{ v.cargo_capacity }} cn</summary>
        <ul class="contents-list">
          {% for row in v.contents %}
          <li>
            {{ row.name }} ×{{ row.count }}
            <form method="post"
                  action="/character/{{ cid }}/vehicle/{{ v.instance_id }}/unload"
                  class="inline-form">
              <input type="hidden" name="item_id" value="{{ row.id }}">
              <button class="chip">Unload</button>
            </form>
          </li>
          {% endfor %}
        </ul>
      </details>
    </article>
    {% endfor %}

  </div>
</section>
{% endif %}
```

- [ ] **Step 3: Include the partial in `sheet.html`**

Find where the inventory/currency group is included and add, after it (using the same `cid` variable the sheet already passes — confirm its name in `sheet.html`; if it's `character_id`, use that):

```html
{% include "_companions.html" %}
```

- [ ] **Step 4: Add minimal styles**

In `aose/web/static/sheet.css`, reuse existing tokens. Add:

```css
.companion-card { border: 1px solid var(--rule); padding: .5rem .75rem;
  margin-block: .5rem; }
.companion-head { display: flex; flex-wrap: wrap; gap: .5rem 1rem;
  align-items: baseline; }
.companion-name { font-weight: 700; }
.companion-sub { color: var(--ink-2); font-style: italic; }
.companion-stat { font-variant-numeric: tabular-nums; }
.companion-saves { color: var(--ink-2); font-size: .9em; margin-top: .25rem; }
.companion-traits { margin: .25rem 0 0; padding-left: 1.1rem; font-size: .9em; }
.contents-list { list-style: none; padding: 0; margin: .25rem 0 0; }
.contents-list li { display: flex; gap: .5rem; align-items: center; }
.inline-form { display: inline-flex; gap: .25rem; margin-top: .25rem; }
```

- [ ] **Step 5: Manual smoke check**

Run: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
Then use the preview workflow (preview_start / preview_snapshot) to: buy a mule and a cart from the shop (Animals / Vehicles categories), confirm the Companions & Holdings section renders with derived AC/THAC0/saves, assign barding to a war horse, and load an item onto the cart. Capture a screenshot.

- [ ] **Step 6: Run full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing `pytest-current` PermissionError).

- [ ] **Step 7: Commit**

```bash
git add aose/web/templates/_companions.html aose/web/templates/sheet.html aose/web/static/sheet.css
git commit -m "feat(sheet): Companions & Holdings section UI"
```

---

### Task 14: Print sheet block

**Files:**
- Modify: `aose/web/templates/sheet_print.html`
- Test: manual

- [ ] **Step 1: Add a compact companions block to `sheet_print.html`**

Mirror the live section but static (no forms). Place it after the inventory block:

```html
{% if sheet.companions %}
<section class="print-companions">
  <h3>Companions &amp; Holdings</h3>
  {% for a in sheet.companions.animals %}
  <p><strong>{{ a.name }}</strong> ({{ a.species }}) — AC {{ a.ac_descending }}
     [{{ a.ac_ascending }}], HP {{ a.hp_current }}/{{ a.hp_max }},
     THAC0 {{ a.thac0 }} [{{ '%+d' % a.attack_bonus }}],
     Save D{{ a.saves.death }} W{{ a.saves.wands }} P{{ a.saves.paralysis }}
     B{{ a.saves.breath }} S{{ a.saves.spells }}.
     {% if a.contents %}Carrying: {{ a.contents | map(attribute='name') | join(', ') }}.{% endif %}</p>
  {% endfor %}
  {% for v in sheet.companions.vehicles %}
  <p><strong>{{ v.name }}</strong> ({{ v.kind }}) — AC {{ v.ac_descending }}
     [{{ v.ac_ascending }}], Hull {{ v.hull_current }}/{{ v.hull_max }},
     Cargo {{ v.cargo_used }}/{{ v.cargo_capacity }} cn.
     {% if v.contents %}Cargo: {{ v.contents | map(attribute='name') | join(', ') }}.{% endif %}</p>
  {% endfor %}
</section>
{% endif %}
```

- [ ] **Step 2: Manual check**

Visit `/character/{id}/print` for a character with a mule + cart; confirm the block renders.

- [ ] **Step 3: Commit**

```bash
git add aose/web/templates/sheet_print.html
git commit -m "feat(print): companions block on the print sheet"
```

---

### Task 15: Docs + final verification

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `CLAUDE.md` (storage-shapes bullet only)

- [ ] **Step 1: Update the docs**

- `docs/CHANGELOG.md`: add a one-line row at the top — date `2026-06-16`, feature "Animals & vehicles (Companions & Holdings Phase A)", branch `feat/companions-and-holdings`, spec slug `animals-and-vehicles`.
- `docs/ARCHITECTURE.md`: add a "Companions & Holdings" subsystem section describing: Animal/Vehicle/AnimalArmor item variants; `AnimalInstance`/`VehicleInstance` roster lists; `monster_stats` HD→stat derivation; the storage-location topology and `ContainerInstance.location`; `companions.py` helpers; the sheet `CompanionsBlock`.
- `CLAUDE.md`: under "Storage shapes", add a bullet: `animals`/`vehicles` lists of per-instance roster entries (carriers as storage locations); `ContainerInstance.location` puts a container on a carrier.

- [ ] **Step 2: Full test run + manual verify**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all pass (ignore the trailing `pytest-current` PermissionError).

Then run the app and, via the preview workflow, verify end-to-end: buy → load → armour → damage → print. Capture a screenshot as proof.

- [ ] **Step 3: Commit**

```bash
git add docs/CHANGELOG.md docs/ARCHITECTURE.md CLAUDE.md
git commit -m "docs: companions & holdings phase A landed"
```

---

## Self-review notes (for the implementer)

- **Spec coverage:** models (Task 1-2), monster_stats + tables (3), data import (4), buy/remove (5), armour (6), load/unload (7), container-on-carrier + encumbrance exclusion (8), detail cards (9), view block (10), routes (11-12), UI (13), print (14), docs (15). Every spec section maps to a task.
- **Type consistency:** `companions.py` helper names used by routes/view (`buy_animal`, `remove_animal`, `assign_armor`, `clear_armor`, `load_onto_animal`, `unload_from_animal`, `animal_load_cn`, `animal_capacity`, `buy_vehicle`, `remove_vehicle`, `vehicle_load_cn`, `vehicle_capacity`, `load_onto_vehicle`, `unload_from_vehicle`, `move_container_to_animal/vehicle/person`, `resolve_hull_max`) match across tasks.
- **Known risk:** Task 11's route test relies on the import-endpoint round-trip for persistence; if your harness already has a route-test fixture pattern (see existing `tests/test_*route*.py`), prefer it and keep the same observable assertions.
