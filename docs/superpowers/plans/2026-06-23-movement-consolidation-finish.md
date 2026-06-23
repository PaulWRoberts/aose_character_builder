# Finish the Movement Consolidation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make spell sources movable/droppable, fix the equipped-weapon double-render, unify magic/enchanted/spell-source removal onto the shared action controls, collapse the redundant shop/companions movement helpers into the single `move_thing` front door with one central capacity gate, and gate scroll cast/decipher/copy on the document being carried on the PC.

**Architecture:** One movement front door (`storage.move_thing`) validates destination capacity in one place (`_check_capacity`) backed by one definition of per-location load (`location_load_cn`, also used by encumbrance). Spell sources gain a `location` and join the move system. The shop `stash/stow/take_out/*_container` and companions `load_onto_*/unload_from_*` mutators and their PC + wizard routes are deleted; the UI's Stash/Take-out/Load buttons become `act_move` posts. Casting eligibility gates on `location.kind == "carried"` in the engine, propagating to the view flags and the cast route for free.

**Tech Stack:** Python 3, FastAPI, Pydantic v2, Jinja2, pytest. Run tests with `.venv\Scripts\python.exe -m pytest`. Run the app with `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`.

**Conventions:**
- The trailing `PermissionError` on `pytest-current` is a known Windows quirk — ignore it.
- Tests use `GameData.load(Path("data"))` and a local `_spec(**kw)` helper (see `tests/test_storage_move_thing.py`).
- No migrations: `location` defaults to carried, old saves load unchanged.
- "Data, not code"; engine stays cycle-free (`storage.py` imports only models + currency).

---

## File Structure

**Models**
- `aose/models/character.py` — add `location` to `SpellSource`.

**Engine**
- `aose/engine/storage.py` — `location_load_cn`, `_check_capacity`, `move_spell_source`, `move_item` auto-unequip, wire the gate into every `move_*`, `move_thing` `source` category.
- `aose/engine/encumbrance.py` — refactor the container-stowed loop to call `location_load_cn`.
- `aose/engine/spell_sources.py` — carried-on-PC gate in `scroll_cast_block_reason`, decipher, copy.
- `aose/engine/shop.py` — **delete** `stash`, `unstash`, `stow`, `take_out`, `stash_container`, `unstash_container`, `_set_container_state`.
- `aose/engine/companions.py` — **delete** `load_onto_animal`, `unload_from_animal`, `load_onto_vehicle`, `unload_from_vehicle` (keep the capacity/load helpers).

**View**
- `aose/sheet/view.py` — `_equipped` weapon-slot fix; bucket spell sources by location; `ContainerView.stowed_spell_sources`.

**Routes**
- `aose/web/routes.py` — delete the 10 redundant PC routes; add `spell_sources` persistence + `source` handling already covered by `move_thing`.
- `aose/web/wizard.py` — delete the 6 redundant wizard routes; add `spell_sources` to the wizard `/inventory/move` draft persistence.

**Templates**
- `aose/web/templates/_inv_row_actions.html` — Stash/Unstash/Take-out → `act_move`.
- `aose/web/templates/_inv_modals.html` — carrier/container Stow/Load → `act_move`.
- `aose/web/templates/sheet.html` — spell-source modal gains Move ▾ + Drop; magic/enchanted modals onto shared Drop + Sell (magic) / Drop (enchanted); render `stowed_spell_sources`.
- `aose/web/templates/_inv_pane.html` — render spell sources by group / stowed in containers.

**Docs**
- `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.

---

## Phase 1 — Model + engine core

### Task 1: `location` field on `SpellSource`

**Files:**
- Modify: `aose/models/character.py:148-162`
- Test: `tests/test_spell_sources.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_spell_sources.py`:

```python
def test_spell_source_defaults_to_carried():
    from aose.models import SpellSource
    from aose.models.storage import StorageLocation
    s = SpellSource(instance_id="s1", kind="scroll", caster_type="arcane")
    assert s.location == StorageLocation(kind="carried")


def test_spell_source_accepts_explicit_location():
    from aose.models import SpellSource
    from aose.models.storage import StorageLocation
    loc = StorageLocation(kind="stashed")
    s = SpellSource(instance_id="s1", kind="scroll", caster_type="arcane", location=loc)
    assert s.location.kind == "stashed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources.py::test_spell_source_defaults_to_carried -v`
Expected: FAIL — `SpellSource` has no field `location` (or `extra="forbid"` rejects it in the second test).

- [ ] **Step 3: Add the field**

In `aose/models/character.py`, inside `class SpellSource`, add after `language: str = "Common"`:

```python
    location: StorageLocation = Field(default_factory=lambda: StorageLocation(kind="carried"))
```

