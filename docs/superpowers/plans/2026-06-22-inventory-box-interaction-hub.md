# Inventory Box as Interaction Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the live-sheet inventory box the single place to view and act on everything a character owns (every top-level inventory), reduce the Manage drawer to acquisition-only, and unify container handling across owners — absorbing the loose-backpack bug.

**Architecture:** A per-owner **capability descriptor** computed in `build_inventory_groups` drives one shared set of Jinja macros (rows + modals) used by the sheet box and the wizard. Container/promotion engine helpers are refactored to resolve the right `(containers, loose)` lists for any owner (PC/animal/vehicle via `spec.*` + `StorageLocation`; retainer via `retainer.spec.*`). The drawer keeps only acquisition forms.

**Tech Stack:** Python 3, FastAPI, Jinja2, Pydantic v2, YAML data, no JS framework. Tests via `pytest`. Run app with `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`. Run tests with `.venv\Scripts\python.exe -m pytest tests/ -q`.

**Spec:** `docs/superpowers/specs/2026-06-22-inventory-box-interaction-hub-design.md`

**Working conventions (read once):**
- All commands are PowerShell; the venv is **not** auto-activated — always invoke `.venv\Scripts\python.exe`.
- No migrations (app not deployed). Model validators that coerce legacy saves are courtesy only.
- The trailing `PermissionError` on `pytest-current` is a known Windows quirk — ignore it.
- Template/route tasks that change rendered UI: after editing, **verify via the preview tools** (preview_start → preview_snapshot/preview_screenshot), never by asking the user.
- Commit after every green task. Branch is `feat/inventory-box-interaction-hub` (already created).

---

## File Structure

**Engine (pure, cycle-free):**
- `aose/engine/storage.py` — add owner-resolution helpers + `use_as_container`; generalize container moves to cross-owner.
- `aose/engine/shop.py` — generalize `new_container_instance` to take a full `StorageLocation`; `_build_row` gains a `can_wield` input so retainer rows skip class filtering; container sell/refund credit to carried.
- `aose/engine/quick_equipment.py` — `apply_kit` routes `Container` ids into `spec.containers`.

**View models + assembly:**
- `aose/engine/shop.py` — extend `TopLevelGroup` with a capability descriptor + per-owner magic/enchanted/sources/ammo/treasure-aware fields; add `OwnerCaps`.
- `aose/sheet/view.py` — `build_inventory_groups`: populate caps, retainer containers, and the per-owner extra collections; factor `format_attack_rows` (shared PC/retainer).

**Templates (live sheet + wizard share these):**
- `aose/web/templates/_inv_pane.html` — three-subsection layout (Equipped · Coins · Carried/Stowed); name the PC pane; render every type into the Carried/Stowed bucket; inline equip.
- `aose/web/templates/_inv_modals.html` *(new)* — shared per-item modal macros for every type, keyed by `(owner, row)`.
- `aose/web/templates/sheet.html` — emit the shared modals over every group; drop legacy three-column box.
- `aose/web/templates/_equipment_ui.html` — strip to acquisition-only tabs (Shop · Enchant · Scribe · Treasure).
- `aose/web/templates/wizard/equipment.html` — render the box for the draft.

**Routes:**
- `aose/web/routes.py` — add `use-as-container`; generalize container move/sell across owners; ensure every box action has a route.
- `aose/web/wizard.py` — wire box actions for the draft (equip/stash/move/stow/take-out/use-as-container).

**Tests:**
- `tests/test_storage_engine.py`, `tests/test_containers.py`, `tests/test_quick_equipment_data.py`, `tests/test_sheet_inventory_box.py`, `tests/test_web.py`, `tests/test_inventory_move_routes.py`, plus new `tests/test_use_as_container.py`.

---

## Phase 1 — Engine + view foundation

### Task 1: `new_container_instance` accepts a full location

**Files:**
- Modify: `aose/engine/shop.py:343-363`
- Test: `tests/test_containers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_containers.py  (add near the other new_container_instance tests)
def test_new_container_instance_accepts_full_location():
    from aose.models.storage import StorageLocation
    from aose.engine.shop import new_container_instance
    fake = _fake_data()  # existing helper in this test module
    loc = StorageLocation(kind="animal", id="abc123")
    inst = new_container_instance("backpack", fake, location=loc)
    assert inst.location == loc
    assert inst.catalog_id == "backpack"
```

- [ ] **Step 2: Run it, expect FAIL**

Run: `.venv\Scripts\python.exe -m pytest tests/test_containers.py -k full_location -q`
Expected: FAIL (`new_container_instance() got an unexpected keyword argument 'location'`).

- [ ] **Step 3: Implement** — replace the signature/body of `new_container_instance`:

