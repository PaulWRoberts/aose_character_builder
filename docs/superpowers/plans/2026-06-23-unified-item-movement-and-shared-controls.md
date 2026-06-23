# Unified Item Movement + Shared Action Controls — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every owned thing (catalog items, containers, coins, gems, jewellery, magic items, enchanted gear, ammunition) location-aware and movable to any top-level inventory or container through one engine front-door and one HTTP route, and give the live sheet one shared set of action-control macros plus a sheet-wide button-size standard.

**Architecture:** Extend the existing `aose/engine/storage.py` location-resolver substrate with a single `move_thing` dispatcher + `move_targets` helper. Add a `location` field to the three instance models (magic/enchanted/ammo). Bucket them by location in `build_inventory_groups` and render container-stowed pointer-types in `ContainerView`. Collapse one `/inventory/move` route over the four typed move routes (PC + wizard). Replace per-modal hand-rolled buttons with `_actions.html` macros and a CSS button-size scale keyed to use context.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, Jinja2, pytest. No JS framework. Run tests with `.venv\Scripts\python.exe -m pytest`.

**Spec:** `docs/superpowers/specs/2026-06-23-unified-item-movement-and-shared-controls-design.md`

**Conventions:**
- Run the app: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
- Run tests: `.venv\Scripts\python.exe -m pytest tests/ -q`
- The trailing `PermissionError` on `pytest-current` is a known Windows quirk — ignore it.
- No migrations (app is not deployed). `location` defaults to carried so old saves load unchanged.
- Commit after every green task.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `aose/models/character.py` | `MagicItemInstance`, `EnchantedInstance`, `AmmoStack` gain `location` | Modify |
| `aose/engine/ammo.py` | `_combine` becomes location-aware; new `unload` already exists | Modify |
| `aose/engine/storage.py` | `move_thing`, `move_instance`, `move_ammo`, `move_targets`, `unload_if_loaded`; `move_valuable` gains `count` | Modify |
| `aose/engine/encumbrance.py` | magic/enchanted/ammo weight filtered to carried; container loop counts stowed magic/ammo | Modify |
| `aose/engine/shop.py` | `ContainerView` gains stowed sub-lists; `TopLevelGroup` already carries the per-type lists | Modify |
| `aose/sheet/view.py` | `build_inventory_groups` buckets magic/enchanted/ammo by location; `_container_views_from` fills stowed sub-lists | Modify |
| `aose/web/routes.py` | `POST /inventory/move`; delete 4 typed move routes; `inv_move_url` → `/inventory/move` | Modify |
| `aose/web/wizard.py` | delete wizard typed move routes; add `/inventory/move`; update `inv_move_url` | Modify |
| `aose/web/templates/_actions.html` | shared action macros | Create |
| `aose/web/templates/_move_dest.html` | drive off `move_targets`, unified `ref`, count for stacking | Modify |
| `aose/web/templates/_inv_modals.html` | refactor coin/gem/jewellery/item/container modals onto `_actions.html` | Modify |
| `aose/web/templates/_inv_row_actions.html` | `.btn` classes; route to `/inventory/move`; merge into `_actions.html` usage | Modify |
| `aose/web/templates/_inv_pane.html` | render container stowed magic/coins/gems/jewellery/ammo; magic/enchanted/ammo rows movable | Modify |
| `aose/web/templates/sheet.html` | magic/enchanted/ammo modals gain Move; one `_char_url`; treasure modals per group | Modify |
| `aose/web/static/sheet.css` | button-size standard; collapse duplicate `.inline-form`; width classes | Modify |
| `tests/test_storage_move_thing.py` | engine move_thing/split/merge/unload tests | Create |
| `tests/test_inventory_move_routes.py` | migrate to single route | Modify |
| `tests/test_sheet_inventory_box.py` | magic/coin/gem in container render; movable magic modal | Modify |

---

## Phase 1 — Models + ammo merge key

### Task 1: Add `location` to the three instance models

**Files:**
- Modify: `aose/models/character.py:12-62`
- Test: `tests/test_models_location.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models_location.py
from aose.models import MagicItemInstance, EnchantedInstance, AmmoStack
from aose.models.storage import StorageLocation


def test_instances_default_to_carried():
    m = MagicItemInstance(instance_id="m1", catalog_id="ring_protection")
    e = EnchantedInstance(instance_id="e1", base_id="sword", enchantment_id="plus1")
    a = AmmoStack(instance_id="a1", base_id="arrow", count=20)
    assert m.location == StorageLocation(kind="carried")
    assert e.location == StorageLocation(kind="carried")
    assert a.location == StorageLocation(kind="carried")


def test_instance_accepts_explicit_location():
    loc = StorageLocation(kind="animal", id="mule1")
    a = AmmoStack(instance_id="a1", base_id="arrow", count=20, location=loc)
    assert a.location == loc


def test_legacy_save_without_location_coerces_to_carried():
    # Old saves never wrote `location`; Pydantic must accept the absence.
    a = AmmoStack.model_validate({"instance_id": "a1", "base_id": "arrow", "count": 5})
    assert a.location == StorageLocation(kind="carried")
```

- [ ] **Step 2: Run test, verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models_location.py -v`
Expected: FAIL — `location` is not a field (extra="forbid" rejects it, or attribute missing).

- [ ] **Step 3: Add the field to each model**

In `aose/models/character.py`, add the import near the top if not present:

```python
from aose.models.storage import StorageLocation
```

Add to `MagicItemInstance` (after `instance_id`/`catalog_id`), `EnchantedInstance` (after `enchantment_id`), and `AmmoStack` (after `count`):

```python
    location: StorageLocation = Field(default_factory=lambda: StorageLocation(kind="carried"))
```

(Confirm `Field` is already imported in this module; it is used elsewhere.)

- [ ] **Step 4: Run test, verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models_location.py -v`
Expected: PASS

- [ ] **Step 5: Run the full model + load suite to catch coercion regressions**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q -k "model or load or storage or character"`
Expected: PASS (or unchanged failures unrelated to this change)

- [ ] **Step 6: Commit**

```bash
git add aose/models/character.py tests/test_models_location.py
git commit -m "feat(models): location field on magic/enchanted/ammo instances"
```

### Task 2: Make ammo `_combine` location-aware

**Files:**
- Modify: `aose/engine/ammo.py:48-58`, and its callers `buy_ammo` (61-68), `add_free_ammo` (71-83)
- Test: `tests/test_ammo.py` (append; create if absent)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ammo.py (append)
from aose.engine import ammo as ammo_engine
from aose.models import AmmoStack
from aose.models.storage import StorageLocation

CARRIED = StorageLocation(kind="carried")
MULE = StorageLocation(kind="animal", id="mule1")


def test_combine_does_not_merge_across_locations():
    stacks = [AmmoStack(instance_id="a1", base_id="arrow", count=5, location=MULE)]
    out = ammo_engine._combine(stacks, "arrow", None, 20, location=CARRIED)
    # The mule stack is untouched; a new carried stack is appended.
    assert len(out) == 2
    mule = next(s for s in out if s.location == MULE)
    carried = next(s for s in out if s.location == CARRIED)
    assert mule.count == 5 and carried.count == 20


def test_combine_merges_same_location():
    stacks = [AmmoStack(instance_id="a1", base_id="arrow", count=5, location=CARRIED)]
    out = ammo_engine._combine(stacks, "arrow", None, 20, location=CARRIED)
    assert len(out) == 1 and out[0].count == 25
```

