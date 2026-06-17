# Quick Equipment (Phase B1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A reusable generator that fills a `CharacterSpec`'s starting kit (armour, weapons, ammo, gear, gold) from the Carcass Crawler "Quick Equipment" rules, driven by data for the named classes and by a proficiency heuristic for the rest.

**Architecture:** A data file (`data/quick_equipment.yaml`) holds the roll tables + per-class kits; a cycle-free engine (`aose/engine/quick_equipment.py`) rolls a `QuickKit` (pure, injectable RNG) and an `apply_kit` helper writes it onto a spec. Classes absent from the data use a heuristic built from `armor_allowed` / `allowed_weapon_ids`. No wizard wiring in this phase — just the engine + tests, ready for Phase B2 (retainers) and a later wizard option to consume.

**Tech Stack:** Python 3, Pydantic v2, pytest. Tests: `.venv\Scripts\python.exe -m pytest`. Ignore the trailing `pytest-current` PermissionError on Windows.

**Spec:** [`docs/superpowers/specs/2026-06-17-retainers-design.md`](../specs/2026-06-17-retainers-design.md) (Plan B1 section).

**Reused helpers (already in the codebase):**
- `aose.engine.dice.roll("3d6", rng)` → int; `roll("1d4"|"1d6"|"1d12", rng)`.
- `aose.engine.proficiency.allowed_weapon_ids(classes, data, ruleset)` → `set[str] | "all"`; `allowed_armor_ids(classes, data)` → `set[str] | "all"`; `base_weapon_id(weapon)`.
- `aose.engine.equip.equip(item_id, inventory=, equipped=, enchanted=, data=, slot=, allowed_weapons=, allowed_armor=, allow_shields=)`; `hand_cost(item, gargantua_1h_2h=False)`.
- `aose.models.AmmoStack(instance_id, base_id, count)`, `Weapon`, `Armor`, `CharacterSpec`, `CharClass`.
- `GameData._load_table(dir, filename)` (added in Phase A for the monster tables) — reuse for `quick_equipment.yaml`.

---

### Task 1: Load the Quick Equipment data + add the missing item

**Files:**
- Modify: `data/equipment/adventuring_gear.yaml`
- Create: `data/quick_equipment.yaml`
- Modify: `aose/data/loader.py` (`GameData` field + `load`)
- Test: `tests/test_quick_equipment_data.py`

- [ ] **Step 1: Add the missing catalog item**

The druid kit references a sprig of mistletoe, absent from the catalog. Append to `data/equipment/adventuring_gear.yaml`:

```yaml
- { id: sprig_of_mistletoe, item_type: gear, name: Sprig of Mistletoe, category: adventuring_gear, cost_gp: 0, description: "A holy symbol for druids." }
```

- [ ] **Step 2: Create `data/quick_equipment.yaml`**

Two top-level keys: `tables` (the roll tables) and `classes` (per-class kits). Each table row is a list of *grants*; a grant is one of `{id, n}` (inventory item, n copies), `{ammo, n}` (an ammo stack), `{armor}` (equip into the armour slot), `{shield: true}` (grant + equip a shield).

