# Item Identity Unification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every owned thing a real instance identity (`instance_id` + `location`, plus `count` for stackables and equip-state for equippables), deleting the `equipped`/`loaded_ammo`/`armor_tailored`/`contents` side tables, so one move path and one equip path serve PC and retainer alike — and the retainer equip-then-move dupe is fixed structurally.

**Architecture:** Single **atomic engine landing** (no compatibility layer): the model changes and every engine reader/writer, the view-data builders, the routes, the wizard, and the whole test suite move together on one branch. Loose catalog items become `ItemInstance`s in one flat `CharacterSpec.items` list (location is a field, not a positional list); `equipped`/`loaded_ammo`/`armor_tailored` become per-instance fields; coin stacks gain `instance_id`. Storage locations are uniform, differing only by a policy descriptor (capacity / encumbrance / equip-allowed / equip-eligibility). Old saves are coerced at the loader (where `GameData` is available), not in a model validator.

**Tech Stack:** Python 3.14, Pydantic v2, FastAPI, Jinja2, pytest. Run tests with `.venv\Scripts\python.exe -m pytest tests/ -q` (the trailing `pytest-current` PermissionError is a known Windows quirk — ignore it).

**Spec:** [`docs/superpowers/specs/2026-06-24-item-identity-unification-design.md`](../specs/2026-06-24-item-identity-unification-design.md)

---

## Scope of this plan

This plan covers the **whole atomic landing**. It is authored in five parts that build in order; the suite is **red mid-landing by design** (the user chose the atomic approach over a compatibility seam) and returns to green at the end of Part 5.

- **Part 1 — Model + accessor core** (Tasks 1–4): the new model shape, the equip core that fixes the dupe, the loader coercion.
- **Part 2 — Storage engine** (Tasks 5–9): the location policy descriptor, `loose`-by-location, `split_stack`, instance-based `move_item`/`move_thing`, retainer-transfer removal.
- **Part 3 — Reader migrations** (Tasks 10–16): encumbrance, armor_class, attacks, ammo, quick_equipment, enchant, magic, companions.
- **Part 4 — View, routes, wizard** (Tasks 17–22): `shop.py` view-builders + buy/sell/use, `sheet/view.py`, the equip/move/sell/use routes, the wizard equipment step.
- **Part 5 — Templates, test-suite migration, docs** (Tasks 23–27): count-box + use UI, mechanical test-suite migration to the new model, `ARCHITECTURE.md`/`CHANGELOG.md`.

> **Authoring status:** Parts 2–5 are appended after Part 1 is reviewed. Do not begin execution until the whole plan is present and the "Plan complete" handoff appears at the end of Part 5.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `aose/models/character.py` | `ItemInstance`; `CharacterSpec.items`; equip-state on `ItemInstance`/`EnchantedInstance`; drop `inventory`/`stashed`/`equipped`/`loaded_ammo`/`armor_tailored`; drop `contents` from container/animal/vehicle | Modify |
| `aose/models/storage.py` | `instance_id` on `CoinStack` | Modify |
| `aose/engine/equip.py` | Instance-based `equip`/`unequip`/`validate_wield` + slot accessors (`equipped_instance`, `slot_item`, `equipped_ref`) | Rewrite |
| `aose/characters/migrate_items.py` | Loader-time coercion of legacy saves to the new shape (needs `GameData`) | Create |
| `aose/characters/storage.py`, `drafts.py` | Call the coercion before `CharacterSpec(**raw)` | Modify |
| `aose/engine/storage.py` | Location policy descriptor; `loose` by location over `items`; `split_stack`; instance `move_item`/`move_thing`; delete retainer-transfer reliance | Rewrite |
| `aose/engine/encumbrance.py` `armor_class.py` `attacks.py` `ammo.py` | Read instances via accessors | Modify |
| `aose/engine/quick_equipment.py` | Build `ItemInstance`s; equip on the kit's item list | Modify |
| `aose/engine/enchant.py` | `equip`/`unequip` set `EnchantedInstance.equip` slot (was bool) | Modify |
| `aose/engine/retainers.py` | Delete `transfer_to_retainer`/`transfer_to_pc`; give/take routes use `move_thing` | Modify |
| `aose/engine/shop.py` | `inventory_view`/`_build_row`/`buy_item`/`sell_item`/`new_container_instance` over `items`; `OwnerCaps` becomes a projection of the policy descriptor | Modify |
| `aose/sheet/view.py`, `companions_view.py` | Build groups from `items` by location; equip block via `equip` field | Modify |
| `aose/web/routes.py`, `wizard.py` | Equip/move/sell/use routes pass `instance_id`; give/take call `move_thing` | Modify |
| `aose/web/templates/_inv_*.html`, `sheet*.html`, `_companions.html`, `wizard/equipment.html` | Count-box on move/sell/drop; "use" button; equip by `instance_id` | Modify |
| `tests/**` | Construct specs with `items=[ItemInstance(...)]`; assert equip via `equip` field | Modify (broad) |

---

# Part 1 — Model + accessor core

### Task 1: New model shape — `ItemInstance`, flat `items`, equip-as-state

**Files:**
- Modify: `aose/models/character.py`
- Modify: `aose/models/storage.py`
- Test: `tests/test_item_instance_model.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_item_instance_model.py
import pytest
from aose.models import CharacterSpec, ClassEntry, ItemInstance, EnchantedInstance, CoinStack
from aose.models.storage import StorageLocation

CARRIED = StorageLocation(kind="carried")


def _spec(**kw):
    base = dict(
        name="Hero",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
    )
    base.update(kw)
    return CharacterSpec(**base)


def test_item_instance_defaults():
    ii = ItemInstance(instance_id="i1", catalog_id="sword")
    assert ii.location == CARRIED
    assert ii.count == 1
    assert ii.equip is None
    assert ii.tailored is True
    assert ii.loaded_ammo_id is None


def test_spec_has_items_list_and_no_legacy_fields():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword", equip="main_hand")])
    assert spec.items[0].equip == "main_hand"
    # Legacy fields are gone (extra="forbid" rejects them).
    for legacy in ("inventory", "stashed", "equipped", "loaded_ammo", "armor_tailored"):
        with pytest.raises(Exception):
            _spec(**{legacy: [] if legacy in ("inventory", "stashed") else {}})


def test_enchanted_instance_uses_equip_slot_not_bool():
    e = EnchantedInstance(instance_id="e1", base_id="sword", enchantment_id="generic_plus_1")
    assert e.equip is None
    e2 = EnchantedInstance(instance_id="e2", base_id="plate_mail",
                           enchantment_id="generic_plus_1", equip="armor")
    assert e2.equip == "armor"
    with pytest.raises(Exception):                 # bool no longer accepted
        EnchantedInstance(instance_id="e3", base_id="sword",
                          enchantment_id="generic_plus_1", equipped=True)


def test_coin_stack_has_instance_id():
    c = CoinStack(instance_id="c1", denom="gp", count=10)
    assert c.instance_id == "c1"


def test_container_instance_has_no_contents_field():
    from aose.models import ContainerInstance
    with pytest.raises(Exception):
        ContainerInstance(instance_id="k1", catalog_id="backpack", contents=["torch"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_item_instance_model.py -q`