- [ ] **Step 2: Run test, verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ammo.py -v -k combine`
Expected: FAIL — `_combine` has no `location` kwarg / merges across locations.

- [ ] **Step 3: Update `_combine` and callers**

Replace `_combine` in `aose/engine/ammo.py`:

```python
def _combine(stacks: list[AmmoStack], base_id: str, enchantment_id: str | None,
             count: int, location: StorageLocation | None = None) -> list[AmmoStack]:
    """Add ``count`` to an existing (base_id, enchantment_id, location) stack, or
    append a fresh one at ``location`` (default carried)."""
    loc = location or StorageLocation(kind="carried")
    for i, s in enumerate(stacks):
        if s.base_id == base_id and s.enchantment_id == enchantment_id and s.location == loc:
            merged = s.model_copy(update={"count": s.count + count})
            return [*stacks[:i], merged, *stacks[i + 1:]]
    fresh = AmmoStack(instance_id=uuid.uuid4().hex, base_id=base_id,
                      enchantment_id=enchantment_id, count=count, location=loc)
    return [*stacks, fresh]
```

Add the import at the top of `aose/engine/ammo.py` if missing:

```python
from aose.models.storage import StorageLocation
```

`buy_ammo` and `add_free_ammo` call `_combine` without `location`; the default (carried) is correct for acquisition. No change needed there.

- [ ] **Step 4: Run test, verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ammo.py -v -k combine`
Expected: PASS

- [ ] **Step 5: Run the ammo + web ammo suites**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q -k ammo`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add aose/engine/ammo.py tests/test_ammo.py
git commit -m "feat(ammo): location-aware stack merge key"
```

---

## Phase 2 — Engine movement front-door

### Task 3: `unload_if_loaded` helper

**Files:**
- Modify: `aose/engine/storage.py` (add helper near the bottom, before `move_thing`)
- Test: `tests/test_storage_move_thing.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storage_move_thing.py
from pathlib import Path

from aose.data.loader import GameData
from aose.engine import storage
from aose.models import (AmmoStack, CharacterSpec, ClassEntry)
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))
CARRIED = StorageLocation(kind="carried")


def _spec(**kw):
    base = dict(
        name="Mover",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
    )
    base.update(kw)
    return CharacterSpec(**base)


def test_unload_if_loaded_drops_the_weapon_key():
    spec = _spec(
        inventory=["short_bow", "arrow"],
        equipped={"main_hand": "short_bow"},
        ammo=[AmmoStack(instance_id="a1", base_id="arrow", count=20)],
        loaded_ammo={"short_bow": "a1"},
    )
    storage.unload_if_loaded(spec, "short_bow")
    assert "short_bow" not in spec.loaded_ammo


def test_unload_if_loaded_is_noop_when_not_loaded():
    spec = _spec(inventory=["sword"], loaded_ammo={})
    storage.unload_if_loaded(spec, "sword")  # must not raise
    assert spec.loaded_ammo == {}
```

(Use a real launcher id from the catalog — verify with
`.venv\Scripts\python.exe -c "from aose.data.loader import GameData; d=GameData.load('data'); print([i for i in d.items if 'bow' in i])"` and substitute the actual id if `short_bow` differs.)

- [ ] **Step 2: Run test, verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py -v -k unload`
Expected: FAIL — `storage.unload_if_loaded` does not exist.

- [ ] **Step 3: Implement the helper**

In `aose/engine/storage.py`:

```python
def unload_if_loaded(spec: CharacterSpec, weapon_key: str) -> None:
    """Drop any loaded-ammo reference keyed by ``weapon_key`` (no-op if absent).
    Run before a weapon or its full ammo stack leaves its bucket so no weapon
    points at a relocated/merged stack."""
    if weapon_key in spec.loaded_ammo:
        del spec.loaded_ammo[weapon_key]
```

- [ ] **Step 4: Run test, verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py -v -k unload`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aose/engine/storage.py tests/test_storage_move_thing.py
git commit -m "feat(storage): unload_if_loaded helper"
```

### Task 4: `move_valuable` gains a split `count` for gems

**Files:**
- Modify: `aose/engine/storage.py:184-206`
- Test: `tests/test_storage_move_thing.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storage_move_thing.py (append)
from aose.models import GemStack

STASHED = StorageLocation(kind="stashed")


def test_gem_partial_move_splits_and_merges():
    spec = _spec(gems=[GemStack(instance_id="g1", value=100, count=5, label="ruby",
                                location=CARRIED)])
    storage.move_valuable(spec, "g1", STASHED, count=2)
    carried = [g for g in spec.gems if g.location == CARRIED]
    stashed = [g for g in spec.gems if g.location == STASHED]
    assert carried[0].count == 3
    assert len(stashed) == 1 and stashed[0].count == 2 and stashed[0].value == 100


def test_gem_partial_move_merges_into_existing_destination_stack():
    spec = _spec(gems=[
        GemStack(instance_id="g1", value=100, count=5, label="ruby", location=CARRIED),
        GemStack(instance_id="g2", value=100, count=1, label="ruby", location=STASHED),
    ])
    storage.move_valuable(spec, "g1", STASHED, count=2)
    stashed = [g for g in spec.gems if g.location == STASHED]
    assert len(stashed) == 1 and stashed[0].count == 3   # merged, not fragmented


def test_gem_full_move_without_count_moves_whole_stack():
    spec = _spec(gems=[GemStack(instance_id="g1", value=50, count=4, label="opal",
                                location=CARRIED)])
    storage.move_valuable(spec, "g1", STASHED)   # count=None → whole stack
    assert all(g.location == STASHED for g in spec.gems)
    assert len(spec.gems) == 1 and spec.gems[0].count == 4
```

- [ ] **Step 2: Run test, verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py -v -k gem`
Expected: FAIL — `move_valuable` takes no `count`.

- [ ] **Step 3: Extend `move_valuable`**

Replace the gem branch of `move_valuable` in `aose/engine/storage.py`. Keep the existing jewellery branch unchanged. New signature + gem handling:

```python
def move_valuable(spec: CharacterSpec, instance_id: str,
                  dest: StorageLocation, count: int | None = None) -> None:
    """Move a gem stack or jewellery piece (by instance_id) to ``dest``.
    For a gem, ``count`` splits N off the source and merges into the matching
    (value, label, dest) stack (one stack per identity+location); ``count=None``
    moves the whole stack. Jewellery is per-piece; ``count`` is ignored."""
    if dest.kind == "container":
        _container(spec, dest.id)
    for i, g in enumerate(spec.gems):
        if g.instance_id == instance_id:
            n = g.count if count is None else count
            if n <= 0 or n > g.count:
                raise StorageError(f"cannot move {n} of {g.count} gems")
            target = next((o for o in spec.gems
                           if o is not g and o.value == g.value
                           and o.label == g.label and o.location == dest), None)
            if target is not None:
                target.count += n
            else:
                spec.gems.append(GemStack(instance_id=__import__("uuid").uuid4().hex,
                                          value=g.value, count=n, label=g.label,
                                          location=dest))
            g.count -= n
            if g.count == 0:
                spec.gems.remove(g)
            # If we created a new dest stack and the source emptied into it,
            # collapse to avoid a redundant pair.
            return
    for j in spec.jewellery:
        if j.instance_id == instance_id:
            j.location = dest
            return
    raise StorageError(f"no gem/jewellery with id {instance_id!r}")
```