```yaml
tables:
  armour_d6:
    - [{armor: leather_armor}]
    - [{armor: leather_armor}, {shield: true}]
    - [{armor: chain_mail}]
    - [{armor: chain_mail}, {shield: true}]
    - [{armor: plate_mail}]
    - [{armor: plate_mail}, {shield: true}]
  general:
    - [{id: battle_axe}]
    - [{id: crossbow}, {ammo: crossbow_bolt, n: 20}]
    - [{id: hand_axe}]
    - [{id: mace}]
    - [{id: polearm}]
    - [{id: short_bow}, {ammo: arrow, n: 20}]
    - [{id: short_sword}]
    - [{id: silver_dagger}]
    - [{id: sling}, {ammo: sling_stone, n: 20}]
    - [{id: spear}]
    - [{id: sword}]
    - [{id: war_hammer}]
  acrobat:
    - [{id: polearm}]
    - [{id: short_bow}, {ammo: arrow, n: 20}]
    - [{id: spear}]
    - [{id: staff}]
  bard:
    - [{id: crossbow}, {ammo: crossbow_bolt, n: 20}]
    - [{id: short_sword}]
    - [{id: sling}, {ammo: sling_stone, n: 20}]
    - [{id: sword}]
  cleric:
    - [{id: mace}]
    - [{id: sling}, {ammo: sling_stone, n: 20}]
    - [{id: staff}]
    - [{id: war_hammer}]
  druid:
    - [{id: club}]
    - [{id: dagger}]
    - [{id: sling}, {ammo: sling_stone, n: 20}]
    - [{id: staff}]
  knight:
    - [{id: lance}]
    - [{id: short_sword}]
    - [{id: sword}]
    - [{id: war_hammer}]
  adventuring_gear:
    - [{id: crowbar}]
    - [{id: hammer_small}, {id: iron_spike, n: 12}]
    - [{id: holy_water_vial}]
    - [{id: lantern}, {id: flask_of_oil, n: 3}]
    - [{id: mirror_small}]
    - [{id: pole_10ft}]
    - [{id: rope_50ft}]
    - [{id: rope_50ft}, {id: grappling_hook}]
    - [{id: sack_large}]
    - [{id: sack_small}]
    - [{id: stakes_and_mallet}]
    - [{id: wolfsbane}]

classes:
  fighter:     {armour: armour_d6, weapons: {table: general, rolls: 2}}
  paladin:     {armour: armour_d6, weapons: {table: general, rolls: 2}, extras: [holy_symbol]}
  ranger:      {armour: {table: armour_d6, die: "1d4"}, weapons: {table: general, rolls: 2}}
  barbarian:   {armour: {table: armour_d6, die: "1d4"}, weapons: {table: general, rolls: 2}}
  cleric:      {armour: armour_d6, weapons: {table: cleric, rolls: 2}, extras: [holy_symbol]}
  druid:       {armour: {fixed: leather_armor}, weapons: {table: druid, rolls: 2}, extras: [sprig_of_mistletoe]}
  thief:       {armour: {fixed: leather_armor}, weapons: {table: general, rolls: 2}, extras: [thieves_tools]}
  acrobat:     {armour: {fixed: leather_armor}, weapons: {table: acrobat, rolls: 2}}
  assassin:    {armour: {fixed: leather_armor}, weapons: {table: general, rolls: 2}}
  magic_user:  {armour: none, weapons: {fixed: [dagger]}}
  illusionist: {armour: none, weapons: {fixed: [dagger]}}
  knight:      {armour: {table: armour_d6, die: "1d4", modifier: 2}, weapons: {table: knight, rolls: 2}}
  arcane_bard: {armour: {table: armour_d6, die: "1d4", ignore_shields: true}, weapons: {table: bard, rolls: 2}}
  dwarf:       {armour: armour_d6, weapons: {table: general, rolls: 2}}
  elf:         {armour: armour_d6, weapons: {table: general, rolls: 2}}
  halfling:    {armour: armour_d6, weapons: {table: general, rolls: 2}}
  half_elf:    {armour: armour_d6, weapons: {table: general, rolls: 2}}
  half_orc:    {armour: {table: armour_d6, die: "1d4"}, weapons: {table: general, rolls: 2}}
  gnome:       {armour: {fixed: leather_armor}, weapons: {table: general, rolls: 2}}
  duergar:     {armour: armour_d6, weapons: {table: general, rolls: 2}}
  svirfneblin: {armour: armour_d6, weapons: {table: general, rolls: 2}}
```

> Any class id above that does not exist in `data/classes/` will be caught by the data test in Step 4 — delete or rename it there (e.g. drop `arcane_bard` if absent). Classes omitted here are intentionally handled by the heuristic (Task 4); omission is not an error.

- [ ] **Step 3: Load it into `GameData`**

In `aose/data/loader.py`, add a field to the `GameData` dataclass:

```python
    quick_equipment: dict = field(default_factory=dict)
```