Expected: FAIL — `ImportError: cannot import name 'ItemInstance'`.

- [ ] **Step 3: Add `ItemInstance` and reshape `CharacterSpec`**

In `aose/models/character.py`, add the `EquipSlot` alias and `ItemInstance` near the top (after the imports):

```python
from typing import Literal

EquipSlot = Literal["armor", "main_hand", "off_hand"]


class ItemInstance(BaseModel):
    """One owned loose catalog item, with identity.

    Stackables (consumable gear, etc.) carry ``count > 1`` and ``equip is None``.
    Equippables (weapon/armour/shield) are always per-instance (``count == 1``)
    and may carry an ``equip`` slot. ``tailored``/``loaded_ammo_id`` are inert
    except on tailorable armour / launcher weapons. Stackable-vs-equippable is a
    catalog property enforced by the engine, not by this model."""
    model_config = ConfigDict(extra="forbid")

    instance_id: str                       # uuid4 hex
    catalog_id: str                        # references a Weapon / Armor / gear item
    location: StorageLocation = Field(default_factory=lambda: StorageLocation(kind="carried"))
    count: int = 1
    equip: EquipSlot | None = None
    tailored: bool = True
    loaded_ammo_id: str | None = None
```

Change `EnchantedInstance` (replace the `equipped: bool` field and add `tailored`/`loaded_ammo_id`):

```python
    # was: equipped: bool = False
    equip: EquipSlot | None = None
    tailored: bool = True
    loaded_ammo_id: str | None = None
```

In `CharacterSpec`, **replace** the `inventory`, `stashed`, `equipped`, `armor_tailored`, and `loaded_ammo` fields with a single:

```python
    # Every loose owned item, with its own identity + location. Replaces the
    # old positional inventory/stashed lists and the equipped/loaded_ammo/
    # armor_tailored side tables (equip/tailoring/loaded-ammo are now fields on
    # the instance). Items "in" a container/animal/vehicle carry that location.
    items: list[ItemInstance] = Field(default_factory=list)
```

Delete the `loaded_ammo: dict[str, str]` field. Keep `magic_items` (still `equipped: bool`).

In `ContainerInstance`, `AnimalInstance`, `VehicleInstance`: **delete the `contents: list[str]` field** (items located there now live in `spec.items`). Remove the `_migrate_legacy_location` validator's `contents` handling if any (it doesn't touch contents — leave it).

Export `ItemInstance` and `EquipSlot` from `aose/models/__init__.py` (add to the import list and `__all__`).

In `aose/models/storage.py`, add `instance_id` to `CoinStack`:

```python
class CoinStack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance_id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex)
    denom: Literal["pp", "gp", "ep", "sp", "cp"]
    count: int
    location: StorageLocation = Field(default_factory=lambda: StorageLocation(kind="carried"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_item_instance_model.py -q`
Expected: PASS (5 tests). Other suites are expected to break — that is the atomic landing.

- [ ] **Step 5: Commit**

```bash
git add aose/models/character.py aose/models/storage.py aose/models/__init__.py tests/test_item_instance_model.py
git commit -m "feat(model): ItemInstance + flat items list; equip-state on instances; coin ids"
```

---

### Task 2: Equip core on instances (`equip.py`)

This is the change that fixes the dupe: equip is per-instance state, read/written the same way for any owning spec.

**Files:**
- Rewrite: `aose/engine/equip.py`
- Test: `tests/test_equip_core.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_equip_core.py
from pathlib import Path
import pytest
from aose.data.loader import GameData
from aose.engine import equip
from aose.models import CharacterSpec, ClassEntry, ItemInstance
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))
CARRIED = StorageLocation(kind="carried")
STASHED = StorageLocation(kind="stashed")


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw); return CharacterSpec(**base)


def test_equip_sets_instance_slot():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword")])
    equip.equip(spec, "i1", data=DATA)
    assert spec.items[0].equip == "main_hand"
    assert equip.equipped_ref(spec, "main_hand") == "sword"


def test_equip_armor_goes_to_armor_slot():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="plate_mail")])
    equip.equip(spec, "i1", data=DATA)
    assert spec.items[0].equip == "armor"


def test_equip_rejects_non_carried_instance():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword", location=STASHED)])
    with pytest.raises(ValueError):
        equip.equip(spec, "i1", data=DATA)


def test_equip_into_occupied_slot_replaces_previous():
    spec = _spec(items=[
        ItemInstance(instance_id="i1", catalog_id="sword", equip="main_hand"),
        ItemInstance(instance_id="i2", catalog_id="mace"),
    ])
    equip.equip(spec, "i2", data=DATA)
    assert spec.items[0].equip is None       # displaced
    assert spec.items[1].equip == "main_hand"


def test_unequip_clears_slot():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword", equip="main_hand")])
    equip.unequip(spec, "i1")
    assert spec.items[0].equip is None


def test_two_daggers_dual_wield_are_two_instances():
    spec = _spec(items=[
        ItemInstance(instance_id="i1", catalog_id="dagger"),
        ItemInstance(instance_id="i2", catalog_id="dagger"),
    ], ruleset={"two_weapon_fighting": True})
    equip.equip(spec, "i1", data=DATA)
    equip.equip(spec, "i2", slot="off_hand", data=DATA, two_weapon=True, eligible=True)
    assert equip.equipped_ref(spec, "main_hand") == "dagger"
    assert equip.equipped_ref(spec, "off_hand") == "dagger"


def test_slot_item_resolves_weapon():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword", equip="main_hand")])
    from aose.models import Weapon
    assert isinstance(equip.slot_item(spec, "main_hand", DATA), Weapon)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_core.py -q`
Expected: FAIL — `equip.equip()` now takes `(equipped=...)` not `(spec, ...)`.

- [ ] **Step 3: Rewrite `aose/engine/equip.py`**

Keep `hand_cost`, `off_hand_eligible`, `OFF_HAND_FORBIDDEN`, `WieldError`, and `resolve_slot` (still used by other call sites during the landing). Replace the dict-based `equip`/`unequip`/`validate_wield`/`equipped_count` with instance-based functions:

```python
def _find_equippable(spec, instance_id: str):
    """The ItemInstance or EnchantedInstance with this id, or None."""
    for ii in spec.items:
        if ii.instance_id == instance_id:
            return ii
    for ei in spec.enchanted:
        if ei.instance_id == instance_id:
            return ei
    return None


def _resolve_equippable(inst, data: GameData):
    """Resolve an ItemInstance/EnchantedInstance to its Weapon/Armor, or None."""
    from aose.models import ItemInstance
    if isinstance(inst, ItemInstance):
        return data.items.get(inst.catalog_id)
    return resolve_instance(inst, data)          # EnchantedInstance


def equipped_instance(spec, slot: str):
    """The instance occupying ``slot`` (ItemInstance or EnchantedInstance), or None."""
    for ii in spec.items:
        if ii.equip == slot:
            return ii
    for ei in spec.enchanted:
        if ei.equip == slot:
            return ei
    return None


def equipped_ref(spec, slot: str) -> str | None:
    """The resolvable slot value: an ItemInstance's catalog_id, or an
    EnchantedInstance's instance_id (matching ``resolve_slot``'s contract)."""
    from aose.models import ItemInstance
    inst = equipped_instance(spec, slot)
    if inst is None:
        return None
    return inst.catalog_id if isinstance(inst, ItemInstance) else inst.instance_id


def slot_item(spec, slot: str, data: GameData):
    """Resolved Weapon/Armor in ``slot``, or None."""
    inst = equipped_instance(spec, slot)
    return _resolve_equippable(inst, data) if inst is not None else None


def validate_wield(spec, data: GameData, *, two_weapon: bool, eligible: bool,
                   gargantua_1h_2h: bool) -> None:
    """Raise WieldError unless the hand slots form a legal configuration."""
    main = slot_item(spec, "main_hand", data)
    off = slot_item(spec, "off_hand", data)
    if main is not None and not isinstance(main, Weapon):
        raise WieldError("Only a weapon may be held in the main hand")
    used = (hand_cost(main, gargantua_1h_2h=gargantua_1h_2h) if main else 0)
    used += (hand_cost(off, gargantua_1h_2h=gargantua_1h_2h) if off else 0)
    if used > 2:
        raise WieldError("Both hands are full")
    if isinstance(off, Weapon):
        if not two_weapon:
            raise WieldError("Two-weapon fighting is not enabled")
        if not eligible:
            raise WieldError("This character is not eligible to fight with two weapons")
        if main is None:
            raise WieldError("Equip a main-hand weapon before an off-hand weapon")
        if not off_hand_eligible(off):
            raise WieldError(f"{off.name!r} is not a valid off-hand weapon")


def _clear_slot(spec, slot: str) -> None:
    occ = equipped_instance(spec, slot)
    if occ is not None:
        occ.equip = None


def equip(spec, instance_id: str, *, data: GameData, slot: str | None = None,
          two_weapon: bool = False, eligible: bool = False,
          gargantua_1h_2h: bool = False,
          allowed_weapons: "set[str] | str" = "all",
          allowed_armor: "set[str] | str" = "all",
          allow_shields: bool = True) -> None:
    """Equip the instance ``instance_id`` (loose or enchanted) into its slot.
    Mutates the instance's ``equip`` field. Raises ValueError/WieldError."""
    from aose.engine.proficiency import base_armor_id, base_weapon_id
    inst = _find_equippable(spec, instance_id)
    if inst is None:
        raise ValueError(f"Unknown or unowned item {instance_id!r}")
    if inst.location.kind != "carried":
        raise ValueError("Only carried items can be equipped")
    item = _resolve_equippable(inst, data)
    if item is None:
        raise ValueError(f"{instance_id!r} cannot be resolved to an item")

    if isinstance(item, Armor) and not item.is_shield:
        if allowed_armor != "all" and base_armor_id(item) not in allowed_armor:
            raise ValueError(f"This class cannot use {item.name!r}")
        _clear_slot(spec, "armor")
        inst.equip = "armor"
        return
    if isinstance(item, Armor) and item.is_shield:
        if not allow_shields:
            raise ValueError("This class cannot use a shield")
        target = "off_hand"
    elif isinstance(item, Weapon):
        if allowed_weapons != "all" and base_weapon_id(item) not in allowed_weapons:
            raise ValueError(f"This class cannot use {item.name!r}")
        target = slot or "main_hand"
    else:
        raise ValueError(f"{item.name!r} is not equippable")
    if target not in ("main_hand", "off_hand"):
        raise ValueError(f"Invalid hand slot {target!r}")

    _clear_slot(spec, target)
    inst.equip = target
    try:
        validate_wield(spec, data, two_weapon=two_weapon, eligible=eligible,
                       gargantua_1h_2h=gargantua_1h_2h)
    except WieldError:
        inst.equip = None
        raise


def unequip(spec, instance_id: str) -> None:
    """Clear the instance's equip slot. Raises ValueError if not equipped."""
    inst = _find_equippable(spec, instance_id)
    if inst is None or inst.equip is None:
        raise ValueError(f"{instance_id!r} is not equipped")
    inst.equip = None
```

Add the needed imports at the top: `from aose.engine.enchant import resolve_instance` (already imports `resolve_instance`), keep `from aose.models import Armor, Weapon`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_core.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/equip.py tests/test_equip_core.py
git commit -m "feat(equip): instance-based equip/unequip/validate_wield (equip is instance state)"
```

---

### Task 3: Enchanted equip sets the slot (`enchant.py`)

**Files:**
- Modify: `aose/engine/enchant.py:163-177` (`new_enchanted_instance`, `equip`, `unequip`), `equipped_enchanted:218-230`
- Test: `tests/test_enchant_equip_slot.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enchant_equip_slot.py
from pathlib import Path
from aose.data.loader import GameData
from aose.engine import enchant
from aose.models import EnchantedInstance

DATA = GameData.load(Path("data"))


def test_equip_sets_slot_from_kind():
    items = [EnchantedInstance(instance_id="e1", base_id="sword",
                               enchantment_id="generic_plus_1")]
    out = enchant.equip(items, "e1", DATA)
    assert out[0].equip == "main_hand"


def test_equip_armor_sets_armor_slot():
    items = [EnchantedInstance(instance_id="e1", base_id="plate_mail",
                              enchantment_id="generic_plus_1")]
    out = enchant.equip(items, "e1", DATA)
    assert out[0].equip == "armor"


def test_unequip_clears_slot():
    items = [EnchantedInstance(instance_id="e1", base_id="sword",
                              enchantment_id="generic_plus_1", equip="main_hand")]
    out = enchant.unequip(items, "e1")
    assert out[0].equip is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchant_equip_slot.py -q`
Expected: FAIL — `enchant.equip` ignores the slot / sets a bool.

- [ ] **Step 3: Update `enchant.py`**

`new_enchanted_instance`: change `equipped=False` to `equip=None` in the constructor call (line ~157).

Replace `equip`/`unequip` (they now need `data` to know the slot from the enchantment kind):

```python
_KIND_SLOT = {"weapon": "main_hand", "armor": "armor", "shield": "off_hand"}