```python
def new_container_instance(catalog_id: str, data: GameData,
                           state: str = "carried",
                           location: "StorageLocation | None" = None) -> ContainerInstance:
    """Create a fresh ContainerInstance for the given catalog item.

    Validates that ``catalog_id`` is a Container. ``location`` (preferred) places
    it at any non-container location; the legacy ``state`` kwarg still works for
    person buckets.
    """
    item = data.items.get(catalog_id)
    if item is None:
        raise UnknownItem(f"No item with id {catalog_id!r}")
    if not isinstance(item, Container):
        raise ValueError(f"{catalog_id!r} is not a container")
    if location is None:
        location = StorageLocation(kind=state)  # type: ignore[arg-type]
    return ContainerInstance(
        instance_id=uuid.uuid4().hex,
        catalog_id=catalog_id,
        location=location,
        contents=[],
    )
```

(`StorageLocation` is already imported at the top of `shop.py`.)

- [ ] **Step 4: Run it, expect PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "container_instance" -q`
Expected: PASS (all existing + new).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/shop.py tests/test_containers.py
git commit -m "feat(shop): new_container_instance accepts a full StorageLocation"
```

---

### Task 2: Owner-resolution helpers in the storage engine

Add helpers that, given an owner `StorageLocation`, return the right containers collection and loose list — handling the retainer's nested spec.

**Files:**
- Modify: `aose/engine/storage.py` (add after `_container`, ~line 40)
- Test: `tests/test_storage_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storage_engine.py
def test_containers_collection_resolves_retainer_vs_spec():
    from aose.engine.storage import containers_collection
    from aose.models.storage import StorageLocation
    spec = _spec_with_retainer()  # see helper below
    pc = containers_collection(spec, StorageLocation(kind="carried"))
    assert pc is spec.containers
    rid = spec.retainers[0].id
    ret = containers_collection(spec, StorageLocation(kind="retainer", id=rid))
    assert ret is spec.retainers[0].spec.containers
```

Add this helper at the top of the test module if not present:

```python
def _spec_with_retainer():
    from aose.models import CharacterSpec, Retainer, Ability
    npc = CharacterSpec(name="Hench", abilities={a: 10 for a in Ability},
                        race_id="human", classes=[], alignment="neutral")
    pc = CharacterSpec(name="Boss", abilities={a: 10 for a in Ability},
                       race_id="human", classes=[], alignment="neutral")
    pc.retainers.append(Retainer(id="ret1", spec=npc, loyalty=7, role=""))
    return pc
```

- [ ] **Step 2: Run it, expect FAIL**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_engine.py -k containers_collection -q`
Expected: FAIL (`cannot import name 'containers_collection'`).

- [ ] **Step 3: Implement** in `aose/engine/storage.py`:

```python
def containers_collection(spec: CharacterSpec, owner: StorageLocation) -> list:
    """The ContainerInstance list that owns containers *at* ``owner``.

    Retainers keep self-contained storage (``retainer.spec.containers``); every
    other owner shares ``spec.containers`` (each entry's own ``location`` selects
    the bucket)."""
    if owner.kind == "retainer":
        return _retainer(spec, owner.id).spec.containers
    return spec.containers
```

- [ ] **Step 4: Run it, expect PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_engine.py -k containers_collection -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/storage.py tests/test_storage_engine.py
git commit -m "feat(storage): containers_collection resolver (retainer vs spec)"
```

---

### Task 3: `use_as_container` — promote a loose Container

**Files:**
- Modify: `aose/engine/storage.py`
- Test: `tests/test_use_as_container.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_use_as_container.py
import pytest
from aose.data.loader import GameData
from aose.engine.storage import use_as_container, StorageError
from aose.models.storage import StorageLocation

DATA = GameData.load("data")

def _pc():
    from aose.models import CharacterSpec, Ability
    return CharacterSpec(name="P", abilities={a: 10 for a in Ability},
                         race_id="human", classes=[], alignment="neutral")

def test_promotes_carried_backpack():
    spec = _pc(); spec.inventory.append("backpack")
    use_as_container(spec, StorageLocation(kind="carried"), "backpack", DATA)
    assert "backpack" not in spec.inventory
    assert len(spec.containers) == 1
    assert spec.containers[0].catalog_id == "backpack"
    assert spec.containers[0].location == StorageLocation(kind="carried")

def test_promotes_stashed_backpack_keeps_location():
    spec = _pc(); spec.stashed.append("backpack")
    use_as_container(spec, StorageLocation(kind="stashed"), "backpack", DATA)
    assert spec.containers[0].location == StorageLocation(kind="stashed")

def test_rejects_non_container():
    spec = _pc(); spec.inventory.append("torch")
    with pytest.raises(StorageError):
        use_as_container(spec, StorageLocation(kind="carried"), "torch", DATA)

def test_rejects_missing_item():
    spec = _pc()
    with pytest.raises(StorageError):
        use_as_container(spec, StorageLocation(kind="carried"), "backpack", DATA)

def test_rejects_promotion_inside_container():
    spec = _pc()
    with pytest.raises(StorageError):
        use_as_container(spec, StorageLocation(kind="container", id="x"),
                         "backpack", DATA)

def test_promotes_onto_retainer_spec():
    from aose.models import Retainer, CharacterSpec, Ability
    spec = _pc()
    npc = CharacterSpec(name="H", abilities={a: 10 for a in Ability},
                        race_id="human", classes=[], alignment="neutral")
    npc.inventory.append("backpack")
    spec.retainers.append(Retainer(id="r1", spec=npc, loyalty=7, role=""))
    use_as_container(spec, StorageLocation(kind="retainer", id="r1"), "backpack", DATA)
    assert "backpack" not in npc.inventory
    assert len(npc.containers) == 1
    assert npc.containers[0].location == StorageLocation(kind="carried")
```