and populate it in `GameData.load(...)`'s `cls(...)`:

```python
            quick_equipment=_load_table(data_dir, "quick_equipment.yaml"),
```

- [ ] **Step 4: Write the data test**

```python
# tests/test_quick_equipment_data.py
from pathlib import Path
from aose.data.loader import GameData
from aose.models import Weapon, Armor, AdventuringGear, Ammunition, Container

DATA = GameData.load(Path("data"))
QE = DATA.quick_equipment


def _grant_ids(tables):
    for rows in tables.values():
        for row in rows:
            for grant in row:
                if "id" in grant:
                    yield grant["id"]
                if "armor" in grant:
                    yield grant["armor"]
                if "ammo" in grant:
                    yield grant["ammo"]


def test_tables_reference_real_items():
    for item_id in _grant_ids(QE["tables"]):
        assert item_id in DATA.items, f"unknown item {item_id}"


def test_class_keys_are_real_classes():
    for class_id in QE["classes"]:
        assert class_id in DATA.classes, f"unknown class {class_id}"


def test_class_extras_and_tables_resolve():
    for class_id, kit in QE["classes"].items():
        for extra in kit.get("extras", []):
            assert extra in DATA.items, f"{class_id} extra {extra} missing"
        w = kit["weapons"]
        if "table" in w:
            assert w["table"] in QE["tables"], f"{class_id} table {w['table']}"
        if "fixed" in w:
            for wid in w["fixed"]:
                assert wid in DATA.items


def test_sprig_of_mistletoe_added():
    assert "sprig_of_mistletoe" in DATA.items
```

- [ ] **Step 5: Run**

Run: `.venv\Scripts\python.exe -m pytest tests/test_quick_equipment_data.py -q`
Expected: PASS (4 passed). If `test_class_keys_are_real_classes` fails, fix the offending key in `quick_equipment.yaml` (delete or rename to the real id).

- [ ] **Step 6: Commit**

```bash
git add data/equipment/adventuring_gear.yaml data/quick_equipment.yaml aose/data/loader.py tests/test_quick_equipment_data.py
git commit -m "feat(data): quick-equipment tables + class kits"
```

---

### Task 2: `roll_kit` — basic gear, armour, weapons, gold

**Files:**
- Create: `aose/engine/quick_equipment.py`
- Test: `tests/test_quick_equipment.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_quick_equipment.py
from pathlib import Path
import random
from aose.data.loader import GameData
from aose.engine import quick_equipment as qe
from aose.models import Weapon, Armor

DATA = GameData.load(Path("data"))


def test_fighter_kit_has_basics_armour_and_two_weapons():
    kit = qe.roll_kit("fighter", DATA, rng=random.Random(1))
    # basic gear
    assert "backpack" in kit.inventory
    assert "tinder_box" in kit.inventory
    assert "waterskin" in kit.inventory
    assert kit.inventory.count("torch") >= 1
    assert kit.inventory.count("iron_rations") >= 1
    assert 3 <= kit.gold <= 18
    # armour equipped from the d6 table
    armor_id = kit.equipped.get("armor")
    assert isinstance(DATA.items[armor_id], Armor)
    # a main-hand weapon was chosen
    assert isinstance(DATA.items[kit.equipped["main_hand"]], Weapon)


def test_magic_user_kit_no_armour_has_dagger():
    kit = qe.roll_kit("magic_user", DATA, rng=random.Random(1))
    assert "armor" not in kit.equipped
    assert "dagger" in kit.inventory


def test_kit_is_deterministic_for_seed():
    a = qe.roll_kit("fighter", DATA, rng=random.Random(42))
    b = qe.roll_kit("fighter", DATA, rng=random.Random(42))
    assert a.model_dump() == b.model_dump()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_quick_equipment.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write the engine core**

`aose/engine/quick_equipment.py`:

```python
"""Quick Equipment generator (Carcass Crawler, Gavin Norman).

Rolls a class-appropriate starting kit (armour, weapons, ammo, gear, gold) onto a
fresh QuickKit, which apply_kit() writes onto a CharacterSpec. Pure + injectable
RNG. Classes present in data.quick_equipment["classes"] use their authored kit;
the rest use a proficiency heuristic (see heuristic_kit). Cycle-free: models,
loader, dice, proficiency, equip only.
"""
from __future__ import annotations

