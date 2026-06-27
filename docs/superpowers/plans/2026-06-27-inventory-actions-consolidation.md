# Inventory Actions Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the broken inventory actions (equip/unequip/move/sell silently failing on the live sheet and wizard) and collapse the per-substrate duplication behind one composition dispatcher, one `/inventory/*` route family, one row source, and one action macro.

**Architecture:** A new `aose/engine/inventory_actions.py` dispatcher routes `equip/unequip/sell/charge/note` by `category ∈ {item, enchanted, magic}` to the existing engine functions (composition, mirroring `storage.move_thing`). Routes become thin shims under `…/inventory/*`. `InventoryRow` gains a `category` field and is built per-instance (no catalog collapse). One Jinja macro renders every per-row action.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Jinja2, pytest. Run Python as `.venv\Scripts\python.exe`. Tests: `.venv\Scripts\python.exe -m pytest tests/ -q`.

---

## Background the executor must know

- `spec.items: list[ItemInstance]` — flat, instance-keyed. An `ItemInstance` has `instance_id`, `catalog_id`, `location: StorageLocation`, `equip: str|None`, `count`, `enchantment_id: str|None`, `loaded_ammo_id`. **Enchanted** items are `ItemInstance`s with `enchantment_id is not None`; **plain** items have it `None`.
- **Magic items** are a *different* model: `spec.magic_items: list[MagicItemInstance]`, equipped via a toggle `equipped: bool` (not a slot).
- Existing engine functions and how they're called today (from `aose/web/routes.py`):
  - `equip.equip(spec, instance_id, *, data, slot, two_weapon, eligible, gargantua_1h_2h, allowed_weapons, allowed_armor, allow_shields)` — mutates `inst.equip` in place. Raises `ValueError`/`equip.WieldError`.
  - `equip.unequip(spec, instance_id)` — mutates in place. Raises `ValueError`.
  - `enchant.remove(items, instance_id) -> list` ; `enchant.use_charge(items, instance_id) -> list` ; `enchant.reset_charges(items, instance_id) -> list` ; `enchant.set_note(items, instance_id, note) -> list` — return a NEW list.
  - `magic.equip_magic(magic_items, instance_id, data) -> list` ; `magic.unequip_magic(magic_items, instance_id) -> list` ; `magic.use_charge(magic_items, instance_id) -> list` ; `magic.reset_charges(magic_items, instance_id) -> list` ; `magic.set_magic_note(magic_items, instance_id, note) -> list` ; `magic.remove_magic(magic_items, gold, instance_id, mode, data) -> (list, int)` — return NEW list(s).
  - `shop.sell_item(spec, catalog_id, mode, data)` and `shop.sell_from_stash(...)` — catalog-keyed, to be retired.
- **Out of scope substrates** (do NOT fold into the dispatcher): animal barding (`/animal/{id}/unequip` → `companions_engine.clear_armor`), containers, coins, gems, jewellery, ammo, spell-sources. Move already unifies these via `storage.move_thing`.
- The wizard equipment step (`aose/web/wizard.py`, templates `aose/web/templates/wizard/equipment.html`) reuses `_inv_pane.html` + `_inv_modals.html`, so its routes move in lockstep.
- "No migrations" project convention — delete dead code, don't keep back-compat shims.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `aose/engine/inventory_actions.py` | The action dispatcher (compose existing engines by category) | **Create** |
| `aose/engine/shop.py` | Add `sell_instance`; retire `sell_item`/`sell_from_stash` | Modify |
| `aose/sheet/view.py` | Per-instance, single-source item rows; `category` on rows | Modify |
| `aose/web/routes.py` | Replace per-item routes with `/inventory/*` family; retainer shims | Modify |
| `aose/web/wizard.py` | Same `/inventory/*` family for the wizard | Modify |
| `aose/web/templates/_inv_row_actions.html` | Single macro for item/enchanted/magic actions | Rewrite |
| `aose/web/templates/_inv_modals.html` | `item_modal` + `magic_modal` both delegate to the macro | Modify |
| `aose/web/templates/_actions.html` | `act_move` item branch → `instance_id` | Modify |
| `aose/web/templates/sheet.html` | Collapse inline magic blocks; iterate single row source | Modify |
| `tests/test_inventory_actions.py` | Dispatcher unit tests | **Create** |
| `tests/test_inventory_box_contract.py` | Rendered-form ↔ route contract test | **Create** |

---

## Task 1: Action dispatcher — equip/unequip

**Files:**
- Create: `aose/engine/inventory_actions.py`
- Test: `tests/test_inventory_actions.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_inventory_actions.py
import uuid
import pytest

from aose.data.loader import GameData
from aose.models import CharacterSpec, ClassEntry, ItemInstance
from aose.models.storage import StorageLocation
from aose.engine import inventory_actions as ia

DATA = GameData.load("data")


def _spec(**kw):
    """Minimal-but-valid PC, matching tests/test_equip_core.py::_spec."""
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw)
    return CharacterSpec(**base)


def _spec_with(catalog_id, enchantment_id=None):
    iid = uuid.uuid4().hex
    spec = _spec(items=[ItemInstance(
        instance_id=iid, catalog_id=catalog_id, count=1,
        location=StorageLocation(kind="carried"), enchantment_id=enchantment_id,
    )])
    return spec, iid


def test_equip_thing_item_sets_slot():
    spec, iid = _spec_with("sword")           # confirmed Weapon id in data/
    ia.equip_thing(spec, "item", iid, data=DATA, owner=None)
    assert next(i for i in spec.items if i.instance_id == iid).equip == "main_hand"


def test_unequip_thing_item_clears_slot():
    spec, iid = _spec_with("sword")
    ia.equip_thing(spec, "item", iid, data=DATA, owner=None)
    ia.unequip_thing(spec, "item", iid, owner=None)
    assert next(i for i in spec.items if i.instance_id == iid).equip is None


def test_bad_category_raises():
    spec, iid = _spec_with("sword")
    with pytest.raises(ia.InventoryActionError):
        ia.equip_thing(spec, "bogus", iid, data=DATA, owner=None)
```