Replace the inline `__import__("uuid")` with a module-level `import uuid` at the top of `storage.py` and use `uuid.uuid4().hex`.

- [ ] **Step 4: Run test, verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py -v -k gem`
Expected: PASS

- [ ] **Step 5: Run existing valuables route tests (whole-stack callers unchanged)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_valuables_routes.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add aose/engine/storage.py tests/test_storage_move_thing.py
git commit -m "feat(storage): gem split-and-merge move with count"
```

### Task 5: `move_ammo` (split + merge + full-stack unload)

**Files:**
- Modify: `aose/engine/storage.py` (add `move_ammo`)
- Test: `tests/test_storage_move_thing.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storage_move_thing.py (append)
MULE = StorageLocation(kind="animal", id="mule1")
from aose.models import AnimalInstance


def _spec_with_mule(**kw):
    kw.setdefault("animals", [AnimalInstance(instance_id="mule1", catalog_id="mule")])
    return _spec(**kw)


def test_ammo_partial_move_keeps_loaded_remainder():
    spec = _spec_with_mule(
        inventory=["short_bow"], equipped={"main_hand": "short_bow"},
        ammo=[AmmoStack(instance_id="a1", base_id="arrow", count=20, location=CARRIED)],
        loaded_ammo={"short_bow": "a1"},
    )
    storage.move_ammo(spec, "a1", MULE, count=5)
    assert spec.loaded_ammo.get("short_bow") == "a1"        # still loaded
    carried = [s for s in spec.ammo if s.location == CARRIED]
    mule = [s for s in spec.ammo if s.location == MULE]
    assert carried[0].count == 15 and mule[0].count == 5


def test_ammo_full_move_unloads_then_relocates():
    spec = _spec_with_mule(
        inventory=["short_bow"], equipped={"main_hand": "short_bow"},
        ammo=[AmmoStack(instance_id="a1", base_id="arrow", count=20, location=CARRIED)],
        loaded_ammo={"short_bow": "a1"},
    )
    storage.move_ammo(spec, "a1", MULE, count=20)
    assert "short_bow" not in spec.loaded_ammo               # unloaded
    assert all(s.location == MULE for s in spec.ammo)


def test_ammo_full_move_merges_into_destination_stack():
    spec = _spec_with_mule(ammo=[
        AmmoStack(instance_id="a1", base_id="arrow", count=20, location=CARRIED),
        AmmoStack(instance_id="a2", base_id="arrow", count=3, location=MULE),
    ])
    storage.move_ammo(spec, "a1", MULE, count=20)
    mule = [s for s in spec.ammo if s.location == MULE]
    assert len(mule) == 1 and mule[0].count == 23            # merged, no fragment
```

- [ ] **Step 2: Run test, verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py -v -k ammo`
Expected: FAIL — `storage.move_ammo` does not exist.

- [ ] **Step 3: Implement `move_ammo`**

In `aose/engine/storage.py`:

```python
def move_ammo(spec: CharacterSpec, instance_id: str,
              dest: StorageLocation, count: int) -> None:
    """Split ``count`` off the ammo stack and merge it into the matching
    (base_id, enchantment_id, dest) stack. Moving the *entire* stack first
    unloads it from any weapon that has it loaded."""
    from aose.engine import ammo as _ammo
    if dest.kind in ("animal", "vehicle"):
        _carrier(spec, dest.kind, dest.id)
    if dest.kind == "container":
        _container(spec, dest.id)
    src = next((s for s in spec.ammo if s.instance_id == instance_id), None)
    if src is None:
        raise StorageError(f"no ammo stack {instance_id!r}")
    if count <= 0 or count > src.count:
        raise StorageError(f"cannot move {count} of {src.count} ammo")
    if count == src.count:
        for key, iid in list(spec.loaded_ammo.items()):
            if iid == instance_id:
                unload_if_loaded(spec, key)
    src.count -= count
    if src.count == 0:
        spec.ammo.remove(src)
    spec.ammo = _ammo._combine(spec.ammo, src.base_id, src.enchantment_id,
                               count, location=dest)
```

- [ ] **Step 4: Run test, verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py -v -k ammo`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aose/engine/storage.py tests/test_storage_move_thing.py
git commit -m "feat(storage): move_ammo split/merge with full-stack unload"
```

### Task 6: `move_instance` (magic/enchanted, auto-unequip)

**Files:**
- Modify: `aose/engine/storage.py` (add `move_instance`)
- Test: `tests/test_storage_move_thing.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storage_move_thing.py (append)
from aose.models import MagicItemInstance, EnchantedInstance, Retainer

CONT = None  # set per-test


def test_magic_move_to_container_repoints_location():
    from aose.models import ContainerInstance
    spec = _spec(
        inventory=["backpack"],
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=CARRIED)],
        magic_items=[MagicItemInstance(instance_id="m1", catalog_id="ring_protection",
                                       equipped=True)],
    )
    dest = StorageLocation(kind="container", id="c1")
    storage.move_instance(spec, "magic", "m1", dest)
    m = spec.magic_items[0]
    assert m.location == dest and m.equipped is False          # auto-unequipped


def test_enchanted_move_to_retainer_is_list_to_list():
    npc = _spec(name="Hench")
    spec = _spec(
        enchanted=[EnchantedInstance(instance_id="e1", base_id="sword",
                                     enchantment_id="plus1", equipped=False)],
        retainers=[Retainer(id="r1", spec=npc, loyalty=7)],
    )
    dest = StorageLocation(kind="retainer", id="r1")
    storage.move_instance(spec, "enchanted", "e1", dest)
    assert spec.enchanted == []                                 # left PC world
    moved = spec.retainers[0].spec.enchanted
    assert len(moved) == 1 and moved[0].location == CARRIED     # reset in retainer world


def test_magic_move_clears_equipped_slot_for_weapon():
    spec = _spec(
        inventory=["sword"], equipped={"main_hand": "sword"},
        magic_items=[MagicItemInstance(instance_id="m1", catalog_id="sword",
                                       equipped=True)],
    )
    storage.move_instance(spec, "magic", "m1", STASHED)
    assert "main_hand" not in spec.equipped or spec.equipped.get("main_hand") != "sword"
```

(Confirm `ring_protection` / `plus1` ids exist via a quick catalog grep; substitute real ids if needed — these are illustrative.)

- [ ] **Step 2: Run test, verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py -v -k "magic or enchanted"`
Expected: FAIL — `storage.move_instance` does not exist.

- [ ] **Step 3: Implement `move_instance`**

In `aose/engine/storage.py`:

```python
def _world_lists(world_spec: CharacterSpec, kind: str) -> list:
    return world_spec.magic_items if kind == "magic" else world_spec.enchanted


def _find_instance(spec: CharacterSpec, kind: str, instance_id: str):
    """Locate a magic/enchanted instance in the PC world or any retainer world.
    Returns (owner_spec, list, inst)."""
    for x in _world_lists(spec, kind):
        if x.instance_id == instance_id:
            return spec, _world_lists(spec, kind), x
    for r in spec.retainers:
        for x in _world_lists(r.spec, kind):
            if x.instance_id == instance_id:
                return r.spec, _world_lists(r.spec, kind), x
    raise StorageError(f"no {kind} instance {instance_id!r}")


def move_instance(spec: CharacterSpec, kind: str, instance_id: str,
                  dest: StorageLocation) -> None:
    """Move a magic or enchanted instance to ``dest`` from anywhere (PC or a
    retainer world). Auto-unequips first (clears the instance ``equipped`` flag
    and any owning-spec equipped slot pointing at it). A move that crosses
    worlds (PC↔retainer) is a list-to-list move; within a world it re-points the
    instance ``location``."""
    if kind not in ("magic", "enchanted"):
        raise StorageError(f"move_instance: bad kind {kind!r}")
    if dest.kind in ("animal", "vehicle"):
        _carrier(spec, dest.kind, dest.id)
    if dest.kind == "container":
        _container(spec, dest.id)
    owner_spec, src_list, inst = _find_instance(spec, kind, instance_id)
    # Auto-unequip on the owning spec.
    catalog_id = getattr(inst, "catalog_id", None) or getattr(inst, "base_id", None)
    inst.equipped = False
    for slot, iid in list(owner_spec.equipped.items()):
        if iid == catalog_id:
            del owner_spec.equipped[slot]
            unload_if_loaded(owner_spec, catalog_id)
    dest_world = _retainer(spec, dest.id).spec if dest.kind == "retainer" else spec
    if dest_world is owner_spec:
        inst.location = dest                       # same world → re-point
    else:
        src_list.remove(inst)                       # cross world → list-to-list
        new_loc = (StorageLocation(kind="carried")
                   if dest.kind == "retainer" else dest)
        _world_lists(dest_world, kind).append(inst.model_copy(update={"location": new_loc}))
```

- [ ] **Step 4: Run test, verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py -v -k "magic or enchanted"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aose/engine/storage.py tests/test_storage_move_thing.py
git commit -m "feat(storage): move_instance for magic/enchanted with auto-unequip"
```

### Task 7: `move_thing` dispatcher + `move_targets`

**Files:**
- Modify: `aose/engine/storage.py` (add both)
- Test: `tests/test_storage_move_thing.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storage_move_thing.py (append)
from aose.models import CoinStack, ContainerInstance


def test_move_thing_dispatches_each_category():
    spec = _spec_with_mule(
        inventory=["torch", "backpack"],
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=CARRIED)],
        coins=[CoinStack(denom="gp", count=10, location=CARRIED)],
        gems=[GemStack(instance_id="g1", value=50, count=2, label="", location=CARRIED)],
        ammo=[AmmoStack(instance_id="a1", base_id="arrow", count=20, location=CARRIED)],
        magic_items=[MagicItemInstance(instance_id="m1", catalog_id="torch")],
    )
    cont = StorageLocation(kind="container", id="c1")
    storage.move_thing(spec, "item", "torch", cont, data=DATA)
    storage.move_thing(spec, "coin", "gp", MULE, count=4, data=DATA)
    storage.move_thing(spec, "gem", "g1", MULE, count=1, data=DATA)
    storage.move_thing(spec, "ammo", "a1", MULE, count=20, data=DATA)
    storage.move_thing(spec, "magic", "m1", MULE, data=DATA)
    # torch moved into container c1
    assert "torch" in spec.containers[0].contents
    # coins split: 6 carried, 4 on mule
    assert sum(c.count for c in spec.coins if c.location == CARRIED) == 6
    assert sum(c.count for c in spec.coins if c.location == MULE) == 4
    assert any(s.location == MULE for s in spec.ammo)
    assert spec.magic_items[0].location == MULE


def test_move_targets_lists_inventories_and_containers():
    spec = _spec_with_mule(
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=CARRIED)],
    )
    targets = storage.move_targets(spec, DATA)
    kinds = {(t["kind"], t.get("id")) for t in targets}
    assert ("carried", None) in kinds
    assert ("stashed", None) in kinds
    assert ("animal", "mule1") in kinds
    assert ("container", "c1") in kinds
```

- [ ] **Step 2: Run test, verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py -v -k "move_thing or move_targets"`
Expected: FAIL — neither function exists.

- [ ] **Step 3: Implement `move_thing` + `move_targets`**

In `aose/engine/storage.py`:

```python
def move_thing(spec: CharacterSpec, category: str, ref_id: str,
               dest: StorageLocation, *, count: int | None = None,
               src: StorageLocation | None = None, data=None) -> None:
    """Single movement front door. ``category`` selects the substrate.
    ``count`` applies to coins/gems/ammo; ``src`` is required for loose items
    (which list to pull from). ``data`` is used by item moves' validation."""
    if category == "item":
        if src is None:
            raise StorageError("item move requires src")
        unload_if_loaded(spec, ref_id)            # a loaded weapon unloads first
        move_item(spec, ref_id, src, dest)
    elif category == "container":
        move_container(spec, ref_id, dest)
    elif category == "coin":
        move_coins(spec, ref_id, src or StorageLocation(kind="carried"), dest,
                   count if count is not None else 0)
    elif category == "gem" or category == "jewellery":
        move_valuable(spec, ref_id, dest, count=count)
    elif category == "ammo":
        move_ammo(spec, ref_id, dest, count if count is not None else 0)
    elif category in ("magic", "enchanted"):
        move_instance(spec, category, ref_id, dest)
    else:
        raise StorageError(f"unknown move category {category!r}")


def move_targets(spec: CharacterSpec, data) -> list[dict]:
    """Every top-level inventory + every container (PC and retainer) as
    {kind, id, label} dicts, for the shared Move control. Callers exclude the
    current location."""
    out: list[dict] = [
        {"kind": "carried", "id": None, "label": spec.name or "Carried"},
        {"kind": "stashed", "id": None, "label": "Stashed"},
    ]
    for a in spec.animals:
        cat = data.items.get(a.catalog_id)
        out.append({"kind": "animal", "id": a.instance_id,
                    "label": a.name or (cat.name if cat else a.catalog_id)})
    for v in spec.vehicles:
        cat = data.items.get(v.catalog_id)
        out.append({"kind": "vehicle", "id": v.instance_id,
                    "label": v.name or (cat.name if cat else v.catalog_id)})
    for r in spec.retainers:
        out.append({"kind": "retainer", "id": r.id, "label": r.spec.name})
    for c in spec.containers:
        cat = data.items.get(c.catalog_id)
        out.append({"kind": "container", "id": c.instance_id,
                    "label": (cat.name if cat else c.catalog_id)})
    for r in spec.retainers:
        for c in r.spec.containers:
            cat = data.items.get(c.catalog_id)
            out.append({"kind": "container", "id": c.instance_id,
                        "label": f"{r.spec.name} ▸ {cat.name if cat else c.catalog_id}"})
    return out
```

- [ ] **Step 4: Run test, verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py -v -k "move_thing or move_targets"`
Expected: PASS

- [ ] **Step 5: Run the whole new engine test file + storage/valuables/ammo**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py tests/test_valuables_routes.py tests/test_inventory_move_routes.py -q`
Expected: PASS (move-route tests still hit the old typed routes — they break in Phase 5, not now).

- [ ] **Step 6: Commit**

```bash
git add aose/engine/storage.py tests/test_storage_move_thing.py
git commit -m "feat(storage): move_thing dispatcher + move_targets"
```

---

## Phase 3 — Encumbrance per-location

### Task 8: Filter magic/enchanted/ammo weight to carried; count stowed in carried containers