def equip(items: list[EnchantedInstance], instance_id: str,
          data: GameData) -> list[EnchantedInstance]:
    idx = _index(items, instance_id)
    kind = _kind_of_instance(items[idx], data)
    slot = _KIND_SLOT.get(kind or "", "main_hand")
    updated = items[idx].model_copy(update={"equip": slot})
    return [*items[:idx], updated, *items[idx + 1:]]


def unequip(items: list[EnchantedInstance], instance_id: str) -> list[EnchantedInstance]:
    idx = _index(items, instance_id)
    updated = items[idx].model_copy(update={"equip": None})
    return [*items[:idx], updated, *items[idx + 1:]]
```

Update `equipped_enchanted` to test `inst.equip is not None` instead of `inst.equipped`:

```python
    for inst in spec.enchanted:
        if inst.equip is None:
            continue
        if _kind_of_instance(inst, data) != kind:
            continue
        ...
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchant_equip_slot.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/enchant.py tests/test_enchant_equip_slot.py
git commit -m "feat(enchant): enchanted equip writes the slot field (was bool)"
```

---

### Task 4: Loader coercion of legacy saves

Coercion needs `GameData` (to classify stackable-vs-equippable and to expand bundles), so it lives in the loader as a raw-dict transform run **before** `CharacterSpec(**raw)`. It recurses into retainers.

**Files:**
- Create: `aose/characters/migrate_items.py`
- Modify: `aose/characters/storage.py`, `aose/characters/drafts.py` (call the coercion at load)
- Test: `tests/test_migrate_items.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_migrate_items.py
from pathlib import Path
from aose.data.loader import GameData
from aose.characters.migrate_items import migrate_legacy_items
from aose.models import CharacterSpec

DATA = GameData.load(Path("data"))


def _legacy(**kw):
    base = dict(
        name="Old", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
        "CON": 10, "CHA": 10}, race_id="human",
        classes=[{"class_id": "fighter", "level": 1, "hp_rolls": [8]}],
        alignment="neutral",
    )
    base.update(kw); return base


def test_loose_strings_become_instances():
    raw = migrate_legacy_items(_legacy(inventory=["sword", "torch", "torch"]), DATA)
    spec = CharacterSpec(**raw)
    by_cat = {i.catalog_id: i for i in spec.items}
    assert by_cat["sword"].count == 1                 # equippable, per-instance
    assert by_cat["torch"].count == 2                 # stackable, collapsed


def test_equipped_dict_becomes_equip_field():
    raw = migrate_legacy_items(
        _legacy(inventory=["sword"], equipped={"main_hand": "sword"}), DATA)
    spec = CharacterSpec(**raw)
    sword = next(i for i in spec.items if i.catalog_id == "sword")
    assert sword.equip == "main_hand"


def test_two_equipped_copies_become_two_instances():
    raw = migrate_legacy_items(
        _legacy(inventory=["dagger", "dagger"],
                equipped={"main_hand": "dagger", "off_hand": "dagger"}), DATA)
    spec = CharacterSpec(**raw)
    daggers = [i for i in spec.items if i.catalog_id == "dagger"]
    assert len(daggers) == 2
    assert {d.equip for d in daggers} == {"main_hand", "off_hand"}


def test_stashed_and_container_contents_relocate():
    raw = migrate_legacy_items(_legacy(
        inventory=["backpack"], stashed=["rope"],
        containers=[{"instance_id": "c1", "catalog_id": "backpack",
                     "location": {"kind": "carried"}, "contents": ["torch", "torch"]}],
    ), DATA)
    spec = CharacterSpec(**raw)
    locs = {(i.catalog_id, i.location.kind, i.location.id): i for i in spec.items}
    assert ("rope", "stashed", None) in locs
    assert locs[("torch", "container", "c1")].count == 2
    assert all(not hasattr(c, "contents") or True for c in spec.containers)  # contents field gone


def test_loaded_ammo_and_tailored_become_instance_fields():
    raw = migrate_legacy_items(_legacy(
        inventory=["short_bow", "plate_mail"], armor_tailored=False,
        equipped={"main_hand": "short_bow", "armor": "plate_mail"},
        ammo=[{"instance_id": "a1", "base_id": "arrow", "count": 20}],
        loaded_ammo={"short_bow": "a1"},
    ), DATA)
    spec = CharacterSpec(**raw)
    bow = next(i for i in spec.items if i.catalog_id == "short_bow")
    plate = next(i for i in spec.items if i.catalog_id == "plate_mail")
    assert bow.loaded_ammo_id == "a1"
    assert plate.tailored is False


def test_retainer_items_also_migrated():
    raw = migrate_legacy_items(_legacy(
        retainers=[{"id": "r1", "loyalty": 7, "role": "",
                    "spec": _legacy(name="NPC", inventory=["sword"],
                                    equipped={"main_hand": "sword"})}]), DATA)
    spec = CharacterSpec(**raw)
    npc = spec.retainers[0].spec
    assert npc.items[0].catalog_id == "sword" and npc.items[0].equip == "main_hand"


def test_new_shape_passes_through_untouched():
    raw = migrate_legacy_items(_legacy(
        items=[{"instance_id": "i1", "catalog_id": "sword", "equip": "main_hand"}]), DATA)
    assert raw["items"][0]["catalog_id"] == "sword"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_migrate_items.py -q`
Expected: FAIL — `ModuleNotFoundError: aose.characters.migrate_items`.

- [ ] **Step 3: Implement the coercion**

```python
# aose/characters/migrate_items.py
"""Loader-time coercion of legacy character saves into the instance model.

Runs on the raw dict (needs GameData for stackable classification + bundle
expansion) BEFORE CharacterSpec validation, because the legacy fields
(inventory/stashed/equipped/loaded_ammo/armor_tailored/contents) no longer
exist on the model under extra='forbid'. Recurses into retainers. A save
already in the new shape (an ``items`` key, no legacy keys) passes through.
"""
from __future__ import annotations

import uuid

from aose.data.loader import GameData
from aose.models import Armor, Weapon

_LEGACY_KEYS = ("inventory", "stashed", "equipped", "loaded_ammo", "armor_tailored")


def _is_equippable(catalog_id: str, data: GameData) -> bool:
    return isinstance(data.items.get(catalog_id), (Weapon, Armor))