> Confirmed real catalog ids in `data/`: `sword`, `mace`, `plate_mail` (see `tests/test_equip_core.py`). Reuse `DATA`/`_spec`/`_spec_with` for every test in this file.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_actions.py -q`
Expected: FAIL — `ModuleNotFoundError: aose.engine.inventory_actions`.

- [ ] **Step 3: Write minimal implementation**

```python
# aose/engine/inventory_actions.py
"""Single front door for per-item actions across the three inventory
substrates, composing the existing engines by ``category``.  Mirrors
``storage.move_thing``: differences between substrates live here as dispatch,
never as duplicated routes/templates.

  category == "item"      → plain ItemInstance   (spec.items, slot equip)
  category == "enchanted" → enchanted ItemInstance (spec.items, slot equip)
  category == "magic"     → MagicItemInstance    (spec.magic_items, toggle equip)

``owner`` selects the world the action runs in.  None / a "carried"/"stashed"
location means the PC itself; a ``retainer`` location runs against that
retainer's nested spec.  (Animal/vehicle "owners" never *equip* regular items —
that path is barding, handled by companions_engine — so they are not accepted
here.)
"""
from __future__ import annotations

from aose.data.loader import GameData
from aose.engine import equip as _equip_eng
from aose.engine import enchant as _enchant
from aose.engine import magic as _magic
from aose.engine import shop as _shop

ITEM_CATEGORIES = ("item", "enchanted")        # both are ItemInstance
ALL_CATEGORIES = ("item", "enchanted", "magic")


class InventoryActionError(ValueError):
    """Unknown category or illegal action (routes map to HTTP 400)."""


def _owning_spec(spec, owner):
    """The spec an action runs against: the PC, or a retainer's nested spec."""
    if owner is not None and getattr(owner, "kind", None) == "retainer":
        ret = next((r for r in spec.retainers if r.id == owner.id), None)
        if ret is None:
            raise InventoryActionError(f"no retainer {owner.id!r}")
        return ret.spec
    return spec


def equip_thing(spec, category, instance_id, *, data: GameData, owner=None,
                slot=None, two_weapon=False, eligible=False,
                gargantua_1h_2h=False, allowed_weapons="all",
                allowed_armor="all", allow_shields=True) -> None:
    target = _owning_spec(spec, owner)
    if category in ITEM_CATEGORIES:
        _equip_eng.equip(
            target, instance_id, data=data, slot=slot,
            two_weapon=two_weapon, eligible=eligible,
            gargantua_1h_2h=gargantua_1h_2h, allowed_weapons=allowed_weapons,
            allowed_armor=allowed_armor, allow_shields=allow_shields)
    elif category == "magic":
        target.magic_items = _magic.equip_magic(target.magic_items, instance_id, data)
    else:
        raise InventoryActionError(f"unknown category {category!r}")


def unequip_thing(spec, category, instance_id, *, owner=None) -> None:
    target = _owning_spec(spec, owner)
    if category in ITEM_CATEGORIES:
        _equip_eng.unequip(target, instance_id)
    elif category == "magic":
        target.magic_items = _magic.unequip_magic(target.magic_items, instance_id)
    else:
        raise InventoryActionError(f"unknown category {category!r}")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_actions.py -q`
Expected: PASS (3 tests). Ignore any trailing `pytest-current` PermissionError (known Windows quirk).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/inventory_actions.py tests/test_inventory_actions.py
git commit -m "feat(inventory): add equip/unequip action dispatcher"
```

---

## Task 2: `shop.sell_instance` — instance-keyed sale

**Files:**
- Modify: `aose/engine/shop.py` (add `sell_instance`, keep `sell_item`/`sell_from_stash` for now)
- Test: `tests/test_shop_spend.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_shop_spend.py
import uuid
from aose.models import CharacterSpec, ClassEntry, ItemInstance
from aose.models.storage import StorageLocation
from aose.engine import shop as _shop
from aose.data.loader import GameData

_SHOP_DATA = GameData.load("data")


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw)
    return CharacterSpec(**base)


def _two_maces_spec():
    ids = [uuid.uuid4().hex, uuid.uuid4().hex]
    spec = _spec(items=[
        ItemInstance(instance_id=ids[0], catalog_id="mace", count=1,
                     location=StorageLocation(kind="carried")),
        ItemInstance(instance_id=ids[1], catalog_id="mace", count=1,
                     location=StorageLocation(kind="carried")),
    ])
    return spec, ids


def test_sell_instance_removes_only_that_instance():
    spec, ids = _two_maces_spec()
    _shop.sell_instance(spec, ids[0], "drop", _SHOP_DATA)
    remaining = [i.instance_id for i in spec.items]
    assert ids[0] not in remaining and ids[1] in remaining


def test_sell_instance_refund_credits_carried_gp():
    spec, ids = _two_maces_spec()
    before = sum(s.count for s in spec.coins
                 if s.denom == "gp" and s.location.kind == "carried")
    _shop.sell_instance(spec, ids[0], "refund", _SHOP_DATA)
    after = sum(s.count for s in spec.coins
                if s.denom == "gp" and s.location.kind == "carried")
    assert after > before   # mace has a positive cost → refund credits gp
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_shop_spend.py -q -k sell_instance`
Expected: FAIL — `AttributeError: module 'aose.engine.shop' has no attribute 'sell_instance'`.

- [ ] **Step 3: Write minimal implementation**

Add to `aose/engine/shop.py` (next to `sell_item`):