- [ ] **Step 2: Run, expect FAIL**

Run: `.venv\Scripts\python.exe -m pytest tests/test_use_as_container.py -q`
Expected: FAIL (`cannot import name 'use_as_container'`).

- [ ] **Step 3: Implement** in `aose/engine/storage.py`:

```python
def use_as_container(spec: CharacterSpec, owner: StorageLocation,
                     item_id: str, data) -> None:
    """Promote one loose copy of a Container item at ``owner`` into a real
    ContainerInstance at that owner. No nesting (owner may not be a container)."""
    from aose.engine.shop import new_container_instance
    from aose.models import Container
    if owner.kind == "container":
        raise StorageError("take the item out of the container first")
    item = data.items.get(item_id)
    if not isinstance(item, Container):
        raise StorageError(f"{item_id!r} is not a container")
    loose = loose_list(spec, owner)
    if item_id not in loose:
        raise StorageError(f"{item_id!r} not at {owner.kind}")
    coll = containers_collection(spec, owner)
    loc = StorageLocation(kind="carried") if owner.kind == "retainer" else owner
    loose.remove(item_id)
    coll.append(new_container_instance(item_id, data, location=loc))
```

- [ ] **Step 4: Run, expect PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_use_as_container.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/storage.py tests/test_use_as_container.py
git commit -m "feat(storage): use_as_container promotes a loose Container to an instance"
```

---

### Task 4: Harden `apply_kit` — Containers become instances

**Files:**
- Modify: `aose/engine/quick_equipment.py:213-221`
- Test: `tests/test_quick_equipment_data.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_quick_equipment_data.py
def test_apply_kit_routes_containers_to_instances():
    from aose.data.loader import GameData
    from aose.engine.quick_equipment import QuickKit, apply_kit
    from aose.models import CharacterSpec, Ability, Container
    data = GameData.load("data")
    spec = CharacterSpec(name="K", abilities={a: 10 for a in Ability},
                         race_id="human", classes=[], alignment="neutral")
    kit = QuickKit(inventory=["backpack", "torch", "torch"])
    apply_kit(spec, kit)
    assert "backpack" not in spec.inventory            # promoted out of loose
    assert spec.inventory.count("torch") == 2          # non-containers stay
    assert [c.catalog_id for c in spec.containers] == ["backpack"]
    assert isinstance(data.items["backpack"], Container)  # guard the fixture id
```

- [ ] **Step 2: Run, expect FAIL**

Run: `.venv\Scripts\python.exe -m pytest tests/test_quick_equipment_data.py -k routes_containers -q`
Expected: FAIL (backpack still loose).

- [ ] **Step 3: Implement** — rewrite `apply_kit`:

```python
def apply_kit(spec: CharacterSpec, kit: QuickKit) -> None:
    """Write a rolled kit onto a CharacterSpec. Container items are promoted to
    ContainerInstances (carried) so granted gear is never a stuck loose string."""
    from aose.models import CoinStack, Container
    from aose.engine.shop import new_container_instance
    from aose.data.loader import _GAME_DATA_FOR_KIT  # see note
    loose: list[str] = []
    containers = list(spec.containers)
    for item_id in kit.inventory:
        item = _kit_data.items.get(item_id) if (_kit_data := getattr(apply_kit, "_data", None)) else None
        loose.append(item_id)
    spec.inventory = list(kit.inventory)
    spec.equipped = dict(kit.equipped)
    spec.ammo = list(kit.ammo)
    if kit.gold > 0:
        spec.coins = [CoinStack(denom="gp", count=kit.gold)]