**Files:**
- Modify: `aose/engine/encumbrance.py:98-180` (`treasure_weight_cn`, `equipment_weight_cn`, the container loop)
- Test: `tests/test_encumbrance.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_encumbrance.py (append)
from aose.engine import encumbrance
from aose.models import MagicItemInstance
from aose.models.storage import StorageLocation


def test_magic_on_a_mule_does_not_count_toward_carried(enc_data):  # use existing data fixture
    from aose.models import CharacterSpec, ClassEntry, AnimalInstance
    spec = CharacterSpec(
        name="X", abilities={"STR":10,"INT":10,"WIS":10,"DEX":10,"CON":10,"CHA":10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        animals=[AnimalInstance(instance_id="mule1", catalog_id="mule")],
        magic_items=[MagicItemInstance(instance_id="m1", catalog_id="rod_of_lordly_might",
                     location=StorageLocation(kind="animal", id="mule1"))],
    )
    carried = encumbrance.carried_weight_cn(spec, enc_data)
    # Moving the same magic item to carried should increase carried weight.
    spec.magic_items[0].location = StorageLocation(kind="carried")
    assert encumbrance.carried_weight_cn(spec, enc_data) > carried
```

(Adapt to the existing data fixture in `test_encumbrance.py` — reuse whatever `GameData` fixture/global that file already defines instead of `enc_data` if different. Use a real treasure-weight magic item id from the catalog.)

- [ ] **Step 2: Run test, verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py -v -k mule`
Expected: FAIL — magic weight counts regardless of location.

- [ ] **Step 3: Add a carried filter**

In `aose/engine/encumbrance.py`, wherever `spec.magic_items` and `spec.enchanted` are iterated for weight (`treasure_weight_cn` ~105-113 and `equipment_weight_cn` ~144-156), guard each with a carried check. Add a small helper near the top:

```python
def _is_carried(obj) -> bool:
    loc = getattr(obj, "location", None)
    return loc is None or loc.kind == "carried"
```

Then in each magic/enchanted/ammo loop, `continue` when `not _is_carried(mi)`. The container loop (lines ~161-176) already filters `c.location.kind == "carried"` and sums stowed coins/gems/jewellery; extend it to also add stowed magic/enchanted/ammo weight by the same `here = StorageLocation(kind="container", id=c.instance_id)` filter (use `treasure_item_weight`/listed weight as appropriate, mirroring how carried magic is weighed).

- [ ] **Step 4: Run test, verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py -v -k mule`
Expected: PASS

- [ ] **Step 5: Run the full encumbrance suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add aose/engine/encumbrance.py tests/test_encumbrance.py
git commit -m "feat(encumbrance): magic/enchanted/ammo weight is location-aware"
```

---

## Phase 4 — View bucketing + container stowed contents

### Task 9: `ContainerView` gains stowed pointer-type sub-lists

**Files:**
- Modify: `aose/engine/shop.py` (`ContainerView` model — add fields)
- Modify: `aose/sheet/view.py:1361-1391` (`_container_views_from` fills them)
- Test: `tests/test_sheet_inventory_box.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sheet_inventory_box.py (append)
def test_container_view_shows_stowed_coins_and_magic(tmp_path):
    from aose.characters import save_character
    from aose.models import (CharacterSpec, ClassEntry, CoinStack, ContainerInstance,
                             MagicItemInstance)
    from aose.models.storage import StorageLocation
    cont_loc = StorageLocation(kind="container", id="c1")
    spec = CharacterSpec(
        name="Bagman",
        abilities={"STR":10,"INT":10,"WIS":10,"DEX":10,"CON":10,"CHA":10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        inventory=["backpack"],
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=StorageLocation(kind="carried"))],
        coins=[CoinStack(denom="gp", count=7, location=cont_loc)],
        magic_items=[MagicItemInstance(instance_id="m1", catalog_id="ring_protection",
                                       location=cont_loc)],
    )
    app = _make_app(tmp_path)
    save_character("tc-stow", spec, tmp_path / "characters")
    body = TestClient(app, follow_redirects=False).get("/character/tc-stow").text
    assert "7 gp" in body            # stowed coins render inside the container block
    # the magic item modal exists and is reachable
    assert 'id="modal-magic-m1"' in body
```

- [ ] **Step 2: Run test, verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py -v -k stowed`
Expected: FAIL — stowed coins/magic are not rendered in the container.

- [ ] **Step 3: Add fields + fill them**

In `aose/engine/shop.py`, add to `ContainerView`:

```python
    stowed_coins: list = Field(default_factory=list)       # CoinRow
    stowed_gems: list = Field(default_factory=list)         # GemRow
    stowed_jewellery: list = Field(default_factory=list)    # JewelleryRow
    stowed_magic: list = Field(default_factory=list)        # MagicItemView
    stowed_enchanted: list = Field(default_factory=list)
    stowed_ammo: list = Field(default_factory=list)         # AmmoRow
```

In `aose/sheet/view.py` `_container_views_from`, after building `content_rows`, compute the container's location and gather pointer-types (reuse the same `_coin_rows`/`_gem_rows`/`_jewellery_rows` helpers defined in `build_inventory_groups` by lifting them to module scope or passing them in). Populate the new `ContainerView(...)` fields. For magic/enchanted/ammo, filter the respective `_magic_items`/`enchanted_items_view`/`ammo_view` outputs by `location == here`.

> Implementation note: `_coin_rows` etc. are nested inside `build_inventory_groups`. Lift them to module-level functions `_coin_rows(spec, loc)`, `_gem_rows(spec, loc)`, `_jewellery_rows(spec, loc)` so both the group builder and `_container_views_from` can call them. Update the group builder call sites accordingly (pure rename, no behaviour change).

- [ ] **Step 4: Render stowed contents in the container block**

In `aose/web/templates/_inv_pane.html`, inside the per-container `{% for c in group.containers %}` loop (after the existing `c.contents` rows), add rows for the new sub-lists so they appear indented under the container — mirroring the existing `↳`-prefixed content rows and the top-level treasure/magic rows. Each is clickable to its existing modal:

```jinja
      {% for cc in c.stowed_coins %}
      <li{% if manage_treasure %} class="clickable" data-modal="modal-coin-container-{{ c.instance_id }}-{{ cc.denom }}"{% endif %}><span><span class="indent">↳</span> {{ cc.count }} {{ cc.denom }}<span class="tag faint">coin</span></span><span class="q">{{ cc.count }} cn</span></li>
      {% endfor %}
      {% for g in c.stowed_gems %}
      <li{% if manage_treasure %} class="clickable" data-modal="modal-gem-{{ g.instance_id }}"{% endif %}><span><span class="indent">↳</span> {% if g.label %}{{ g.label }}{% else %}{{ g.value }} gp gem{% endif %} × {{ g.count }}<span class="tag faint">gem · {{ g.stack_value }} gp</span></span><span class="q">{{ g.count }} cn</span></li>
      {% endfor %}
      {% for j in c.stowed_jewellery %}
      <li{% if manage_treasure %} class="clickable" data-modal="modal-jewel-{{ j.instance_id }}"{% endif %}><span><span class="indent">↳</span> {% if j.label %}{{ j.label }}{% else %}jewellery{% endif %}<span class="tag faint">jewel · {{ j.effective_value }} gp</span></span><span class="q">10 cn</span></li>
      {% endfor %}
      {% for mi in c.stowed_magic %}
      <li class="clickable" data-modal="modal-magic-{{ mi.instance_id }}"><span><span class="indent">↳</span> {{ mi.name }} <span class="tag stamp">magic</span></span></li>
      {% endfor %}
      {% for mi in c.stowed_enchanted %}
      <li class="clickable" data-modal="modal-magic-{{ mi.instance_id }}"><span><span class="indent">↳</span> {{ mi.name }} <span class="tag stamp">enchanted</span></span></li>
      {% endfor %}
      {% for a in c.stowed_ammo %}
      <li class="clickable" data-modal="modal-ammo-{{ a.instance_id }}"><span><span class="indent">↳</span> {{ a.name }}</span><span class="q">× {{ a.count }}</span></li>
      {% endfor %}
```