```python
def sell_instance(spec, instance_id: str, mode: str, data: GameData) -> None:
    """Remove one bundle from the exact ItemInstance ``instance_id`` (carried or
    stashed); credit carried gp per mode.  Replaces the catalog-keyed
    ``sell_item``/``sell_from_stash`` — operates on the instance the user clicked,
    so multiple instances of one catalog id are unambiguous."""
    from aose.engine import storage as _storage
    if mode not in REMOVE_MODES:
        raise ValueError(f"Unknown remove mode {mode!r}; want one of {REMOVE_MODES}")
    inst = next((i for i in spec.items if i.instance_id == instance_id), None)
    if inst is None:
        raise ValueError(f"no item instance {instance_id!r}")
    item = data.items.get(inst.catalog_id)
    bundle = _bundle_count(item)
    remove_n = bundle if mode == "refund" else 1
    if inst.count < remove_n:
        raise ValueError(
            f"Cannot {mode} {inst.catalog_id!r}: insufficient count {inst.count} < {remove_n}")
    if inst.count <= remove_n:
        inst.equip = None
        inst.loaded_ammo_id = None
        spec.items.remove(inst)
    else:
        inst.count -= remove_n
    credit = _removal_gold(inst.catalog_id, mode, data)
    if credit:
        _storage._add_coins(spec, "gp", credit, StorageLocation(kind="carried"))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_shop_spend.py -q -k sell_instance`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/shop.py tests/test_shop_spend.py
git commit -m "feat(shop): instance-keyed sell_instance"
```

---

## Task 3: Dispatcher — sell/charge/note

**Files:**
- Modify: `aose/engine/inventory_actions.py`
- Test: `tests/test_inventory_actions.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_inventory_actions.py
def test_sell_thing_item_drop_removes():
    spec, iid = _spec_with("mace")
    ia.sell_thing(spec, "item", iid, "drop", DATA)
    assert all(i.instance_id != iid for i in spec.items)


def test_sell_thing_enchanted_drops_via_enchant_remove():
    spec, iid = _spec_with("sword", enchantment_id=ENCHANT_ID)
    ia.sell_thing(spec, "enchanted", iid, "drop", DATA)
    assert all(i.instance_id != iid for i in spec.items)
```

> Define `ENCHANT_ID` at the top of the test file with a real id from
> `data/enchantments.yaml` whose compatible bases include `sword` (inspect with
> `grep -n "id:" data/enchantments.yaml`). `enchant.remove` only needs the
> instance to exist, so any valid enchanted `ItemInstance` works.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_actions.py -q -k "sell_thing"`
Expected: FAIL — `AttributeError: ... has no attribute 'sell_thing'`.

- [ ] **Step 3: Implement**

Append to `aose/engine/inventory_actions.py`:

```python
def sell_thing(spec, category, instance_id, mode: str, data: GameData,
               *, owner=None) -> None:
    target = _owning_spec(spec, owner)
    if category == "item":
        _shop.sell_instance(target, instance_id, mode, data)
    elif category == "enchanted":
        # Enchanted items have no resale price; every mode is a drop.
        target.items = _enchant.remove(target.items, instance_id)
    elif category == "magic":
        gold = _carried_gp(target)
        target.magic_items, new_gold = _magic.remove_magic(
            target.magic_items, gold, instance_id, mode, data)
        _set_carried_gp(target, new_gold)
    else:
        raise InventoryActionError(f"unknown category {category!r}")


def use_charge_thing(spec, category, instance_id, *, owner=None) -> None:
    target = _owning_spec(spec, owner)
    if category == "enchanted":
        target.items = _enchant.use_charge(target.items, instance_id)
    elif category == "magic":
        target.magic_items = _magic.use_charge(target.magic_items, instance_id)
    else:
        raise InventoryActionError(f"{category!r} has no charges")


def reset_charges_thing(spec, category, instance_id, *, owner=None) -> None:
    target = _owning_spec(spec, owner)
    if category == "enchanted":
        target.items = _enchant.reset_charges(target.items, instance_id)
    elif category == "magic":
        target.magic_items = _magic.reset_charges(target.magic_items, instance_id)
    else:
        raise InventoryActionError(f"{category!r} has no charges")


def set_note_thing(spec, category, instance_id, note: str, *, owner=None) -> None:
    target = _owning_spec(spec, owner)
    if category == "enchanted":
        target.items = _enchant.set_note(target.items, instance_id, note)
    elif category == "magic":
        target.magic_items = _magic.set_magic_note(target.magic_items, instance_id, note)
    else:
        raise InventoryActionError(f"{category!r} has no note")
```

Add the gp helpers near the top of the module (copied intent from `routes._get_gold`/`_set_gold`):

```python
from aose.models import CoinStack
from aose.models.storage import StorageLocation as _SL


def _carried_gp(spec) -> int:
    return next((s.count for s in spec.coins
                 if s.denom == "gp" and s.location.kind == "carried"), 0)


def _set_carried_gp(spec, amount: int) -> None:
    carried = _SL(kind="carried")
    spec.coins = [s for s in spec.coins
                  if not (s.denom == "gp" and s.location == carried)]
    if amount > 0:
        spec.coins.append(CoinStack(denom="gp", count=amount))
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_actions.py -q`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/inventory_actions.py tests/test_inventory_actions.py
git commit -m "feat(inventory): dispatcher sell/charge/note across categories"
```

---

## Task 4: Per-instance, single-source item rows in the view

**Files:**
- Modify: `aose/engine/shop.py` (`InventoryRow.category` field)
- Modify: `aose/sheet/view.py` (`_item_rows_at` helper; use it for carried/stashed/equipped)
- Test: `tests/test_inventory_view.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_inventory_view.py
import uuid
from aose.models import CharacterSpec, ClassEntry, ItemInstance
from aose.models.storage import StorageLocation
from aose.data.loader import GameData
from aose.sheet.view import build_inventory_groups

_VIEW_DATA = GameData.load("data")


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw)
    return CharacterSpec(**base)


def test_two_identical_weapons_render_as_two_rows_with_distinct_ids():
    ids = [uuid.uuid4().hex, uuid.uuid4().hex]
    spec = _spec(items=[
        ItemInstance(instance_id=ids[0], catalog_id="mace", count=1,
                     location=StorageLocation(kind="carried")),
        ItemInstance(instance_id=ids[1], catalog_id="mace", count=1,
                     location=StorageLocation(kind="carried")),
    ])
    groups = build_inventory_groups(spec, _VIEW_DATA)
    carried = next(g for g in groups if g.kind == "carried")
    mace_rows = [r for r in carried.loose if r.id == "mace"]
    assert len(mace_rows) == 2
    assert {r.instance_id for r in mace_rows} == set(ids)
    assert all(r.category == "item" for r in mace_rows)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_view.py -q -k two_identical`
Expected: FAIL — either one row of count 2 (collapse) or `category` attribute missing.

- [ ] **Step 3a: Add `category` to `InventoryRow`**

In `aose/engine/shop.py`, in `class InventoryRow`, add after `instance_id`:

```python
    category: str = "item"       # "item" | "enchanted" — drives the action macro