(`StorageLocation` and `Field` are already imported in this module.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/models/character.py tests/test_spell_sources.py
git commit -m "feat(models): SpellSource carries a StorageLocation"
```

---

### Task 2: `location_load_cn` — one definition of per-location load

**Files:**
- Modify: `aose/engine/storage.py` (add near the other helpers, before `move_thing`)
- Test: `tests/test_storage_helpers.py`

The raw load at a location = sum of every movable substrate whose `.location == loc`,
each by its **raw encumbrance weight**: loose items by `weight_cn`, coins 1 cn each,
gems 1 cn each, jewellery 10 cn each, ammo 0 cn (ammunition is weightless in this
system), magic items by `treasure_item_weight or weight_cn`, enchanted by resolved
weight, scroll spell sources 1 cn (spellbooks 0). This matches the raw sums the old
`stow`/`load_onto_*` and the container view used. Barding is **not** counted here (it
is worn, not stored) — the animal capacity check adds it separately (Task 4).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_storage_helpers.py` (create imports as needed):

```python
from pathlib import Path
from aose.data.loader import GameData
from aose.engine import storage
from aose.models import CharacterSpec, ClassEntry, CoinStack, GemStack, ContainerInstance
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))


def _spec(**kw):
    base = dict(
        name="Loader",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
    )
    base.update(kw)
    return CharacterSpec(**base)


def test_location_load_cn_sums_loose_and_coins_at_a_container():
    here = StorageLocation(kind="container", id="c1")
    sword_cn = DATA.items["sword"].weight_cn
    spec = _spec(
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=StorageLocation(kind="carried"),
                                      contents=["sword"])],
        coins=[CoinStack(denom="gp", count=7, location=here)],
        gems=[GemStack(instance_id="g1", value=50, count=3, label="", location=here)],
    )
    # sword weight + 7 coins (1cn) + 3 gems (1cn)
    assert storage.location_load_cn(spec, here, DATA) == sword_cn + 7 + 3


def test_location_load_cn_is_zero_for_empty_location():
    loc = StorageLocation(kind="animal", id="zzz")
    assert storage.location_load_cn(_spec(), loc, DATA) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_helpers.py::test_location_load_cn_sums_loose_and_coins_at_a_container -v`
Expected: FAIL — `module 'aose.engine.storage' has no attribute 'location_load_cn'`.

- [ ] **Step 3: Implement `location_load_cn`**

In `aose/engine/storage.py`, add (after `loose_list`, before `move_item`):

```python
def location_load_cn(spec: CharacterSpec, loc: StorageLocation, data) -> int:
    """Raw encumbrance weight of every substrate stored *at* ``loc``.

    Loose items by ``weight_cn``; coins 1 cn each; gems 1 cn each; jewellery
    10 cn each; ammunition 0 cn; magic items by treasure-weight-or-own-weight;
    enchanted by resolved weight; scroll spell sources 1 cn (spellbooks 0).
    Does NOT include an animal's worn barding (that is added by the capacity
    check). This is the single definition of "current load here", shared with
    the encumbrance container loop.
    """
    from aose.engine.encumbrance import treasure_item_weight
    from aose.engine.enchant import resolve_instance
    from aose.models import Armor, Weapon

    total = 0
    for item_id in loose_list(spec, loc):
        item = data.items.get(item_id)
        if item is not None:
            total += item.weight_cn
    total += sum(s.count for s in spec.coins if s.location == loc)
    total += sum(g.count for g in spec.gems if g.location == loc)
    total += 10 * sum(1 for j in spec.jewellery if j.location == loc)
    for mi in spec.magic_items:
        if mi.location == loc:
            item = data.items.get(mi.catalog_id)
            if item is not None:
                total += treasure_item_weight(item) or item.weight_cn
    for inst in spec.enchanted:
        if inst.location == loc:
            resolved = resolve_instance(inst, data)
            if isinstance(resolved, Armor):
                total += int(resolved.weight_cn * resolved.weight_multiplier)
            elif isinstance(resolved, Weapon):
                total += resolved.weight_cn
    total += sum(1 for s in spec.spell_sources
                 if s.location == loc and s.kind == "scroll")
    return total
```

Note: `loose_list` raises for `loc` kinds that have no loose list, but every kind
that reaches `_check_capacity` (container/animal/vehicle) has one. For an animal/
vehicle with no matching carrier, `loose_list` raises `StorageError`; the
empty-location test uses a non-existent animal id, so guard it: wrap the loose
sum in a try/except that treats a missing carrier as zero loose items:

```python
    try:
        loose = loose_list(spec, loc)
    except StorageError:
        loose = []
    for item_id in loose:
        ...
```

Use the guarded version.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_helpers.py -v -k location_load_cn`
Expected: PASS (both).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/storage.py tests/test_storage_helpers.py
git commit -m "feat(storage): location_load_cn — one definition of per-location load"
```

---

### Task 3: `_check_capacity` gate (container caps)

**Files:**
- Modify: `aose/engine/storage.py`
- Test: `tests/test_storage_helpers.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_storage_helpers.py`:

```python
import pytest


def test_check_capacity_rejects_overfilling_a_container():
    # belt_pouch capacity_cn == 50; a sword (60 cn) does not fit.
    here = StorageLocation(kind="container", id="p1")
    spec = _spec(containers=[ContainerInstance(
        instance_id="p1", catalog_id="belt_pouch",
        location=StorageLocation(kind="carried"))])
    added = DATA.items["sword"].weight_cn
    with pytest.raises(storage.StorageError):
        storage._check_capacity(spec, here, added, DATA)


def test_check_capacity_allows_fitting_into_a_container():
    here = StorageLocation(kind="container", id="p1")
    spec = _spec(containers=[ContainerInstance(
        instance_id="p1", catalog_id="belt_pouch",
        location=StorageLocation(kind="carried"))])
    storage._check_capacity(spec, here, 10, DATA)  # 10 <= 50, must not raise


def test_check_capacity_never_blocks_carried_stashed_retainer():
    for kind in ("carried", "stashed"):
        storage._check_capacity(_spec(), StorageLocation(kind=kind), 99999, DATA)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_helpers.py -v -k check_capacity`
Expected: FAIL — `_check_capacity` does not exist.

- [ ] **Step 3: Implement `_check_capacity` (container kind first)**

In `aose/engine/storage.py`, add after `location_load_cn`:

```python
def _check_capacity(spec: CharacterSpec, dest: StorageLocation,
                    added_cn: int, data) -> None:
    """Reject a move that would push a capacity-bound destination over its cap.

    Hard caps: container (capacity_cn), animal (max_load_encumbered_cn, incl.
    worn barding), vehicle (cargo_capacity_cn). carried / stashed / retainer have
    no hard cap (PC + retainer suffer encumbrance instead; stashed is weightless).
    A ``None`` cap means unlimited — except an animal that is not a beast of
    burden (cap None) carries nothing, so any positive load is rejected.
    """
    if dest.kind in ("carried", "stashed", "retainer"):
        return
    if dest.kind == "container":
        catalog = data.items.get(_container(spec, dest.id).catalog_id)
        cap = getattr(catalog, "capacity_cn", None)
        current = location_load_cn(spec, dest, data)
        if cap is not None and current + added_cn > cap:
            raise StorageError(
                f"{getattr(catalog, 'name', dest.id)} full: "
                f"{current}/{cap} cn, move adds {added_cn} cn")
        return
    # animal / vehicle handled in Task 4
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_helpers.py -v -k check_capacity`
Expected: PASS (all three).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/storage.py tests/test_storage_helpers.py
git commit -m "feat(storage): _check_capacity gate for container caps"
```

---

### Task 4: `_check_capacity` for animals + vehicles

**Files:**
- Modify: `aose/engine/storage.py`
- Test: `tests/test_storage_helpers.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_storage_helpers.py`:

```python
from aose.models import AnimalInstance, VehicleInstance


def test_check_capacity_rejects_overloading_an_animal():
    # war_dog is not a beast of burden (cap None) -> carries nothing.
    here = StorageLocation(kind="animal", id="d1")
    spec = _spec(animals=[AnimalInstance(instance_id="d1", catalog_id="war_dog")])
    with pytest.raises(storage.StorageError):
        storage._check_capacity(spec, here, 1, DATA)


def test_check_capacity_allows_load_within_mule_cap():
    here = StorageLocation(kind="animal", id="m1")
    spec = _spec(animals=[AnimalInstance(instance_id="m1", catalog_id="mule")])
    storage._check_capacity(spec, here, 100, DATA)  # mule cap is thousands; ok


def test_check_capacity_rejects_overloading_a_vehicle():
    here = StorageLocation(kind="vehicle", id="v1")
    cat = DATA.items["cart"]
    spec = _spec(vehicles=[VehicleInstance(instance_id="v1", catalog_id="cart",
                                           hull_max=1)])
    over = cat.cargo_capacity_cn + 1
    with pytest.raises(storage.StorageError):
        storage._check_capacity(spec, here, over, DATA)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_helpers.py -v -k "overloading or mule_cap"`
Expected: FAIL — animal/vehicle branch returns None (no raise).

- [ ] **Step 3: Implement the animal/vehicle branch**

Replace the trailing comment `# animal / vehicle handled in Task 4` in `_check_capacity` with:

```python
    if dest.kind == "animal":
        from aose.engine.companions import animal_capacity
        animal = _carrier(spec, "animal", dest.id)
        cap = animal_capacity(animal, data)   # max_load_encumbered_cn or None
        worn = (data.items[animal.armor_id].weight_cn
                if animal.armor_id and animal.armor_id in data.items else 0)
        current = worn + location_load_cn(spec, dest, data)
        if cap is None or current + added_cn > cap:
            name = data.items[animal.catalog_id].name if animal.catalog_id in data.items else dest.id
            raise StorageError(f"{name} cannot carry that much "
                               f"({current}/{cap if cap is not None else 0} cn)")
        return
    if dest.kind == "vehicle":
        from aose.engine.companions import vehicle_capacity
        vehicle = _carrier(spec, "vehicle", dest.id)
        cap = vehicle_capacity(vehicle, data)
        current = location_load_cn(spec, dest, data)
        if current + added_cn > cap:
            name = data.items[vehicle.catalog_id].name if vehicle.catalog_id in data.items else dest.id
            raise StorageError(f"{name} is over capacity ({current}/{cap} cn)")
        return
    raise StorageError(f"no capacity rule for destination {dest.kind!r}")
```

(`animal_capacity` and `vehicle_capacity` already exist in `companions.py`; importing
them here is one-directional — `companions` does not import `storage`, so no cycle.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_helpers.py -v -k check_capacity`
Expected: PASS (all six).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/storage.py tests/test_storage_helpers.py
git commit -m "feat(storage): _check_capacity for animals + vehicles"
```

---

### Task 5: `move_item` auto-unequips the last carried copy

**Files:**
- Modify: `aose/engine/storage.py` (`move_item`)
- Test: `tests/test_storage_move_thing.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_storage_move_thing.py`:

```python
def test_moving_last_copy_of_equipped_item_unequips_it():
    spec = _spec(inventory=["sword"], equipped={"main_hand": "sword"})
    storage.move_item(spec, "sword", CARRIED, STASHED)
    assert "main_hand" not in spec.equipped
    assert spec.stashed == ["sword"]


def test_moving_one_of_two_copies_keeps_the_equipped_one():
    spec = _spec(inventory=["sword", "sword"], equipped={"main_hand": "sword"})
    storage.move_item(spec, "sword", CARRIED, STASHED)
    assert spec.equipped.get("main_hand") == "sword"   # a carried copy remains
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py -v -k "unequips_it or two_copies"`
Expected: FAIL — first test fails (slot still present).

- [ ] **Step 3: Implement auto-unequip in `move_item`**

Replace the body of `move_item` in `aose/engine/storage.py` with:

```python
def move_item(spec: CharacterSpec, item_id: str,
              src: StorageLocation, dest: StorageLocation) -> None:
    """Move one copy of ``item_id`` from ``src``'s loose list to ``dest``'s.
    If the moved copy was the last carried copy occupying an equipped slot,
    free that slot (and unload any ammo keyed to it)."""
    src_list = loose_list(spec, src)
    if item_id not in src_list:
        raise StorageError(f"{item_id!r} not at {src.kind}")
    dest_list = loose_list(spec, dest)
    src_list.remove(item_id)
    dest_list.append(item_id)
    # If no carried copy remains, free any equipped slot pointing at it.
    if src.kind == "carried" and spec.inventory.count(item_id) == 0:
        for slot, iid in list(spec.equipped.items()):
            if iid == item_id:
                del spec.equipped[slot]
                unload_if_loaded(spec, item_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py -v -k "unequips_it or two_copies"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/storage.py tests/test_storage_move_thing.py
git commit -m "feat(storage): move_item frees the slot of a moved-away equipped item"
```

---

### Task 6: `move_spell_source` + `source` category in `move_thing`

**Files:**
- Modify: `aose/engine/storage.py`
- Test: `tests/test_storage_move_thing.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_storage_move_thing.py`:

```python
from aose.models import SpellSource, SpellSourceEntry, Retainer


def _scroll(iid="s1", loc=None):
    return SpellSource(instance_id=iid, kind="scroll", caster_type="arcane",
                       entries=[SpellSourceEntry(spell_id="magic_missile")],
                       location=loc or CARRIED)


def test_move_spell_source_repoints_location_same_world():
    spec = _spec(spell_sources=[_scroll()])
    storage.move_thing(spec, "source", "s1", STASHED, data=DATA)
    assert spec.spell_sources[0].location == STASHED


def test_move_spell_source_to_container():
    spec = _spec(
        spell_sources=[_scroll()],
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=CARRIED)],
    )
    dest = StorageLocation(kind="container", id="c1")
    storage.move_thing(spec, "source", "s1", dest, data=DATA)
    assert spec.spell_sources[0].location == dest
```

(`magic_missile` is a real spell id; adjust if the data dir uses another — pick any
arcane spell present in `DATA.spells`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py -v -k move_spell_source`
Expected: FAIL — `move_thing` raises `unknown move category 'source'`.

- [ ] **Step 3: Implement `move_spell_source` and register the category**

In `aose/engine/storage.py`, add:

```python
def _find_spell_source(spec: CharacterSpec, instance_id: str):
    """Return (owner_spec, list, src) for a spell source in the PC world or any
    retainer world."""
    for s in spec.spell_sources:
        if s.instance_id == instance_id:
            return spec, spec.spell_sources, s
    for r in spec.retainers:
        for s in r.spec.spell_sources:
            if s.instance_id == instance_id:
                return r.spec, r.spec.spell_sources, s
    raise StorageError(f"no spell source {instance_id!r}")


def move_spell_source(spec: CharacterSpec, instance_id: str,
                      dest: StorageLocation, data) -> None:
    """Move a spell book / scroll to ``dest``. Same world → re-point location;
    cross world (PC↔retainer) → list-to-list into retainer.spec.spell_sources."""
    if dest.kind in ("animal", "vehicle"):
        _carrier(spec, dest.kind, dest.id)
    if dest.kind == "container":
        _container(spec, dest.id)
    owner_spec, src_list, src = _find_spell_source(spec, instance_id)
    added = 1 if src.kind == "scroll" else 0
    _check_capacity(spec, dest, added, data)
    dest_world = _retainer(spec, dest.id).spec if dest.kind == "retainer" else spec
    if dest_world is owner_spec:
        src.location = dest
    else:
        src_list.remove(src)
        new_loc = (StorageLocation(kind="carried")
                   if dest.kind == "retainer" else dest)
        dest_world.spell_sources.append(src.model_copy(update={"location": new_loc}))
```

In `move_thing`, add a branch before the final `else`:

```python
    elif category == "source":
        move_spell_source(spec, ref_id, dest, data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py -v -k move_spell_source`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/storage.py tests/test_storage_move_thing.py
git commit -m "feat(storage): move_spell_source + 'source' move category"
```

---

### Task 7: Wire the capacity gate into the remaining move functions

**Files:**
- Modify: `aose/engine/storage.py` (`move_item`, `move_coins`, `move_valuable`, `move_ammo`, `move_instance`, `move_container`)
- Test: `tests/test_storage_move_thing.py`

The gate must run before each commit so **every** category respects caps. Each call
computes the per-move `added_cn`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_storage_move_thing.py`:

```python
def test_move_thing_item_into_full_container_rejected():
    spec = _spec(
        inventory=["sword"],
        containers=[ContainerInstance(instance_id="p1", catalog_id="belt_pouch",
                                      location=CARRIED)],   # cap 50; sword 60
    )
    dest = StorageLocation(kind="container", id="p1")
    import pytest
    with pytest.raises(storage.StorageError):
        storage.move_thing(spec, "item", "sword", dest, src=CARRIED, data=DATA)
    assert spec.inventory == ["sword"]   # unchanged on rejection


def test_move_thing_coins_onto_retainer_never_blocked():
    from aose.models import CoinStack, Retainer
    ret_spec = _spec(name="Hench")
    spec = _spec(coins=[CoinStack(denom="gp", count=500, location=CARRIED)],
                 retainers=[Retainer(id="r1", spec=ret_spec, loyalty=7, role="torchbearer")])
    dest = StorageLocation(kind="retainer", id="r1")
    storage.move_thing(spec, "coin", "gp", dest, count=500, src=CARRIED, data=DATA)
    # accepted; coins now on the retainer
    assert any(c.location == dest and c.count == 500 for c in spec.coins)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py -v -k "full_container_rejected or never_blocked"`
Expected: FAIL — the item move into the pouch currently succeeds (no gate).

- [ ] **Step 3: Add gate calls in each move function**

In `aose/engine/storage.py`:

`move_item` — after computing `dest_list` and **before** `src_list.remove`:

```python
    item = data.items.get(item_id) if data is not None else None
    added = item.weight_cn if item is not None else 0
    _check_capacity(spec, dest, added, data)
```

(Note: `move_item` gains a `data` param — change its signature to
`def move_item(spec, item_id, src, dest, data=None)` and pass `data` from
`move_thing`'s `item` branch.)

`move_coins` — after the `count <= 0` check, before `_take_coins`:

```python
    _check_capacity(spec, dest, count, data)
```

(Add `data` param to `move_coins`; pass it through from `move_thing`. `data` may be
`None` for carried/stashed/retainer dests, which the gate returns early for — but
container/animal/vehicle dests always supply `data` from the route.)

`move_valuable` — compute the added weight per branch: for a gem move add `n` (1 cn
each); for jewellery add `10`. Insert `_check_capacity(spec, dest, n, data)` for the
gem branch (after computing `n`, before mutating) and `_check_capacity(spec, dest, 10, data)`
for the jewellery branch. Add a `data` param.

`move_ammo` — ammo is 0 cn; still call `_check_capacity(spec, dest, 0, data)` for
symmetry (it will pass). Add a `data` param.

`move_instance` — compute the instance's resolved weight and gate before relocating:

```python
    added = _instance_weight(inst, kind, data)
    _check_capacity(spec, dest, added, data)
```

with a small helper:

```python
def _instance_weight(inst, kind, data) -> int:
    from aose.engine.encumbrance import treasure_item_weight
    from aose.engine.enchant import resolve_instance
    from aose.models import Armor, Weapon
    if kind == "magic":
        item = data.items.get(getattr(inst, "catalog_id", None))
        return (treasure_item_weight(item) or item.weight_cn) if item else 0
    resolved = resolve_instance(inst, data)
    if isinstance(resolved, Armor):
        return int(resolved.weight_cn * resolved.weight_multiplier)
    if isinstance(resolved, Weapon):
        return resolved.weight_cn
    return 0
```

`move_container` — a container itself has weight + scaled contents, but containers
may only move to carried/stashed/animal/vehicle (never into another container) and
animal/vehicle caps for a whole container are an edge case; gate with the container's
own catalog `weight_cn`:

```python
    cat = data.items.get(c.catalog_id) if data is not None else None
    added = cat.weight_cn if cat is not None else 0
    _check_capacity(spec, dest, added, data)
```

Then update `move_thing` to pass `data` into `move_item`, `move_coins`,
`move_valuable`, `move_ammo` (it already passes nothing today — thread `data`
through). `move_container` and `move_instance` already receive `spec` and can take
`data`; update their `move_thing` call sites to pass `data`.

- [ ] **Step 4: Run the full move-thing + helpers suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py tests/test_storage_helpers.py -v`
Expected: PASS, including the two new tests. Fix any call-site signature mismatches
the run surfaces.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/storage.py tests/test_storage_move_thing.py
git commit -m "feat(storage): enforce capacity on every move category"
```

---

## Phase 2 — Casting gate

### Task 8: A non-carried document cannot be cast / deciphered / copied

**Files:**
- Modify: `aose/engine/spell_sources.py`
- Test: `tests/test_spell_sources.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_spell_sources.py` (reuse the module's existing fixtures; adapt the
`spec`/`data` builders already present there):

```python
def test_scroll_not_carried_is_not_castable(arcane_caster_spec, data):
    # arcane_caster_spec: a spec with an arcane class; build a usable, unlocked scroll
    from aose.models import SpellSource, SpellSourceEntry
    from aose.models.storage import StorageLocation
    spell_id = next(iter(data.spells))
    scroll = SpellSource(instance_id="s1", kind="scroll", caster_type="arcane",
                         unlocked=True, location=StorageLocation(kind="stashed"),
                         entries=[SpellSourceEntry(spell_id=spell_id)])
    from aose.engine import spell_sources as ss
    assert ss.can_cast_scroll(scroll, arcane_caster_spec, data) is False
    assert "person" in ss.scroll_cast_block_reason(scroll, arcane_caster_spec, data)
```

If `test_spell_sources.py` has no shared `arcane_caster_spec`/`data` fixtures, build
the spec inline the way the existing tests in that file do (match their style), and
place a carried unlocked arcane scroll alongside to assert it *is* castable.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources.py -v -k not_carried`
Expected: FAIL — a stashed scroll is currently castable.

- [ ] **Step 3: Add the carried gate**

In `aose/engine/spell_sources.py`, at the **top** of `scroll_cast_block_reason`
(before the `kind != "scroll"` check):

```python
    if source.location.kind != "carried":
        return "not on your person"
```

In `read_scroll`, after fetching `src` (before the kind/unlocked checks):

```python
    if src.location.kind != "carried":
        raise SpellSourceError("you must be carrying the scroll to read it")
```

In `copyable_spell_ids`, return an empty set when the source is not carried — add at
the top:

```python
    if source.location.kind != "carried":
        return set()
```

(`copy_spell` already rejects spells not in `copyable_spell_ids`, so it inherits the
gate.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources.py tests/test_spell_sources_view.py -v`
Expected: PASS. Existing tests that build scrolls without a `location` still pass
(default carried).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/spell_sources.py tests/test_spell_sources.py
git commit -m "feat(spell-sources): cast/decipher/copy require the document be carried"
```

---

## Phase 3 — Encumbrance refactor

### Task 9: Encumbrance container loop calls `location_load_cn`

**Files:**
- Modify: `aose/engine/encumbrance.py:172-201`
- Test: `tests/test_encumbrance.py`

- [ ] **Step 1: Write the failing (characterization) test**

Add to `tests/test_encumbrance.py`:

```python
def test_carried_container_weight_uses_location_load_cn():
    from aose.engine import storage
    from aose.models import CharacterSpec, ClassEntry, ContainerInstance, CoinStack
    from aose.models.storage import StorageLocation
    here = StorageLocation(kind="container", id="c1")
    spec = CharacterSpec(
        name="E", abilities={"STR":10,"INT":10,"WIS":10,"DEX":10,"CON":10,"CHA":10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=StorageLocation(kind="carried"),
                                      contents=["sword"])],
        coins=[CoinStack(denom="gp", count=10, location=here)],
    )
    raw = storage.location_load_cn(spec, here, DATA)
    cat = DATA.items["backpack"]
    expected_contribution = cat.weight_cn + int(cat.weight_multiplier * raw)
    # equipment_weight_cn includes this container contribution
    assert equipment_weight_cn(spec, DATA) >= expected_contribution
```

(`DATA` and `equipment_weight_cn` are already imported in `test_encumbrance.py`; if
not, import them at the top.)

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py::test_carried_container_weight_uses_location_load_cn -v`
Expected: likely PASS already (this characterizes current behavior) — that's fine; it
guards the refactor. If it fails, the current inline sum diverges from
`location_load_cn`; reconcile before refactoring.

- [ ] **Step 3: Refactor the container loop**

In `aose/engine/encumbrance.py`, replace the body of the
`for c in spec.containers:` loop (the block computing `raw` from contents + coins +
gems + jewellery + magic + enchanted) with a call to the shared helper:

```python
    from aose.engine.storage import location_load_cn
    for c in spec.containers:
        if c.location.kind != "carried":
            continue
        catalog = data.items.get(c.catalog_id)
        if not isinstance(catalog, _Container):
            continue
        here = StorageLocation(kind="container", id=c.instance_id)
        raw = location_load_cn(spec, here, data)
        total += catalog.weight_cn + int(catalog.weight_multiplier * raw)
```

Remove the now-dead inline per-substrate summation for the container loop. Keep the
`has_gear`/flat-80 logic and the non-container passes intact.

Note the import direction: `encumbrance` importing `storage` is new. `storage`
imports `encumbrance` lazily *inside functions* (`treasure_item_weight`), and
`encumbrance` will import `location_load_cn` lazily inside this function too — keep
both lazy (function-local) to avoid a module-load cycle.

- [ ] **Step 4: Run the encumbrance suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py -v`
Expected: PASS (all existing + new). If a number shifts, the old inline sum and
`location_load_cn` disagreed — investigate which is correct (spell sources stowed in
a container now count 1 cn each, which the old loop omitted; that is the intended
fix, so update any stale expected value).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/encumbrance.py tests/test_encumbrance.py
git commit -m "refactor(encumbrance): container load via shared location_load_cn"
```

---

## Phase 4 — View

### Task 10: Fix the equipped-weapon double-render

**Files:**
- Modify: `aose/sheet/view.py:718-723` (`_equipped`)
- Test: `tests/test_sheet_inventory_box.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_sheet_inventory_box.py`:

```python
def test_wielded_weapon_not_in_equipped_worn():
    from aose.sheet.view import build_inventory_groups
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="W", abilities={"STR":12,"INT":10,"WIS":10,"DEX":10,"CON":10,"CHA":10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral", inventory=["sword"], equipped={"main_hand": "sword"},
    )
    groups = build_inventory_groups(spec, DATA)
    pc = next(g for g in groups if g.kind == "carried")
    worn_slots = {e.slot for e in pc.equipped_worn}
    assert "main_hand" not in worn_slots and "off_hand" not in worn_slots
    # the weapon still appears as an attack profile
    assert any(a.name.lower().startswith("sword") for a in pc.equipped_attacks)
```

(`DATA` is loaded at the top of `test_sheet_inventory_box.py`; if not, add
`DATA = GameData.load(Path("data"))`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py -v -k double` (use `-k worn`)
Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py::test_wielded_weapon_not_in_equipped_worn -v`
Expected: FAIL — `main_hand` currently appears in `equipped_worn`.

- [ ] **Step 3: Skip weapon slots in `_equipped`**

Replace `_equipped` in `aose/sheet/view.py`:

```python
_WEAPON_SLOTS = {"main_hand", "off_hand"}


def _equipped(spec: CharacterSpec, data: GameData) -> list[EquippedRow]:
    """Worn items (armour / shield / barding) only. Weapon slots render as
    attack profiles, not as worn rows — including them double-renders the weapon."""
    rows: list[EquippedRow] = []
    for slot, item_id in spec.equipped.items():
        if slot in _WEAPON_SLOTS:
            continue
        name = data.items[item_id].name if item_id in data.items else item_id
        rows.append(EquippedRow(slot=slot, item_name=name, item_id=item_id))
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py -v`
Expected: PASS. If an existing test asserted a weapon in `equipped_worn`, update it —
that was asserting the bug.

- [ ] **Step 5: Commit**

```bash
git add aose/sheet/view.py tests/test_sheet_inventory_box.py
git commit -m "fix(sheet): wielded weapons render once (attack profile, not worn row)"
```

---

### Task 11: Bucket spell sources by location + `ContainerView.stowed_spell_sources`

**Files:**
- Modify: `aose/sheet/view.py` (`build_inventory_groups`, `_container_views_from`), `aose/engine/shop.py` (`ContainerView` model)
- Test: `tests/test_sheet_inventory_box.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_sheet_inventory_box.py`:

```python
def test_spell_source_buckets_under_its_location():
    from aose.sheet.view import build_inventory_groups
    from aose.models import (CharacterSpec, ClassEntry, SpellSource,
                             SpellSourceEntry, AnimalInstance)
    from aose.models.storage import StorageLocation
    spell_id = next(iter(DATA.spells))
    on_mule = StorageLocation(kind="animal", id="m1")
    spec = CharacterSpec(
        name="S", abilities={"STR":10,"INT":10,"WIS":10,"DEX":10,"CON":10,"CHA":10},
        race_id="human", classes=[ClassEntry(class_id="magic_user", level=1, hp_rolls=[4])],
        alignment="neutral",
        animals=[AnimalInstance(instance_id="m1", catalog_id="mule")],
        spell_sources=[SpellSource(instance_id="s1", kind="scroll", caster_type="arcane",
                                   location=on_mule,
                                   entries=[SpellSourceEntry(spell_id=spell_id)])],
    )
    groups = build_inventory_groups(spec, DATA)
    carried = next(g for g in groups if g.kind == "carried")
    mule = next(g for g in groups if g.kind == "animal" and g.id == "m1")
    assert not carried.spell_sources
    assert any(s.instance_id == "s1" for s in mule.spell_sources)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py::test_spell_source_buckets_under_its_location -v`
Expected: FAIL — spell sources are hard-wired to the carried group.

- [ ] **Step 3a: Add `stowed_spell_sources` to `ContainerView`**

In `aose/engine/shop.py`, `class ContainerView`, add beside the other `stowed_*`:

```python
    stowed_spell_sources: list = Field(default_factory=list)   # SpellSourceView
```

- [ ] **Step 3b: Add a location-filtered spell-source view helper**

In `aose/sheet/view.py`, refactor `spell_sources_view` to accept an optional location
filter, OR add a thin wrapper. Simplest: add a parameter to the existing builder
loop. Replace the `for source in spec.spell_sources:` iteration so it can be filtered:

```python
def spell_sources_view(spec: CharacterSpec, data: GameData,
                       location: "StorageLocation | None" = None) -> list[SpellSourceView]:
    ...
    for source in spec.spell_sources:
        if location is not None and source.location != location:
            continue
        ...
```

(Add the `location` param to the signature and the single guard at the top of the
loop; everything else is unchanged.)

- [ ] **Step 3c: Bucket per group in `build_inventory_groups`**

In `aose/sheet/view.py`:
- Carried group: change `pc_spell_sources = spell_sources_view(spec, data)` to
  `spell_sources_view(spec, data, carried_loc)`.
- Stashed group: add `spell_sources=spell_sources_view(spec, data, stashed_loc)`.
- Animal/vehicle groups: add `spell_sources=spell_sources_view(spec, data, <carrier_loc>)`
  where `<carrier_loc> = StorageLocation(kind="animal"/"vehicle", id=instance_id)`.
- Retainer groups: retainers keep their own world — use the retainer's own spec:
  `spell_sources=spell_sources_view(r.spec, data, StorageLocation(kind="carried"))`
  (mirrors how retainer magic items are surfaced).
- In `_container_views_from`, add
  `stowed_spell_sources=spell_sources_view(spec, data, here)` to each `ContainerView(...)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py tests/test_spell_sources_view.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/sheet/view.py aose/engine/shop.py tests/test_sheet_inventory_box.py
git commit -m "feat(sheet): bucket spell sources by location; stowed_spell_sources on containers"
```

---

## Phase 5 — Delete the redundant movement families

### Task 12: Delete companions load/unload mutators + their routes

**Files:**
- Modify: `aose/engine/companions.py` (delete 4 functions; keep the capacity/load helpers)
- Modify: `aose/web/routes.py` (delete `/animal/{id}/load`, `/animal/{id}/unload`, `/vehicle/{id}/load`, `/vehicle/{id}/unload`)
- Modify: `tests/test_companions_load.py`

- [ ] **Step 1: Re-point the companions tests onto `move_thing`**

In `tests/test_companions_load.py`, replace assertions that call
`load_onto_animal`/`unload_from_animal`/`load_onto_vehicle`/`unload_from_vehicle`
with `storage.move_thing(spec, "item", item_id, dest, src=CARRIED, data=DATA)` and its
reverse, asserting the same end states (item on/off the carrier, overload rejected).
Keep tests for `animal_capacity`/`animal_load_cn`/`vehicle_capacity`/`vehicle_load_cn`
unchanged.

- [ ] **Step 2: Run to verify the rewritten tests fail against the not-yet-deleted code**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companions_load.py -v`
Expected: the rewritten move-based tests should already PASS (the engine is in place
from Phase 1); the goal of this step is to confirm `move_thing` covers the behavior
before deleting the old functions.

- [ ] **Step 3: Delete the four mutators and the four routes**

- In `aose/engine/companions.py`, delete `load_onto_animal`, `unload_from_animal`,
  `load_onto_vehicle`, `unload_from_vehicle`. Keep `animal_capacity`, `animal_load_cn`,
  `vehicle_capacity`, `vehicle_load_cn`, `_items_weight`, `_find_animal`, `_find_vehicle`.
- In `aose/web/routes.py`, delete the route functions at
  `/character/{character_id}/animal/{instance_id}/load`,
  `.../animal/{instance_id}/unload`, `.../vehicle/{instance_id}/load`,
  `.../vehicle/{instance_id}/unload`. Remove the now-unused
  `companions_engine.load_onto_animal` etc. references.

- [ ] **Step 4: Run the companions + route suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companions_load.py tests/test_companion_routes.py -v`
Expected: PASS. Fix any import of a deleted symbol.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/companions.py aose/web/routes.py tests/test_companions_load.py
git commit -m "refactor: carrier load/unload goes through move_thing; delete companions mutators"
```

---

### Task 13: Delete shop stash/stow/take_out/*_container + their PC routes

**Files:**
- Modify: `aose/engine/shop.py` (delete `stash`, `unstash`, `stow`, `take_out`, `stash_container`, `unstash_container`, `_set_container_state`)
- Modify: `aose/web/routes.py` (delete `/equipment/stash`, `/unstash`, `/stow`, `/take-out`, `/stash-container`, `/unstash-container` and the corresponding imports)
- Modify: `tests/` (re-point any test calling these onto `move_thing`)

- [ ] **Step 1: Grep every call site**

Run:
```bash
grep -rnE "shop_stow|shop_take_out|shop_stash|shop_unstash|stash_container|unstash_container|\.stow\(|\.take_out\(|_set_container_state|/equipment/stash|/equipment/unstash|/equipment/stow|/equipment/take-out|/equipment/stash-container|/equipment/unstash-container" aose tests
```
List every hit; each must be migrated or deleted in this task.

- [ ] **Step 2: Re-point tests onto `move_thing`**

For each test calling `stash`/`unstash`/`stow`/`take_out`/`stash_container`/
`unstash_container`, rewrite to `storage.move_thing(...)` with the equivalent
src/dest (carried↔stashed for stash/unstash; carried↔container for stow/take-out;
`move_thing(spec, "container", id, dest)` for stash/unstash-container). Assert the
same end state. Run them to confirm they pass against the still-present engine
(`move_thing` already does this).

- [ ] **Step 3: Delete the engine functions and routes**

- `aose/engine/shop.py`: delete `stash`, `unstash`, `stow`, `take_out`,
  `stash_container`, `unstash_container`, `_set_container_state`.
- `aose/web/routes.py`: delete the six route handlers and their `shop_*` imports
  (`stash as shop_stash`, `unstash as shop_unstash`, `stow as shop_stow`,
  `take_out as shop_take_out`, `stash_container as shop_stash_container`,
  `unstash_container as shop_unstash_container`). Keep `sell_*`/`remove_*`/`buy_*`
  imports.

- [ ] **Step 4: Run the broad suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py tests/test_inventory_move_routes.py tests/test_storage.py -v`
Expected: PASS. Fix any dangling import of a deleted symbol (`ImportError` at
collection time points right at it).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/shop.py aose/web/routes.py tests
git commit -m "refactor: stash/stow/take-out go through move_thing; delete shop helpers + routes"
```

---

### Task 14: Delete the wizard's redundant routes + persist spell_sources

**Files:**
- Modify: `aose/web/wizard.py` (delete `stash`, `unstash`, `stow`, `take-out`, `stash-container`, `unstash-container`; add `spell_sources` to the `/inventory/move` draft persistence)
- Test: `tests/test_inventory_move_routes.py` (wizard cases)

- [ ] **Step 1: Grep wizard call sites**

Run:
```bash
grep -nE "shop_stow|shop_take_out|shop_stash|shop_unstash|stash_container|unstash_container|/equipment/stash|/equipment/unstash|/equipment/stow|/equipment/take-out|/equipment/stash-container|/equipment/unstash-container|inventory/move" aose/web/wizard.py
```

- [ ] **Step 2: Add `spell_sources` to the wizard move persistence + write a failing test**

In `aose/web/wizard.py`, the `wiz_inventory_move` handler's `draft.update({...})`
(around line 1959) omits `spell_sources`. Add:

```python
        "spell_sources": [s.model_dump() for s in spec.spell_sources],
```

Add a wizard test in `tests/test_inventory_move_routes.py` asserting that POSTing
`category=source` (when a draft carries a spell source) persists the new location —
or, if drafts never carry spell sources in practice, a lighter test asserting the
deleted routes 404 (next step). Prefer the 404 test if spell-source creation isn't
reachable in the wizard.

- [ ] **Step 3: Delete the six wizard routes**

Delete the wizard handlers for `/{draft_id}/equipment/stash`, `/unstash`, `/stow`,
`/take-out`, `/stash-container`, `/unstash-container`, and remove their `shop_*`
imports from `wizard.py`. Add a test asserting e.g.
`client.post("/wizard/<draft>/equipment/stow", ...)` returns 404.

- [ ] **Step 4: Run the route suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_move_routes.py -v`
Expected: PASS, including the new 404 assertions.

- [ ] **Step 5: Commit**

```bash
git add aose/web/wizard.py tests/test_inventory_move_routes.py
git commit -m "refactor(wizard): delete redundant move routes; persist spell_sources on move"
```

---

## Phase 6 — Templates: shared controls

### Task 15: Stash / Unstash / Take-out buttons → `act_move`

**Files:**
- Modify: `aose/web/templates/_inv_row_actions.html`
- Test: manual via the running app + `tests/test_inventory_move_routes.py` already green

- [ ] **Step 1: Replace the typed Stash/Unstash/Take-out forms**

In `_inv_row_actions.html`:
- `state == "stashed"` branch: replace the `/unstash` form with an `act_move`
  targeting `carried`:
  ```jinja
  {{ act_move(inv_move_url, {"category": "item", "id": row.id}, move_targets, state, src_id) }}
  ```
  (the generic Move ▾ already lists Carried as a destination — the dedicated
  "Unstash" button becomes redundant; remove it).
- `state == "container"` branch: replace the `/take-out` form similarly — the Move ▾
  already lists the container's owner location. Remove the dedicated "Take out" form.
- The generic `act_move` block lower in the macro already covers carried→stashed
  ("Stash" = pick Stashed in Move ▾), so the standalone Stash button (if any) is
  removed.

Keep Equip / Off-hand / Unequip and the Drop/Sell block unchanged.

- [ ] **Step 2: Verify the page renders**

Start the app:
`.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
Open a character sheet; confirm loose/stashed/container rows still expose Move ▾ to
every destination and no longer 500 (the deleted routes are no longer referenced).

- [ ] **Step 3: Run the web suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_move_routes.py tests/test_sheet_inventory_box.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add aose/web/templates/_inv_row_actions.html
git commit -m "feat(ui): stash/unstash/take-out via the shared Move control"
```

---

### Task 16: Carrier / container Stow / Load → `act_move`; container modal unchanged routes

**Files:**
- Modify: `aose/web/templates/_inv_modals.html`, `aose/web/templates/_companions.html` (if it holds Load buttons), `aose/web/templates/sheet.html`
- Test: manual + route suite

- [ ] **Step 1: Grep templates for the deleted routes**

Run:
```bash
grep -rnE "equipment/stow|equipment/take-out|equipment/stash\b|equipment/unstash\b|equipment/stash-container|equipment/unstash-container|/animal/[^\"]*/load|/animal/[^\"]*/unload|/vehicle/[^\"]*/load|/vehicle/[^\"]*/unload" aose/web/templates
```
Every hit is a button that must become an `act_move` (or be removed because Move ▾
already covers it).

- [ ] **Step 2: Replace each with `act_move`**

For animal/vehicle Load buttons, render the item's Move ▾ with the carrier as a
destination (already in `move_targets`); delete the dedicated Load/Unload forms. For
container Stow, the loose-row Move ▾ already lists the container. Remove the bespoke
forms. Keep `stash-container`/`unstash-container` as Move ▾ on the container modal
(category `container`, dest carried/stashed) — the container modal already has an
`act_move` for containers (`_inv_modals.html` `container_modal`); ensure it lists
carried + stashed and drop any leftover stash-container button.

- [ ] **Step 3: Verify rendering + routes**

Restart the app; load a character with an animal and a container; confirm loading a
mule and stowing in a sack both work through Move ▾ and that an over-capacity move
shows the 400 (FastAPI error) rather than silently succeeding.

- [ ] **Step 4: Run the suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companion_routes.py tests/test_inventory_move_routes.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/templates
git commit -m "feat(ui): carrier load + container stow via the shared Move control"
```

---

### Task 17: Magic / enchanted / spell-source removal onto shared controls

**Files:**
- Modify: `aose/web/templates/sheet.html` (magic/enchanted modal block ~996-1051; spell-source modal ~1105-1150), `aose/web/templates/_inv_pane.html` (spell-source rows), possibly `aose/web/templates/_actions.html` (a shared `act_sell` if not present)
- Modify: `aose/web/routes.py` (extend `remove-enchanted`? No — enchanted stays Drop-only) and confirm `remove-magic` mode plumbing
- Test: manual + route suite

- [ ] **Step 1: Magic modal — Drop + Sell ▾**

In `sheet.html`, the unequipped-magic branch (currently a single "Remove" button →
`remove-magic`): replace with the shared controls:
- **Move ▾** (already present — keep).
- **Drop**: a form posting `remove-magic` with `mode=drop` (button label "Drop",
  `class="btn btn-inline danger"`).
- **Sell ▾**: a `<select class="sell-dest">` posting `remove-magic` with
  `mode=sell|refund` — mirror the loose-item Sell ▾ in `_inv_row_actions.html`. Only
  render Sell ▾ when the magic item has a positive catalog `cost_gp`
  (`mi.cost_gp > 0`); add `cost_gp` to `MagicItemView` if not already present (check
  `magic_items_view` in `view.py` — add the field there).

- [ ] **Step 2: Enchanted modal — Drop only**

Enchanted instances have no single catalog price; keep **Move ▾** + a single **Drop**
button posting `remove-enchanted` (relabel the existing "Remove" → "Drop", no mode,
no Sell).

- [ ] **Step 3: Spell-source modal — Move ▾ + Drop**

In the `modal-source-{{ src.instance_id }}` block, add a `row-actions` section:
- **Move ▾**: `{{ act_move("/character/" ~ character_id ~ "/inventory/move", {"category": "source", "id": src.instance_id}, move_targets, src_group_kind, src_group_id) }}`
  — the source modal currently iterates `sheet.spell_sources` (flat). Change the loop
  to iterate per group (like the magic modal at `sheet.html:994`) so each source has
  its `group.kind`/`group.id` for the Move source location; include container-stowed
  sources too.
- **Drop**: a form posting `/character/{{ character_id }}/spell-sources/remove` with
  `instance_id` (label "Drop", `class="btn btn-inline danger"`).

- [ ] **Step 4: Render spell sources by group in `_inv_pane.html`**

`_inv_pane.html` already renders `group.spell_sources` (it iterates them at the
"Spell sources" comment). Confirm it now shows them for every group (it will, since
groups are populated in Task 11) and add a `stowed_spell_sources` loop inside the
container block mirroring `stowed_magic`.

- [ ] **Step 5: Verify + run suites**

Restart the app; confirm: a carried scroll shows Move ▾ + Drop and its spells in the
cast list; a stashed scroll shows Move ▾ + Drop but its spells are **not** castable;
a magic item shows Drop + Sell ▾ (when priced); an enchanted item shows Drop only.

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources_view.py tests/test_sheet_inventory_box.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/web/templates aose/web/routes.py aose/sheet/view.py
git commit -m "feat(ui): magic Drop+Sell, enchanted/spell-source Drop, spell-source Move"
```

---

## Phase 7 — Docs + full verification

### Task 18: Full regression + docs

**Files:**
- Modify: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`
- Modify: `CLAUDE.md` only if a storage shape note changed (SpellSource now carries `location`)

- [ ] **Step 1: Run the whole suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all green (ignore the trailing `pytest-current` PermissionError). Fix any
failure before proceeding.

- [ ] **Step 2: Update `ARCHITECTURE.md` in place**

Edit the storage / encumbrance / spell-sources subsystem sections:
- Storage: `move_thing` now covers `source`; `_check_capacity` + `location_load_cn`
  are the single capacity/load definitions; carrier load + stash/stow go through the
  one front door (shop/companions movement helpers removed).
- Encumbrance: container load via `location_load_cn`.
- Spell sources: now carry `location`; cast/decipher/copy require carried-on-PC.

- [ ] **Step 3: Add the CHANGELOG row**

Prepend one dated row to `docs/CHANGELOG.md`:
`2026-06-23 | Finish movement consolidation (spell-source movement, capacity gate, equipped double-render fix, drop/sell unification) | feat/movement-consolidation-finish | movement-consolidation-finish`

- [ ] **Step 4: Update `CLAUDE.md` storage-shapes note**

In the Storage shapes section, add that `spell_sources: list[SpellSource]` now each
carry a `location: StorageLocation` (default Carried); scroll casting/decipher/copy
require the document be carried on the PC.

- [ ] **Step 5: Manual verification pass**

Start the app and verify end-to-end:
1. Wielded weapon shows once in Equipped.
2. A scroll can be moved to stash / a container / a mule / a retainer, and dropped.
3. A stashed scroll's spells are not castable; carried again, they are.
4. Magic item shows Drop + Sell; enchanted shows Drop; both move.
5. Moving an item into a full belt pouch / overloaded mule is rejected with a 400.
6. Moving onto a retainer is never blocked.

- [ ] **Step 6: Commit**

```bash
git add docs/ARCHITECTURE.md docs/CHANGELOG.md CLAUDE.md
git commit -m "docs: movement consolidation finish — architecture, changelog, claude.md"
```

---

## Self-Review notes (for the implementer)

- **Spec coverage:** spell-source movement (Tasks 1, 6, 11, 17); drop/sell unification
  (Task 17); double-render (Task 10); collapse shop+companions families (Tasks 12-14);
  central capacity gate incl. animals/vehicles/containers, retainer no-block (Tasks 3,
  4, 7); carried-on-PC casting gate (Task 8); encumbrance one-definition (Tasks 2, 9).
- **Ammo/load disambiguation:** `ammo/load` and `ammo/unload` (loading a *launcher*)
  are NOT carrier-load routes — do **not** delete them.
- **Cycle watch:** `encumbrance` ↔ `storage` cross-imports must stay function-local
  (lazy) on both sides.
- **`data` threading:** several `move_*` functions gain a `data` param in Task 7;
  update their `move_thing` call sites in the same task or the suite breaks.