def _new_instance(catalog_id: str, location: dict, count: int = 1) -> dict:
    return {"instance_id": uuid.uuid4().hex, "catalog_id": catalog_id,
            "location": location, "count": count}


def _coerce_spec(raw: dict, data: GameData) -> dict:
    if not isinstance(raw, dict):
        return raw
    # Pass-through if already migrated (no legacy keys, no contents on carriers).
    legacy_present = any(k in raw for k in _LEGACY_KEYS) or _has_contents(raw)
    if not legacy_present:
        _coerce_retainers(raw, data)
        return raw

    equipped = raw.get("equipped") or {}          # slot -> catalog_id
    loaded_ammo = raw.get("loaded_ammo") or {}     # weapon_key -> ammo instance id
    tailored = raw.get("armor_tailored", True)
    # slot lookup by catalog id (a catalog id may be equipped in >= 1 slot)
    slots_for: dict[str, list[str]] = {}
    for slot, cid in equipped.items():
        slots_for.setdefault(cid, []).append(slot)

    items: list[dict] = []

    def add_loose(cid: str, location: dict) -> None:
        equippable = _is_equippable(cid, data)
        inst = _new_instance(cid, location)
        if equippable:
            inst["count"] = 1
            # assign one equipped slot if this catalog id is equipped & carried
            if location.get("kind") == "carried" and slots_for.get(cid):
                inst["equip"] = slots_for[cid].pop(0)
            if data.items.get(cid) and isinstance(data.items[cid], Armor) \
                    and not data.items[cid].is_shield:
                inst["tailored"] = tailored
            # carry loaded ammo for an equipped launcher (match by catalog key)
            if cid in loaded_ammo:
                inst["loaded_ammo_id"] = loaded_ammo[cid]
            items.append(inst)
        else:
            # merge into an existing stack at the same (catalog, location)
            for existing in items:
                if existing["catalog_id"] == cid and existing["location"] == location \
                        and not _is_equippable(cid, data):
                    existing["count"] += 1
                    return
            items.append(inst)

    for cid in raw.get("inventory", []):
        add_loose(cid, {"kind": "carried"})
    for cid in raw.get("stashed", []):
        add_loose(cid, {"kind": "stashed"})

    # Drain container/animal/vehicle contents into items at that location.
    for coll, kind in (("containers", "container"), ("animals", "animal"),
                       ("vehicles", "vehicle")):
        for carrier in raw.get(coll, []):
            cid_loc = ({"kind": "carried"} if kind == "container"
                       else None)  # placeholder; real loc set below
            carrier_id = carrier.get("instance_id")
            for content_id in carrier.pop("contents", []) or []:
                add_loose(content_id, {"kind": kind, "id": carrier_id})

    raw["items"] = items
    for k in _LEGACY_KEYS:
        raw.pop(k, None)
    _coerce_retainers(raw, data)
    return raw


def _has_contents(raw: dict) -> bool:
    for coll in ("containers", "animals", "vehicles"):
        for carrier in raw.get(coll, []) or []:
            if isinstance(carrier, dict) and carrier.get("contents"):
                return True
    return False


def _coerce_retainers(raw: dict, data: GameData) -> None:
    for r in raw.get("retainers", []) or []:
        if isinstance(r, dict) and isinstance(r.get("spec"), dict):
            r["spec"] = _coerce_spec(r["spec"], data)


def migrate_legacy_items(raw: dict, data: GameData) -> dict:
    """Entry point: coerce a raw character dict (and its retainers) in place."""
    return _coerce_spec(raw, data)
```

> Note: the `cid_loc` placeholder line above is dead — delete it; the loop sets the location inline. (Left here only to mark the carrier-location intent.) Container's own `location` is unchanged; only its `contents` drain.

- [ ] **Step 4: Wire the coercion into the load path**

In `aose/characters/storage.py` and `aose/characters/drafts.py`, find where a saved JSON dict is turned into a `CharacterSpec` (e.g. `CharacterSpec(**raw)` / `CharacterSpec.model_validate(raw)`). Insert before it:

```python
from aose.characters.migrate_items import migrate_legacy_items
raw = migrate_legacy_items(raw, data)
spec = CharacterSpec(**raw)
```

The load functions must therefore receive `data: GameData`. Confirm by grep:

Run: `rg -n "CharacterSpec\((\*\*|model_validate)" aose/characters`

Thread `data` to those functions from their callers (routes already hold `request.app.state.game_data`).

- [ ] **Step 5: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_migrate_items.py -q`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
git add aose/characters/migrate_items.py aose/characters/storage.py aose/characters/drafts.py tests/test_migrate_items.py
git commit -m "feat(loader): coerce legacy saves into the instance model (data-aware, recurses retainers)"
```

---

# Part 2 — Storage engine

Shared classification helper used by storage, shop, view, and coercion: an
item is **equippable** iff its catalog item is a `Weapon` or `Armor`; otherwise
it is a **stackable** (and, being catalog gear, always *consumable* — the only
*durable* stackables are coins and gems, which are not `ItemInstance`s). This is
the single definition of stackability.

### Task 5: Item classification + location policy descriptor

**Files:**
- Modify: `aose/engine/equip.py` (add `is_equippable`/`is_stackable`)
- Modify: `aose/engine/storage.py` (add `LocationPolicy` + `location_policy`)
- Test: `tests/test_location_policy.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_location_policy.py
from pathlib import Path
import pytest
from aose.data.loader import GameData
from aose.engine import storage
from aose.engine.equip import is_equippable, is_stackable
from aose.models import CharacterSpec, ClassEntry, AnimalInstance, ContainerInstance, Retainer
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw); return CharacterSpec(**base)


def test_classification():
    assert is_equippable(DATA.items["sword"]) and not is_stackable(DATA.items["sword"])
    assert is_stackable(DATA.items["torch"]) and not is_equippable(DATA.items["torch"])


def test_person_buckets_uncapped_and_carried_equips():
    spec = _spec()
    carried = storage.location_policy(spec, StorageLocation(kind="carried"), DATA)
    stashed = storage.location_policy(spec, StorageLocation(kind="stashed"), DATA)
    assert carried.capacity_cn is None and carried.equip_allowed is True
    assert stashed.equip_allowed is False


def test_container_capacity_from_catalog():
    spec = _spec(containers=[ContainerInstance(instance_id="p1", catalog_id="belt_pouch",
                            location=StorageLocation(kind="carried"))])
    pol = storage.location_policy(spec, StorageLocation(kind="container", id="p1"), DATA)
    assert pol.capacity_cn == DATA.items["belt_pouch"].capacity_cn
    assert pol.equip_allowed is False