```

- [ ] **Step 3b: Add a per-instance row builder in `aose/sheet/view.py`**

Add near the other inventory helpers (above `build_inventory_groups`):

```python
def _item_rows_at(spec, loc, data, aw, aa, ash, *, two_weapon, eligible,
                  gargantua):
    """Per-instance InventoryRows for plain items at ``loc``.  One row per
    ItemInstance (equippables stay distinct; stackables are already one merged
    instance).  Each row carries its real instance_id + category='item'."""
    from aose.engine.shop import _build_row
    from aose.models import Ammunition
    off_full = any(i.equip == "off_hand" for i in spec.items)
    rows = []
    for inst in spec.items:
        if inst.enchantment_id is not None or inst.location != loc:
            continue
        if isinstance(data.items.get(inst.catalog_id), Ammunition):
            continue
        if inst.equip is not None:
            continue   # equipped rows are built separately
        r = _build_row(inst.catalog_id, inst.count, data, aw, aa, ash,
                       two_weapon=two_weapon, eligible=eligible, off_full=off_full)
        rows.append(r.model_copy(update={"instance_id": inst.instance_id,
                                         "category": "item"}))
    rows.sort(key=lambda r: r.name)
    return rows


def _equipped_item_rows(spec, data, aw, aa, ash, *, two_weapon, eligible,
                        gargantua):
    """Per-instance InventoryRows for equipped plain items (slot occupants)."""
    from aose.engine.shop import _build_row
    rows = []
    for inst in spec.items:
        if inst.equip is None or inst.enchantment_id is not None:
            continue
        r = _build_row(inst.catalog_id, inst.count, data, aw, aa, ash,
                       two_weapon=two_weapon, eligible=eligible)
        rows.append(r.model_copy(update={"instance_id": inst.instance_id,
                                         "category": "item"}))
    rows.sort(key=lambda r: r.name)
    return rows
```

- [ ] **Step 3c: Use the new builders for the carried & stashed groups**

In `build_inventory_groups` (`aose/sheet/view.py`), replace the `inv_view` round-trip (the block building `_inv_ids`/`_stash_ids`/`_equip_dict`/`inv_view = inventory_view(...)`, currently ~lines 1517–1525) with direct per-instance rows. Where the carried group currently sets `equipped=inv_view.equipped` and `loose=inv_view.carried`, use:

```python
    _eq_kwargs = dict(two_weapon=spec.ruleset.two_weapon_fighting,
                      eligible=_pc_eligible, gargantua=_pc_gargantua)
    pc_equipped_rows = _equipped_item_rows(spec, data, _pc_aw, _pc_aa, _pc_as, **_eq_kwargs)
    pc_carried_rows = _item_rows_at(spec, carried_loc, data, _pc_aw, _pc_aa, _pc_as, **_eq_kwargs)
    pc_stashed_rows = _item_rows_at(spec, stashed_loc, data, _pc_aw, _pc_aa, _pc_as, **_eq_kwargs)
```

Then set `equipped=pc_equipped_rows`, `loose=pc_carried_rows` on the carried group and `loose=pc_stashed_rows` on the stashed group. Define `_pc_eligible` and `_pc_gargantua` once near `_pc_aw`/`_pc_aa`/`_pc_as` using the existing helpers already imported in this module:

```python
    from aose.engine.proficiency import two_weapon_eligible as _twe
    from aose.engine.features import one_handed_two_handed_weapons as _1h2h
    _pc_classes = [data.classes[e.class_id] for e in spec.classes if e.class_id in data.classes]
    _pc_eligible = _twe(_pc_classes)
    _pc_gargantua = _1h2h(spec, data)