```

> **Implementation note (resolve cleanly, do not ship the sketch above):** `apply_kit`
> currently has no `GameData` handle, so it cannot classify ids. Choose the
> simplest real fix: **change `apply_kit(spec, kit)` → `apply_kit(spec, kit, data)`**
> and update the single caller `aose/engine/retainers.py:89`
> (`quick_equipment.apply_kit(spec, kit, data)`). Then implement:

```python
def apply_kit(spec: CharacterSpec, kit: QuickKit, data: GameData) -> None:
    from aose.models import CoinStack, Container
    from aose.engine.shop import new_container_instance
    loose: list[str] = []
    new_containers: list = []
    for item_id in kit.inventory:
        item = data.items.get(item_id)
        if isinstance(item, Container):
            new_containers.append(new_container_instance(item_id, data))  # carried
        else:
            loose.append(item_id)
    spec.inventory = loose
    spec.equipped = dict(kit.equipped)
    spec.ammo = list(kit.ammo)
    spec.containers = [*spec.containers, *new_containers]
    if kit.gold > 0:
        spec.coins = [CoinStack(denom="gp", count=kit.gold)]
```

Update the test fixture call accordingly (`apply_kit(spec, kit, data)`).

- [ ] **Step 4: Run, expect PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_quick_equipment_data.py tests/test_retainer_xp.py tests/test_companion_instances.py -q`
Expected: PASS (kit + retainer generation still green).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/quick_equipment.py aose/engine/retainers.py tests/test_quick_equipment_data.py
git commit -m "feat(quick-equipment): grant containers as instances, not loose strings"
```

---

### Task 5: Generalize container move + sell across owners

`move_container` (storage.py) and `sell_container`/`remove_container` (shop.py) assume `spec.containers`. Make container move handle cross-owner (PC↔retainer is a list-to-list move) and make sell resolve the right collection.

**Files:**
- Modify: `aose/engine/storage.py:68-77` (`move_container`)
- Modify: `aose/engine/shop.py:775+` (`sell_container`) and `remove_container`
- Test: `tests/test_container_on_carrier.py`, `tests/test_containers.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_container_on_carrier.py
def test_move_container_pc_to_retainer_relocates_lists():
    from aose.engine.storage import move_container
    from aose.engine.shop import new_container_instance
    from aose.models.storage import StorageLocation
    from aose.models import Retainer, CharacterSpec, Ability
    data = _data()  # existing module fixture
    spec = CharacterSpec(name="P", abilities={a: 10 for a in Ability},
                         race_id="human", classes=[], alignment="neutral")
    spec.containers.append(new_container_instance("backpack", data))  # carried
    cid = spec.containers[0].instance_id
    npc = CharacterSpec(name="H", abilities={a: 10 for a in Ability},
                        race_id="human", classes=[], alignment="neutral")
    spec.retainers.append(Retainer(id="r1", spec=npc, loyalty=7, role=""))
    move_container(spec, cid, StorageLocation(kind="retainer", id="r1"))
    assert spec.containers == []
    assert len(npc.containers) == 1
    assert npc.containers[0].location == StorageLocation(kind="carried")
```

- [ ] **Step 2: Run, expect FAIL**

Run: `.venv\Scripts\python.exe -m pytest tests/test_container_on_carrier.py -k pc_to_retainer -q`
Expected: FAIL (`move_container` raises "no container with id" or leaves it in `spec.containers`).

- [ ] **Step 3: Implement** — replace `move_container` in `storage.py`:

```python
def move_container(spec: CharacterSpec, container_id: str,
                   dest: StorageLocation) -> None:
    """Re-home a container. ``dest`` may not be a container (no nesting).
    A retainer source/dest moves the instance between containers lists; all
    other moves only update the instance ``location``."""
    if dest.kind == "container":
        raise StorageError("a container cannot go inside another container")
    src_coll, idx = _find_container_anywhere(spec, container_id)
    c = src_coll[idx]
    if dest.kind in ("animal", "vehicle"):
        _carrier(spec, dest.kind, dest.id)            # validate existence
    dest_coll = containers_collection(spec, dest)
    new_loc = StorageLocation(kind="carried") if dest.kind == "retainer" else dest
    if dest_coll is src_coll:
        c.location = new_loc
    else:
        src_coll.pop(idx)
        dest_coll.append(c.model_copy(update={"location": new_loc}))


def _find_container_anywhere(spec: CharacterSpec, container_id: str):
    """Return (collection_list, index) for a container in spec.containers or any
    retainer.spec.containers."""
    for i, c in enumerate(spec.containers):
        if c.instance_id == container_id:
            return spec.containers, i
    for r in spec.retainers:
        for i, c in enumerate(r.spec.containers):
            if c.instance_id == container_id:
                return r.spec.containers, i
    raise StorageError(f"no container with id {container_id!r}")