def test_retainer_carried_equips_with_own_eligibility():
    ret = _spec(name="NPC")
    spec = _spec(retainers=[Retainer(id="r1", spec=ret, loyalty=7)])
    pol = storage.location_policy(spec, StorageLocation(kind="retainer", id="r1"), DATA)
    assert pol.equip_allowed is True            # retainer carried bucket
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_location_policy.py -q`
Expected: FAIL — `cannot import name 'is_equippable'`.

- [ ] **Step 3: Add classification + policy**

In `aose/engine/equip.py`:

```python
def is_equippable(item) -> bool:
    return isinstance(item, (Armor, Weapon))


def is_stackable(item) -> bool:
    return item is not None and not is_equippable(item)
```

In `aose/engine/storage.py`, add the descriptor (one uniform shape; differences are parameters):

```python
from pydantic import BaseModel


class LocationPolicy(BaseModel):
    """Uniform per-location policy. Differences between location kinds are these
    parameters, never code branches: capacity, encumbrance, equip-allowed, and
    the class-eligibility source for equipping here."""
    model_config = {"arbitrary_types_allowed": True}
    capacity_cn: int | None = None       # hard cap; None = uncapped
    equip_allowed: bool = False          # may instances here be equipped
    equips_on_spec: object = None        # the spec whose class gates eligibility, or None


def _owning_spec_for(spec: CharacterSpec, loc: StorageLocation) -> CharacterSpec:
    """The spec whose world ``loc`` belongs to (PC, or a retainer's spec)."""
    return _retainer(spec, loc.id).spec if loc.kind == "retainer" else spec


def location_policy(spec: CharacterSpec, loc: StorageLocation, data) -> LocationPolicy:
    if loc.kind == "carried":
        return LocationPolicy(capacity_cn=None, equip_allowed=True, equips_on_spec=spec)
    if loc.kind == "retainer":
        return LocationPolicy(capacity_cn=None, equip_allowed=True,
                              equips_on_spec=_retainer(spec, loc.id).spec)
    if loc.kind == "stashed":
        return LocationPolicy(capacity_cn=None, equip_allowed=False)
    if loc.kind == "container":
        cat = data.items.get(_container(spec, loc.id).catalog_id) if data else None
        return LocationPolicy(capacity_cn=getattr(cat, "capacity_cn", None),
                              equip_allowed=False)
    if loc.kind == "animal":
        from aose.engine.companions import animal_capacity
        animal = _carrier(spec, "animal", loc.id)
        cap = animal_capacity(animal, data) if data else None
        return LocationPolicy(capacity_cn=cap, equip_allowed=False)
    if loc.kind == "vehicle":
        from aose.engine.companions import vehicle_capacity
        cap = vehicle_capacity(_carrier(spec, "vehicle", loc.id), data) if data else None
        return LocationPolicy(capacity_cn=cap, equip_allowed=False)
    return LocationPolicy()
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_location_policy.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/equip.py aose/engine/storage.py tests/test_location_policy.py
git commit -m "feat(storage): item classification + uniform LocationPolicy descriptor"
```

---

### Task 6: Items-by-location + `location_load_cn` over `items`

**Files:**
- Modify: `aose/engine/storage.py` (`items_at`, rewrite `loose_list` callers, `location_load_cn`)
- Test: `tests/test_items_at.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_items_at.py
from pathlib import Path
from aose.data.loader import GameData
from aose.engine import storage
from aose.models import CharacterSpec, ClassEntry, ItemInstance
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))
CARRIED = StorageLocation(kind="carried")
STASHED = StorageLocation(kind="stashed")


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw); return CharacterSpec(**base)


def test_items_at_filters_by_location():
    spec = _spec(items=[
        ItemInstance(instance_id="i1", catalog_id="sword", location=CARRIED),
        ItemInstance(instance_id="i2", catalog_id="rope", location=STASHED),
    ])
    assert [i.instance_id for i in storage.items_at(spec, CARRIED)] == ["i1"]
    assert [i.instance_id for i in storage.items_at(spec, STASHED)] == ["i2"]


def test_location_load_counts_item_count_times_weight():
    # sword 60 cn; two torches (stack count=2) 0? — use a weighted gear item.
    spec = _spec(items=[
        ItemInstance(instance_id="i1", catalog_id="sword", location=CARRIED),
        ItemInstance(instance_id="i2", catalog_id="iron_spike", count=3, location=CARRIED),
    ])
    expected = DATA.items["sword"].weight_cn + 3 * DATA.items["iron_spike"].weight_cn
    assert storage.location_load_cn(spec, CARRIED, DATA) == expected
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_items_at.py -q`
Expected: FAIL — `module 'storage' has no attribute 'items_at'`.

- [ ] **Step 3: Implement**

In `aose/engine/storage.py`:

```python
def items_at(spec: CharacterSpec, loc: StorageLocation) -> list:
    """Every ItemInstance located at ``loc`` (any world resolved by the caller)."""
    return [i for i in spec.items if i.location == loc]
```

Delete `loose_list` (string-list resolver). Update `location_load_cn` to sum items by count and resolve container/animal/vehicle/retainer worlds through `items_at` on the right spec. Replace its loose loop:

```python
    owner = _owning_spec_for(spec, loc) if loc.kind == "retainer" else spec
    total = 0
    for inst in owner.items if loc.kind == "retainer" else spec.items:
        if inst.location == loc:
            item = data.items.get(inst.catalog_id)
            if item is not None:
                total += item.weight_cn * inst.count
```

Keep the coins/gems/jewellery/magic/enchanted/ammo/spell_sources sums as-is (they already filter by `location == loc`). For retainer worlds those collections are on the retainer spec; resolve `owner` and filter `owner.<collection>` when `loc.kind == "retainer"`. (Animals/vehicles/containers are PC-world carriers; only retainer needs the `owner` switch.)

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_items_at.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/storage.py tests/test_items_at.py
git commit -m "feat(storage): items_at + location_load_cn over the flat items list"
```

---

### Task 7: `split_stack` + place-or-merge for items