import random
import uuid
from typing import Optional

from pydantic import BaseModel, Field

from aose.data.loader import GameData
from aose.engine.dice import roll
from aose.engine.equip import equip, hand_cost
from aose.models import AmmoStack, Armor, CharacterSpec, Weapon


class QuickKit(BaseModel):
    inventory: list[str] = Field(default_factory=list)
    equipped: dict[str, str] = Field(default_factory=dict)
    ammo: list[AmmoStack] = Field(default_factory=list)
    gold: int = 0


# Basic equipment every character receives.
_BASIC = ["backpack", "tinder_box", "waterskin"]


def _apply_grants(grants: list[dict], kit: QuickKit, *,
                  pending_armor: list, pending_shield: list) -> None:
    """Apply a table row's grants to the kit. Armour/shield are deferred to the
    caller (equipped after all weapons are known, for the hand budget)."""
    for g in grants:
        if "id" in g:
            kit.inventory.extend([g["id"]] * int(g.get("n", 1)))
        elif "ammo" in g:
            kit.ammo.append(AmmoStack(instance_id=uuid.uuid4().hex,
                                      base_id=g["ammo"], count=int(g.get("n", 1))))
        elif "armor" in g:
            pending_armor.append(g["armor"])
        elif g.get("shield"):
            pending_shield.append("shield")


def _roll_armour_row(spec, tables: dict, rng) -> list[dict]:
    """Resolve an armour spec to a chosen table row (list of grants).

    spec forms: "armour_d6" | {table, die?, modifier?, ignore_shields?}
                | {fixed: <armor_id>} | "none".
    """
    if spec == "none" or spec is None:
        return []
    if isinstance(spec, dict) and "fixed" in spec:
        return [{"armor": spec["fixed"]}]
    table_name = spec if isinstance(spec, str) else spec.get("table", "armour_d6")
    rows = tables[table_name]
    die = (spec.get("die") if isinstance(spec, dict) else None) or "1d6"
    modifier = (spec.get("modifier") if isinstance(spec, dict) else 0) or 0
    idx = roll(die, rng) + modifier            # 1-based table position
    idx = max(1, min(idx, len(rows)))
    row = list(rows[idx - 1])
    if isinstance(spec, dict) and spec.get("ignore_shields"):
        row = [g for g in row if not g.get("shield")]
    return row


def _roll_weapons(wspec: dict, tables: dict, kit: QuickKit, rng) -> None:
    if "fixed" in wspec:
        for wid in wspec["fixed"]:
            kit.inventory.append(wid)
        return
    rows = tables[wspec["table"]]
    pa, ps = [], []  # weapon tables never grant armour/shield
    for _ in range(int(wspec.get("rolls", 1))):
        chosen = rows[roll(f"1d{len(rows)}", rng) - 1]
        _apply_grants(chosen, kit, pending_armor=pa, pending_shield=ps)


def _equip_loadout(kit: QuickKit, pending_armor, pending_shield,
                   data: GameData) -> None:
    """Equip rolled armour, then a main-hand weapon, then a shield if hands free.
    All allowances are open here (kit is class-appropriate by construction)."""
    for armor_id in pending_armor[:1]:
        kit.inventory.append(armor_id)
        kit.equipped = equip(armor_id, inventory=kit.inventory,
                             equipped=kit.equipped, enchanted=[], data=data)
    # main hand: first melee weapon, else first weapon present in inventory.
    weapons = [i for i in kit.inventory if isinstance(data.items.get(i), Weapon)]
    melee = [i for i in weapons if "melee" in data.items[i].quality_ids]
    main = (melee or weapons or [None])[0]
    if main is not None:
        kit.equipped = equip(main, inventory=kit.inventory,
                             equipped=kit.equipped, enchanted=[], data=data)
    # shield only if a hand remains free (main not two-handed).
    if pending_shield:
        kit.inventory.append("shield")
        main_item = data.items.get(kit.equipped.get("main_hand"))
        used = hand_cost(main_item) if main_item else 0
        if used < 2:
            kit.equipped = equip("shield", inventory=kit.inventory,
                                 equipped=kit.equipped, enchanted=[], data=data)