The coin modal id `modal-coin-container-<cid>-<denom>` requires the coin modal to also be rendered for container locations — handled in Task 14 when treasure modals are rendered per group **and per container location**. Gem/jewellery/magic/ammo modals are already rendered globally by instance id, so those clicks resolve immediately.

- [ ] **Step 5: Run test, verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py -v -k stowed`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add aose/engine/shop.py aose/sheet/view.py aose/web/templates/_inv_pane.html tests/test_sheet_inventory_box.py
git commit -m "feat(view): containers carry + render stowed coins/gems/jewellery/magic/ammo"
```

### Task 10: Bucket magic/enchanted/ammo by location across groups

**Files:**
- Modify: `aose/sheet/view.py:1404-1527` (`build_inventory_groups`)
- Test: `tests/test_sheet_inventory_box.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sheet_inventory_box.py (append)
def test_magic_on_carrier_buckets_under_carrier():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.sheet.view import build_inventory_groups
    from aose.models import (CharacterSpec, ClassEntry, AnimalInstance,
                             MagicItemInstance)
    from aose.models.storage import StorageLocation
    data = GameData.load(Path("data"))
    mule = StorageLocation(kind="animal", id="mule1")
    spec = CharacterSpec(
        name="Packer",
        abilities={"STR":10,"INT":10,"WIS":10,"DEX":10,"CON":10,"CHA":10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        animals=[AnimalInstance(instance_id="mule1", catalog_id="mule")],
        magic_items=[MagicItemInstance(instance_id="m1", catalog_id="ring_protection",
                                       location=mule)],
    )
    groups = build_inventory_groups(spec, data)
    carried = next(g for g in groups if g.kind == "carried")
    animal = next(g for g in groups if g.kind == "animal")
    assert all(mi.instance_id != "m1" for mi in carried.magic_items)   # not in PC
    assert any(mi.instance_id == "m1" for mi in animal.magic_items)    # under mule
```

- [ ] **Step 2: Run test, verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py -v -k carrier_buckets`
Expected: FAIL — magic items always go to the PC carried group.

- [ ] **Step 3: Bucket by location**

In `build_inventory_groups`:
- Compute `pc_magic_unequipped` / `pc_enchanted` / `pc_ammo` filtered to carried location only.
- For each animal/vehicle group, add `magic_items`, `enchanted`, `ammo` filtered to that carrier's location.
- Retainer groups already read `retainer.spec.*`; add their magic/enchanted/ammo filtered to the retainer's carried location.
- Container-stowed pointer-types are handled by Task 9 (rendered inside the container, not the group bucket) — ensure the group-level lists exclude container-located items (filter `location.kind != "container"` as well as matching the group's own loc).

Use the lifted `_magic_items`/`enchanted_items_view`/`ammo_view` outputs and filter by `.location`.

- [ ] **Step 4: Run test, verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py -v -k carrier_buckets`
Expected: PASS

- [ ] **Step 5: Run the full view + box suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py tests/test_inventory_view.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add aose/sheet/view.py tests/test_sheet_inventory_box.py
git commit -m "feat(view): bucket magic/enchanted/ammo by storage location"
```

---

## Phase 5 — Single move route (delete typed routes)

### Task 11: Add `POST /character/{id}/inventory/move`

**Files:**
- Modify: `aose/web/routes.py:440-504` (replace the four typed routes with one)
- Test: `tests/test_inventory_move_routes.py` (rewrite move assertions)

- [ ] **Step 1: Enumerate every call site to migrate**

Run (record the output; every hit must be updated in this phase):

```bash
grep -rn "move-item\|move-coins\|move-valuable\|move-container" aose/ tests/
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_inventory_move_routes.py — add (and later remove old typed-route tests)
def test_single_move_route_moves_item_to_container(client):
    from aose.models import ContainerInstance
    from aose.models.storage import StorageLocation
    _save_char(client, inventory=["torch", "backpack"],
               containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                             location=StorageLocation(kind="carried"))])
    r = client.post("/character/Hero/inventory/move", data={
        "category": "item", "item_id": "torch",
        "src_kind": "carried", "src_id": "",
        "dest_kind": "container", "dest_id": "c1",
    })
    assert r.status_code == 303
    spec = load_character("Hero", client._characters_dir)
    assert "torch" in spec.containers[0].contents


def test_old_typed_move_routes_are_gone(client):
    _save_char(client, inventory=["torch"])
    r = client.post("/character/Hero/inventory/move-item", data={
        "item_id": "torch", "src_kind": "carried", "dest_kind": "stashed"})
    assert r.status_code == 404
```

- [ ] **Step 3: Run test, verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_move_routes.py -v -k "single_move or typed_move_routes_are_gone"`
Expected: FAIL — `/inventory/move` 404s; the typed route still exists.

- [ ] **Step 4: Replace the four routes with one**

In `aose/web/routes.py`, delete `inventory_move_item`, `inventory_move_container`, `inventory_move_coins`, `inventory_move_valuable` (440-504) and add:

```python
@router.post("/character/{character_id}/inventory/move")
async def inventory_move(request: Request, character_id: str):
    """Single movement front door for every owned thing."""
    from aose.engine import storage as _storage
    spec = _load_spec_or_404(request, character_id)
    form = await request.form()
    category = form.get("category", "")
    ref_id = (form.get("item_id") or form.get("instance_id")
              or form.get("denom") or "")
    dest = _loc(form.get("dest_kind", "carried"), form.get("dest_id") or None)
    src = (_loc(form.get("src_kind"), form.get("src_id") or None)
           if form.get("src_kind") else None)
    raw = form.get("count")
    count = int(raw) if raw not in (None, "") else None
    try:
        _storage.move_thing(spec, category, ref_id, dest,
                            count=count, src=src,
                            data=request.app.state.game_data)
    except (KeyError, _storage.StorageError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

Update line 235: `"inv_move_url": f"/character/{character_id}/inventory/move"`.

- [ ] **Step 5: Run test, verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_move_routes.py -v -k "single_move or typed_move_routes_are_gone"`
Expected: PASS

- [ ] **Step 6: Migrate the rest of `test_inventory_move_routes.py`**