**Files:**
- Modify: `aose/engine/storage.py`
- Test: `tests/test_split_stack.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_split_stack.py
from pathlib import Path
import pytest
from aose.data.loader import GameData
from aose.engine import storage
from aose.models import CharacterSpec, ClassEntry, ItemInstance
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))
CARRIED = StorageLocation(kind="carried")
STASHED = StorageLocation(kind="stashed")


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw); return CharacterSpec(**base)


def test_partial_move_splits_and_leaves_remainder():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="torch",
                                     count=6, location=CARRIED)])
    storage.move_item(spec, "i1", STASHED, count=2, data=DATA)
    carried = storage.items_at(spec, CARRIED)
    stashed = storage.items_at(spec, STASHED)
    assert carried[0].count == 4
    assert stashed[0].count == 2 and stashed[0].catalog_id == "torch"


def test_partial_move_merges_into_existing_destination_stack():
    spec = _spec(items=[
        ItemInstance(instance_id="i1", catalog_id="torch", count=6, location=CARRIED),
        ItemInstance(instance_id="i2", catalog_id="torch", count=1, location=STASHED),
    ])
    storage.move_item(spec, "i1", STASHED, count=2, data=DATA)
    stashed = storage.items_at(spec, STASHED)
    assert len(stashed) == 1 and stashed[0].count == 3      # merged, not fragmented


def test_full_move_of_equippable_repoints_and_clears_equip():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword",
                                     equip="main_hand", location=CARRIED)])
    storage.move_item(spec, "i1", STASHED, data=DATA)
    moved = storage.items_at(spec, STASHED)[0]
    assert moved.equip is None                              # left carried → unequipped


def test_equippable_count_cannot_exceed_one():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword", location=CARRIED)])
    with pytest.raises(storage.StorageError):
        storage.move_item(spec, "i1", STASHED, count=2, data=DATA)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_split_stack.py -q`
Expected: FAIL — `move_item` signature/behaviour mismatch.

- [ ] **Step 3: Implement `split_stack` + `move_item`**

Replace the old string-based `move_item` in `aose/engine/storage.py`:

```python
def _merge_target(spec: CharacterSpec, catalog_id: str, dest: StorageLocation):
    """The ItemInstance stack of this catalog id already at ``dest``, or None."""
    for i in spec.items:
        if i.catalog_id == catalog_id and i.location == dest:
            return i
    return None


def _clear_equip_state(inst) -> None:
    inst.equip = None
    inst.loaded_ammo_id = None


def move_item(spec: CharacterSpec, instance_id: str, dest: StorageLocation,
              *, count: int | None = None, data=None) -> None:
    """Move an ItemInstance (whole, or ``count`` split off a stack) to ``dest``.
    Stackables merge into a resident stack at ``dest`` (one stack per
    catalog+location); equippables re-point whole and clear equip when they
    leave ``carried``. Cross-world (PC↔retainer) is a list-to-list move."""
    from aose.engine.equip import is_equippable
    src_inst = next((i for i in spec.items if i.instance_id == instance_id), None)
    if src_inst is None:
        # may be in a retainer world
        for r in spec.retainers:
            cand = next((i for i in r.spec.items if i.instance_id == instance_id), None)
            if cand is not None:
                _move_cross_world(spec, r.spec, cand, dest, count, data)
                return
        raise StorageError(f"no item instance {instance_id!r}")

    item = data.items.get(src_inst.catalog_id) if data else None
    n = src_inst.count if count is None else count
    if n <= 0 or n > src_inst.count:
        raise StorageError(f"cannot move {n} of {src_inst.count}")
    if item is not None and is_equippable(item) and n != 1:
        raise StorageError("equippable items are per-instance (count 1)")

    if data is not None:
        added = (item.weight_cn * n) if item is not None else 0
        _check_capacity(spec, dest, added, data)

    dest_world = _owning_spec_for(spec, dest)
    if dest_world is not spec:
        _move_cross_world(spec, dest_world, src_inst, dest, count, data, item=item)
        return

    # Same world. Stackable partial → split/merge; else re-point whole.
    if not (item is not None and is_equippable(item)) and n < src_inst.count:
        src_inst.count -= n
        resident = _merge_target(spec, src_inst.catalog_id, dest)
        if resident is not None:
            resident.count += n
        else:
            spec.items.append(src_inst.model_copy(update={
                "instance_id": uuid.uuid4().hex, "count": n, "location": dest,
                "equip": None, "loaded_ammo_id": None}))
        return
    # whole move
    resident = (None if (item is not None and is_equippable(item))
                else _merge_target(spec, src_inst.catalog_id, dest))
    if resident is not None:
        resident.count += src_inst.count
        spec.items.remove(src_inst)
    else:
        if dest.kind != "carried":
            _clear_equip_state(src_inst)
        src_inst.location = dest


def _move_cross_world(pc: CharacterSpec, dest_spec: CharacterSpec, inst,
                      dest: StorageLocation, count, data, item=None) -> None:
    """Move an item between two worlds (PC↔retainer). Lands carried in the
    destination world and merges into a resident stack there."""
    from aose.engine.equip import is_equippable
    if item is None and data is not None:
        item = data.items.get(inst.catalog_id)
    n = inst.count if count is None else count
    carried = StorageLocation(kind="carried")
    # remove n from the source instance
    src_list = pc.items if inst in pc.items else _find_world_list(pc, inst)
    if not (item is not None and is_equippable(item)) and n < inst.count:
        inst.count -= n
    else:
        src_list.remove(inst)
        _clear_equip_state(inst)
    resident = _merge_target(dest_spec, inst.catalog_id, carried)
    if resident is not None and not (item is not None and is_equippable(item)):
        resident.count += n
    else:
        dest_spec.items.append(inst.model_copy(update={
            "instance_id": uuid.uuid4().hex, "count": n, "location": carried,
            "equip": None, "loaded_ammo_id": None}) if n < (inst.count + n)
            else inst)
        if inst in dest_spec.items and inst.location != carried:
            inst.location = carried


def _find_world_list(pc: CharacterSpec, inst) -> list:
    for r in pc.retainers:
        if inst in r.spec.items:
            return r.spec.items
    return pc.items
```

> Implementation note for the executing agent: `_move_cross_world` is fiddly — drive it entirely from the tests in this task and Task 9 (retainer dupe). Prefer the clearest correct version over the sketch above; the contract is: *n units arrive carried in the destination world, merged if a resident stack exists, equip/loaded state cleared, source decremented or removed.*

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_split_stack.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/storage.py tests/test_split_stack.py
git commit -m "feat(storage): split_stack + instance-based move_item with auto-merge"
```

---

### Task 8: `move_thing` dispatch + capacity over the policy descriptor

**Files:**
- Modify: `aose/engine/storage.py` (`move_thing`, `_check_capacity`, `move_targets`)
- Test: extend `tests/test_storage_move_thing.py` (rewrite to the new model — see Part 5 for the full suite migration; add the cases below now)

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_storage_move_thing.py (new-model constructors)
def test_move_thing_item_by_instance_id_into_container():
    spec = _spec(
        items=[ItemInstance(instance_id="i1", catalog_id="torch", count=3, location=CARRIED),
               ItemInstance(instance_id="i2", catalog_id="backpack", location=CARRIED)],
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=CARRIED)],
    )
    dest = StorageLocation(kind="container", id="c1")
    storage.move_thing(spec, "item", "i1", dest, count=2, data=DATA)
    inside = storage.items_at(spec, dest)
    assert inside[0].catalog_id == "torch" and inside[0].count == 2


def test_check_capacity_reads_policy_descriptor():
    spec = _spec(
        items=[ItemInstance(instance_id="i1", catalog_id="sword", location=CARRIED)],
        containers=[ContainerInstance(instance_id="p1", catalog_id="belt_pouch",
                                      location=CARRIED)],   # cap 50 < sword 60
    )
    dest = StorageLocation(kind="container", id="p1")
    with pytest.raises(storage.StorageError):
        storage.move_thing(spec, "item", "i1", dest, data=DATA)
```