```

Then in `shop.py` `sell_container(spec, instance_id, mode, data)` — replace its
`spec.containers` lookup with `_find_container_anywhere` (import from storage) so a
retainer-owned container can be sold; credit lands in carried coins (existing
behaviour already uses the PC gold/coins path — keep it). Mirror the same lookup in
any other container helper that hard-codes `spec.containers` for the **sheet** flow
(`stash_container`/`unstash_container` are person-only and may stay).

- [ ] **Step 4: Run, expect PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_container_on_carrier.py tests/test_containers.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/storage.py aose/engine/shop.py tests/test_container_on_carrier.py
git commit -m "feat(storage): cross-owner container move + sell (incl. retainers)"
```

---

### Task 6: `OwnerCaps` descriptor + `TopLevelGroup` extensions

**Files:**
- Modify: `aose/engine/shop.py` (add `OwnerCaps`; extend `TopLevelGroup`)
- Test: `tests/test_sheet_inventory_box.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sheet_inventory_box.py
def test_toplevelgroup_has_caps_and_extra_collections():
    from aose.engine.shop import TopLevelGroup, OwnerCaps
    g = TopLevelGroup(kind="vehicle", label="Cart",
                      caps=OwnerCaps(has_equipped=False, can_wield=False,
                                     can_stash=False, bucket_label="Stowed"))
    assert g.caps.bucket_label == "Stowed"
    assert g.magic_items == [] and g.enchanted == []
    assert g.spell_sources == [] and g.ammo == []
```

- [ ] **Step 2: Run, expect FAIL**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py -k caps_and_extra -q`
Expected: FAIL (`cannot import name 'OwnerCaps'`).

- [ ] **Step 3: Implement** in `shop.py` (near `TopLevelGroup`):

```python
class OwnerCaps(BaseModel):
    """Per-inventory capabilities; templates gate on these (no per-owner branches)."""
    has_equipped: bool = False   # show Equipped subsection + label is "Carried"
    can_wield: bool = False      # inline/modal Equip on loose rows
    can_stash: bool = False      # offer Stash/Unstash
    class_filter_equip: bool = True  # PC filters by class; retainers do not
    bucket_label: str = "Carried"    # "Carried" or "Stowed"
```

Extend `TopLevelGroup` with:

```python
    caps: OwnerCaps = Field(default_factory=OwnerCaps)
    magic_items: list = Field(default_factory=list)   # MagicItemView
    enchanted: list = Field(default_factory=list)      # MagicItemView (enchanted)
    spell_sources: list = Field(default_factory=list)  # SpellSourceView
    ammo: list = Field(default_factory=list)           # AmmoView
```

- [ ] **Step 4: Run, expect PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py -k caps_and_extra -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/shop.py tests/test_sheet_inventory_box.py
git commit -m "feat(view): OwnerCaps descriptor + per-owner collections on TopLevelGroup"
```

---

### Task 7: Populate caps, retainer containers, and per-owner collections

**Files:**
- Modify: `aose/sheet/view.py` `build_inventory_groups` (carried ~1400, stashed ~1419, animals ~1430, vehicles ~1456, retainers ~1472) and `_carrier_container_views` (~1361).
- Test: `tests/test_sheet_inventory_box.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_carried_caps_and_stashed_label(_sheet_for):  # use existing fixture style
    sheet = _sheet_for(_pc_with_items())
    carried = next(g for g in sheet.inventory_groups if g.kind == "carried")
    stashed = next(g for g in sheet.inventory_groups if g.kind == "stashed")
    assert carried.caps.has_equipped and carried.caps.can_wield
    assert carried.caps.bucket_label == "Carried"
    assert carried.label == sheet.name                      # PC pane titled by name
    assert not stashed.caps.can_wield
    assert stashed.caps.bucket_label == "Stowed"

def test_vehicle_label_stowed_and_animal_carried():
    sheet = _sheet_for(_pc_with_cart_and_horse())
    veh = next(g for g in sheet.inventory_groups if g.kind == "vehicle")
    ani = next(g for g in sheet.inventory_groups if g.kind == "animal")
    assert veh.caps.bucket_label == "Stowed" and not veh.caps.has_equipped
    assert ani.caps.bucket_label == "Carried" and ani.caps.has_equipped

def test_retainer_group_renders_its_container():
    sheet = _sheet_for(_pc_with_retainer_holding_backpack_container())
    ret = next(g for g in sheet.inventory_groups if g.kind == "retainer")
    assert any(c.catalog_id == "backpack" for c in ret.containers)
    assert ret.caps.can_wield                                # retainers wield
    assert ret.caps.class_filter_equip is False
```

(Build the `_pc_with_*` helpers from existing fixtures in this test module; a
retainer container is `npc.spec.containers.append(new_container_instance("backpack", data))`.)