def roll_kit(class_id: str, data: GameData,
             rng: Optional[random.Random] = None) -> QuickKit:
    rng = rng or random.Random()
    kit = QuickKit()
    # 1. basic gear + variable quantities + gold
    kit.inventory.extend(_BASIC)
    kit.inventory.extend(["torch"] * roll("1d6", rng))
    kit.inventory.extend(["iron_rations"] * roll("1d6", rng))
    kit.gold = roll("3d6", rng)

    classes = data.quick_equipment.get("classes", {})
    tables = data.quick_equipment.get("tables", {})

    if class_id in classes:
        kit_spec = classes[class_id]
        pending_armor: list = []
        pending_shield: list = []
        armour_row = _roll_armour_row(kit_spec.get("armour", "none"), tables, rng)
        _apply_grants(armour_row, kit, pending_armor=pending_armor,
                      pending_shield=pending_shield)
        _roll_weapons(kit_spec["weapons"], tables, kit, rng)
        for extra in kit_spec.get("extras", []):
            kit.inventory.append(extra)
        _equip_loadout(kit, pending_armor, pending_shield, data)
    else:
        _heuristic_fill(class_id, data, kit, tables, rng)   # Task 4

    # 3. adventuring gear: 1d12 twice
    ag = tables.get("adventuring_gear", [])
    if ag:
        for _ in range(2):
            row = ag[roll(f"1d{len(ag)}", rng) - 1]
            _apply_grants(row, kit, pending_armor=[], pending_shield=[])
    return kit
```

> `_heuristic_fill` is added in Task 4; until then the `else` branch raises
> `NameError` for unknown classes. The Task 2 tests only use known classes, so
> they pass now; add a temporary `def _heuristic_fill(*a, **k): pass` stub if you
> want a green run before Task 4, then replace it.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_quick_equipment.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/quick_equipment.py tests/test_quick_equipment.py
git commit -m "feat(engine): quick_equipment roll_kit (basics, armour, weapons, gold)"
```

---

### Task 3: Ammo + two-handed hand-budget + `apply_kit`

**Files:**
- Modify: `aose/engine/quick_equipment.py`
- Test: `tests/test_quick_equipment.py` (extend)

- [ ] **Step 1: Add failing tests**

