# Stackable Actions + Storage Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the inventory-actions consolidation by closing six equipment bugs holistically: make container/carrier contents carry real instance ids, make container resolution world-aware (PC ↔ retainer), give every item-add path one merge rule, gate Equip by location, and replace ammo's bespoke modal with one composed **stackable-actions** component (quantity box → Move / Sell / Drop / Consume) shared by items, ammo, coins, and gems.

**Architecture:** Three engine fixes + one template/JS component, all extending the existing `storage.move_thing` / `inv_row_actions` consolidation (see `docs/superpowers/specs/2026-06-27-inventory-actions-consolidation-design.md`). No new class hierarchy — composition and shared pure functions, per project convention. No data migrations (app isn't deployed).

**Tech Stack:** Python 3 / Pydantic v2 / FastAPI / Jinja2; vanilla JS (`inventory.js`). Tests: pytest.

---

## Spec recap (locked decisions from the user)

The canonical **stackable interface**, applied to every stackable substrate via composition:

- A **quantity numberbox** with up/down adjusters (native `<input type="number">`). Default value = current stack size; clamped to `1..count`.
- A **single "Move to…" dropdown** that moves `count` (the box value) — no separate Move button.
- A **separate Sell** control that sells `count` (sellable items only).
- **Coins** (and anything unsellable) get **Drop** in place of Sell.
- **Standard stacking items** (the `spec.items` consumables — not treasure) additionally get a **Consume** button that removes exactly one.
- Built once, composed everywhere. No substrate rolls its own action UI.

Plus the five non-stacking bugs:

1. Equip offered at locations that can't equip (stashed / animal / vehicle / container).
2. Moving an item *out of* a container → `no item instance ''` (contents rows lack `instance_id`).
3. Moving an item *into a retainer's* container → `no container with id '…'` (resolution not world-aware).
6. Loose (un-merged) torches/rations on retainers (`apply_kit` doesn't merge stackables).

(Bugs 4 & 5 are the ammo-specific UI — solved by the stackable component.)

---

## File map

| File | Responsibility | Change |
|---|---|---|
| `aose/sheet/view.py` | row builders | Add `_instance_row`; route all contents through it (Part A) |
| `aose/sheet/companions_view.py` | animal/vehicle contents | Use `_instance_row` (Part A) |
| `aose/engine/shop.py` | `_build_row`, `inventory_view`, `sell_instance` | per-instance contents; count-aware sell (Parts A, D) |
| `aose/web/templates/_inv_row_actions.html` | per-row item/enchanted/magic actions | gate Equip by location (Part A) |
| `aose/engine/storage.py` | movement vocabulary | world-aware `_container`; owning-world item landing; `add_item`; `consume_item` (Parts B, C, D) |
| `aose/engine/quick_equipment.py` | `apply_kit` | merge via `storage.add_item` (Part C) |
| `aose/web/templates/_actions.html` | shared action macros | new `stack_actions` macro (Part D) |
| `aose/web/templates/_inv_modals.html` | item/coin/gem modals | use `stack_actions` (Part D) |
| `aose/web/templates/sheet.html` | ammo modals | delete bespoke ammo modal; ammo flows through `item_modal` (Part D) |
| `aose/web/static/inventory.js` | client glue | qty→count copy; allow move auto-submit with external qty box (Part D) |
| `aose/web/routes.py` / `aose/web/wizard.py` | routes | count-aware sell; new `consume` route (Part D) |

---

## PART A — Single per-instance row source (bugs 1 & 2)

### Task A1: `_instance_row` helper — one builder that always attaches identity

**Files:**
- Modify: `aose/sheet/view.py` (add helper near `_item_rows_at`, ~line 1400)
- Test: `tests/test_sheet_inventory_box.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sheet_inventory_box.py
def test_container_contents_rows_carry_instance_id(make_character, game_data):
    """A plain item inside a container must expose its real instance_id so the
    modal's move/sell/equip forms target it (regression: bug 2 'no item instance')."""
    from aose.models import ItemInstance
    from aose.models.storage import StorageLocation
    from aose.engine.shop import new_container_instance
    from aose.sheet.view import build_inventory_groups

    spec = make_character()
    cont = new_container_instance("backpack", game_data)
    spec.containers.append(cont)
    here = StorageLocation(kind="container", id=cont.instance_id)
    spec.items.append(ItemInstance(instance_id="torch-iid", catalog_id="torch",
                                   count=3, location=here))

    groups = build_inventory_groups(spec, game_data)
    carried = next(g for g in groups if g.kind == "carried")
    view = next(c for c in carried.containers if c.instance_id == cont.instance_id)
    rows = [r for r in view.contents if r.id == "torch"]
    assert rows and rows[0].instance_id == "torch-iid"
    assert rows[0].category == "item"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py::test_container_contents_rows_carry_instance_id -q`
Expected: FAIL — `assert '' == 'torch-iid'` (contents row has empty `instance_id`).

- [ ] **Step 3: Add the shared helper and use it for container contents**

In `aose/sheet/view.py`, add near `_item_rows_at` (after line 1419):

```python
def _instance_row(inst, data, aw="all", aa="all", ash=True, *,
                  two_weapon=False, eligible=False, off_full=False):
    """One InventoryRow for a single ItemInstance, always carrying its real
    instance_id + category. The single per-instance row builder — every place
    that renders an ItemInstance (loose, equipped, container/animal/vehicle
    contents) goes through here so action forms always target the instance."""
    from aose.engine.shop import _build_row
    r = _build_row(inst.catalog_id, inst.count, data, aw, aa, ash,
                   two_weapon=two_weapon, eligible=eligible, off_full=off_full)
    cat = "enchanted" if inst.enchantment_id is not None else "item"
    return r.model_copy(update={"instance_id": inst.instance_id, "category": cat})
```

Then in `_container_views_from` replace the `content_rows` builder (lines 1498-1501):

```python
            content_rows = sorted(
                [_instance_row(i, data) for i in plain_items],
                key=lambda r: r.name,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py::test_container_contents_rows_carry_instance_id -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aose/sheet/view.py tests/test_sheet_inventory_box.py
git commit -m "fix(view): container contents rows carry real instance_id + category"
```

### Task A2: Same fix for animal/vehicle contents

**Files:**
- Modify: `aose/sheet/companions_view.py:86-91`
- Test: `tests/test_companions.py` (or wherever companion content rows are asserted)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_companions.py
def test_animal_contents_rows_carry_instance_id(make_character, game_data):
    from aose.models import ItemInstance, AnimalInstance
    from aose.models.storage import StorageLocation
    from aose.sheet.companions_view import companions_block

    spec = make_character()
    spec.animals.append(AnimalInstance(instance_id="mule1", catalog_id="mule"))
    here = StorageLocation(kind="animal", id="mule1")
    spec.items.append(ItemInstance(instance_id="rations-iid",
                                   catalog_id="iron_rations", count=5, location=here))

    block = companions_block(spec, game_data)
    card = next(a for a in block.animals if a.instance_id == "mule1")
    row = next(r for r in card.contents if r.id == "iron_rations")
    assert row.instance_id == "rations-iid"
    assert row.category == "item"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companions.py::test_animal_contents_rows_carry_instance_id -q`
Expected: FAIL — empty `instance_id`.

- [ ] **Step 3: Use the shared helper**

In `aose/sheet/companions_view.py`, rewrite `_content_rows` (lines 86-91):

```python
def _content_rows(spec, loc, data: GameData) -> list[InventoryRow]:
    from aose.engine.storage import items_at
    from aose.sheet.view import _instance_row
    rows = [_instance_row(inst, data) for inst in items_at(spec, loc)]
    rows.sort(key=lambda r: r.name)
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companions.py::test_animal_contents_rows_carry_instance_id -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aose/sheet/companions_view.py tests/test_companions.py
git commit -m "fix(view): animal/vehicle contents rows carry real instance_id"
```

### Task A3: Gate Equip on the location's equip policy (bug 1)

`LocationPolicy.equip_allowed` is True only for `carried` and `retainer`. The macro's
`state` argument is exactly the location kind, so gate on it.

**Files:**
- Modify: `aose/web/templates/_inv_row_actions.html:26`
- Test: `tests/test_sheet_inventory_box.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sheet_inventory_box.py
import re
from starlette.testclient import TestClient

def _equip_forms_in(html, instance_id):
    # crude: find /equip forms that carry this instance_id
    return re.findall(rf'action="[^"]*/equip"[^>]*>.*?{instance_id}', html, re.S)

def test_no_equip_action_for_stashed_weapon(client, make_character, game_data, save_spec):
    """A weapon in the stash must not offer Equip (bug 1)."""
    from aose.models import ItemInstance
    from aose.models.storage import StorageLocation
    spec = make_character()
    spec.items.append(ItemInstance(instance_id="sling-stash", catalog_id="sling",
                                    count=1, location=StorageLocation(kind="stashed")))
    cid = save_spec(spec)
    html = client.get(f"/character/{cid}").text
    # The stashed sling modal id:
    assert 'modal-item-stashed-sling-stash' in html
    # No equip form anywhere targets the stashed instance
    assert f'name="instance_id" value="sling-stash"' in html       # it is rendered
    assert not re.search(r'/equip"[^<]*?sling-stash', html, re.S)   # but never to /equip
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py::test_no_equip_action_for_stashed_weapon -q`
Expected: FAIL — an Equip form targets `sling-stash`.

- [ ] **Step 3: Add the location gate**

In `aose/web/templates/_inv_row_actions.html`, change the equip branch condition (line 26) from:

```jinja
  {% elif row.equippable | default(False) or cat in ("enchanted", "magic") %}
```

to:

```jinja
  {% elif (state in ("carried", "retainer")) and (row.equippable | default(False) or cat in ("enchanted", "magic")) %}
```

(`state` is the macro's 3rd positional param — the location kind. Only `carried`
and `retainer` have `equip_allowed=True` in `storage.location_policy`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py::test_no_equip_action_for_stashed_weapon -q`
Expected: PASS

- [ ] **Step 5: Run the inventory-box suite to confirm no regressions**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py tests/test_equip_core.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add aose/web/templates/_inv_row_actions.html tests/test_sheet_inventory_box.py
git commit -m "fix(templates): only offer Equip where the location permits it"
```

---

## PART B — World-aware container resolution (bug 3)

### Task B1: `_container` searches every world

**Files:**
- Modify: `aose/engine/storage.py:63-67`
- Test: `tests/test_inventory_move_routes.py` (engine-level)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storage_worlds.py  (new file)
import pytest
from aose.models import ItemInstance
from aose.models.storage import StorageLocation
from aose.engine import storage
from aose.engine.shop import new_container_instance


def test_move_item_into_retainer_container(make_character_with_retainer, game_data):
    """Moving a PC item into a retainer-owned container must land it in the
    retainer's world at that container (regression: bug 3 'no container with id')."""
    spec, rid = make_character_with_retainer(game_data)
    ret = next(r for r in spec.retainers if r.id == rid)
    cont = new_container_instance("backpack", game_data)
    ret.spec.containers.append(cont)
    spec.items.append(ItemInstance(instance_id="rope-iid", catalog_id="rope",
                                   count=1, location=StorageLocation(kind="carried")))

    dest = StorageLocation(kind="container", id=cont.instance_id)
    storage.move_item(spec, "rope-iid", dest, data=game_data)

    # Gone from PC world, present in retainer world at the container.
    assert all(i.instance_id != "rope-iid" for i in spec.items)
    landed = [i for i in ret.spec.items
              if i.catalog_id == "rope" and i.location == dest]
    assert landed and landed[0].count == 1
```

> If `make_character_with_retainer` doesn't exist, add it to `tests/conftest.py`:
> ```python
> @pytest.fixture
> def make_character_with_retainer(make_character):
>     def _make(game_data):
>         from aose.engine.retainers import generate_retainer
>         spec = make_character()
>         ret = generate_retainer(name="Hench", class_ids=["fighter"], level=1,
>                                 race_id="human", alignment="neutral",
>                                 hiring_spec=spec, data=game_data)
>         spec.retainers.append(ret)
>         return spec, ret.id
>     return _make
> ```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_worlds.py::test_move_item_into_retainer_container -q`
Expected: FAIL — `StorageError: no container with id '…'`.

- [ ] **Step 3: Make `_container` world-aware and return its owning spec**

In `aose/engine/storage.py`, replace `_container` (lines 63-67):

```python
def _container_owner(spec: CharacterSpec, id_: str):
    """Return (owning_spec, ContainerInstance) for a container in the PC world or
    any retainer world. Container contents live in their owner's world."""
    for c in spec.containers:
        if c.instance_id == id_:
            return spec, c
    for r in spec.retainers:
        for c in r.spec.containers:
            if c.instance_id == id_:
                return r.spec, c
    raise StorageError(f"no container with id {id_!r}")


def _container(spec: CharacterSpec, id_: str):
    """The ContainerInstance for ``id_`` in any world (back-compat shim)."""
    return _container_owner(spec, id_)[1]
```

Then make `location_policy` use the owner's catalog lookup — it already calls
`_container(spec, loc.id)`; that now resolves retainer containers too, so the
`capacity_cn` branch (lines 99-102) works unchanged.

- [ ] **Step 4: Update `_owning_spec_for` so a container dest selects its owner**

In `aose/engine/storage.py`, replace `_owning_spec_for` (lines 70-72):

```python
def _owning_spec_for(spec: CharacterSpec, loc: StorageLocation) -> CharacterSpec:
    """The spec whose world ``loc`` belongs to (PC, or a retainer's spec)."""
    if loc.kind == "retainer":
        return _retainer(spec, loc.id).spec
    if loc.kind == "container":
        return _container_owner(spec, loc.id)[0]
    return spec
```

- [ ] **Step 5: Teach `_move_cross_world` to land at an explicit dest (not always carried)**

A container dest is a cross-world move whose landing location is the container,
not `carried`. In `aose/engine/storage.py`, change `_move_cross_world`'s landing
location from the hard-coded `carried` to the real `dest` (lines 263-292). Replace
the function body's location choices:

```python
def _move_cross_world(pc: CharacterSpec, dest_spec: CharacterSpec, inst,
                      dest: StorageLocation, count, data, item=None) -> None:
    """Move an item between two worlds (PC↔retainer). Lands at ``dest`` in the
    destination world (``dest`` is ``carried`` for a retainer target, or the
    container location for a retainer-owned container) and merges into a resident
    stack there."""
    from aose.engine.equip import is_equippable
    if item is None and data is not None:
        item = data.items.get(inst.catalog_id)
    n = inst.count if count is None else count
    equippable = item is not None and is_equippable(item)
    land = StorageLocation(kind="carried") if dest.kind == "retainer" else dest
    src_list = _find_world_list(pc, inst)
    if equippable or n >= inst.count:
        src_list.remove(inst)
        _clear_equip_state(inst)
        resident = None if equippable else _merge_target(dest_spec, inst, land)
        if resident is not None:
            resident.count += n
        else:
            dest_spec.items.append(inst.model_copy(update={
                "instance_id": uuid.uuid4().hex, "count": n,
                "location": land, "equip": None, "loaded_ammo_id": None}))
    else:
        inst.count -= n
        resident = _merge_target(dest_spec, inst, land)
        if resident is not None:
            resident.count += n
        else:
            dest_spec.items.append(inst.model_copy(update={
                "instance_id": uuid.uuid4().hex, "count": n,
                "location": land, "equip": None, "loaded_ammo_id": None}))
```

Note `_move_cross_world` is reached from `move_item` in two spots (lines 314 and
332) whenever `dest_spec is not spec` — which now includes a retainer-owned
container. No call-site change needed beyond the new `_owning_spec_for`.

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_worlds.py -q`
Expected: PASS

- [ ] **Step 7: Guard the reverse + same-world container moves**

```python
# tests/test_storage_worlds.py
def test_move_item_out_of_retainer_container_to_pc(make_character_with_retainer, game_data):
    spec, rid = make_character_with_retainer(game_data)
    ret = next(r for r in spec.retainers if r.id == rid)
    cont = new_container_instance("backpack", game_data)
    ret.spec.containers.append(cont)
    here = StorageLocation(kind="container", id=cont.instance_id)
    ret.spec.items.append(ItemInstance(instance_id="torch-r", catalog_id="torch",
                                        count=2, location=here))

    storage.move_item(spec, "torch-r", StorageLocation(kind="carried"), data=game_data)
    assert all(i.instance_id != "torch-r" for i in ret.spec.items)
    assert any(i.catalog_id == "torch" and i.location.kind == "carried"
               for i in spec.items)
```

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_worlds.py -q`
Expected: PASS (the cross-world path already handles src in retainer world via
`move_item`'s retainer-search branch, lines 304-315).

- [ ] **Step 8: Commit**

```bash
git add aose/engine/storage.py tests/test_storage_worlds.py tests/conftest.py
git commit -m "fix(storage): resolve containers in every world; cross-world moves land at dest"
```

### Task B2: World-aware resolution for coins/gems/magic/spell-source into retainer containers

`move_valuable`, `move_instance`, `move_spell_source` call `_container(spec, dest.id)`
purely to validate existence — now world-aware, so the validation passes. But they
still mutate `spec.<collection>`, which is wrong for a retainer-owned container.
Scope note: only **items** are reported broken (bug 3). Coins/gems/magic/source into a
retainer's container is a pre-existing gap; fix it the same way for consistency.

**Files:**
- Modify: `aose/engine/storage.py` (`move_valuable`, `move_instance`, `move_spell_source`)
- Test: `tests/test_storage_worlds.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storage_worlds.py
def test_move_coins_into_retainer_container(make_character_with_retainer, game_data):
    spec, rid = make_character_with_retainer(game_data)
    ret = next(r for r in spec.retainers if r.id == rid)
    cont = new_container_instance("backpack", game_data)
    ret.spec.containers.append(cont)
    from aose.models import CoinStack
    spec.coins = [CoinStack(denom="gp", count=10, location=StorageLocation(kind="carried"))]

    dest = StorageLocation(kind="container", id=cont.instance_id)
    storage.move_coins(spec, "gp", StorageLocation(kind="carried"), dest, 4, game_data)
    landed = [c for c in ret.spec.coins if c.denom == "gp" and c.location == dest]
    assert landed and landed[0].count == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_worlds.py::test_move_coins_into_retainer_container -q`
Expected: FAIL — coins land in `spec.coins`, not `ret.spec.coins`.

- [ ] **Step 3: Route coin movement through the owning world**

In `aose/engine/storage.py`, change `move_coins` (lines 430-437) to add to the
destination's owning world:

```python
def move_coins(spec: CharacterSpec, denom: str,
               src: StorageLocation, dest: StorageLocation, count: int,
               data=None) -> None:
    if count <= 0:
        raise StorageError("move count must be positive")
    _check_capacity(spec, dest, count, data)
    _take_coins(spec, denom, count, src)
    _add_coins(_owning_spec_for(spec, dest), denom, count, dest)
```

> `_take_coins`/`_add_coins` operate on `spec.coins`; passing the owning spec to
> `_add_coins` lands the coins in the retainer's world. Source is always the PC
> world here (the move modal only offers PC-world sources for coins).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_worlds.py::test_move_coins_into_retainer_container -q`
Expected: PASS

- [ ] **Step 5: Repeat for gems (same pattern) and add a test**

In `move_valuable` (lines 461-494), replace `spec.gems`/`spec.jewellery` mutations
with the owning spec. Minimal change: at the top, after the container-existence
check, resolve `owner = _owning_spec_for(spec, dest)` and operate on `owner.gems`
/ `owner.jewellery` when appending the moved stack/piece, while still locating the
source in `spec.gems`/`spec.jewellery`. Add `test_move_gems_into_retainer_container`
mirroring the coin test.

> Magic items (`move_instance`) and spell sources (`move_spell_source`) already
> branch on `dest.kind == "retainer"` only. Extend their `dest_world` selection
> to `_owning_spec_for(spec, dest)` so a retainer-owned container also lands in the
> retainer world. Add one test each if time permits; otherwise leave a `# TODO`
> referencing this task — items + coins + gems cover the reported surface.

- [ ] **Step 6: Commit**

```bash
git add aose/engine/storage.py tests/test_storage_worlds.py
git commit -m "fix(storage): coins/gems land in the owning world of a container dest"
```

---

## PART C — One merge rule for every item-add path (bug 6)

### Task C1: `storage.add_item` — the single stackable-aware add

**Files:**
- Modify: `aose/engine/storage.py` (new public function)
- Test: `tests/test_storage_worlds.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storage_worlds.py
def test_add_item_merges_stackables(make_character, game_data):
    from aose.engine import storage
    from aose.models.storage import StorageLocation
    spec = make_character()
    carried = StorageLocation(kind="carried")
    storage.add_item(spec, "torch", 3, carried, game_data)
    storage.add_item(spec, "torch", 2, carried, game_data)
    torches = [i for i in spec.items if i.catalog_id == "torch"]
    assert len(torches) == 1 and torches[0].count == 5


def test_add_item_keeps_equippables_separate(make_character, game_data):
    from aose.engine import storage
    from aose.models.storage import StorageLocation
    spec = make_character()
    carried = StorageLocation(kind="carried")
    storage.add_item(spec, "sword", 1, carried, game_data)
    storage.add_item(spec, "sword", 1, carried, game_data)
    swords = [i for i in spec.items if i.catalog_id == "sword"]
    assert len(swords) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_worlds.py -k add_item -q`
Expected: FAIL — `AttributeError: module 'aose.engine.storage' has no attribute 'add_item'`.

- [ ] **Step 3: Implement `add_item`**

In `aose/engine/storage.py`, add (after `move_item`):

```python
def add_item(spec: CharacterSpec, catalog_id: str, count: int,
             loc: StorageLocation, data) -> None:
    """Add ``count`` of ``catalog_id`` at ``loc``. Stackables merge into a
    resident (catalog_id, enchantment_id=None, location) stack; equippables are
    appended as distinct count-1 instances. The single add front door — buy/grant/
    kit paths compose this so merge behaviour can never diverge again."""
    from aose.engine.equip import is_stackable
    item = data.items.get(catalog_id)
    if is_stackable(item):
        resident = next((i for i in spec.items
                         if i.catalog_id == catalog_id and i.enchantment_id is None
                         and i.location == loc), None)
        if resident is not None:
            resident.count += count
            return
        spec.items.append(ItemInstance(instance_id=uuid.uuid4().hex,
                                        catalog_id=catalog_id, count=count,
                                        location=loc))
        return
    for _ in range(count):
        spec.items.append(ItemInstance(instance_id=uuid.uuid4().hex,
                                       catalog_id=catalog_id, count=1, location=loc))
```

Add the import at the top of `storage.py` (it already imports from `aose.models`):

```python
from aose.models import CharacterSpec, CoinStack, GemStack, ItemInstance, JewelleryPiece
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_worlds.py -k add_item -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aose/engine/storage.py tests/test_storage_worlds.py
git commit -m "feat(storage): add_item — single stackable-aware add front door"
```

### Task C2: Route `apply_kit` through `add_item` (retainers stop hoarding loose torches)

**Files:**
- Modify: `aose/engine/quick_equipment.py:212-241`
- Test: `tests/test_quick_equipment.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_quick_equipment.py
def test_apply_kit_merges_stackables(game_data):
    from aose.engine import quick_equipment as qe
    from aose.models import CharacterSpec
    spec = CharacterSpec(name="Kit", abilities={a: 10 for a in
        ("str","dex","con","int","wis","cha")}, classes=[])
    kit = qe.QuickKit(inventory=["torch", "torch", "torch", "iron_rations", "iron_rations"])
    qe.apply_kit(spec, kit, game_data)
    torches = [i for i in spec.items if i.catalog_id == "torch"]
    rations = [i for i in spec.items if i.catalog_id == "iron_rations"]
    assert len(torches) == 1 and torches[0].count == 3
    assert len(rations) == 1 and rations[0].count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_quick_equipment.py::test_apply_kit_merges_stackables -q`
Expected: FAIL — `len(torches) == 3`.

- [ ] **Step 3: Use `add_item` in `apply_kit`**

In `aose/engine/quick_equipment.py`, rewrite the inventory/ammo loops in
`apply_kit` (lines 222-241):

```python
    from aose.engine.storage import add_item

    # Build ItemInstances for each catalog_id in kit.inventory (merging stackables).
    for item_id in kit.inventory:
        item = data.items.get(item_id)
        if isinstance(item, Container):
            spec.containers.append(new_container_instance(item_id, data))
        else:
            add_item(spec, item_id, 1, CARRIED, data)

    # Ammo grants (merge into the resident ammo stack of that catalog id).
    for grant in kit.ammo:
        add_item(spec, grant["base_id"], int(grant["count"]), CARRIED, data)
```

(Leave the equip-intentions loop and gold as-is. `ItemInstance` import in this
function is now unused there but is still referenced by the equip loop's `next(...)`
— keep the import.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_quick_equipment.py::test_apply_kit_merges_stackables -q`
Expected: PASS

- [ ] **Step 5: Fold `add_free_item` / `buy_item` onto the same helper (DRY)**

In `aose/engine/shop.py`, replace the stackable-merge blocks in `add_free_item`
(lines 572-585) and `buy_item` (lines 600-613) with `storage.add_item`:

```python
    # add_free_item, after the Container branch:
    from aose.engine.storage import add_item
    add_item(spec, item_id, _bundle_count(item), carried, data)
    return
```

```python
    # buy_item, after spend(...) and the Container branch:
    from aose.engine.storage import add_item
    add_item(spec, item_id, _bundle_count(item), carried, data)
    return
```

Remove the now-dead `is_stackable` imports and trailing `spec.items.append(...)`
blocks in both functions.

- [ ] **Step 6: Run the shop + quick-equipment suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_quick_equipment.py tests/test_shop.py tests/test_retainer_routes.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add aose/engine/quick_equipment.py aose/engine/shop.py tests/test_quick_equipment.py
git commit -m "fix(equipment): all item-add paths merge stackables via storage.add_item"
```

---

## PART D — Unified stackable-actions component (bugs 4 & 5 + the spec)

**Component model.** A `.stack-actions` block holds **one** quantity `<input
type="number">` (`.stack-qty`, value = count, min=1, max=count) *outside* the
individual action forms, plus these forms (each only hidden inputs + its dropdown/
button, so existing auto-submit keeps working):

- Move: `.move-form` → `inv_move_url`, hidden `count` filled from `.stack-qty` on submit.
- Sell: `.sell-form` → `…/inventory/sell`, hidden `count`, with the half/refund `.sell-dest` dropdown.
- Drop: button → `…/inventory/sell` `mode=drop` (or coins → `…/coins/add` negative), hidden `count`.
- Consume (stacking items only): button → `…/inventory/consume`, removes one.

JS copies `.stack-qty` → the submitting form's hidden `count` just-in-time. This is
the only new client glue.

### Task D1: count-aware `sell_instance` and a `consume_item` engine function

**Files:**
- Modify: `aose/engine/shop.py:636-661` (`sell_instance` gains `count`)
- Modify: `aose/engine/storage.py` (add `consume_item`)
- Test: `tests/test_shop.py`, `tests/test_storage_worlds.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_shop.py
def test_sell_instance_sells_count(make_character, game_data):
    from aose.engine.shop import sell_instance
    from aose.models import ItemInstance
    from aose.models.storage import StorageLocation
    spec = make_character()
    spec.items.append(ItemInstance(instance_id="t", catalog_id="torch", count=6,
                                    location=StorageLocation(kind="carried")))
    sell_instance(spec, "t", "drop", game_data, count=4)
    torch = next(i for i in spec.items if i.instance_id == "t")
    assert torch.count == 2
```

```python
# tests/test_storage_worlds.py
def test_consume_item_removes_one(make_character, game_data):
    from aose.engine import storage
    from aose.models import ItemInstance
    from aose.models.storage import StorageLocation
    spec = make_character()
    spec.items.append(ItemInstance(instance_id="t", catalog_id="torch", count=2,
                                    location=StorageLocation(kind="carried")))
    storage.consume_item(spec, "t")
    assert next(i for i in spec.items if i.instance_id == "t").count == 1
    storage.consume_item(spec, "t")
    assert all(i.instance_id != "t" for i in spec.items)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_shop.py::test_sell_instance_sells_count tests/test_storage_worlds.py::test_consume_item_removes_one -q`
Expected: FAIL — `sell_instance() got an unexpected keyword 'count'`; `no attribute 'consume_item'`.

- [ ] **Step 3: Add `count` to `sell_instance`**

In `aose/engine/shop.py`, change the signature and removal math (lines 636-661):

```python
def sell_instance(spec, instance_id: str, mode: str, data: GameData,
                  *, count: int | None = None) -> None:
    """Remove ``count`` units (default: one bundle for refund, else 1) from the
    exact ItemInstance and credit carried gp per mode. ``count`` lets the shared
    stackable component sell N at once."""
    from aose.engine import storage as _storage
    if mode not in REMOVE_MODES:
        raise ValueError(f"Unknown remove mode {mode!r}; want one of {REMOVE_MODES}")
    inst = next((i for i in spec.items if i.instance_id == instance_id), None)
    if inst is None:
        raise ValueError(f"no item instance {instance_id!r}")
    item = data.items.get(inst.catalog_id)
    bundle = _bundle_count(item)
    base = bundle if mode == "refund" else 1
    remove_n = base if count is None else max(1, min(count, inst.count))
    if inst.count < remove_n:
        raise ValueError(
            f"Cannot {mode} {inst.catalog_id!r}: insufficient count {inst.count} < {remove_n}")
    if inst.count <= remove_n:
        inst.equip = None
        inst.loaded_ammo_id = None
        spec.items.remove(inst)
    else:
        inst.count -= remove_n
    # Credit scales with units removed (refund credits per bundle).
    units = remove_n
    credit = _removal_gold(inst.catalog_id, mode, data)
    if mode == "refund":
        credit = credit * (units // bundle if bundle else units)
    elif mode == "sell":
        credit = int(int(item.cost_gp / bundle / 2) * units) if item else 0
    if credit:
        _storage._add_coins(spec, "gp", credit, StorageLocation(kind="carried"))
```

> Verify `_removal_gold`'s existing per-mode math against this; if `_removal_gold`
> already returns a per-call (1-unit / 1-bundle) value, the scaling above is
> correct. Keep one source of truth — if it's cleaner to add a `count` param to
> `_removal_gold`, do that instead and call it once.

- [ ] **Step 4: Add `consume_item` to storage**

In `aose/engine/storage.py`:

```python
def consume_item(spec: CharacterSpec, instance_id: str) -> None:
    """Remove exactly one unit from a stacking item the user 'uses' (torch, ration,
    arrow). Searches the PC world and every retainer world. Drops the stack at 0."""
    for world in [spec, *(r.spec for r in spec.retainers)]:
        inst = next((i for i in world.items if i.instance_id == instance_id), None)
        if inst is None:
            continue
        if inst.count <= 1:
            _clear_weapon_loads(world, inst.instance_id)
            world.items.remove(inst)
        else:
            inst.count -= 1
        return
    raise StorageError(f"no item instance {instance_id!r}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_shop.py::test_sell_instance_sells_count tests/test_storage_worlds.py::test_consume_item_removes_one -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add aose/engine/shop.py aose/engine/storage.py tests/test_shop.py tests/test_storage_worlds.py
git commit -m "feat(engine): count-aware sell_instance + consume_item"
```

### Task D2: Routes — count on sell, new `consume` route (sheet + wizard)

**Files:**
- Modify: `aose/web/routes.py:472-510` (sell reads `count`), add `/inventory/consume`
- Modify: `aose/web/wizard.py` (mirror both)
- Test: `tests/test_inventory_move_routes.py` (or `test_inventory_actions.py`)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_inventory_actions.py
def test_consume_route_removes_one(client, make_character, save_spec, game_data):
    from aose.models import ItemInstance
    from aose.models.storage import StorageLocation
    spec = make_character()
    spec.items.append(ItemInstance(instance_id="t", catalog_id="torch", count=2,
                                    location=StorageLocation(kind="carried")))
    cid = save_spec(spec)
    r = client.post(f"/character/{cid}/inventory/consume",
                    data={"category": "item", "instance_id": "t"}, follow_redirects=False)
    assert r.status_code == 303
    reloaded = ...  # load spec via the test's loader
    assert next(i for i in reloaded.items if i.instance_id == "t").count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_actions.py::test_consume_route_removes_one -q`
Expected: FAIL — 404 (route missing).

- [ ] **Step 3: Add `count` to the sell handler and add the consume route**

In `aose/web/routes.py`, in `inventory_sell` (lines 472-510), read `count` from the
form and pass it through:

```python
    raw = form.get("count")
    count = int(raw) if raw not in (None, "") else None
    _ia.sell_thing(spec, category, instance_id, mode, data, count=count)
```

> `sell_thing` (the dispatcher in `inventory_actions.py`) forwards `count` to
> `shop.sell_instance`. Add `count: int | None = None` to `sell_thing` and pass it
> to the `item`/`enchanted` branch; magic items ignore `count` (per-instance).

Add the consume route after the sell route:

```python
@router.post("/character/{character_id}/inventory/consume")
async def inventory_consume(request: Request, character_id: str):
    from aose.engine import storage as _storage
    spec = _load_spec_or_404(request, character_id)
    form = await request.form()
    try:
        _storage.consume_item(spec, form.get("instance_id", ""))
    except _storage.StorageError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Mirror in `aose/web/wizard.py`**

Add `count` parsing to the wizard's `/inventory/sell` handler (line 1782) and a
`/{draft_id}/inventory/consume` route that loads the draft spec, calls
`storage.consume_item`, saves the draft, and 303-redirects to the equipment step —
matching the existing wizard route pattern.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_actions.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add aose/web/routes.py aose/web/wizard.py aose/engine/inventory_actions.py tests/test_inventory_actions.py
git commit -m "feat(routes): count-aware sell + /inventory/consume (sheet + wizard)"
```

### Task D3: The `stack_actions` macro

**Files:**
- Modify: `aose/web/templates/_actions.html` (new macro; retire `act_stepper` use for ammo)
- Test: `tests/test_sheet_inventory_box.py` (form-shape assertions)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sheet_inventory_box.py
def test_stack_actions_quantity_box_and_no_ammo_stepper(client, make_character, save_spec, game_data):
    from aose.models import ItemInstance
    from aose.models.storage import StorageLocation
    spec = make_character()
    spec.items.append(ItemInstance(instance_id="ar", catalog_id="arrow", count=20,
                                    location=StorageLocation(kind="carried")))
    cid = save_spec(spec)
    html = client.get(f"/character/{cid}").text
    # Quantity box present for the arrow stack, defaulting to the stack size:
    assert 'class="stack-qty"' in html
    assert 'value="20"' in html and 'max="20"' in html
    # The old +/- stepper form posting to /ammo/adjust is gone:
    assert "/ammo/adjust" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py::test_stack_actions_quantity_box_and_no_ammo_stepper -q`
Expected: FAIL — no `.stack-qty`; `/ammo/adjust` still present.

- [ ] **Step 3: Add the `stack_actions` macro**

In `aose/web/templates/_actions.html`, add:

```jinja
{# Unified stackable actions. One quantity box (default = stack size, clamped
   1..count) drives every action form below it. Forms hold only hidden inputs +
   their dropdown/button so the existing move/sell auto-submit still fires;
   inventory.js copies the qty into each form's hidden `count` on submit.
   Params:
     move_url, sell_url   action endpoints (sell_url unused when not sellable)
     ref                  {category, id}  (id = instance_id, or denom for coins)
     move_targets, cur_kind, cur_id   move source/destination context
     count                current stack size
     sellable             show Sell (half/refund) — false for coins/unsellable
     droppable_coin       render coin Drop (POST /coins/add negative) instead
     consumable           show Consume (stacking items only)
     sell_gp, cost_gp, can_refund, bundle_count   sell labels
     consume_url, drop_url   endpoints for consume / non-coin drop #}
{% macro stack_actions(move_url, ref, move_targets, cur_kind, cur_id, count,
                       *, sellable=False, consumable=False, droppable_coin=False,
                       sell_url="", consume_url="", drop_url="",
                       sell_gp=0, cost_gp=0, can_refund=True, bundle_count=1) %}
<div class="stack-actions" data-max="{{ count }}">
  <label class="stack-qty-label">Qty
    <input type="number" class="stack-qty" value="{{ count }}" min="1" max="{{ count }}" step="1">
  </label>

  {# Move — single dropdown, auto-submits; qty copied into hidden count by JS #}
  <form method="post" action="{{ move_url }}" class="inline-form move-form">
    <input type="hidden" name="category" value="{{ ref.category }}">
    {% if ref.category == 'coin' %}<input type="hidden" name="denom" value="{{ ref.id }}">
    {% else %}<input type="hidden" name="instance_id" value="{{ ref.id }}">{% endif %}
    <input type="hidden" name="src_kind" value="{{ cur_kind }}">
    <input type="hidden" name="src_id" value="{{ cur_id or '' }}">
    <input type="hidden" name="count" value="{{ count }}">
    {{ move_dest_control(move_targets, ref, cur_kind, cur_id) }}
  </form>

  {% if sellable %}
  <form method="post" action="{{ sell_url }}" class="inline-form sell-form">
    <input type="hidden" name="category" value="{{ ref.category }}">
    <input type="hidden" name="instance_id" value="{{ ref.id }}">
    <input type="hidden" name="count" value="{{ count }}">
    <input type="hidden" name="mode" value="">
    <select class="sell-dest">
      <option value="" disabled selected>Sell…</option>
      <option value="sell">+{{ sell_gp }}&nbsp;gp&nbsp;ea (half price)</option>
      {% if can_refund %}<option value="refund">+{{ cost_gp | int }}&nbsp;gp&nbsp;/bundle (refund)</option>{% endif %}
    </select>
  </form>
  <form method="post" action="{{ sell_url }}" class="inline-form drop-form">
    <input type="hidden" name="category" value="{{ ref.category }}">
    <input type="hidden" name="instance_id" value="{{ ref.id }}">
    <input type="hidden" name="count" value="{{ count }}">
    <button type="submit" name="mode" value="drop" class="btn btn-inline danger" title="Throw away — no gold back">Drop</button>
  </form>
  {% elif droppable_coin %}
  {# Coins: Drop = add negative count at this location #}
  <form method="post" action="{{ drop_url }}" class="inline-form drop-form">
    <input type="hidden" name="denom" value="{{ ref.id }}">
    <input type="hidden" name="loc_kind" value="{{ cur_kind }}">
    <input type="hidden" name="loc_id" value="{{ cur_id or '' }}">
    <input type="hidden" name="count" value="-{{ count }}" class="stack-neg-count">
    <button type="submit" class="btn btn-inline danger">Drop</button>
  </form>
  {% endif %}

  {% if consumable %}
  <form method="post" action="{{ consume_url }}" class="inline-form">
    <input type="hidden" name="category" value="{{ ref.category }}">
    <input type="hidden" name="instance_id" value="{{ ref.id }}">
    <button type="submit" class="btn btn-inline">Use one</button>
  </form>
  {% endif %}
</div>
{% endmacro %}
```

- [ ] **Step 4: Keep this task green by wiring ammo first (smallest substrate)**

Replace the two bespoke ammo modals in `aose/web/templates/sheet.html:1029-1056`
with `item_modal(a_as_row, group.kind, prefix, target_url_prefix, src_id=group.id)`
where ammo rows already carry `instance_id`. Simplest: render ammo through the same
`{% for row in group.loose %}` path by **including ammo in `group.loose`** (Task D5),
or — interim — call `stack_actions` directly in the ammo modal body:

```jinja
{{ stack_actions(_char_url ~ "/inventory/move",
                 {"category": "item", "id": a.instance_id},
                 move_targets, gkind, gid, a.count,
                 sellable=False, consumable=True,
                 consume_url=_char_url ~ "/inventory/consume") }}
```

Delete the `act_stepper(... /ammo/adjust ...)` lines.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py::test_stack_actions_quantity_box_and_no_ammo_stepper -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add aose/web/templates/_actions.html aose/web/templates/sheet.html tests/test_sheet_inventory_box.py
git commit -m "feat(templates): unified stack_actions macro; ammo drops bespoke stepper"
```

### Task D4: JS — copy qty into the submitting form's count; allow move auto-submit with external qty box

**Files:**
- Modify: `aose/web/static/inventory.js`
- Test: manual + `tests/test_sheet_inventory_box.py` (markup already covers presence)

- [ ] **Step 1: Add the qty→count copy on submit (inside `.stack-actions`)**

In `aose/web/static/inventory.js`, add a submit listener:

```javascript
/* Stackable quantity binding.
 *
 * A `.stack-actions` block holds one `.stack-qty` numberbox (default = stack
 * size, clamped 1..data-max) shared by sibling action forms (move / sell / drop /
 * consume). On submit of any such form we copy the qty into its hidden
 * input[name=count] (negating for coin-drop's stack-neg-count). The qty box lives
 * OUTSIDE the forms so move/sell keep their existing dropdown auto-submit. */
(function () {
    document.addEventListener("submit", function (e) {
        const form = e.target;
        const box = form.closest ? form.closest(".stack-actions") : null;
        if (!box) return;
        const qtyEl = box.querySelector(".stack-qty");
        if (!qtyEl) return;
        const max = parseInt(box.dataset.max || qtyEl.max || "1", 10);
        let qty = parseInt(qtyEl.value || "1", 10);
        if (isNaN(qty)) qty = max;
        qty = Math.max(1, Math.min(qty, max));
        const count = form.querySelector("input[name='count']");
        if (count) count.value = count.classList.contains("stack-neg-count")
            ? String(-qty) : String(qty);
    });
})();
```

- [ ] **Step 2: Confirm move auto-submit still fires**

The move-form inside `.stack-actions` contains only hidden inputs + the
`select.move-dest` (the qty box is a sibling, not inside the form), so the existing
`change` handler's `hasUserInput` guard (lines 73-78) still sees no visible input
and auto-submits. **No change needed** — but verify by reading the move-form markup
from Task D3: it has no non-hidden inputs. Good.

- [ ] **Step 3: Manual verification (preview)**

Start the app, open a character with an arrow stack, set qty to 5, pick a move
destination → 5 arrows move, 15 remain. Set qty 3, Sell → 3 sold. Use one → 1 fewer.

Run: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`

- [ ] **Step 4: Commit**

```bash
git add aose/web/static/inventory.js
git commit -m "feat(js): stack-actions qty binding; move keeps dropdown auto-submit"
```

### Task D5: Make ammo a first-class loose item; route coins & gems through `stack_actions`

**Files:**
- Modify: `aose/web/templates/_inv_modals.html` (coin_modal, gem_modal use `stack_actions`)
- Modify: `aose/web/templates/_inv_row_actions.html` (item rows: add Consume + qty for stackables via `stack_actions`)
- Modify: `aose/sheet/view.py` (optionally fold ammo rows into `group.loose` so one path renders them)
- Test: `tests/test_sheet_inventory_box.py`

- [ ] **Step 1: Write the failing test (coins get a qty box + Drop, not Sell)**

```python
# tests/test_sheet_inventory_box.py
def test_coins_use_stack_actions_with_drop(client, make_character, save_spec, game_data):
    from aose.models import CoinStack
    from aose.models.storage import StorageLocation
    spec = make_character()
    spec.coins = [CoinStack(denom="gp", count=50, location=StorageLocation(kind="carried"))]
    cid = save_spec(spec)
    html = client.get(f"/character/{cid}").text
    # Coin modal now composes the shared component:
    assert 'modal-coin-carried--gp' in html
    # qty box defaulting to 50 and a Drop (not Sell) control:
    assert 'class="stack-qty"' in html and 'value="50"' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py::test_coins_use_stack_actions_with_drop -q`
Expected: FAIL — coin modal still uses the old hand-rolled Move/Adjust block.

- [ ] **Step 3: Rewrite `coin_modal`'s Move/Adjust block to use `stack_actions`**

In `aose/web/templates/_inv_modals.html`, replace the Move + Adjust `ov-section`s
of `coin_modal` (keep Convert as a coin-specific section) with:

```jinja
    <div class="ov-section">
      <h4>Move / Drop</h4>
      {{ stack_actions(url_prefix ~ "/inventory/move",
                       {"category": "coin", "id": c.denom},
                       move_targets, lk, lid, c.count,
                       sellable=False, droppable_coin=True,
                       drop_url=url_prefix ~ "/coins/add") }}
    </div>
```

Import the macro at the top of `_inv_modals.html`:

```jinja
{% from "_actions.html" import stack_actions with context %}
```

- [ ] **Step 4: Rewrite `gem_modal` to use `stack_actions`**

Gems are sellable treasure (no Consume). Replace the gem `row-actions` Move/±1/Drop
with `stack_actions(..., sellable=True, sell_url=url_prefix ~ "/gems/sell", ...)`.
Keep "Sell all" as a gem-specific convenience button if desired. Gems credit via the
gem routes; map the sell dropdown's `sell`/`refund` modes to the gem sell endpoint
(or add a small `count` to `/gems/sell`). Add an assertion to the test for the gem qty box.

- [ ] **Step 5: Give plain stacking item rows the Consume button**

In `aose/web/templates/_inv_row_actions.html`, where the item Move + Sell/Drop are
rendered (lines 46-81), replace the bespoke `act_move` + sell/drop forms with a
single `stack_actions` call for `category == "item"` rows, passing
`consumable=(row.equippable is false and cat == "item")`, `sellable=(row.cost_gp >
0)`, `sell_url=inv_prefix ~ "/sell"`, `consume_url=inv_prefix ~ "/consume"`,
`count=row.count`. Equippable rows keep Equip/Unequip above and pass `count=1`,
`consumable=False`.

> This is the line that finally unifies plain items, ammo, coins, and gems on one
> component. Equip/unequip/charge/note stay where they are (Part A's macro head).

- [ ] **Step 6: Fold ammo into `group.loose` (single render path)**

In `aose/sheet/view.py` `build_inventory_groups`, append ammo instances to the
group's `loose` rows via `_instance_row` (they're plain stackable `ItemInstance`s),
and stop populating the separate `group.ammo` list for the carried/stashed/carrier
panes — OR keep `group.ammo` but render it through `item_modal` like loose rows.
Remove the bespoke ammo `<li>`/modal blocks in `_inv_pane.html:158-164` and
`sheet.html:1027-1057` once ammo rows flow through `item_modal`.

> Keep the **ammo-loading** UI (load/unload into a weapon) — that lives in
> `item_modal`'s `load_options` section and is unrelated to stacking. Only the
> count stepper + bespoke move are removed.

- [ ] **Step 7: Run the full inventory + move + ammo suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py tests/test_inventory_move_routes.py tests/test_ammunition.py tests/test_gems*.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add aose/web/templates/ aose/sheet/view.py tests/
git commit -m "feat(inventory): items, ammo, coins, gems share the stack_actions component"
```

---

## PART E — Full sweep, docs, manual verification

### Task E1: Full test run + contract test extension

- [ ] **Step 1: Run the whole suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing `pytest-current` PermissionError — known Windows quirk).

- [ ] **Step 2: Extend the contract test**

In the existing inventory contract test (per the consolidation spec §F), add cases
that render a container with contents, an animal with contents, and a retainer with
a container, then assert every action `<form>` carries a **non-empty** `instance_id`
(or `denom` for coins) and points at a live route. This is the test that would have
caught bug 2.

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py -k contract -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_sheet_inventory_box.py
git commit -m "test: contract test asserts every contents/retainer action form has an instance id"
```

### Task E2: Manual end-to-end verification (the six reported bugs)

- [ ] Start the app: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
- [ ] **Bug 1:** Stash a sling → no Equip option in its modal; same for an item on a horse/cart.
- [ ] **Bug 2:** Put items in a backpack → open a content item → Move it out → succeeds (no `no item instance ''`).
- [ ] **Bug 3:** Move an item into a retainer's backpack → succeeds; the item appears inside that retainer's backpack.
- [ ] **Bugs 4/5:** Arrows show the same single Move dropdown + qty box + Sell as every other stack — no separate Move button, no +/- stepper.
- [ ] **Bug 6:** Recruit a retainer → torches/rations appear as single merged stacks (×N), not loose.

### Task E3: Docs

- [ ] **Step 1: CHANGELOG** — add one row to the top of `docs/CHANGELOG.md`:

```
| 2026-06-27 | Stackable actions + storage fixes (instance-keyed contents, world-aware containers, one add/merge path, unified stack_actions) | feat/stackable-actions-and-storage-fixes | 2026-06-27-stackable-actions-and-storage-fixes |
```

- [ ] **Step 2: ARCHITECTURE** — update the inventory/storage section in place:
  document `storage.add_item` (single add front door), world-aware container
  resolution (`_container_owner`), `consume_item`, and the `stack_actions`
  component as the canonical stackable UI (qty box → move/sell/drop/consume).

- [ ] **Step 3: Commit**

```bash
git add docs/CHANGELOG.md docs/ARCHITECTURE.md
git commit -m "docs: land stackable-actions-and-storage-fixes in CHANGELOG + ARCHITECTURE"
```

---

## Self-review notes

- **Spec coverage:** qty box (D3), single move dropdown (D3 + D4 auto-submit), separate sell (D3),
  coins→Drop (D3/D5), consume for stacking items (D1/D2/D3/D5), "compose, don't reroll" (one
  `stack_actions` macro + one `add_item` + one `_instance_row`). Bugs 1/2/3/6 → Parts A/B/C.
- **Types stay consistent:** `_instance_row(inst, data, …)`, `add_item(spec, catalog_id, count, loc, data)`,
  `consume_item(spec, instance_id)`, `sell_instance(…, *, count=None)`, `stack_actions(move_url, ref, move_targets, cur_kind, cur_id, count, *, …)`.
- **Open verification:** confirm `_removal_gold`'s per-mode return shape before trusting the D1 credit-scaling math; prefer adding `count` to `_removal_gold` if cleaner.
- **Deferred (noted, not reported):** selling a *retainer-owned* item via `sell_instance` still only searches `spec.items`; out of scope here (no UI path reported). Flagged in ARCHITECTURE follow-ups.