Rewrite every existing test that posted to a typed route to post to `/inventory/move` with the new `category` + fields. Run the whole file:

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_move_routes.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add aose/web/routes.py tests/test_inventory_move_routes.py
git commit -m "feat(routes): single /inventory/move; delete typed move routes"
```

### Task 12: Wizard — single move route

**Files:**
- Modify: `aose/web/wizard.py:1957-2100` (replace `post_equipment_move_item` + `wiz_move_container`), `:1764` (`inv_move_url`)
- Test: `tests/test_wizard*.py` (whichever covers equipment move; grep first)

- [ ] **Step 1: Find wizard move coverage**

Run: `grep -rn "equipment/move-item\|inventory/move-container\|inv_move_url" aose/web/wizard.py tests/`

- [ ] **Step 2: Write/adjust the failing test**

Add a wizard test mirroring Task 11 against `/wizard/{id}/inventory/move`, and a 404 assertion for the old `/wizard/{id}/equipment/move-item`.

- [ ] **Step 3: Run, verify fail.** Then replace the two wizard routes with a single `POST /{draft_id}/inventory/move` that loads the draft spec, calls `storage.move_thing`, saves the draft, and redirects to the equipment step. Mirror the PC route body but use the draft load/save helpers already in `wizard.py`. Update `inv_move_url` to `/wizard/{draft_id}/inventory/move`.

- [ ] **Step 4: Run, verify pass.**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q -k wizard`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aose/web/wizard.py tests/
git commit -m "feat(wizard): single /inventory/move; delete typed move routes"
```

---

## Phase 6 — Shared action macros + button-size standard

### Task 13: Create `_actions.html` macros

**Files:**
- Create: `aose/web/templates/_actions.html`
- Modify: `aose/web/templates/_move_dest.html` (drive off `move_targets` + unified `ref`)

- [ ] **Step 1: Generalise `_move_dest.html`**

Rewrite `move_dest_control` to accept the `move_targets` list and a `ref` (category + ids), drop `allow_containers`/`allow_retainers`, and render a `count` input only when `category in ("coin","gem","ammo")`. The select options carry `data-kind`/`data-id`; the existing `inventory.js` submit handler already copies them into `dest_kind`/`dest_id`. Exclude the current `(cur_kind, cur_id)` and, when moving a container, all `container` targets.

- [ ] **Step 2: Write the action macros**

```jinja
{# aose/web/templates/_actions.html — the single source of truth for an action control. #}
{% from "_move_dest.html" import move_dest_control with context %}

{% macro act_button(label, url, hidden={}, variant="default", size="modal", attrs="") %}
<form method="post" action="{{ url }}" class="inline-form">
  {% for k, v in hidden.items() %}<input type="hidden" name="{{ k }}" value="{{ v }}">{% endfor %}
  <button type="submit" class="btn{% if size == 'inline' %} btn-inline{% elif size == 'tool' %} btn-tool{% elif size == 'cta' %} btn-cta{% endif %}{% if variant == 'solid' %} solid{% elif variant == 'danger' %} danger{% endif %}" {{ attrs }}>{{ label }}</button>
</form>
{% endmacro %}

{% macro act_move(url, ref, move_targets, cur_kind, cur_id, count=none) %}
<form method="post" action="{{ url }}" class="inline-form move-form">
  <input type="hidden" name="category" value="{{ ref.category }}">
  {% if ref.category == 'coin' %}<input type="hidden" name="denom" value="{{ ref.id }}">
  {% elif ref.category == 'item' %}<input type="hidden" name="item_id" value="{{ ref.id }}">
  {% else %}<input type="hidden" name="instance_id" value="{{ ref.id }}">{% endif %}
  <input type="hidden" name="src_kind" value="{{ cur_kind }}">
  <input type="hidden" name="src_id" value="{{ cur_id }}">
  {% if ref.category in ('coin','gem','ammo') and count is not none %}
  <input type="number" name="count" value="{{ count }}" min="1" class="act-num">
  {% endif %}
  {{ move_dest_control(move_targets, ref, cur_kind, cur_id) }}
  {% if ref.category in ('coin','gem','ammo') %}<button class="btn btn-inline" type="submit">Move</button>{% endif %}
</form>
{% endmacro %}

{% macro act_stepper(url, hidden={}, field="delta") %}
<form method="post" action="{{ url }}" class="inline-form">
  {% for k, v in hidden.items() %}<input type="hidden" name="{{ k }}" value="{{ v }}">{% endfor %}
  <button class="btn btn-inline" type="submit" name="{{ field }}" value="1">+</button>
  <button class="btn btn-inline" type="submit" name="{{ field }}" value="-1">−</button>
</form>
{% endmacro %}
```

(`act_sell` and `act_select` follow the same pattern — model them on the existing `sell-form`/`sell-dest` and coin-convert markup; keep the `.sell-dest`/`.move-dest` classes so `inventory.js` keeps working.)

- [ ] **Step 3: Smoke-test render**

Add a throwaway assertion in `tests/test_sheet_inventory_box.py` that the sheet still renders (200) after importing the new macros, then remove it. Or simply run the box suite after Task 14 wiring.

- [ ] **Step 4: Commit**

```bash
git add aose/web/templates/_actions.html aose/web/templates/_move_dest.html
git commit -m "feat(ui): shared action-control macros + move_targets dest control"
```

### Task 14: Route every inventory/treasure modal through the macros

**Files:**
- Modify: `aose/web/templates/_inv_modals.html`, `_inv_row_actions.html`, `_inv_pane.html`, `sheet.html`
- Test: `tests/test_sheet_inventory_box.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sheet_inventory_box.py (append)
def test_magic_modal_has_move_control(tmp_path):
    from aose.characters import save_character
    from aose.models import CharacterSpec, ClassEntry, MagicItemInstance
    spec = CharacterSpec(
        name="Wiz", abilities={"STR":10,"INT":10,"WIS":10,"DEX":10,"CON":10,"CHA":10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        magic_items=[MagicItemInstance(instance_id="m1", catalog_id="ring_protection")],
    )
    app = _make_app(tmp_path)
    save_character("tc-mm", spec, tmp_path / "characters")
    body = TestClient(app, follow_redirects=False).get("/character/tc-mm").text
    # magic modal now offers a Move targeting /inventory/move with category=magic
    seg = body.split('id="modal-magic-m1"')[1].split("</div>")[0:6]
    seg = "".join(seg)
    assert "/inventory/move" in body
    assert 'value="magic"' in body          # ref.category for the magic Move form


def test_no_bare_button_in_inventory_action_rows(tmp_path):
    from aose.characters import save_character
    save_character("tc-bare", _treasure_spec(), tmp_path / "characters")
    app = _make_app(tmp_path)
    body = TestClient(app, follow_redirects=False).get("/character/tc-bare").text
    # crude guard: equip/unequip buttons now carry a .btn class (no bare <button>)
    assert "<button type=\"submit\">Unequip</button>" not in body
    assert "<button type=\"submit\">Equip</button>" not in body
```

- [ ] **Step 2: Run, verify fail.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py -v -k "magic_modal_has_move or no_bare_button"`
Expected: FAIL — magic modal has no Move; bare buttons present.

- [ ] **Step 3: Wire the macros**

- Import `act_button`, `act_move`, `act_stepper` (and `act_sell`/`act_select`) in `_inv_modals.html` and `sheet.html`.
- In the **magic/enchanted modal** (`sheet.html` ~994-1024): add `act_move(_char_url ~ "/inventory/move", {"category": ("enchanted" if is_ench else "magic"), "id": mi.instance_id}, move_targets, group_kind, group_id, none)`. The modal is rendered per group, so pass the owning group's kind/id (today these modals are PC-only at carried; once Task 10 buckets them, render per group like the treasure modals).
- In the **ammo modal** (`sheet.html` ~1034-1054): add `act_move(..., {"category": "ammo", "id": a.instance_id}, ..., count=a.count)` plus the existing ± stepper via `act_stepper`.
- In **coin/gem/jewellery modals** (`_inv_modals.html`): replace the hand-rolled Move forms with `act_move(..., count=…)` (coins/gems carry count; jewellery no count). Keep Convert/Sell/Adjust/Drop as `act_button`/`act_select`.
- In `_inv_row_actions.html`: give Equip/Unequip/Off-hand/Unstash/Take-out `.btn .btn-inline` classes (no bare buttons); point the Move form at `/inventory/move` with the unified `ref` (category `item`).
- Pass `move_targets` into the template context: in `routes.py`, add `"move_targets": storage.move_targets(spec, game_data)` to the sheet context; in `wizard.py`, the same for the draft spec.
- **Container-located treasure modals:** the coin modal id is location-keyed (`modal-coin-<kind>-<id>-<denom>`), so render a coin modal for each container's `stowed_coins` too. Extend the per-group treasure-modal loop in `sheet.html` to also iterate `for c in group.containers` and emit `coin_modal` for `c.stowed_coins` with the container's `(kind="container", id=c.instance_id)` as the source location. Gem/jewellery/magic/ammo modals are already global-by-instance-id, so no duplication needed for them.

- [ ] **Step 4: Run, verify pass.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py -q`
Expected: PASS

- [ ] **Step 5: Manual render check**

Start the app, open a character with a magic item, a coin stack, and a container; confirm each modal shows a Move targeting every inventory + container, and moving a magic ring into a backpack renders it inside the container.

Run: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`

- [ ] **Step 6: Commit**

```bash
git add aose/web/templates/ aose/web/routes.py aose/web/wizard.py tests/test_sheet_inventory_box.py
git commit -m "feat(ui): every inventory/treasure modal routes through shared macros + Move"
```

### Task 15: Sheet-wide button-size standard (CSS)

**Files:**
- Modify: `aose/web/static/sheet.css` (~283-315 buttons/forms; ~454-481 legacy button block; ~897 duplicate `.inline-form`)
- Test: none (visual); guarded by the no-bare-button test from Task 14

- [ ] **Step 1: Define the size scale**

In `aose/web/static/sheet.css`, refactor the button block so size is a context modifier on `.btn`:

```css
/* buttons — size by use context; variant (solid/danger/link) is orthogonal */
.btn{ font-family:var(--display); font-weight:600; font-size:10px; letter-spacing:.07em;
      text-transform:uppercase; padding:4px 9px; border:1.5px solid var(--ink);
      background:var(--box); color:var(--ink); cursor:pointer; line-height:1; }
.btn.btn-inline{ font-size:9px; padding:3px 6px; }          /* row / inline-form */
.btn.btn-tool{ padding:3px 7px; font-size:9px; border-color:#f7f5ed; color:#f7f5ed; background:transparent; }
.btn.btn-tool:hover{ background:#f7f5ed; color:var(--ink); }
.btn.btn-tool.dark{ border-color:var(--ink); color:var(--ink); background:var(--box); }
.btn.btn-cta{ font-size:11px; padding:6px 14px; }            /* wizard Next / Roll */
/* keep existing .btn.solid / .btn.danger / .btn.link variant rules */
```

Alias the retired `.btn.tool` to `.btn.btn-tool` (either rename call-sites — there are few — or add `.btn.tool{ @extend }`-style duplicate selectors that share the declarations) so dark-bar buttons keep their look.

- [ ] **Step 2: Collapse the duplicate `.inline-form`**

Delete the second `.inline-form` rule (~line 897, `gap:.25rem`); keep the first (`gap:6px`). Add width classes used by the macros:

```css
.act-num{ width:4rem; }
.act-select{ max-width:9rem; }
```

- [ ] **Step 3: Kill the bare-button action fall-through**

The legacy `button,.button{…}` block (~454) stays for genuinely unstyled controls, but every inventory action button now carries `.btn` (Task 14), so no inventory control depends on it. Verify the `.btn-inline` sizing on Equip/Unequip etc. looks right against the old bare-button size.

- [ ] **Step 4: Apply context classes sheet-wide**

Grep for `class="btn tool"` and `class="btn solid"` across templates and re-point toolbar buttons to `.btn.btn-tool` and primary CTAs (wizard Next, Roll, level-up confirm) to `.btn.btn-cta`. Leave `.solid`/`.danger` as variant classes.

Run: `grep -rn 'btn tool\|btn solid\|class="btn"' aose/web/templates/`

- [ ] **Step 5: Visual verification**

Start the app; spot-check inline (row), modal, toolbar, and CTA buttons render at their context size; no button unexpectedly shrank/grew.

- [ ] **Step 6: Run the box suite + commit**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py -q`
Expected: PASS

```bash
git add aose/web/static/sheet.css aose/web/templates/
git commit -m "feat(ui): sheet-wide button-size standard keyed to use context"
```

---

## Phase 7 — Docs + verification

### Task 16: Update docs + full-suite verification

**Files:**
- Modify: `docs/ARCHITECTURE.md` (inventory/treasure/encumbrance + a controls note, in place)
- Modify: `docs/CHANGELOG.md` (one dated row at top)
- Modify: `CLAUDE.md` only if orientation changed (a new top-level dir/storage shape — `location` on magic/enchanted/ammo qualifies as a storage-shape note)

- [ ] **Step 1: Update `ARCHITECTURE.md`** in place: the inventory-groups bullet (magic/enchanted/ammo now location-bucketed; containers render stowed pointer-types), the coin/gem/jewellery-modal note (Move now targets containers/retainers via `move_thing`), the encumbrance note (magic/ammo carried-filtered), and add a short "shared action controls + button-size standard" note under the sheet/overlay section. Update the move-route bullet to the single `/inventory/move`.

- [ ] **Step 2: Update `CLAUDE.md`** storage-shapes list: note `magic_items`/`enchanted`/`ammo` now carry `location: StorageLocation`; movement goes through `storage.move_thing` + `POST /inventory/move`.

- [ ] **Step 3: Add `CHANGELOG.md`** row:

```
| 2026-06-23 | Unified item movement: every owned thing (incl. magic/enchanted/ammo, now location-aware) moves to any inventory or container via one `move_thing` engine front-door + single `POST /inventory/move`; stacking types split-and-merge; moving unloads ammo/weapons; shared `_actions.html` macros + sheet-wide button-size standard | feat/unified-item-movement | 2026-06-23-unified-item-movement-and-shared-controls |
```

- [ ] **Step 4: Full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing `pytest-current` PermissionError).

- [ ] **Step 5: Print parity + wizard smoke**

Open `/character/{id}/print` and the wizard equipment step; confirm both render and the wizard box stays `manage_treasure=False` (no carriers mid-creation).

- [ ] **Step 6: Commit**

```bash
git add docs/ CLAUDE.md
git commit -m "docs: unified item movement + shared controls"
```

---

## Self-Review notes (for the executor)

- **Catalog-item Move into a retainer** uses `move_item`, which already resolves
  `retainer.spec.inventory` (Task 7 `move_thing` passes through). No special case.
- **Coins into a container** rely on the container's `location.kind == "carried"`
  for weight; a coin in a stashed container weighs zero (consistent with stashed).
- **`move_targets` ordering** mirrors the old `move_dest_control` (top-levels, then
  containers); keep it stable so the dropdown order doesn't churn.
- **Real catalog ids** in tests (`ring_protection`, `short_bow`, `plus1`,
  `rod_of_lordly_might`) are illustrative — verify against `data/` and substitute the
  actual ids before asserting; a wrong id fails loudly at `GameData.load`/lookup.