```python
def test_ranged_weapon_yields_ammo_stack():
    # force the sling/bow path by seeding until a launcher appears, or assert
    # over many seeds that whenever a launcher is in inventory an ammo stack exists.
    for seed in range(50):
        kit = qe.roll_kit("fighter", DATA, rng=random.Random(seed))
        launchers = {"short_bow", "crossbow", "sling"} & set(kit.inventory)
        if launchers:
            assert kit.ammo, f"launcher {launchers} but no ammo (seed {seed})"
            assert kit.ammo[0].count == 20
            return
    raise AssertionError("no launcher rolled in 50 seeds")


def test_two_handed_main_leaves_off_hand_empty():
    # polearm is two-handed; when it's the main hand, no shield should be equipped
    for seed in range(50):
        kit = qe.roll_kit("fighter", DATA, rng=random.Random(seed))
        main = kit.equipped.get("main_hand")
        if main and "two_handed" in DATA.items[main].quality_ids:
            assert "off_hand" not in kit.equipped or \
                   DATA.items[DATA.items and kit.equipped.get("off_hand")] is None
            assert kit.equipped.get("off_hand") != "shield"
            return


def test_apply_kit_writes_onto_spec():
    from aose.models import CharacterSpec
    spec = CharacterSpec(
        name="R", abilities={"str": 10, "int": 10, "wis": 10, "dex": 10,
                             "con": 10, "cha": 10},
        race_id="human", classes=[{"class_id": "fighter"}], alignment="neutral")
    kit = qe.roll_kit("fighter", DATA, rng=random.Random(1))
    qe.apply_kit(spec, kit)
    assert spec.inventory == kit.inventory
    assert spec.equipped == kit.equipped
    assert spec.ammo == kit.ammo
    assert spec.gold == kit.gold
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_quick_equipment.py -q`
Expected: FAIL — `apply_kit` not defined (ammo/two-handed already pass from Task 2's logic; keep them as regression guards).

- [ ] **Step 3: Add `apply_kit`**

Append to `aose/engine/quick_equipment.py`:

```python
def apply_kit(spec: CharacterSpec, kit: QuickKit) -> None:
    """Write a rolled kit onto a CharacterSpec (replaces inventory/equipped/ammo
    and sets gold). Used by retainer generation and, later, the wizard."""
    spec.inventory = list(kit.inventory)
    spec.equipped = dict(kit.equipped)
    spec.ammo = list(kit.ammo)
    spec.gold = kit.gold
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_quick_equipment.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/quick_equipment.py tests/test_quick_equipment.py
git commit -m "feat(engine): quick_equipment ammo + apply_kit"
```

---

### Task 4: Proficiency heuristic for unlisted classes

**Files:**
- Modify: `aose/engine/quick_equipment.py`
- Test: `tests/test_quick_equipment_heuristic.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_quick_equipment_heuristic.py
from pathlib import Path
import random
from aose.data.loader import GameData
from aose.engine import quick_equipment as qe
from aose.models import Weapon, Armor

DATA = GameData.load(Path("data"))

# pick a class id that is NOT in quick_equipment.yaml's classes map
UNLISTED = next(cid for cid in DATA.classes
                if cid not in DATA.quick_equipment.get("classes", {}))


def test_unlisted_class_gets_basic_gear_and_a_weapon():
    kit = qe.roll_kit(UNLISTED, DATA, rng=random.Random(1))
    assert "backpack" in kit.inventory
    weapons = [i for i in kit.inventory if isinstance(DATA.items.get(i), Weapon)]
    assert weapons, f"{UNLISTED} got no weapon"


def test_heuristic_armour_respects_class_allowance():
    # for every unlisted class, any equipped armour must be one the class allows
    from aose.engine.proficiency import allowed_armor_ids
    for cid, cls in DATA.classes.items():
        if cid in DATA.quick_equipment.get("classes", {}):
            continue
        kit = qe.roll_kit(cid, DATA, rng=random.Random(3))
        armor_id = kit.equipped.get("armor")
        if armor_id:
            allowed = allowed_armor_ids([cls], DATA)
            assert allowed == "all" or armor_id in allowed, f"{cid}: {armor_id}"


def test_heuristic_weapon_respects_class_allowance():
    from aose.engine.proficiency import allowed_weapon_ids, base_weapon_id
    for cid, cls in DATA.classes.items():
        if cid in DATA.quick_equipment.get("classes", {}):
            continue
        kit = qe.roll_kit(cid, DATA, rng=random.Random(3))
        allowed = allowed_weapon_ids([cls], DATA)
        if allowed == "all":
            continue
        for wid in (i for i in kit.inventory
                    if isinstance(DATA.items.get(i), Weapon)):
            assert base_weapon_id(DATA.items[wid]) in allowed, f"{cid}: {wid}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_quick_equipment_heuristic.py -q`
Expected: FAIL — `_heuristic_fill` missing/stub (or `NameError`).

- [ ] **Step 3: Implement the heuristic**

Add to `aose/engine/quick_equipment.py` (imports at top: `from aose.engine.proficiency import allowed_armor_ids, allowed_weapon_ids`):

```python
# Ammo each launcher needs, for heuristic grants.
_LAUNCHER_AMMO = {"short_bow": "arrow", "long_bow": "arrow",
                  "crossbow": "crossbow_bolt", "sling": "sling_stone"}


def _heuristic_armour_row(cls, data, tables, rng) -> list[dict]:
    """Filter the d6 armour table to rows the class can wear, then roll among
    the survivors. Shield rows kept only when the class allows shields."""
    allowed = allowed_armor_ids([cls], data)
    rows = []
    for row in tables.get("armour_d6", []):
        armor_id = next((g["armor"] for g in row if "armor" in g), None)
        has_shield = any(g.get("shield") for g in row)
        if allowed != "all" and armor_id not in allowed:
            continue
        if has_shield and not cls.shields_allowed:
            continue
        rows.append(row)
    if not rows:
        return []
    return list(rows[roll(f"1d{len(rows)}", rng) - 1])


def _heuristic_weapons(cls, data, kit: QuickKit, rng) -> None:
    """All-weapons → general d12 twice. A limited set: >2 ids → custom uniform
    roll twice; 1-2 ids → grant them outright. Ammo added for launchers."""
    allowed = allowed_weapon_ids([cls], data)
    tables = data.quick_equipment.get("tables", {})

    def _grant_weapon(wid: str) -> None:
        kit.inventory.append(wid)
        ammo = _LAUNCHER_AMMO.get(wid)
        if ammo:
            kit.ammo.append(AmmoStack(instance_id=uuid.uuid4().hex,
                                      base_id=ammo, count=20))

    if allowed == "all":
        rows = tables["general"]
        for _ in range(2):
            row = rows[roll(f"1d{len(rows)}", rng) - 1]
            _apply_grants(row, kit, pending_armor=[], pending_shield=[])
        return
    ids = sorted(allowed)
    if len(ids) <= 2:
        for wid in ids:
            _grant_weapon(wid)
        return
    for _ in range(2):
        _grant_weapon(ids[roll(f"1d{len(ids)}", rng) - 1])


def _heuristic_fill(class_id: str, data: GameData, kit: QuickKit,
                    tables: dict, rng) -> None:
    cls = data.classes.get(class_id)
    if cls is None:
        _grant = kit.inventory.append
        _grant("dagger")
        return
    pending_armor: list = []
    pending_shield: list = []
    armour_row = _heuristic_armour_row(cls, data, tables, rng)
    _apply_grants(armour_row, kit, pending_armor=pending_armor,
                  pending_shield=pending_shield)
    _heuristic_weapons(cls, data, kit, rng)
    if not any(isinstance(data.items.get(i), Weapon) for i in kit.inventory):
        kit.inventory.append("dagger")   # guarantee at least one weapon
    _equip_loadout(kit, pending_armor, pending_shield, data)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_quick_equipment_heuristic.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all pass (ignore the trailing `pytest-current` PermissionError).

- [ ] **Step 6: Commit**

```bash
git add aose/engine/quick_equipment.py tests/test_quick_equipment_heuristic.py
git commit -m "feat(engine): quick_equipment proficiency heuristic for unlisted classes"
```

---

## Self-review notes (for the implementer)

- **Spec coverage:** data tables + class kits (Task 1), basic/armour/weapons/gold roll (Task 2), ammo + apply_kit (Task 3), proficiency heuristic (Task 4). Gold = 3d6 (RAW), spellbook untouched (B2 concern), all per the spec's resolved decisions.
- **Type consistency:** `QuickKit` fields (`inventory`/`equipped`/`ammo`/`gold`), `roll_kit(class_id, data, rng)`, `apply_kit(spec, kit)`, internal `_apply_grants`/`_roll_armour_row`/`_roll_weapons`/`_equip_loadout`/`_heuristic_fill` are referenced consistently across tasks.
- **Known risks:** (1) `_equip_loadout` calls `equip(...)` with open allowances — correct, because each kit is class-appropriate by construction (explicit table) or filtered to allowances (heuristic). (2) `dice.roll` accepts any `NdM` (regex `\d+d\d+`, verified in `aose/engine/dice.py`), so the `1d{len(rows)}` table-roll idiom is safe for any row count — no special-casing needed.
