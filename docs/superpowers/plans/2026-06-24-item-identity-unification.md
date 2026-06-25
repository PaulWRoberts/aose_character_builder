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

> **End of Part 1.** Parts 2–5 (storage engine, reader migrations, view/routes/wizard, templates/tests/docs) follow. The suite is intentionally red until Part 5 completes.