- [ ] **Step 2: Run, expect FAIL**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py -k "caps_and_stashed or label_stowed or retainer_group_renders" -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `build_inventory_groups`, set `caps=` on each `TopLevelGroup`:
- carried: `OwnerCaps(has_equipped=True, can_wield=True, can_stash=True, class_filter_equip=True, bucket_label="Carried")`, and `label=spec.name`.
- stashed: `OwnerCaps(has_equipped=False, can_wield=False, can_stash=False, bucket_label="Stowed")`.
- animal: `OwnerCaps(has_equipped=bool(barding_worn) or True, can_wield=False, bucket_label="Carried")` — animals always show the Equipped section (barding) so `has_equipped=True`.
- vehicle: `OwnerCaps(has_equipped=False, can_wield=False, bucket_label="Stowed")`.
- retainer: `OwnerCaps(has_equipped=bool(ret_attacks or ret_worn), can_wield=True, can_stash=False, class_filter_equip=False, bucket_label="Carried")`.

Generalize `_carrier_container_views(loc)` to also accept a containers source:
add `def _containers_for(loc, source):` that iterates `source` instead of the
captured `spec.containers`, then call it with `spec.containers` for animal/vehicle
and with `retainer.spec.containers` for the retainer group (location = the
retainer's own carried/stashed). Set `containers=` on the retainer group.

Populate the retainer group's per-owner extra collections from its own spec where
they exist (`retainer.spec.magic_items`, `.enchanted`, `.spell_sources`, `.ammo`)
using the same view builders the PC uses (factor those builders if needed). For
the PC carried group, attach `magic_items` (unequipped), `enchanted`,
`spell_sources`, and `ammo` so the box can render them (see Task 8 for the view
shapes — reuse existing `_magic_items`, enchanted rows, `sheet.spell_sources`,
`sheet.ammo`).

- [ ] **Step 4: Run, expect PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/sheet/view.py tests/test_sheet_inventory_box.py
git commit -m "feat(view): populate OwnerCaps, retainer containers, per-owner collections"
```

---

### Task 8: Factor `format_attack_rows` (shared PC/retainer) — guard PC output

**Files:**
- Modify: `aose/sheet/view.py` (extract the PC attack-row assembly into a helper used by both the PC Combat block and `build_inventory_groups`).
- Test: `tests/test_sheet_inventory_box.py` (snapshot the PC attack rows before/after).

- [ ] **Step 1: Write a characterization test** capturing current PC attack-row fields for a fighter with a sword + bow (to_hit_ascending, damage, range_ft, tags). Assert exact values.
- [ ] **Step 2: Run, expect PASS** (it characterizes current behaviour).
- [ ] **Step 3: Extract** `format_attack_rows(profiles, ...)` and route both the PC Combat block and the carried/retainer equipped rows through it. No behaviour change intended.
- [ ] **Step 4: Run full sheet tests, expect PASS** — `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py tests/test_web.py -q`.
- [ ] **Step 5: Commit** `refactor(view): shared format_attack_rows for PC + retainers`.

---

## Phase 2 — Box becomes the interaction hub

> **All Phase 2 tasks render UI. After each edit: `preview_start` (if not running),
> reload, `preview_snapshot`/`preview_screenshot` to confirm; fix from source.**
> Each task ends with a `pytest` web smoke (`GET /character/<id>` → 200) + a
> targeted assertion, then commit.

### Task 9: Shared per-item modal macros (`_inv_modals.html`)

**Files:**
- Create: `aose/web/templates/_inv_modals.html`
- Reference (do not duplicate logic — move it): the action forms currently in
  `_equipment_ui.html` (magic table 425-475, enchanted 484-529, gems 721-748,
  jewellery 777-794, coin_table 155-194, sources/docs 591-647, ammo 365-385) and
  `_inv_row_actions.html` (move/sell/drop/equip).

- [ ] **Step 1:** Define macros, each taking `(thing, owner, caps, url_prefix, coins_url_prefix)` and emitting one `<div class="overlay modal" id="modal-...">`:
  - `item_modal(row, owner, caps, url_prefix)` → details + `inv_row_actions` (move/sell/drop/equip gated by `caps`).
  - `container_modal(c, owner, caps, url_prefix)` → details + Move-to ▾ + Sell ▾ (empty only) + Drop.
  - `coin_modal(coin, owner, prefix, groups)` → Convert ▾ + Move ▾ + Adjust.
  - `gem_modal` / `jewellery_modal` → their existing actions + Move ▾.
  - `magic_modal` / `enchanted_modal` → equip/charges/note/remove.
  - `source_modal` → read/cast/copy/remove (move the document controls here).
  - `ammo_modal` → adjust/load/unload/remove.
  Modal id convention: `modal-<type>-<owner.kind>-<owner.id|'self'>-<row id/instance>`.
- [ ] **Step 2–4:** Wire `sheet.html` to loop every group (and each container) and emit the matching modals; remove the now-superseded per-type modal blocks from `sheet.html`. Verify via preview that clicking a magic item / gem / coin / scroll opens a modal with the right buttons.
- [ ] **Step 5:** `pytest tests/test_web.py -q` + commit `feat(sheet): shared per-item modal macros for every owned type`.

### Task 10: Three-subsection pane layout + inline equip (`_inv_pane.html`)

- [ ] Rewrite the pane body to render exactly **Equipped** (if `caps.has_equipped`), **Coins**, and **`{{ caps.bucket_label }}`** (everything else: loose, containers, magic, enchanted, sources, ammo, gems, jewellery), each row clickable to its Task-9 modal.
- [ ] Loose equippable rows render an inline Equip/Off-hand button when `caps.can_wield` (and, when `caps.class_filter_equip`, only if `row.class_allowed`).
- [ ] Use `group.label` for the pane title (PC already set to `sheet.name` in Task 7).
- [ ] Verify via preview: PC pane titled by name; Stashed/vehicle bucket reads "Stowed"; animal reads "Carried"; inline equip present for PC/retainer only.
- [ ] `pytest tests/test_sheet_inventory_box.py tests/test_web.py -q`; commit `feat(sheet): three-subsection inventory panes + inline equip`.

### Task 11: Container row parity in the box (move/sell/drop)

- [ ] Ensure container rows in every pane expose Move-to ▾ + Sell ▾ (empty-only) + Drop via the `container_modal`, plus stow/take-out for contents. Remove the old carried-only stash/unstash divergence.
- [ ] Verify via preview on a PC container and an animal/retainer container.
- [ ] `pytest tests/test_web.py tests/test_inventory_move_routes.py -q`; commit `feat(sheet): unified container actions in the box`.

---

## Phase 3 — Drawer becomes acquisition-only

### Task 12: Strip owned-item UI; reorder + rename tabs

**Files:** `aose/web/templates/_equipment_ui.html`

- [ ] Tab bar order/names: **Shop** (first, `data-tab="shop"` default on) · **Enchant** (was Magic) · **Scribe** (was Documents) · **Treasure**. Keep tab gating (Enchant when `magic_acquisition`; Scribe when `spell_sources is defined`; Treasure when `valuables is defined`).
- [ ] Delete: the `inv` pane (Carried/Stashed/coins/containers/group panels), `inv_table`, `container_table`, `inv_group_panel`, `coin_table`, the owned magic/enchanted tables, the document management table, the ammo section, the carried "Add coins" block. **Keep only**: Shop table, the add-enchanted form, the add spell-book/scroll form, and a Treasure tab containing add-coins + add-gem + add-jewellery.
- [ ] Move the custom-item (`other_possessions`) add form into the drawer (Shop tab footer).
- [ ] Verify via preview: drawer shows four acquisition tabs, no owned items.
- [ ] `pytest tests/test_web.py tests/test_wizard.py -q`; commit `feat(drawer): acquisition-only tabs (Shop/Enchant/Scribe/Treasure)`.

### Task 13: Treasure tab absorbs add-coins; routes intact

- [ ] In the Treasure tab, add the add-coins form (denom + count → `coins/add` at carried), beside add-gem/add-jewellery. Existing management forms (sell/convert/adjust/mark-damaged) are **not** here — they live in box modals (Task 9).
- [ ] Verify add-coins/add-gem/add-jewellery still deposit to carried.
- [ ] `pytest tests/test_web.py -q`; commit `feat(drawer): Treasure tab absorbs add-coins`.

---

## Phase 4 — Wizard reuses the box

### Task 14: Render the box for the draft (Carried + Stashed)

**Files:** `aose/web/templates/wizard/equipment.html`, `aose/web/wizard.py`

- [ ] In `wizard.py`'s equipment GET handler, build `inventory_groups` for the draft spec restricted to carried + stashed (no carriers/retainers mid-creation) using `build_inventory_groups`; pass them + the shared box partial context to the template.
- [ ] `wizard/equipment.html`: include the inventory box (the `_inv_pane.html` macro over the carried/stashed groups) above the existing `_equipment_ui.html` (now Shop + acquisition).
- [ ] Ensure the box's actions point at wizard routes via the `url_prefix`/`coins_url_prefix` the macros already accept.
- [ ] Verify via preview: start a draft, buy a sword, see it in the box, equip it inline.
- [ ] `pytest tests/test_wizard.py -q`; commit `feat(wizard): equipment step renders the inventory box`.

### Task 15: Wire missing wizard actions (incl. use-as-container)

**Files:** `aose/web/wizard.py`

- [ ] Add any box actions the wizard lacks. At minimum a wizard `use-as-container` POST mirroring the sheet route (Task 16). Confirm equip/unequip/stash/unstash/stow/take-out/move-item/move-container exist for drafts; add thin handlers where missing, each: load draft → mutate via the engine → save draft → redirect to the equipment step.
- [ ] Add a wizard web test: promote a loose backpack during creation; assert it becomes a container in the draft.
- [ ] `pytest tests/test_wizard.py -q`; commit `feat(wizard): box actions incl. use-as-container`.

---

## Phase 5 — Routes, cleanup, docs, verification

### Task 16: Sheet route `use-as-container` + generalized container routes

**Files:** `aose/web/routes.py`

- [ ] **Step 1:** Web test — `POST /character/<id>/inventory/use-as-container` with `owner_kind`/`owner_id`/`item_id` promotes a loose backpack; assert `spec.containers` grew and the loose copy is gone.
- [ ] **Step 2:** Run, expect FAIL (404/handler missing).
- [ ] **Step 3:** Add the route:

```python
@router.post("/character/{character_id}/inventory/use-as-container")
async def inventory_use_as_container(request: Request, character_id: str):
    from aose.engine import storage as _storage
    spec = _load_spec_or_404(request, character_id)
    form = await request.form()
    owner = _loc(form.get("owner_kind", "carried"), form.get("owner_id") or None)
    try:
        _storage.use_as_container(spec, owner, form["item_id"], request.app.state.game_data)
    except (KeyError, _storage.StorageError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] Confirm `inventory_move_container` already accepts a retainer `dest_kind`; if the box sends `owner_kind` for the source, thread it through (the generalized `move_container` finds the container regardless of source).
- [ ] **Step 4:** Run, expect PASS — `pytest tests/test_inventory_move_routes.py -q`.
- [ ] **Step 5:** Commit `feat(routes): use-as-container + owner-aware container moves`.

### Task 17: Dead-code sweep

- [ ] Grep for callers of `inventory_view` and the legacy `InventoryView`/`inventory_rows`. If the sheet box and wizard now use `inventory_groups` exclusively and only `sheet_print.html`/tests reference `inventory_view`, leave `inventory_view` for print; otherwise remove genuinely unused view models, macros, and route context fields surfaced by the strip in Task 12.
- [ ] Remove now-unused imports/macros in `sheet.html` and `_equipment_ui.html`.
- [ ] Run the full suite: `.venv\Scripts\python.exe -m pytest tests/ -q`. Expected: all green (ignore the pytest-current PermissionError).
- [ ] Commit `chore: remove dead inventory code paths after drawer strip`.

### Task 18: Docs + final verification

- [ ] `docs/CHANGELOG.md`: add a top row (date 2026-06-22, feature, branch `feat/inventory-box-interaction-hub`, spec/plan slug).
- [ ] `docs/ARCHITECTURE.md`: update the **Inventory, containers & encumbrance** and **Sheet & UI** sections in place — box is the interaction hub, drawer is acquisition-only, `OwnerCaps`, `use_as_container`, retainer containers via shared helpers.
- [ ] `CLAUDE.md`: only if orientation shifted (e.g., the drawer's role). Add a one-liner if so; otherwise leave it.
- [ ] Full preview pass: PC with a retainer (holding a container), an animal, a vehicle, gems/jewellery/coins, a magic item, a scroll. Confirm: every pane shows Equipped/Coins/Carried-or-Stowed; every row opens the right modal with the right buttons; inline equip on PC/retainer only; drawer is acquisition-only; "use as container" promotes a loose backpack. Screenshot for the user.
- [ ] `pytest tests/ -q` green; commit `docs(inventory): record interaction-hub redesign`.

---

## Self-Review notes (for the executor)

- **Spec coverage:** Phase 1 = engine/view foundation incl. promotion + grant hardening + retainer containers (spec §Engine, §Retainer containers, §Decisions 1). Phase 2 = box hub + three-subsection layout + modals + inline equip (spec §Box structure, §Per-item modals, §Decision 6). Phase 3 = drawer acquisition-only (spec §Drawer). Phase 4 = wizard (spec §Wizard, §Decision 5). Phase 5 = routes/cleanup/docs (spec §Cleanup, §Phasing 5). Capability table → `OwnerCaps` (Task 6/7). Scope lines (magic/etc. PC-bucket; custom items) honoured in Task 7/12.
- **Type consistency:** `OwnerCaps(has_equipped, can_wield, can_stash, class_filter_equip, bucket_label)` used identically in Tasks 6/7/10. `use_as_container(spec, owner, item_id, data)` signature identical in Tasks 3/15/16. `apply_kit(spec, kit, data)` updated at its one caller (Task 4).
- **Known soft spots (resolve live, not by guessing):** exact Jinja for Phase 2 macros and the wizard route plumbing are specified by contract + acceptance + preview verification rather than full source, because they must be validated against the running app. Keep each macro single-responsibility and gated solely by `caps`.