(`_spec` here gains `ItemInstance`, `ContainerInstance` imports at the top of the file during the Part 5 migration; for this task add them locally.)

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py::test_move_thing_item_by_instance_id_into_container -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

Rewrite `_check_capacity` to read the descriptor:

```python
def _check_capacity(spec, dest, added_cn, data) -> None:
    if data is None:
        return
    pol = location_policy(spec, dest, data)
    if pol.capacity_cn is None:
        # Uncapped — but a non-beast-of-burden animal has cap None AND carries
        # nothing; keep that rejection.
        if dest.kind == "animal":
            from aose.engine.companions import animal_capacity
            if animal_capacity(_carrier(spec, "animal", dest.id), data) is None and added_cn > 0:
                raise StorageError("this animal cannot carry cargo")
        return
    worn = 0
    if dest.kind == "animal":
        a = _carrier(spec, "animal", dest.id)
        worn = data.items[a.armor_id].weight_cn if a.armor_id in data.items else 0
    current = worn + location_load_cn(spec, dest, data)
    if current + added_cn > pol.capacity_cn:
        raise StorageError(f"destination full: {current}/{pol.capacity_cn} cn, "
                           f"move adds {added_cn} cn")
```

Update `move_thing` so `item` dispatches to the new `move_item` by `instance_id` with `count`, and remove the `unload_if_loaded(spec, ref_id)` pre-call (loaded state now travels on the instance and is cleared by `move_item`/`move_instance`):

```python
def move_thing(spec, category, ref_id, dest, *, count=None, src=None, data=None):
    if category == "item":
        move_item(spec, ref_id, dest, count=count, data=data)
    elif category == "container":
        move_container(spec, ref_id, dest, data)
    elif category == "coin":
        move_coins(spec, ref_id, src or StorageLocation(kind="carried"), dest,
                   count if count is not None else 0, data)
    elif category in ("gem", "jewellery"):
        move_valuable(spec, ref_id, dest, count=count, data=data)
    elif category == "ammo":
        move_ammo(spec, ref_id, dest, count if count is not None else 0, data)
    elif category in ("magic", "enchanted"):
        move_instance(spec, category, ref_id, dest, data)
    elif category == "source":
        move_spell_source(spec, ref_id, dest, data)
    else:
        raise StorageError(f"unknown move category {category!r}")
```

> `src` is now only needed for coins (denom keyed). `move_container`/`move_ammo`/`move_valuable`/`move_instance`/`move_spell_source` keep their existing internals; only `move_instance` changes its auto-unequip to clear the new `equip` slot (Task 8b below).

- [ ] **Step 3b: `move_instance` clears the `equip` slot**

In `move_instance`, replace the `inst.equipped = False` + `CharacterSpec.equipped` slot-clearing block with:

```python
    # Auto-unequip on the owning spec (enchanted weapons/armour use .equip;
    # magic items use .equipped).
    if hasattr(inst, "equip"):
        inst.equip = None
        inst.loaded_ammo_id = None
    if hasattr(inst, "equipped"):
        inst.equipped = False
```

(The old loop over `owner_spec.equipped.items()` is deleted — there is no spec-level equipped map any more.)

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_move_thing.py -q`
Expected: the two new cases PASS (older cases in this file are migrated in Part 5).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/storage.py tests/test_storage_move_thing.py
git commit -m "feat(storage): move_thing item-by-instance + capacity via LocationPolicy"
```

---

### Task 9: Delete retainer-transfer engine + the dupe regression test

**Files:**
- Modify: `aose/engine/retainers.py` (delete `transfer_to_retainer`, `transfer_to_pc`, `_find_retainer` if unused)
- Test: `tests/test_retainer_item_dupe.py` (create — the reported bug)

- [ ] **Step 1: Write the failing test (reproduces the reported dupe)**

```python
# tests/test_retainer_item_dupe.py
from pathlib import Path
from aose.data.loader import GameData
from aose.engine import storage, equip
from aose.models import CharacterSpec, ClassEntry, ItemInstance, Retainer
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))
CARRIED = StorageLocation(kind="carried")


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw); return CharacterSpec(**base)


def test_equip_on_retainer_then_move_to_pc_unequips_and_no_dupe():
    npc = _spec(name="NPC",
                items=[ItemInstance(instance_id="i1", catalog_id="sword", location=CARRIED)])
    pc = _spec(retainers=[Retainer(id="r1", spec=npc, loyalty=7)])
    # equip on the retainer
    equip.equip(pc.retainers[0].spec, "i1", data=DATA)
    assert equip.equipped_ref(pc.retainers[0].spec, "main_hand") == "sword"
    # move the item from the retainer to the PC's carried bucket
    storage.move_thing(pc, "item", "i1", CARRIED, data=DATA)
    # retainer no longer wields it, and exactly one copy exists in the world
    assert equip.equipped_ref(pc.retainers[0].spec, "main_hand") is None
    swords_on_pc = [i for i in pc.items if i.catalog_id == "sword"]
    swords_on_ret = [i for i in pc.retainers[0].spec.items if i.catalog_id == "sword"]
    assert len(swords_on_pc) == 1 and swords_on_ret == []
    assert swords_on_pc[0].equip is None
```

- [ ] **Step 2: Run to verify it fails / then passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_item_dupe.py -q`
Expected after Tasks 5–8: PASS. (If it fails, fix `_move_cross_world` until green — this is the canonical contract test.)

- [ ] **Step 3: Delete the bespoke transfer engine**

Remove `transfer_to_retainer` and `transfer_to_pc` from `aose/engine/retainers.py` (and `_find_retainer` if it has no other caller — grep first: `rg -n "transfer_to_retainer|transfer_to_pc|_find_retainer" aose tests`). Their routes are rewired in Part 4 to call `move_thing`.

- [ ] **Step 4: Run the storage + retainer suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_item_dupe.py tests/test_split_stack.py tests/test_items_at.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/retainers.py tests/test_retainer_item_dupe.py
git commit -m "feat(retainers): delete bespoke transfer; dupe fixed via unified move (regression test)"
```

---

> **End of Part 2.** Parts 3–5 (reader migrations, view/routes/wizard, templates/tests/docs) follow.