```

> Keep `inventory_view`/`inv_view` only if other call sites still need it; once carried/stashed/equipped no longer reference `inv_view`, delete the `inv_view` line. The retainer/animal/vehicle loose rows already use `_build_row` per instance — give them `category="item"` + their `instance_id` the same way (`_build_row(...).model_copy(update={"instance_id": i.instance_id, "category": "item"})`) so their action forms also work. Equipped retainer/animal rows: set `instance_id`/`category` likewise.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_view.py tests/test_sheet_inventory_box.py -q`
Expected: PASS. Fix any existing assertions that expected catalog-collapsed rows (they should now expect per-instance rows).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/shop.py aose/sheet/view.py tests/test_inventory_view.py
git commit -m "feat(view): per-instance single-source inventory rows with category"
```

---

## Task 5: New `/inventory/*` route family (character sheet)

**Files:**
- Modify: `aose/web/routes.py`
- Test: `tests/test_inventory_action_routes.py` (**create**)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_inventory_action_routes.py
"""HTTP tests for the unified /inventory/* action family.
Fixture style copied verbatim from tests/test_inventory_move_routes.py."""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character
from aose.models import CharacterSpec, ClassEntry, ItemInstance
from aose.models.storage import StorageLocation
from aose.web.app import create_app

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    app = create_app(
        data_dir=DATA_DIR, characters_dir=characters_dir, drafts_dir=drafts_dir,
        examples_dir=examples_dir, settings_path=tmp_path / "settings.json",
    )
    c = TestClient(app, follow_redirects=False)
    c._characters_dir = characters_dir
    return c


def _save_hero(client, items):
    spec = CharacterSpec(
        name="Hero", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
        "CON": 10, "CHA": 10}, race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral", items=items)
    save_character("hero", spec, client._characters_dir)


def test_equip_route_accepts_instance_id(client):
    _save_hero(client, [ItemInstance(
        instance_id="i1", catalog_id="sword",
        location=StorageLocation(kind="carried"))])
    resp = client.post("/character/hero/inventory/equip",
                       data={"category": "item", "instance_id": "i1"})
    assert resp.status_code == 303
    assert load_character("hero", client._characters_dir).items[0].equip == "main_hand"


def test_old_equipment_equip_route_is_gone(client):
    _save_hero(client, [ItemInstance(
        instance_id="i1", catalog_id="sword",
        location=StorageLocation(kind="carried"))])
    resp = client.post("/character/hero/equipment/equip",
                       data={"instance_id": "i1"})
    assert resp.status_code == 404
```

> The second test is only valid AFTER Task 9 deletes the old route — until then it
> will fail; mark it `@pytest.mark.skip("enabled in Task 9")` if running Task 5 in
> isolation, then drop the skip in Task 9.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_action_routes.py -q`
Expected: FAIL — 404 (route doesn't exist yet).

- [ ] **Step 3: Implement the route family**

In `aose/web/routes.py`, add a helper + the family (place near the existing `/inventory/move` route). Use the existing `_load_spec_or_404`, `save_character`, `allowed_weapon_ids`, `allowed_armor_ids`, `shields_allowed`, `two_weapon_eligible`, `_1h2h` already imported in this file:

```python
from aose.engine import inventory_actions as _ia


def _equip_gates(spec, data):
    classes = [data.classes[e.class_id] for e in spec.classes if e.class_id in data.classes]
    return dict(
        two_weapon=spec.ruleset.two_weapon_fighting,
        eligible=two_weapon_eligible(classes),
        gargantua_1h_2h=_1h2h(spec, data),
        allowed_weapons=allowed_weapon_ids(classes, data, spec.ruleset),
        allowed_armor=allowed_armor_ids(classes, data),
        allow_shields=shields_allowed(classes),
    )


@router.post("/character/{character_id}/inventory/equip")
async def inventory_equip(request: Request, character_id: str,
                          category: str = Form(...), instance_id: str = Form(...),
                          slot: str | None = Form(None)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        _ia.equip_thing(spec, category, instance_id, data=data, slot=slot,
                        **_equip_gates(spec, data))
    except (ValueError, WieldError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/inventory/unequip")
async def inventory_unequip(request: Request, character_id: str,
                            category: str = Form(...), instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        _ia.unequip_thing(spec, category, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/inventory/sell")
async def inventory_sell(request: Request, character_id: str,
                         category: str = Form(...), instance_id: str = Form(...),
                         mode: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        _ia.sell_thing(spec, category, instance_id, mode, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/inventory/charge")
async def inventory_charge(request: Request, character_id: str,
                           category: str = Form(...), instance_id: str = Form(...),
                           op: str = Form("use")):
    spec = _load_spec_or_404(request, character_id)
    try:
        if op == "reset":
            _ia.reset_charges_thing(spec, category, instance_id)
        else:
            _ia.use_charge_thing(spec, category, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/inventory/note")
async def inventory_note(request: Request, character_id: str,
                         category: str = Form(...), instance_id: str = Form(...),
                         note: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    try:
        _ia.set_note_thing(spec, category, instance_id, note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_action_routes.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_inventory_action_routes.py
git commit -m "feat(routes): unified /inventory/{equip,unequip,sell,charge,note} family"
```

---

## Task 6: Wizard `/inventory/*` family + retainer shims

**Files:**
- Modify: `aose/web/wizard.py` (mirror the family; persistence via the wizard's draft-save helper)
- Modify: `aose/web/routes.py` (retainer `/equip` `/unequip` → dispatcher with `owner`)
- Test: `tests/test_wizard.py`, `tests/test_retainer_routes.py` (append a 303 smoke each)

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_retainer_routes.py — adapt to the file's existing fixtures
def test_retainer_equip_accepts_instance_id(retainer_client):
    client, character_id, rid, iid = retainer_client("sword")
    resp = client.post(
        f"/character/{character_id}/retainer/{rid}/equip",
        data={"category": "item", "instance_id": iid}, follow_redirects=False)
    assert resp.status_code == 303
```

```python
# append to tests/test_wizard.py — adapt to the file's existing draft fixtures
def test_wizard_equip_accepts_instance_id(wizard_equipment_draft):
    client, draft_id, iid = wizard_equipment_draft("sword")
    resp = client.post(f"/wizard/{draft_id}/inventory/equip",
                       data={"category": "item", "instance_id": iid},
                       follow_redirects=False)
    assert resp.status_code == 303
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_routes.py tests/test_wizard.py -q -k "accepts_instance_id"`
Expected: FAIL — retainer route still wants `item_id` (422), wizard route 404.

- [ ] **Step 3a: Retainer shims (`aose/web/routes.py`)** — replace `retainer_equip`/`retainer_unequip` bodies:

```python
@router.post("/character/{character_id}/retainer/{retainer_id}/unequip")
async def retainer_unequip(request: Request, character_id: str, retainer_id: str,
                           category: str = Form("item"), instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    owner = _SL(kind="retainer", id=retainer_id)
    try:
        _ia.unequip_thing(spec, category, instance_id, owner=owner)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/retainer/{retainer_id}/equip")
async def retainer_equip(request: Request, character_id: str, retainer_id: str,
                         category: str = Form("item"), instance_id: str = Form(...),
                         slot: str | None = Form(None)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    ret = next((r for r in spec.retainers if r.id == retainer_id), None)
    if ret is None:
        raise HTTPException(404, "No such retainer")
    owner = _SL(kind="retainer", id=retainer_id)
    try:
        _ia.equip_thing(spec, category, instance_id, data=data, owner=owner, slot=slot,
                        two_weapon=ret.spec.ruleset.two_weapon_fighting)
    except (ValueError, WieldError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 3b: Wizard family (`aose/web/wizard.py`)** — add the `/inventory/*` routes mirroring Task 5 but using the wizard's draft load/save pattern (read the existing `post_equipment_equip`/`post_equipment_unequip` to copy the exact draft-spec load + `save_draft` calls). Each handler loads the draft spec, calls `_ia.<action>_thing(...)`, saves the draft, and redirects to `/wizard/{draft_id}/equipment`. Wizard categories are `item`/`enchanted`/`magic` exactly as the sheet. Delete the wizard's old `/equipment/equip` and `/equipment/unequip` routes.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_routes.py tests/test_wizard.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py aose/web/wizard.py tests/test_retainer_routes.py tests/test_wizard.py
git commit -m "feat(routes): wizard inventory family + retainer dispatcher shims"
```

---

## Task 7: Unify the action macro + `act_move` for items

**Files:**
- Rewrite: `aose/web/templates/_inv_row_actions.html`
- Modify: `aose/web/templates/_actions.html` (`act_move` item branch)
- Modify: `aose/web/templates/_inv_modals.html` (`item_modal` passes `equipped` flag)

- [ ] **Step 1: Switch `act_move` to instance_id**

In `aose/web/templates/_actions.html`, change the item branch of `act_move`:

```jinja
  {% if ref.category == 'coin' %}<input type="hidden" name="denom" value="{{ ref.id }}">
  {% else %}<input type="hidden" name="instance_id" value="{{ ref.id }}">{% endif %}
```

(Remove the separate `item_id` branch — every non-coin category now posts `instance_id`. Callers already pass the instance id for gem/jewellery/magic; the item callers will pass `row.instance_id`, see Step 3.)

- [ ] **Step 2: Rewrite `_inv_row_actions.html` as the single category-aware macro**

```jinja
{% from "_actions.html" import act_move with context %}
{# Single per-row action macro for all three inventory substrates.
   row.category ∈ {"item","enchanted","magic"}; row.instance_id is required.
   `equipped` is the caller's truth for whether this row occupies a slot.
   `inv_prefix` is the /inventory action prefix, e.g. "/character/<id>/inventory"
   or "/wizard/<id>/inventory" or "/character/<id>/retainer/<rid>". #}
{% macro inv_row_actions(row, inv_prefix, state, equipped=False, show_remove=True, src_id="") %}
  {%- set cat = row.category | default("item") -%}
  {% if equipped %}
    <form method="post" action="{{ inv_prefix }}/unequip" class="inline-form">
      <input type="hidden" name="category" value="{{ cat }}">
      <input type="hidden" name="instance_id" value="{{ row.instance_id }}">
      <button type="submit" class="btn btn-inline">Unequip</button>
    </form>
    {% if row.charges_remaining is defined and row.charges_remaining is not none %}
    <span class="muted small">Charges {{ row.charges_remaining }} / {{ row.charges_max }}</span>
    <form method="post" action="{{ inv_prefix }}/charge" class="inline-form">
      <input type="hidden" name="category" value="{{ cat }}">
      <input type="hidden" name="instance_id" value="{{ row.instance_id }}">
      <input type="hidden" name="op" value="use">
      <button type="submit" class="btn btn-inline"{% if row.charges_remaining == 0 %} disabled{% endif %}>Use one</button>
    </form>
    {% endif %}
  {% elif row.equippable | default(False) or cat in ("enchanted", "magic") %}
    {% if row.class_allowed | default(True) %}
    <form method="post" action="{{ inv_prefix }}/equip" class="inline-form">
      <input type="hidden" name="category" value="{{ cat }}">
      <input type="hidden" name="instance_id" value="{{ row.instance_id }}">
      <button type="submit" class="btn btn-inline">Equip</button>
    </form>
    {% if row.can_off_hand | default(False) %}
    <form method="post" action="{{ inv_prefix }}/equip" class="inline-form">
      <input type="hidden" name="category" value="{{ cat }}">
      <input type="hidden" name="instance_id" value="{{ row.instance_id }}">
      <input type="hidden" name="slot" value="off_hand">
      <button type="submit" class="btn btn-inline"{% if row.off_hand_blocked %} disabled title="Off hand occupied"{% endif %}>Off-hand</button>
    </form>
    {% endif %}
    {% else %}
    <span class="muted small" title="Your class cannot use this item">Not usable</span>
    {% endif %}
  {% endif %}

  {% if move_targets is defined %}
    {{ act_move(inv_prefix ~ "/move", {"category": cat, "id": row.instance_id}, move_targets, ("carried" if equipped else state), src_id) }}
  {% endif %}

  {% if show_remove %}
    {% if cat == "enchanted" %}
      <form method="post" action="{{ inv_prefix }}/sell" class="inline-form">
        <input type="hidden" name="category" value="enchanted">
        <input type="hidden" name="instance_id" value="{{ row.instance_id }}">
        <button type="submit" name="mode" value="drop" class="btn btn-inline danger">Drop</button>
      </form>
    {% else %}
      {% if (row.cost_gp | default(0)) > 0 %}
      <form method="post" action="{{ inv_prefix }}/sell" class="sell-form inline-form">
        <input type="hidden" name="category" value="{{ cat }}">
        <input type="hidden" name="instance_id" value="{{ row.instance_id }}">
        <input type="hidden" name="mode" value="">
        <select class="sell-dest">
          <option value="" disabled selected>Sell…</option>
          <option value="sell">+{{ row.sell_gp | default((row.cost_gp / 2) | int) }}&nbsp;gp (half price)</option>
          {% if row.can_refund | default(True) %}
          <option value="refund">+{{ row.cost_gp | int }}&nbsp;gp (refund{% if (row.bundle_count | default(1)) > 1 %}&nbsp;×{{ row.bundle_count }}{% endif %})</option>
          {% endif %}
        </select>
      </form>
      {% endif %}
      <form method="post" action="{{ inv_prefix }}/sell" class="inline-form">
        <input type="hidden" name="category" value="{{ cat }}">
        <input type="hidden" name="instance_id" value="{{ row.instance_id }}">
        <button type="submit" name="mode" value="drop" class="btn btn-inline danger" title="Throw away — no gold back">Drop</button>
      </form>
    {% endif %}
  {% endif %}
{% endmacro %}
```

- [ ] **Step 3: Update `item_modal` to pass the new prefix + `equipped`**

In `aose/web/templates/_inv_modals.html`, `item_modal` currently passes `url_prefix` ending in `/equipment` and a `state`. Change its `inv_row_actions` call to compute the `/inventory` prefix and the equipped flag:

```jinja
    {%- set inv_prefix = url_prefix.replace('/equipment','') ~ '/inventory'
          if url_prefix.endswith('/equipment') else url_prefix -%}
    <div class="row-actions">{{ inv_row_actions(row, inv_prefix, state, equipped=(state == "equipped"), show_remove=(state in ("carried", "stashed")), src_id=src_id) }}</div>
```

> The sheet passes `target_url_prefix = /character/<id>/equipment`; `.replace('/equipment','')` yields `/character/<id>`, then `+ /inventory`. Retainer modals pass `ret_url = /character/<id>/retainer/<rid>` (no `/equipment` suffix) → used as-is, so retainer forms post to `/character/<id>/retainer/<rid>/equip` etc., which the Task 6 shims serve.

- [ ] **Step 3b: Remove the dead macro import**

`aose/web/templates/_equipment_ui.html` line 1 imports `inv_row_actions` but never calls it. Delete that import line so the changed macro signature has no stale reference.

- [ ] **Step 4: Render check**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py -q`
Expected: PASS (template renders; no Jinja errors). If a test asserted old form fields, update it to the new `category`/`instance_id` fields.

- [ ] **Step 5: Commit**

```bash
git add aose/web/templates/_inv_row_actions.html aose/web/templates/_actions.html aose/web/templates/_inv_modals.html aose/web/templates/_equipment_ui.html
git commit -m "feat(templates): single category-aware inv_row_actions macro"
```

---

## Task 8: Collapse the inline magic blocks; single modal source in sheet.html

**Files:**
- Modify: `aose/web/templates/_inv_modals.html` (add `magic_modal` delegating to the macro)
- Modify: `aose/web/templates/sheet.html` (replace inline magic blocks; point carried/stashed/equipped modals at the single row source)
- Modify: `aose/web/routes.py` and `aose/web/wizard.py` (stop passing `inventory_view`; ensure rows carry `category`)

- [ ] **Step 1: Add `magic_modal` macro to `_inv_modals.html`**

```jinja
{# Per-magic/enchanted-item modal — delegates all actions to inv_row_actions.
   `mi` is a MagicItemView carrying .category ("magic"|"enchanted"), .instance_id,
   .equipped, .charges_remaining, .cost_gp, .class_allowed, .modifier_summary. #}
{% macro magic_modal(mi, inv_prefix, src_kind, src_id) %}
<div class="overlay modal" id="modal-magic-{{ mi.instance_id }}" role="dialog" aria-label="{{ mi.name }}">
  <div class="ov-head"><h3>{{ mi.name }}</h3><button class="x" data-close>×</button></div>
  <div class="ov-body">
    {% if mi.modifier_summary %}<p style="margin:0 0 8px">{% for chip in mi.modifier_summary %}<span class="tag stamp">{{ chip }}</span> {% endfor %}</p>{% endif %}
    {% if mi.description %}<div class="prose">{{ mi.description | markdown | safe }}</div>{% endif %}
    <div class="row-actions">{{ inv_row_actions(mi, inv_prefix, src_kind, equipped=mi.equipped, show_remove=True, src_id=src_id) }}</div>
  </div>
</div>
{% endmacro %}
```

Add `from "_inv_row_actions.html" import inv_row_actions with context` at the top of `_inv_modals.html` if not already imported.

- [ ] **Step 2: Give MagicItemView its `category`**

In `aose/sheet/view.py`, the `MagicItemView` model (the one with `instance_id`, `equipped`, `modifier_summary`, `charges_remaining`, `cost_gp`, `class_allowed`) gains:

```python
    category: str = "magic"     # "magic" | "enchanted"
```

In `enchanted_items_view(...)`, set `category="enchanted"` on each row it builds; `magic_items_view(...)` leaves the default `"magic"`. (Both functions are in `aose/sheet/view.py`.)

- [ ] **Step 3: Replace the inline magic blocks in `sheet.html`**

Replace `sheet.html` lines ~990–1091 (the two inline `modal-magic-*` blocks — top-level and container-stowed) with calls to `magic_modal`. The PC `/inventory` prefix is `_char_url ~ "/inventory"`:

```jinja
{%- set _inv = _char_url ~ "/inventory" -%}
{% for group in sheet.inventory_groups %}
{%- set gkind = group.kind -%}{%- set gid = group.id or "" -%}
{% for mi in group.equipped_magic + group.magic_items + group.enchanted %}
{{ magic_modal(mi, _inv, gkind, gid) }}
{% endfor %}
{% for c in group.containers %}
{% for mi in c.stowed_magic + c.stowed_enchanted %}
{{ magic_modal(mi, _inv, "container", c.instance_id) }}
{% endfor %}
{% endfor %}
{% endfor %}
```

Import `magic_modal` in the `_inv_modals.html` import line at the top of `sheet.html`.

- [ ] **Step 4: Point the carried/stashed/equipped item modals at the single source**

Replace `sheet.html` lines 954–960 (which iterate `inventory_view.*`) with iteration over the carried/stashed groups so there is one row source:

```jinja
{% set _cg = sheet.inventory_groups | selectattr("kind","equalto","carried") | first | default(none) %}
{% set _sg = sheet.inventory_groups | selectattr("kind","equalto","stashed") | first | default(none) %}
{% if _cg %}{% for row in _cg.loose %}{{ item_modal(row, "carried", "carried", target_url_prefix) }}{% endfor %}{% endif %}
{% if _sg %}{% for row in _sg.loose %}{{ item_modal(row, "stashed", "stashed", target_url_prefix) }}{% endfor %}{% endif %}
{% if _cg %}{% for row in _cg.equipped %}
{%- set lo = ammo_load_options.get(row.instance_id) -%}
{%- set atk = sheet.attacks | selectattr('manageable_item_id', 'equalto', row.instance_id) | first -%}
{{ item_modal(row, "equipped", "equipped", target_url_prefix, load_options=lo, attack=atk) }}
{% endfor %}{% endif %}
```

- [ ] **Step 5: Stop passing `inventory_view` from the routes**

In `aose/web/routes.py` `character_sheet` and `aose/web/wizard.py` `_equipment_context`, remove the `inventory_view=...` context entry and the now-dead `_inv_list`/`_stash_list`/`_eq_dict` reconstruction (the `shop_inventory_view(...)` block). Grep both files for `inventory_view` and remove the dead context. Keep everything else.

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (full suite). Fix fallout (template KeyErrors for removed context, tests asserting `inventory_view`).

- [ ] **Step 6: Commit**

```bash
git add aose/web/templates/_inv_modals.html aose/web/templates/sheet.html aose/sheet/view.py aose/web/routes.py aose/web/wizard.py
git commit -m "feat(templates): one magic_modal + single row source; drop inventory_view ctx"
```

---

## Task 9: Contract test + delete dead routes/funcs

**Files:**
- Create: `tests/test_inventory_box_contract.py`
- Modify: `aose/web/routes.py`, `aose/web/wizard.py` (delete old routes), `aose/engine/shop.py` (delete `sell_item`/`sell_from_stash`), `aose/web/templates/sheet.html` (remove stale imports)

- [ ] **Step 1: Write the contract test**

```python
# tests/test_inventory_box_contract.py
"""Guards the template↔route contract that silently broke after the items
refactor: every action <form> the inventory box renders must POST to a live
route with the field names that route declares."""
import re
from html.parser import HTMLParser
from fastapi.testclient import TestClient
from aose.web.app import app


class _Forms(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self._cur = None
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self._cur = {"action": a.get("action", ""), "method": a.get("method", "get"), "fields": set()}
        elif tag in ("input", "select", "button") and self._cur is not None and a.get("name"):
            self._cur["fields"].add(a["name"])
    def handle_endtag(self, tag):
        if tag == "form" and self._cur is not None:
            self.forms.append(self._cur); self._cur = None


def test_inventory_action_forms_match_routes(inventory_box_character):
    """`inventory_box_character` fixture: a saved character with an equipped
    weapon, a carried weapon, a stashed item, an enchanted item, and a magic
    item; returns (client, character_id)."""
    client, character_id = inventory_box_character
    html = client.get(f"/character/{character_id}").text
    p = _Forms(); p.feed(html)

    routes = {(r.path, m) for r in app.routes for m in getattr(r, "methods", []) or []}
    EXPECTED = {
        "/inventory/equip": {"category", "instance_id"},
        "/inventory/unequip": {"category", "instance_id"},
        "/inventory/sell": {"category", "instance_id", "mode"},
        "/inventory/move": {"category"},
    }
    seen = set()
    for f in p.forms:
        for suffix, required in EXPECTED.items():
            if f["action"].endswith(suffix):
                seen.add(suffix)
                assert required <= f["fields"], (
                    f"{f['action']} missing {required - f['fields']}")
                # the path must resolve to a real POST route
                tmpl = f["action"].replace(character_id, "{character_id}")
                assert (tmpl, "POST") in routes, f"no POST route for {f['action']}"
    assert {"/inventory/equip", "/inventory/unequip", "/inventory/sell"} <= seen
```

> Build `inventory_box_character` as a pytest fixture using the **exact** `create_app` client fixture from Task 5 (`tests/test_inventory_action_routes.py`). Save a "hero" with: one equipped weapon (`ItemInstance(catalog_id="sword", equip="main_hand")`), one carried weapon (`ItemInstance(catalog_id="mace", location=carried)`), one stashed item (`location=stashed`), one enchanted `ItemInstance` (`enchantment_id=ENCHANT_ID`), and one `MagicItemInstance` in `magic_items` (see `tests/test_magic_items.py` for how to construct one). Return `(client, "hero")`. This guarantees every form variant renders.

- [ ] **Step 2: Run — expect PASS** (the implementation from Tasks 5–8 already satisfies the contract)

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_box_contract.py -q`
Expected: PASS. If it fails, a template still posts the wrong field — fix the template, not the test.

- [ ] **Step 3: Delete dead routes and functions**

- In `aose/web/routes.py` delete: `equipment_equip`, `equipment_unequip`, `equipment_remove`, `equipment_equip_magic`, `equipment_unequip_magic`, `equipment_use_charge`, `equipment_reset_charges`, `equipment_remove_magic`, `equipment_magic_note`, `equipment_equip_enchanted`, `equipment_unequip_enchanted`, `equipment_enchanted_use_charge`, `equipment_enchanted_reset_charges`, `equipment_remove_enchanted`, `equipment_enchanted_note`. Remove now-unused imports they pulled in (`equip as _equip`, `unequip as _unequip`, the `_magic`/`_enchant` action aliases, `shop_sell_item`, `shop_sell_from_stash`) — let the test suite tell you which are still used.
- In `aose/web/wizard.py` delete the old `/equipment/equip` and `/equipment/unequip` routes (and any enchanted/magic equivalents) plus now-unused imports.
- In `aose/engine/shop.py` delete `sell_item` and `sell_from_stash`.

- [ ] **Step 4: Full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS. Resolve any `ImportError`/`NameError` from deleted symbols by removing their last references.

- [ ] **Step 5: Manual smoke (the original bug)**

Run the app: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`. On a character's live sheet, open a carried weapon → **Equip**; open it under Equipped → **Unequip**; **Move** a carried item to Stashed; **Sell** a carried item. Each must redirect and reflect the change (no 422/400).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "test(inventory): box↔route contract test; delete dead per-substrate routes"
```

---

## Self-review notes (for the executor)

- **Spec §A–F coverage:** §A→Tasks 1,3; §B→Task 2; §C→Tasks 5,6,9; §D→Task 4; §E→Tasks 7,8; §F→Tasks 1,2,3,9.
- **Animal `/unequip` is barding** (`companions_engine.clear_armor`) — intentionally NOT folded into the dispatcher.
- **Enchanted "sell" is always drop** — there is no half-price path; the macro shows only Drop for `category == "enchanted"`.
- **Two modal shells remain** (`item_modal` for InventoryRow, `magic_modal` for MagicItemView) but both delegate to the one `inv_row_actions` macro — the actual duplication (the action forms) is gone, which is the maintainability goal.
- If any existing test encodes the OLD behaviour (catalog-collapsed rows, `item_id` form fields, old route paths), update the test to the new contract — that is expected fallout, not a regression.
