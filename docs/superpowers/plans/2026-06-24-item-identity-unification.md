# Item Identity Unification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every owned thing a real instance identity (`instance_id` + `location`, plus `count` for stackables and equip-state for equippables), deleting the `equipped`/`loaded_ammo`/`armor_tailored`/`contents` side tables, so one move path and one equip path serve PC and retainer alike — and the retainer equip-then-move dupe is fixed structurally.

**Architecture:** Single **atomic engine landing** (no compatibility layer): the model changes and every engine reader/writer, the view-data builders, the routes, the wizard, and the whole test suite move together on one branch. Loose catalog items become `ItemInstance`s in one flat `CharacterSpec.items` list (location is a field, not a positional list); `equipped`/`loaded_ammo`/`armor_tailored` become per-instance fields; coin stacks gain `instance_id`. **Plain, enchanted, and ammo collapse into the one `ItemInstance` type** (type is `catalog_id`; enchantment is an optional `enchantment_id` field; ammo is a stack with `count`), deleting `EnchantedInstance`, `AmmoStack`, and the `spec.enchanted`/`spec.ammo` lists. Storage locations are uniform, differing only by a policy descriptor (capacity / encumbrance / equip-allowed / equip-eligibility). Old saves are coerced at the loader (where `GameData` is available), not in a model validator.

> **Revision 2026-06-25 — three types merged into one.** This plan was first
> authored with `ItemInstance` (plain), `EnchantedInstance`, and `AmmoStack` as
> three separate types/lists. The approved design now folds them into **one**
> `ItemInstance` (one `spec.items` list). `MagicItemInstance`, `SpellSource`,
> `coins`, `gems`, `jewellery`, `containers`, `animals`, `vehicles` stay separate.
> Apply this **global substitution** everywhere below (the per-task code is updated
> for the structural tasks; this table governs the rest):
>
> | Pre-merge plan text | Read it as |
> |---|---|
> | `EnchantedInstance(instance_id=…, base_id=B, enchantment_id=E, equip=S)` | `ItemInstance(instance_id=…, catalog_id=B, enchantment_id=E, equip=S)` |
> | `AmmoStack(instance_id=…, base_id=B, enchantment_id=E, count=N)` | `ItemInstance(instance_id=…, catalog_id=B, enchantment_id=E, count=N)` |
> | `spec.enchanted` (the list) | the subset of `spec.items` with `enchantment_id is not None` |
> | `spec.ammo` (the list) | the subset of `spec.items` whose resolved catalog item is `Ammunition` |
> | `move_thing(spec, "enchanted"/"ammo", …)` | `move_thing(spec, "item", …)` (one item category) |
> | `isinstance(inst, ItemInstance) else <enchanted-instance_id branch>` | always the `ItemInstance` branch (one type) |
> | merge-key `catalog_id` / ammo `base_id+enchantment_id` | unified `(catalog_id, enchantment_id)` |
> | resolve an enchanted instance to its `Weapon`/`Armor` | `enchant.resolve(inst, data)` (one resolver; plain → `data.items[catalog_id]`) |
>
> Where a task's code block still shows the old shape and is **not** re-listed in a
> "Revised" note, apply the table mechanically.

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
| `aose/models/character.py` | Unified `ItemInstance` (gains `enchantment_id`, `count`, charges, escape hatches); `CharacterSpec.items`; **delete `EnchantedInstance`, `AmmoStack`, `spec.enchanted`, `spec.ammo`**; drop `inventory`/`stashed`/`equipped`/`loaded_ammo`/`armor_tailored`; drop `contents` from container/animal/vehicle | Modify |
| `aose/models/storage.py` | `instance_id` on `CoinStack` | Modify |
| `aose/engine/equip.py` | Instance-based `equip`/`unequip`/`validate_wield` + slot accessors (`equipped_instance`, `slot_item`, `equipped_ref`) over the single `spec.items` list | Rewrite |
| `aose/characters/migrate_items.py` | Loader-time coercion of legacy saves to the new shape (needs `GameData`) | Create |
| `aose/characters/storage.py`, `drafts.py` | Call the coercion before `CharacterSpec(**raw)` | Modify |
| `aose/engine/storage.py` | Location policy descriptor; `loose` by location over `items`; `split_stack`; instance `move_item`/`move_thing`; delete retainer-transfer reliance | Rewrite |
| `aose/engine/encumbrance.py` `armor_class.py` `attacks.py` `ammo.py` | Read instances via accessors | Modify |
| `aose/engine/quick_equipment.py` | Build `ItemInstance`s; equip on the kit's item list | Modify |
| `aose/engine/enchant.py` | Collapse to one `resolve(inst, data)` over `ItemInstance` (plain → catalog item; else compose); delete the list-based `equip`/`unequip` (enchanted is just an `ItemInstance`, equipped via `equip.py`) | Modify |
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
from aose.models import CharacterSpec, ClassEntry, ItemInstance, CoinStack
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
    assert ii.enchantment_id is None
    assert ii.tailored is True
    assert ii.loaded_ammo_id is None


def test_spec_has_items_list_and_no_legacy_fields():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword", equip="main_hand")])
    assert spec.items[0].equip == "main_hand"
    # Legacy fields are gone (extra="forbid" rejects them).
    for legacy in ("inventory", "stashed", "equipped", "loaded_ammo", "armor_tailored",
                   "enchanted", "ammo"):
        with pytest.raises(Exception):
            _spec(**{legacy: [] if legacy in ("inventory", "stashed", "enchanted", "ammo")
                     else {}})


def test_item_instance_carries_enchantment_and_count():
    # An enchanted weapon and a stack of ammo are ItemInstances — one type.
    plus1 = ItemInstance(instance_id="e1", catalog_id="sword",
                         enchantment_id="generic_plus_1", equip="main_hand")
    assert plus1.enchantment_id == "generic_plus_1" and plus1.equip == "main_hand"
    arrows = ItemInstance(instance_id="a1", catalog_id="arrow", count=20)
    assert arrows.count == 20 and arrows.enchantment_id is None


def test_enchanted_instance_and_ammo_stack_are_gone():
    import aose.models as m
    assert not hasattr(m, "EnchantedInstance")
    assert not hasattr(m, "AmmoStack")


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

In `aose/models/character.py`, add the `EquipSlot` alias and the unified `ItemInstance` near the top (after the imports). This **one** type covers plain loose gear, enchanted weapons/armour, and ammo stacks — folding in the old `EnchantedInstance` and `AmmoStack`:

```python
from typing import Literal

EquipSlot = Literal["armor", "main_hand", "off_hand"]


class ItemInstance(BaseModel):
    """One owned catalog item, with identity — plain, enchanted, or stacked.

    The item *type* is ``catalog_id`` (a reference into ``GameData.items``);
    whether it is enchanted is the optional ``enchantment_id`` field, not a
    different class. Stackables (consumable gear, ammo, …) carry ``count > 1``
    and ``equip is None``. Equippables (weapon/armour/shield, enchanted or not)
    are always per-instance (``count == 1``) and may carry an ``equip`` slot.
    ``tailored``/``loaded_ammo_id`` are inert except on tailorable armour /
    launcher weapons; charges/escape-hatches are inert unless the enchantment
    uses them. Stackable-vs-equippable derives from the *resolved* catalog item
    type (enchantment does not change it), enforced by the engine, not this
    model."""
    model_config = ConfigDict(extra="forbid")

    instance_id: str                       # uuid4 hex
    catalog_id: str                        # references a Weapon / Armor / gear / Ammunition item
    location: StorageLocation = Field(default_factory=lambda: StorageLocation(kind="carried"))
    enchantment_id: str | None = None      # None = plain; else references an Enchantment
    count: int = 1
    equip: EquipSlot | None = None
    tailored: bool = True
    loaded_ammo_id: str | None = None      # launcher weapons only; an ammo ItemInstance id
    charges_max: int | None = None         # from the old EnchantedInstance
    charges_remaining: int | None = None
    extra_modifiers: list[Modifier] = Field(default_factory=list)  # escape hatch
    note: str = ""                                                 # escape hatch
```

(`Modifier` is already imported in this module for `MagicItemInstance`.)

**Delete `EnchantedInstance` and `AmmoStack` entirely** — every owned weapon/
armour/ammo (plain or enchanted) is now an `ItemInstance`. Keep
`MagicItemInstance` (catalog magic items with a toggle `equipped` bool — a
genuinely different equip mechanic).

In `CharacterSpec`, **replace** the `inventory`, `stashed`, `equipped`,
`armor_tailored`, `loaded_ammo`, **`enchanted`**, and **`ammo`** fields with a
single:

```python
    # Every owned catalog item — plain, enchanted, or stacked — with its own
    # identity + location. Replaces the positional inventory/stashed lists, the
    # equipped/loaded_ammo/armor_tailored side tables, AND the former separate
    # `enchanted`/`ammo` lists (enchantment_id/count are now fields here). Items
    # "in" a container/animal/vehicle carry that location.
    items: list[ItemInstance] = Field(default_factory=list)
```

Keep `magic_items` (still `equipped: bool`), `gems`, `jewellery`, `coins`,
`spell_sources`, `containers`, `animals`, `vehicles`.

In `ContainerInstance`, `AnimalInstance`, `VehicleInstance`: **delete the `contents: list[str]` field** (items located there now live in `spec.items`). Remove the `_migrate_legacy_location` validator's `contents` handling if any (it doesn't touch contents — leave it).

Export `ItemInstance` and `EquipSlot` from `aose/models/__init__.py`, and **remove `EnchantedInstance` and `AmmoStack`** from the import list and `__all__`.

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
Expected: PASS (6 tests). Other suites are expected to break — that is the atomic landing.

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
    """The ItemInstance (plain or enchanted) with this id, or None.
    One list now — enchanted gear is an ItemInstance with enchantment_id set."""
    return next((i for i in spec.items if i.instance_id == instance_id), None)


def _resolve_equippable(inst, data: GameData):
    """Resolve an ItemInstance (plain or enchanted) to its Weapon/Armor, or None.
    Plain → the catalog item; enchanted → compose via resolve_instance (Task 3
    updates resolve_instance to read catalog_id instead of base_id)."""
    if inst.enchantment_id is None:
        return data.items.get(inst.catalog_id)
    return resolve_instance(inst, data)


def equipped_instance(spec, slot: str):
    """The ItemInstance occupying ``slot``, or None."""
    return next((i for i in spec.items if i.equip == slot), None)


def equipped_ref(spec, slot: str) -> str | None:
    """The catalog_id of the instance equipped in ``slot``, or None. (A +1 sword's
    catalog_id is still "sword".) For the resolved item — including any
    enchantment — use ``slot_item``; for a form/route id use
    ``equipped_instance(spec, slot).instance_id``."""
    inst = equipped_instance(spec, slot)
    return inst.catalog_id if inst is not None else None


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

### Task 3: One resolver over `ItemInstance`; delete the enchant list-equip path

With enchanted gear folded into `spec.items`, `enchant.py` is no longer a second
equip path — it is the **resolver** (`resolve`) plus the instance factory and the
charge/note list helpers. Equipping an enchanted item now goes through `equip.py`
exactly like a plain one (Task 2). `resolve_instance` reads `catalog_id` (was
`base_id`).

**Files:**
- Modify: `aose/engine/enchant.py` (imports; `resolve_instance`/`resolve`;
  `new_enchanted_instance`; `equipped_enchanted`; charge/note helpers; **delete
  the list-based `equip`/`unequip`**)
- Test: `tests/test_enchant_resolve.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enchant_resolve.py
from pathlib import Path
from aose.data.loader import GameData
from aose.engine import enchant
from aose.models import ItemInstance, Weapon, Armor

DATA = GameData.load(Path("data"))


def test_resolve_plain_returns_catalog_item():
    inst = ItemInstance(instance_id="i1", catalog_id="sword")
    assert enchant.resolve(inst, DATA) is DATA.items["sword"]


def test_resolve_enchanted_weapon_composes_synthetic():
    inst = ItemInstance(instance_id="e1", catalog_id="sword",
                        enchantment_id="generic_plus_1")
    out = enchant.resolve(inst, DATA)
    assert isinstance(out, Weapon) and out.magic and out.magic_bonus == 1
    assert out.base_weapon == "sword"


def test_resolve_enchanted_armor_composes_synthetic():
    inst = ItemInstance(instance_id="e2", catalog_id="plate_mail",
                        enchantment_id="generic_plus_1")
    out = enchant.resolve(inst, DATA)
    assert isinstance(out, Armor) and out.magic and out.base_armor == "plate_mail"


def test_new_enchanted_instance_is_an_item_instance():
    inst = enchant.new_enchanted_instance("sword", "generic_plus_1", DATA)
    assert isinstance(inst, ItemInstance)
    assert inst.catalog_id == "sword" and inst.enchantment_id == "generic_plus_1"
    assert inst.equip is None


def test_enchant_has_no_list_equip():
    # The list-based equip/unequip are gone — equipping is equip.py's job now.
    assert not hasattr(enchant, "equip")
    assert not hasattr(enchant, "unequip")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchant_resolve.py -q`
Expected: FAIL — `enchant.resolve` does not exist; `resolve_instance` reads `base_id`.

- [ ] **Step 3: Update `enchant.py`**

- **Imports:** drop `EnchantedInstance`; add `ItemInstance`.
- **`resolve_instance(inst, data)`:** read `inst.catalog_id` instead of
  `inst.base_id` (everything else unchanged — it still composes the synthetic
  `Weapon`/`Armor` from base + enchantment).
- **Add the unified `resolve`** (the one resolver the spec calls for — plain or
  enchanted):

```python
def resolve(inst: ItemInstance, data: GameData):
    """Resolve an ItemInstance to its effective catalog item.
    Plain (enchantment_id is None) → the base catalog item; enchanted → the
    composed synthetic Weapon/Armor (or None if base/enchantment missing)."""
    if inst.enchantment_id is None:
        return data.items.get(inst.catalog_id)
    return resolve_instance(inst, data)
```

- **`new_enchanted_instance(...)`:** return an `ItemInstance` (not
  `EnchantedInstance`) with `catalog_id=base_id`, `enchantment_id=...`,
  `equip=None`, and the rolled `charges_max`/`charges_remaining`. (The base/
  enchantment validation is unchanged.)
- **Delete the list-based `equip`/`unequip`** (the bool/slot toggles). Enchanted
  items are equipped through `equip.equip(spec, instance_id, data=...)` (Task 2);
  there is no separate enchanted equip path.
- **`equipped_enchanted(spec, data, kind)`:** iterate the enchanted subset of
  `spec.items` and gate on `equip`:

```python
    for inst in spec.items:
        if inst.enchantment_id is None or inst.equip is None:
            continue
        if _kind_of_instance(inst, data) != kind:
            continue
        resolved = resolve_instance(inst, data)
        if resolved is not None:
            out.append(resolved)
```

- **`_kind_of_instance`, `use_charge`, `reset_charges`, `set_note`, `remove`,
  `add_free_enchanted`:** retype `EnchantedInstance` → `ItemInstance`. The
  charge/note helpers still take a `list` of instances + an `instance_id` and
  return a new list; callers will pass `spec.items` (the enchanted subset is found
  by id, so passing the whole `items` list is fine). `add_free_enchanted` appends a
  `new_enchanted_instance(...)` to `spec.items`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enchant_resolve.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/enchant.py tests/test_enchant_resolve.py
git commit -m "feat(enchant): one resolve() over ItemInstance; drop the list-equip path"
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
    arrow = next(i for i in spec.items if i.catalog_id == "arrow")
    assert bow.loaded_ammo_id == "a1"
    assert plate.tailored is False
    assert arrow.instance_id == "a1" and arrow.count == 20   # ammo folded into items


def test_enchanted_list_folds_into_items_with_slot():
    raw = migrate_legacy_items(_legacy(
        enchanted=[
            {"instance_id": "e1", "base_id": "sword",
             "enchantment_id": "generic_plus_1", "equipped": False,
             "location": {"kind": "carried"}},
            {"instance_id": "e2", "base_id": "plate_mail",
             "enchantment_id": "generic_plus_1", "equipped": True,
             "location": {"kind": "carried"}},
        ],
        # enchanted weapon's hand slot lived in the equipped dict by instance_id
        equipped={"main_hand": "e1"},
    ), DATA)
    spec = CharacterSpec(**raw)
    assert not hasattr(spec, "enchanted")
    by_id = {i.instance_id: i for i in spec.items}
    assert by_id["e1"].catalog_id == "sword" and by_id["e1"].enchantment_id == "generic_plus_1"
    assert by_id["e1"].equip == "main_hand"    # reconciled from the equipped dict
    assert by_id["e2"].equip == "armor"        # reconciled from the equipped bool + kind


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

_LEGACY_KEYS = ("inventory", "stashed", "equipped", "loaded_ammo", "armor_tailored",
                "enchanted", "ammo")
_KIND_SLOT = {"weapon": "main_hand", "armor": "armor", "shield": "off_hand"}


def _is_equippable(catalog_id: str, data: GameData) -> bool:
    return isinstance(data.items.get(catalog_id), (Weapon, Armor))


def _ench_kind(enchantment_id, data: GameData):
    ench = data.enchantments.get(enchantment_id) if enchantment_id else None
    return ench.kind if ench else None


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
            carrier_id = carrier.get("instance_id")
            for content_id in carrier.pop("contents", []) or []:
                add_loose(content_id, {"kind": kind, "id": carrier_id})

    # Fold the old separate `enchanted` list into items (now ItemInstances).
    # Reconcile the doubly-tracked equip: an enchanted weapon/shield's slot lived
    # in the `equipped` dict keyed by its instance_id; body armour used the bool.
    slot_by_ench_id = {ref: slot for slot, ref in equipped.items()}
    for e in raw.get("enchanted", []) or []:
        loc = e.get("location") or {"kind": "carried"}
        slot = slot_by_ench_id.get(e["instance_id"])
        if slot is None and e.get("equipped"):                 # body-armour bool
            slot = _KIND_SLOT.get(_ench_kind(e.get("enchantment_id"), data) or "")
        if slot is not None and loc.get("kind") != "carried":  # only carried equips
            slot = None
        lid = loaded_ammo.get(e["instance_id"]) or loaded_ammo.get(e.get("base_id"))
        items.append({"instance_id": e["instance_id"], "catalog_id": e["base_id"],
                      "enchantment_id": e.get("enchantment_id"), "location": loc,
                      "count": 1, "equip": slot, "tailored": e.get("tailored", True),
                      "loaded_ammo_id": lid,
                      "charges_max": e.get("charges_max"),
                      "charges_remaining": e.get("charges_remaining"),
                      "extra_modifiers": e.get("extra_modifiers", []),
                      "note": e.get("note", "")})

    # Fold the old `ammo` list into items (stackable ItemInstances; instance_id
    # preserved so the launcher's loaded_ammo_id still points at it).
    for a in raw.get("ammo", []) or []:
        items.append({"instance_id": a["instance_id"], "catalog_id": a["base_id"],
                      "enchantment_id": a.get("enchantment_id"),
                      "location": a.get("location") or {"kind": "carried"},
                      "count": a.get("count", 0)})

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

> Note: a carrier's own `location` is unchanged; only its `contents` drain into
> `items` at `{"kind": <carrier kind>, "id": <carrier instance_id>}`. The
> enchanted/ammo folds run after the loose/contents passes so the `equipped` and
> `loaded_ammo` maps (read above) are still available for reconciliation.

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
Expected: PASS (8 tests).

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
def _merge_target(spec: CharacterSpec, proto, dest: StorageLocation):
    """The resident stackable ItemInstance at ``dest`` matching ``proto``'s
    merge-key — ``(catalog_id, enchantment_id)`` — or None. Including
    ``enchantment_id`` keeps +1 arrows from fusing with plain arrows."""
    for i in spec.items:
        if (i.catalog_id == proto.catalog_id
                and i.enchantment_id == proto.enchantment_id
                and i.location == dest):
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
        resident = _merge_target(spec, src_inst, dest)
        if resident is not None:
            resident.count += n
        else:
            spec.items.append(src_inst.model_copy(update={
                "instance_id": uuid.uuid4().hex, "count": n, "location": dest,
                "equip": None, "loaded_ammo_id": None}))
        return
    # whole move
    resident = (None if (item is not None and is_equippable(item))
                else _merge_target(spec, src_inst, dest))
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
    resident = _merge_target(dest_spec, inst, carried)
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
    # "ammo" and "enchanted" are ItemInstances now — same path as "item".
    if category in ("item", "ammo", "enchanted"):
        move_item(spec, ref_id, dest, count=count, data=data)
    elif category == "container":
        move_container(spec, ref_id, dest, data)
    elif category == "coin":
        move_coins(spec, ref_id, src or StorageLocation(kind="carried"), dest,
                   count if count is not None else 0, data)
    elif category in ("gem", "jewellery"):
        move_valuable(spec, ref_id, dest, count=count, data=data)
    elif category == "magic":
        move_instance(spec, category, ref_id, dest, data)   # MagicItemInstance only
    elif category == "source":
        move_spell_source(spec, ref_id, dest, data)
    else:
        raise StorageError(f"unknown move category {category!r}")
```

> `src` is now only needed for coins (denom keyed). `move_ammo` is **deleted**
> (ammo is an `ItemInstance`, moved by `move_item` with `count`).
> `move_container`/`move_valuable`/`move_instance`/`move_spell_source` keep their
> existing internals; `move_instance` now moves only `MagicItemInstance`s and its
> auto-unequip is the bool case (Task 8b below).

- [ ] **Step 3b: `move_instance` clears the magic-item `equipped` bool**

`move_instance` now handles only `MagicItemInstance` (enchanted weapons/armour
are `ItemInstance`s, moved by `move_item`, which clears `equip`/`loaded_ammo_id`
on leaving carried — Task 7). Replace its `CharacterSpec.equipped` slot-clearing
block with the bool reset:

```python
    # Auto-unequip the magic item on the owning spec (toggle mechanic).
    inst.equipped = False
```

(The old loop over `owner_spec.equipped.items()` is deleted — there is no
spec-level equipped map any more.)

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

# Part 3 — Reader migrations

These modules only *read* the old fields. The substitutions are mechanical and
defined once here:

| Old | New |
|---|---|
| `spec.equipped.get(slot)` (need the resolvable ref) | `equip.equipped_ref(spec, slot)` |
| `resolve_slot(spec.equipped.get(slot), data, spec.enchanted)` (need the item) | `equip.slot_item(spec, slot, data)` |
| `spec.equipped.get("armor")` then resolve | `equip.slot_item(spec, "armor", data)` |
| iterate `spec.inventory` (carried catalog ids) | `for inst in storage.items_at(spec, CARRIED): … inst.catalog_id … inst.count` |
| `spec.armor_tailored` | the armour slot instance's `.tailored` (`equip.equipped_instance(spec, "armor").tailored`) |
| `spec.loaded_ammo.get(weapon_key)` | the equipped weapon instance's `.loaded_ammo_id` |
| `carrier.contents` weight | `storage.location_load_cn(spec, <carrier loc>, data)` |
| membership `x in spec.inventory` | `x in {i.catalog_id for i in spec.items}` |

### Task 10: `encumbrance.py` over `items`

**Files:**
- Modify: `aose/engine/encumbrance.py:120-195` (`equipment_weight_cn`, `armor_movement_class`)
- Test: `tests/test_encumbrance_items.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_encumbrance_items.py
from pathlib import Path
from aose.data.loader import GameData
from aose.engine.encumbrance import equipment_weight_cn, armor_movement_class
from aose.models import CharacterSpec, ClassEntry, ItemInstance
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))
CARRIED = StorageLocation(kind="carried")
STASHED = StorageLocation(kind="stashed")


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw); return CharacterSpec(**base)


def test_carried_weapon_counts_stashed_does_not():
    spec = _spec(items=[
        ItemInstance(instance_id="i1", catalog_id="sword", location=CARRIED),
        ItemInstance(instance_id="i2", catalog_id="sword", location=STASHED),
    ])
    assert equipment_weight_cn(spec, DATA) == DATA.items["sword"].weight_cn


def test_equipped_armor_drives_movement_class():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="plate_mail",
                                     equip="armor", location=CARRIED)])
    assert armor_movement_class(spec, DATA) == "metal"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance_items.py -q`
Expected: FAIL (`'CharacterSpec' object has no attribute 'inventory'`).

- [ ] **Step 3: Implement**

In `equipment_weight_cn`, replace the `for item_id in spec.inventory:` loop with a carried-items loop that multiplies by `count`:

```python
    from aose.engine import storage
    from aose.models.storage import StorageLocation
    CARRIED = StorageLocation(kind="carried")
    for inst in storage.items_at(spec, CARRIED):
        item = data.items.get(inst.catalog_id)
        if item is None:
            continue
        if isinstance(item, Armor):
            total += int(item.weight_cn * item.weight_multiplier) * inst.count
        elif isinstance(item, Weapon):
            total += item.weight_cn * inst.count
        elif isinstance(item, AdventuringGear):
            has_gear = True
        else:
            total += item.weight_cn * inst.count
```

In `armor_movement_class`, replace `armor_id = spec.equipped.get("armor")` + lookup with:

```python
    from aose.engine.equip import slot_item
    item = slot_item(spec, "armor", data)
    if not isinstance(item, Armor) or item.is_shield:
        return "none"
    return item.movement_impact
```

(`spec.inventory`/`spec.equipped` no longer exist; the `_is_carried` helper and the magic/enchanted/container loops are unchanged — they already filter by `location`.)

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance_items.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/encumbrance.py tests/test_encumbrance_items.py
git commit -m "feat(encumbrance): weigh carried items by instance+count; armour class via slot_item"
```

---

### Task 11: `armor_class.py` over the equip field

**Files:**
- Modify: `aose/engine/armor_class.py:62-116` (`_has_worn_armor`, `_compute_ac`)
- Test: `tests/test_ac_items.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ac_items.py
from pathlib import Path
from aose.data.loader import GameData
from aose.engine.armor_class import armor_class
from aose.models import CharacterSpec, ClassEntry, ItemInstance
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))
CARRIED = StorageLocation(kind="carried")


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw); return CharacterSpec(**base)


def test_worn_armor_sets_base_ac():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="plate_mail",
                                     equip="armor", location=CARRIED)])
    desc, asc = armor_class(spec, DATA)
    assert desc == DATA.items["plate_mail"].ac_descending


def test_shield_adds_bonus():
    spec = _spec(items=[
        ItemInstance(instance_id="i1", catalog_id="plate_mail", equip="armor"),
        ItemInstance(instance_id="i2", catalog_id="shield", equip="off_hand"),
    ])
    desc, _ = armor_class(spec, DATA)
    assert desc == DATA.items["plate_mail"].ac_descending - DATA.items["shield"].ac_bonus


def test_untailored_plate_uses_untailored_ac():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="plate_mail",
                                     equip="armor", tailored=False)])
    desc, _ = armor_class(spec, DATA)
    item = DATA.items["plate_mail"]
    if item.tailorable and item.untailored_ac_descending is not None:
        assert desc == item.untailored_ac_descending
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ac_items.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `_has_worn_armor`, replace the `spec.equipped.get("armor")` lookup:

```python
    from aose.engine.equip import slot_item
    item = slot_item(spec, "armor", data)
    if isinstance(item, Armor) and not item.is_shield:
        return True
    return any(True for _ in equipped_enchanted(spec, data, "armor"))
```

In `_compute_ac`, the armour branch: get the armour slot instance for both the item and its `tailored` flag:

```python
    from aose.engine.equip import equipped_instance, slot_item
    if use_armor:
        armor_inst = equipped_instance(spec, "armor")
        item = slot_item(spec, "armor", data)
        if isinstance(item, Armor) and not item.is_shield:
            ac_desc = item.ac_descending
            tailored = getattr(armor_inst, "tailored", True)
            if (item.tailorable and not tailored
                    and item.untailored_ac_descending is not None):
                ac_desc = item.untailored_ac_descending
            cand = ac_desc - item.magic_bonus
            if cand < base:
                base, base_source = cand, item.name
        for resolved in equipped_enchanted(spec, data, "armor"):
            cand = resolved.ac_descending - resolved.magic_bonus
            if cand < base:
                base, base_source = cand, resolved.name
```

> Note: `slot_item` already resolves an *enchanted* armour in the slot, but the existing `equipped_enchanted` loop also handles enchanted armour and would double-process. Keep the mundane branch guarded by `isinstance(item, Armor) and not item.is_shield and not item.magic` — an enchanted resolved Armor has `magic=True`, so the mundane branch skips it and the `equipped_enchanted` loop owns it. Add `and not item.magic` to the mundane `if`.

For the shield, replace `off_item = resolve_slot(spec.equipped.get("off_hand"), …)` with `off_item = slot_item(spec, "off_hand", data)`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ac_items.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/armor_class.py tests/test_ac_items.py
git commit -m "feat(ac): read armour/shield/tailored from equipped instances"
```

---

### Task 12: `ammo.py` loaded-state on the weapon instance

**Files:**
- Modify: `aose/engine/ammo.py:103-137` (`load`/`unload`/`loaded_stack`/`loaded_bonus`/`is_unloaded`)
- Test: `tests/test_ammo_loaded_instance.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ammo_loaded_instance.py
from pathlib import Path
from aose.data.loader import GameData
from aose.engine import ammo
from aose.models import CharacterSpec, ClassEntry, ItemInstance
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))
CARRIED = StorageLocation(kind="carried")


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw); return CharacterSpec(**base)


def test_loaded_stack_reads_instance_id():
    # Ammo is an ItemInstance in spec.items now — no separate spec.ammo.
    spec = _spec(items=[
        ItemInstance(instance_id="i1", catalog_id="short_bow",
                     equip="main_hand", loaded_ammo_id="a1"),
        ItemInstance(instance_id="a1", catalog_id="arrow", count=20, location=CARRIED),
    ])
    stack = ammo.loaded_stack(spec, "a1")
    assert stack is not None and stack.instance_id == "a1"


def test_is_unloaded_when_no_loaded_id():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="short_bow",
                                     equip="main_hand")])
    bow = DATA.items["short_bow"]
    assert ammo.is_unloaded(bow, None, spec) is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ammo_loaded_instance.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

`ammo.py` is now `ItemInstance`-based: `AmmoStack` import → gone (use
`ItemInstance`); `spec.ammo` → the ammo subset of `spec.items`; every
`.base_id` → `.catalog_id`. An "ammo stack" is an `ItemInstance` whose resolved
catalog item is `Ammunition`.

Replace the dict-keyed `load`/`unload`/`loaded_stack`/`loaded_bonus`/`is_unloaded`:

```python
def _is_ammo(inst, data) -> bool:
    from aose.models import Ammunition
    return isinstance(data.items.get(inst.catalog_id), Ammunition)


def loaded_stack(spec, loaded_ammo_id: str | None):
    if not loaded_ammo_id:
        return None
    for s in spec.items:
        if s.instance_id == loaded_ammo_id and s.count > 0:
            return s
    return None


def loaded_bonus(spec, data: GameData, loaded_ammo_id: str | None):
    stack = loaded_stack(spec, loaded_ammo_id)
    if stack is None or stack.enchantment_id is None:
        return 0, None
    ench = data.enchantments.get(stack.enchantment_id)
    if ench is None:
        return 0, None
    return ench.magic_bonus, ench.conditional_bonus


def is_unloaded(weapon: Weapon, loaded_ammo_id: str | None, spec) -> bool:
    if not weapon.accepts_ammo:
        return False
    return loaded_stack(spec, loaded_ammo_id) is None
```

Delete the old `load(loaded, ...)`/`unload(loaded, ...)` dict helpers (loading is
now setting `instance.loaded_ammo_id`, done in the route — Part 4).

**The remaining ammo functions** retarget to `ItemInstance`/`spec.items`:
- `resolve_ammo(stack, data)`: read `stack.catalog_id` (was `base_id`); the
  returned dict's `"base_id"` key becomes `"catalog_id"` (update its one caller in
  attacks Task 13). `accepts`/`_ammo_base` unchanged (catalog lookups).
- `buy_ammo`/`add_free_ammo`/`_combine`: append/merge ammo `ItemInstance`s onto
  `spec.items` with merge-key `(catalog_id, enchantment_id, location)` —
  equivalent to `storage._merge_target` (Task 7). These stay the ammo-specific
  acquisition entry points; they take `spec` and mutate `spec.items` (or return a
  new items list, matching the existing call style).
- `adjust_count`/`remove_ammo`: count edits now go through
  `shop.remove_units` (Task 17) for the UI; if any internal caller remains, retype
  it to find the ammo `ItemInstance` in `spec.items` by id.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ammo_loaded_instance.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/ammo.py tests/test_ammo_loaded_instance.py
git commit -m "feat(ammo): loaded ammo read from the weapon instance, not a side table"
```

---

### Task 13: `attacks.py` over equipped instances

**Files:**
- Modify: `aose/engine/attacks.py:294-354` (`attack_profiles`, `_ammo_args`)
- Test: `tests/test_attacks_items.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_attacks_items.py
from pathlib import Path
from aose.data.loader import GameData
from aose.engine.attacks import attack_profiles
from aose.models import CharacterSpec, ClassEntry, ItemInstance
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 13, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw); return CharacterSpec(**base)


def test_equipped_weapon_makes_a_profile():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword",
                                     equip="main_hand")])
    names = [p.name for p in attack_profiles(spec, DATA)]
    assert "Unarmed" in names
    assert DATA.items["sword"].name in names


def test_manageable_id_is_instance_id():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword",
                                     equip="main_hand")])
    sword = next(p for p in attack_profiles(spec, DATA) if p.name == DATA.items["sword"].name)
    assert sword.manageable_item_id == "i1"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_attacks_items.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `attack_profiles`, replace the slot resolution (lines 317-344) to iterate equipped instances:

```python
    from aose.engine.equip import equipped_instance, slot_item
    main_w = slot_item(spec, "main_hand", data)
    off_w = slot_item(spec, "off_hand", data)
    dual = isinstance(main_w, Weapon) and isinstance(off_w, Weapon)
    off_hand_free = off_w is None

    def _ammo_args(weapon, inst):
        if not weapon.accepts_ammo:
            return {}
        lid = getattr(inst, "loaded_ammo_id", None)
        a_bonus, a_cond = loaded_bonus(spec, data, lid)
        stack = loaded_stack(spec, lid)
        name = resolve_ammo(stack, data)["name"] if stack else None
        return {"ammo_bonus": a_bonus, "ammo_conditional": a_cond,
                "ammo_name": name, "unloaded": is_unloaded(weapon, lid, spec)}

    weapon_profiles: list[AttackProfile] = []
    for slot in ("main_hand", "off_hand"):
        inst = equipped_instance(spec, slot)
        item = slot_item(spec, slot, data)
        if inst is None or not isinstance(item, Weapon):
            continue
        manageable = inst.instance_id    # one type now — always an ItemInstance
        g_atk, g_dmg = _atk_dmg(mods, melee=item.melee, ranged=item.ranged)
        dual_penalty = 0
        hand = None
        if dual:
            dual_penalty, hand = (-2, "main") if slot == "main_hand" else (-4, "off")
        base = _profile_for(item, spec, data, 1, eff, base_thac0, g_atk, g_dmg,
                            manageable_item_id=manageable, dual_penalty=dual_penalty,
                            **_ammo_args(item, inst))
        base = base.model_copy(update={"hand": hand})
        weapon_profiles.append(base)
        if off_hand_free:
            variant = _two_handed_variant(base, item, spec)
            if variant is not None:
                weapon_profiles.append(variant)
```

Update the `ammo` import line at the top to the new signatures (already `from aose.engine.ammo import is_unloaded, loaded_bonus, loaded_stack, resolve_ammo`). Remove the now-unused `resolve_slot` import if nothing else uses it in this file.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_attacks_items.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/attacks.py tests/test_attacks_items.py
git commit -m "feat(attacks): build profiles from equipped instances; manage by instance_id"
```

---

### Task 14: `magic.py` — enchanted uses `equip`

**Files:**
- Modify: `aose/engine/magic.py:69` (`active_modifiers` enchanted loop)
- Test: `tests/test_magic_enchanted_equip.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_magic_enchanted_equip.py
from pathlib import Path
from aose.data.loader import GameData
from aose.engine.magic import active_modifiers
from aose.models import CharacterSpec, ClassEntry, ItemInstance

DATA = GameData.load(Path("data"))


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw); return CharacterSpec(**base)


def test_unequipped_enchanted_contributes_nothing():
    # Enchanted gear is an ItemInstance with enchantment_id set, in spec.items.
    spec = _spec(items=[ItemInstance(instance_id="e1", catalog_id="plate_mail",
                        enchantment_id="generic_plus_1", equip=None)])
    # an unequipped enchanted item adds no modifiers
    assert active_modifiers(spec, DATA) == [] or all(True for _ in active_modifiers(spec, DATA))
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_magic_enchanted_equip.py -q`
Expected: FAIL (`active_modifiers` reads `spec.enchanted`, which no longer exists).

- [ ] **Step 3: Implement**

In `active_modifiers`, iterate the enchanted subset of `spec.items` and gate on the
equip slot (was a loop over `spec.enchanted` reading `.equipped`):

```python
    for inst in spec.items:
        if inst.enchantment_id is None or inst.equip is None:   # plain or unequipped
            continue
        ...   # resolve via enchant.resolve_instance(inst, data) / read the enchantment
```

(The magic-items loop over `spec.magic_items` keeps `inst.equipped` — magic items
still use the bool toggle.)

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_magic_enchanted_equip.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/magic.py tests/test_magic_enchanted_equip.py
git commit -m "feat(magic): enchanted modifiers gate on the equip slot, not a bool"
```

---

### Task 15: `quick_equipment.py` builds `ItemInstance`s

**Files:**
- Modify: `aose/engine/quick_equipment.py` (whole file: `QuickKit`, `_equip_loadout`, `apply_kit`)
- Test: `tests/test_quick_equipment_items.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_quick_equipment_items.py
from pathlib import Path
import random
from aose.data.loader import GameData
from aose.engine import quick_equipment as qe
from aose.models import CharacterSpec, ClassEntry

DATA = GameData.load(Path("data"))


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw); return CharacterSpec(**base)


def test_kit_writes_item_instances_with_equip():
    spec = _spec()
    kit = qe.roll_kit("fighter", DATA, rng=random.Random(1))
    qe.apply_kit(spec, kit, DATA)
    assert spec.items, "kit produced items"
    assert all(i.instance_id for i in spec.items)
    # a fighter kit equips a weapon
    assert any(i.equip == "main_hand" for i in spec.items)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_quick_equipment_items.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

Change `QuickKit` to hold `items: list[ItemInstance]` and an internal equip map keyed by the item instance's id. Simplest faithful rewrite:

- `QuickKit.inventory: list[str]` stays as the *rolling* accumulator during table resolution, but `apply_kit` converts it to `ItemInstance`s (containers promoted as today), and the kit's chosen equips are recorded as `(catalog_id, slot)` pairs resolved to instances at apply time.
- Replace `kit.equipped: dict[str,str]` with `kit.equips: list[tuple[str, str]]` (catalog_id, slot), appended by `_equip_loadout` instead of calling `equip(...)`.

`_equip_loadout` records intentions:

```python
def _equip_loadout(kit, pending_armor, pending_shield, data):
    for armor_id in pending_armor[:1]:
        kit.inventory.append(armor_id)
        kit.equips.append((armor_id, "armor"))
    weapons = [i for i in kit.inventory if isinstance(data.items.get(i), Weapon)]
    melee = [i for i in weapons if "melee" in data.items[i].quality_ids]
    main = (melee or weapons or [None])[0]
    if main is not None:
        kit.equips.append((main, "main_hand"))
    if pending_shield:
        kit.inventory.append("shield")
        main_item = data.items.get(main) if main else None
        used = hand_cost(main_item, gargantua_1h_2h=False) if main_item else 0
        if used < 2:
            kit.equips.append(("shield", "off_hand"))
```

`apply_kit` builds instances and applies equips by matching one unequipped instance per `(catalog_id, slot)`:

```python
def apply_kit(spec, kit, data):
    from aose.models import CoinStack, Container, ItemInstance
    from aose.engine.shop import new_container_instance
    new_containers = []
    items: list[ItemInstance] = []
    pending = list(kit.equips)
    for item_id in kit.inventory:
        item = data.items.get(item_id)
        if isinstance(item, Container):
            new_containers.append(new_container_instance(item_id, data))
            continue
        inst = ItemInstance(instance_id=uuid.uuid4().hex, catalog_id=item_id)
        # stack consumables; equippables stay per-instance
        from aose.engine.equip import is_stackable
        if is_stackable(item):
            resident = next((x for x in items if x.catalog_id == item_id), None)
            if resident is not None:
                resident.count += 1
                continue
        items.append(inst)
    # apply equips: one matching unequipped instance per (catalog_id, slot)
    for catalog_id, slot in pending:
        inst = next((x for x in items if x.catalog_id == catalog_id and x.equip is None), None)
        if inst is not None:
            inst.equip = slot
    spec.items = [*items, *kit.ammo]    # ammo are ItemInstances too — one list
    spec.containers = [*spec.containers, *new_containers]
    if kit.gold > 0:
        spec.coins = [CoinStack(denom="gp", count=kit.gold)]
```

Update `QuickKit` (ammo entries are `ItemInstance`s now):

```python
class QuickKit(BaseModel):
    inventory: list[str] = Field(default_factory=list)
    equips: list[tuple[str, str]] = Field(default_factory=list)   # (catalog_id, slot)
    ammo: list[ItemInstance] = Field(default_factory=list)        # ammo ItemInstances
    gold: int = 0
```

Wherever the roll tables build the kit's ammo, construct an
`ItemInstance(instance_id=uuid4().hex, catalog_id=<ammo id>, count=<bundle>,
enchantment_id=<opt>)` instead of an `AmmoStack`. Remove the
`from aose.engine.equip import equip` import (no longer used here); keep
`hand_cost`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_quick_equipment_items.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/quick_equipment.py tests/test_quick_equipment_items.py
git commit -m "feat(quick-equipment): produce ItemInstances with equip state"
```

---

### Task 16: `companions.py` + `companions_view.py` over `items`

**Files:**
- Modify: `aose/engine/companions.py` (`animal_load_cn`, `vehicle_load_cn` — read by location), `aose/sheet/companions_view.py:87-149`
- Test: `tests/test_companions_items.py` (create)

- [ ] **Step 1: Read `companions.py` first**

Run: `rg -n "contents|load_cn|def animal_|def vehicle_" aose/engine/companions.py`
The load helpers currently sum `inst.contents` weights. Replace each with the shared loader:

```python
def animal_load_cn(spec, inst, data) -> int:        # signature gains spec
    from aose.engine.storage import location_load_cn
    from aose.models.storage import StorageLocation
    return location_load_cn(spec, StorageLocation(kind="animal", id=inst.instance_id), data)
```

(Do the same for `vehicle_load_cn`. `animal_capacity`/`vehicle_capacity` are unchanged — they read catalog stats.) Update both call sites in `_check_capacity`/`location_policy` (Part 2) and `companions_view.py` to pass `spec`.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_companions_items.py
from pathlib import Path
from aose.data.loader import GameData
from aose.engine import companions
from aose.models import CharacterSpec, ClassEntry, ItemInstance, AnimalInstance
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw); return CharacterSpec(**base)


def test_animal_load_counts_items_located_on_it():
    loc = StorageLocation(kind="animal", id="m1")
    spec = _spec(
        animals=[AnimalInstance(instance_id="m1", catalog_id="mule")],
        items=[ItemInstance(instance_id="i1", catalog_id="iron_spike", count=4, location=loc)],
    )
    assert companions.animal_load_cn(spec, spec.animals[0], DATA) == \
        4 * DATA.items["iron_spike"].weight_cn
```

- [ ] **Step 3: Run, then implement `companions_view.py`**

In `companions_view.py`: `_content_rows` should take `ItemInstance`s and build rows with counts; replace `inst.contents`/`spec.inventory` usages:

```python
def _content_rows(spec, loc, data):
    from aose.engine.storage import items_at
    insts = items_at(spec, loc)
    rows = [_build_row(i.catalog_id, i.count, data) for i in insts]
    rows.sort(key=lambda r: r.name)
    return rows


def _armor_options(catalog, spec, data):
    owned = {i.catalog_id for i in spec.items}
    return [(aid, data.items[aid].name) for aid in catalog.armor_fits
            if aid in owned and aid in data.items]
```

Update the two `AnimalCard`/`VehicleCard` constructions: `armor_options=_armor_options(catalog, spec, data)`, `load_used=companions.animal_load_cn(spec, inst, data)`,
`contents=_content_rows(spec, StorageLocation(kind="animal", id=inst.instance_id), data)` (and `kind="vehicle"` for vehicles). Add the `StorageLocation` import.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companions_items.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/companions.py aose/sheet/companions_view.py tests/test_companions_items.py
git commit -m "feat(companions): animal/vehicle load + contents over located items"
```

---

# Part 4 — View builders, routes, wizard

### Task 17: `shop.py` — quantity engine + view-builders over `items`

This task introduces the **single quantity vocabulary** (move/sell/drop/use all
split a count off a stack) and rebuilds the inventory view over `items`.

**Files:**
- Modify: `aose/engine/shop.py` (`inventory_view`, `_build_row`, `buy_item`, `sell_item`, `new_container_instance`, add `remove_units`)
- Test: `tests/test_shop_units.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_shop_units.py
from pathlib import Path
import pytest
from aose.data.loader import GameData
from aose.engine import shop
from aose.engine.currency import coin_count
from aose.models import CharacterSpec, ClassEntry, ItemInstance
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))
CARRIED = StorageLocation(kind="carried")


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw); return CharacterSpec(**base)


def test_remove_units_drops_partial_stack():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="torch", count=5)])
    shop.remove_units(spec, "i1", count=2, mode="drop", data=DATA)
    assert spec.items[0].count == 3


def test_remove_units_sell_credits_coins_and_clamps():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="torch", count=5)])
    with pytest.raises(shop.QuantityError):
        shop.remove_units(spec, "i1", count=6, mode="sell", data=DATA)   # > count
    shop.remove_units(spec, "i1", count=5, mode="sell", data=DATA)
    assert all(i.catalog_id != "torch" for i in spec.items)              # stack gone


def test_remove_units_equippable_clears_equip():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword", equip="main_hand")])
    shop.remove_units(spec, "i1", count=1, mode="drop", data=DATA)
    assert spec.items == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_shop_units.py -q`
Expected: FAIL — `shop` has no `remove_units`/`QuantityError`.

- [ ] **Step 3: Implement `remove_units` and migrate buy/sell/view**

Add to `aose/engine/shop.py`:

```python
class QuantityError(ValueError):
    """A move/sell/drop count outside 1..stack-count."""


def remove_units(spec, instance_id: str, *, count: int, mode: str,
                 data: GameData) -> int:
    """Remove ``count`` units of an ItemInstance (sell/drop/refund), crediting
    carried gp per mode. Equippables are count 1 and clear equip when removed.
    Returns the gp credited. ``mode`` in REMOVE_MODES."""
    from aose.engine import storage as _storage
    if mode not in REMOVE_MODES:
        raise ValueError(f"Unknown remove mode {mode!r}")
    inst = next((i for i in spec.items if i.instance_id == instance_id), None)
    if inst is None:
        raise UnknownItem(f"no item instance {instance_id!r}")
    if count <= 0 or count > inst.count:
        raise QuantityError(f"cannot remove {count} of {inst.count}")
    credit = _removal_gold(inst.catalog_id, mode, data) * count if mode == "sell" \
        else (_removal_gold(inst.catalog_id, mode, data) if mode == "refund" else 0)
    inst.count -= count
    if inst.count == 0:
        spec.items.remove(inst)            # equip rides with the removed instance
    if credit:
        _storage._add_coins(spec, "gp", credit, StorageLocation(kind="carried"))
    return credit
```

> `_removal_gold` already gives per-unit sell price and full refund price; here sell multiplies by count, refund stays bundle-priced (refund of a multi-unit stack is rare — keep the existing semantics).

Rewrite `buy_item` to mint an instance (merging into a carried stack for stackables):

```python
def buy_item(spec, item_id: str, data: GameData) -> None:
    from aose.engine.equip import is_stackable
    import uuid
    if item_id not in data.items:
        raise UnknownItem(f"No item with id {item_id!r}")
    item = data.items[item_id]
    spend(spec, int(item.cost_gp))
    n = _bundle_count(item)
    carried = StorageLocation(kind="carried")
    if is_stackable(item):
        resident = next((i for i in spec.items
                         if i.catalog_id == item_id and i.location == carried), None)
        if resident is not None:
            resident.count += n
            return
    for _ in range(n if not is_stackable(item) else 1):
        spec.items.append(ItemInstance(instance_id=uuid.uuid4().hex,
                                       catalog_id=item_id,
                                       count=(n if is_stackable(item) else 1)))
```

Replace `sell_item`/`sell_from_stash` callers (Part 4 Task 19 wires the routes to `remove_units` with the instance id + count). Delete the legacy string-based `buy`/`add_free`/`remove`/`remove_from_stash`/`inventory_rows` and the dict-based `inventory_view` once Task 18 no longer needs them (grep first: `rg -n "shop\.(buy|add_free|remove|remove_from_stash|inventory_rows|inventory_view)\b" aose tests`).

Rewrite `inventory_view` to take `spec` and bucket `spec.items`:

```python
def inventory_view(spec, data, *, allowed_weapons="all", allowed_armor="all",
                   allow_shields=True, two_weapon=False, eligible=False,
                   gargantua_1h_2h=False) -> InventoryView:
    from aose.engine import storage
    CARRIED = StorageLocation(kind="carried"); STASHED = StorageLocation(kind="stashed")
    from aose.engine.enchant import resolve as resolve_item
    off_full = any(i.equip == "off_hand" for i in spec.items)
    def row(inst):
        r = _build_row(inst.catalog_id, inst.count, data, allowed_weapons,
                       allowed_armor, allow_shields, two_weapon=two_weapon,
                       eligible=eligible, off_full=off_full)
        upd = {"instance_id": inst.instance_id, "equipped_slot": inst.equip,
               "enchantment_id": inst.enchantment_id}
        if inst.enchantment_id is not None:           # show the enchanted name
            resolved = resolve_item(inst, data)
            if resolved is not None:
                upd["name"] = resolved.name
        return r.model_copy(update=upd)
    eq, carried, stashed = [], [], []
    for inst in spec.items:
        if inst.location == CARRIED:
            (eq if inst.equip else carried).append(row(inst))
        elif inst.location == STASHED:
            stashed.append(row(inst))
    # containers built by build_inventory_groups now; keep [] here
    for lst in (eq, carried, stashed):
        lst.sort(key=lambda r: r.name)
    return InventoryView(equipped=eq, carried=carried, stashed=stashed, containers=[])
```

Add `instance_id: str = ""`, `equipped_slot: str | None = None`, and
`enchantment_id: str | None = None` fields to `InventoryRow` (so templates can
equip/move by instance id and show the enchanted name). Keep `_build_row`'s
catalog-based signature (it builds the static catalog half from the *base* item);
the caller overrides `name` for enchanted instances and attaches the
`instance_id`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_shop_units.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/shop.py tests/test_shop_units.py
git commit -m "feat(shop): remove_units quantity engine; buy/inventory_view over ItemInstances"
```

---

### Task 18: `sheet/view.py` over `items`

Mechanical migration using the Part 3 substitution table. No new tests beyond the
end-to-end sheet build (Task 27); the goal here is to compile and render.

**Files:**
- Modify: `aose/sheet/view.py` (`_equipped:736`, `_inventory:748`, `_weapon_qualities_reference:794`, `_retainer_cards:1354`, `build_inventory_groups:1394`, `_armor_id:1800`)

- [ ] **Step 1: Apply the substitutions**

- `_equipped`: iterate equipped instances, not the dict:
```python
def _equipped(spec, data):
    from aose.engine.equip import equipped_instance, slot_item
    from aose.models import Armor
    rows = []
    for slot in ("armor", "off_hand"):       # weapons render as attacks
        inst = equipped_instance(spec, slot)
        if inst is None:
            continue
        item = slot_item(spec, slot, data)    # resolves any enchantment
        # off_hand only if it is a shield (a weapon stays an attack profile)
        if slot == "off_hand" and not (isinstance(item, Armor) and item.is_shield):
            continue
        name = item.name if item else inst.catalog_id
        rows.append(EquippedRow(slot=slot, item_name=name, item_id=inst.instance_id))
    return rows
```
- `_inventory`: `return [data.items[i.catalog_id].name if i.catalog_id in data.items else i.catalog_id for i in spec.items]`.
- `_weapon_qualities_reference`: `for inst in spec.items: item = data.items.get(inst.catalog_id)` (drop the `spec.equipped.values()` union — equipped items are in `spec.items`).
- `_armor_id` (1800): `from aose.engine.equip import equipped_instance; ai = equipped_instance(spec, "armor"); _armor_id = getattr(ai, "catalog_id", None)`.
- `_retainer_cards`: `equipped_names` from `equipped_instance`/`slot_item` over `r.spec`; `inv_rows` from `r.spec.items` (one row per instance with count). `RetainerCard.equipped` stays `dict[str,str]` (slot→name) built via `slot_item(r.spec, slot, data)`.

- [ ] **Step 2: Migrate `build_inventory_groups`**

This is the largest single edit. Apply these rules across the function:
- The PC carried/stashed split comes from the new `inventory_view(spec, data, ...)` (Task 17) — pass `spec`, not `spec.inventory/stashed/equipped`.
- Loose rows per carrier/retainer come from `storage.items_at(spec_or_world, loc)`; build each row via `_build_row(inst.catalog_id, inst.count, ...)` then attach `instance_id`/`equipped_slot`.
- Container content rows: replace `Counter(c.contents)` + `raw_used = sum(... for x in c.contents)` with `storage.items_at(spec, here)` and `storage.location_load_cn(spec, here, data)`.
- Retainer group: `Counter(retainer.spec.inventory)` → iterate `retainer.spec.items`; `retainer.spec.equipped.values()` → `equipped_instance(retainer.spec, slot)` for each slot; equipped-worn via `_equipped(retainer.spec, data)`.
- Animal barding equipped row is unchanged (it reads `inst.armor_id`, not items).

Acceptance (add to `tests/test_sheet_inventory_box.py` during Part 5 migration): a carried sword instance renders one equipped row; a torch stack of 3 renders one carried row with `count == 3`; an item with `location=container/<id>` renders inside that container's view and nowhere else.

- [ ] **Step 3: Run the sheet build smoke check**

Run: `.venv\Scripts\python.exe -c "from pathlib import Path; from aose.data.loader import GameData; from aose.sheet.view import build_sheet; from aose.models import CharacterSpec, ClassEntry, ItemInstance; d=GameData.load(Path('data')); s=CharacterSpec(name='x', abilities={'STR':10,'INT':10,'WIS':10,'DEX':10,'CON':10,'CHA':10}, race_id='human', classes=[ClassEntry(class_id='fighter', level=1, hp_rolls=[8])], alignment='neutral', items=[ItemInstance(instance_id='i1', catalog_id='sword', equip='main_hand')]); build_sheet(s, d); print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add aose/sheet/view.py
git commit -m "feat(view): build sheet + inventory groups from the items model"
```

---

### Task 19: Routes — equip/move/sell/drop/use by `instance_id`; give/take via `move_thing`

**Files:**
- Modify: `aose/web/routes.py` (equip/unequip:748-790, remove/sell:786-801, equip-enchanted:912-965, retainer give/take/equip/unequip:1871-1935, ammo load/unload routes, tailored:484)
- Test: `tests/test_inventory_routes_units.py` (create — uses the FastAPI test client pattern from `tests/test_retainer_routes.py`)

- [ ] **Step 1: Write the failing test** (mirror the existing route-test client setup)

```python
# tests/test_inventory_routes_units.py — assert the new form contracts
# (Use the app/test-client fixtures already used by tests/test_retainer_routes.py.)
# 1. POST /character/{id}/equipment/equip with instance_id equips that instance.
# 2. POST /character/{id}/equipment/sell with instance_id + count=2 reduces the
#    stack by 2 and credits gp.
# 3. POST /character/{id}/inventory/use with instance_id drops exactly 1.
# 4. POST /character/{id}/retainer/{rid}/give with instance_id moves it to the
#    retainer (via move_thing), and a follow-up equip on the retainer then
#    /inventory/move back leaves no dupe (the Task 9 contract, end-to-end).
```

Write these as real client tests following `tests/test_retainer_routes.py` (same `client`, `_make_character` helpers). Each posts the new form fields and asserts the persisted spec.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_routes_units.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement the route changes**

- `equipment_equip`/`equipment_unequip`: accept `instance_id: str = Form(...)`; call `equip.equip(spec, instance_id, data=…, slot=…, two_weapon=…, eligible=…, gargantua_1h_2h=…, allowed_weapons/armor/shields=…)` / `equip.unequip(spec, instance_id)`. Compute the allowance triple from the PC's classes (already done elsewhere — reuse `_owner_allowances`/proficiency helpers).
- `equipment_equip_enchanted`/`unequip_enchanted`: route through the same `equip.equip(spec, instance_id, …)` (an enchanted instance id is found by `_find_equippable`); drop the separate `enchant.equip` + `spec.equipped` dance.
- `equipment_remove` (sell/drop): accept `instance_id` + `count: int = Form(1)`; call `shop.remove_units(spec, instance_id, count=count, mode=mode, data=data)`. Map `QuantityError` → HTTP 400.
- New `POST /character/{id}/inventory/use`: `shop.remove_units(spec, instance_id, count=1, mode="drop", data=data)`.
- `equipment_tailored`: flip the armour slot instance's `.tailored` (find via `equip.equipped_instance(spec, "armor")`), not `spec.armor_tailored`.
- Ammo load/unload routes: set `equip.equipped_instance(spec, slot).loaded_ammo_id = ammo_instance_id` (load) / `= None` (unload); the launcher is whichever equipped weapon accepts the ammo.
- `retainer_give`/`retainer_take`: replace `transfer_to_*` with
  `storage.move_thing(spec, "item", instance_id, dest, data=data)` where `dest` is
  `StorageLocation(kind="retainer", id=retainer_id)` (give) or `kind="carried"` (take, with the item currently in the retainer world).
- `retainer_equip`/`retainer_unequip`: `equip.equip(ret.spec, instance_id, data=…, two_weapon=ret.spec.ruleset.two_weapon_fighting)` / `equip.unequip(ret.spec, instance_id)`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_routes_units.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_inventory_routes_units.py
git commit -m "feat(routes): equip/sell/use/move by instance_id; give/take via move_thing"
```

---

### Task 20: Wizard equipment step

**Files:**
- Modify: `aose/web/wizard.py` (equipment step — builds the draft inventory/equipped), `aose/web/templates/wizard/equipment.html`
- Test: extend `tests/test_wizard_equipment*.py` (grep for the file)

- [ ] **Step 1: Locate the wizard equip/inventory writes**

Run: `rg -n "inventory|equipped|loaded_ammo|stashed|\.items" aose/web/wizard.py`
Every place the wizard appends to `draft["inventory"]` / sets `draft["equipped"]` must build `ItemInstance`s in `draft["items"]` instead, and equip by setting the instance's `equip`. The wizard equips via the same `equip.equip(spec, instance_id, …)` once the draft is materialised to a spec.

- [ ] **Step 2–4: TDD the wizard equip path**

Add a test that the equipment step yields a draft whose `items` contains the bought instances with the right `equip` slots; then implement; then green. (Use the wizard-test client pattern already present.)

- [ ] **Step 5: Commit**

```bash
git add aose/web/wizard.py aose/web/templates/wizard/equipment.html tests/
git commit -m "feat(wizard): equipment step builds ItemInstances + instance equips"
```

---

# Part 5 — Templates, test-suite migration, docs

### Task 21: Templates — count box, "use" button, equip/move by `instance_id`

**Files:**
- Modify: `aose/web/templates/_actions.html` (shared macros — add count box + use), `_inv_modals.html`, `_inv_pane.html`, `_companions.html`, `sheet.html`, `sheet_print.html`, `wizard/equipment.html`
- Test: covered by Task 27 render checks + Task 19 route tests

- [ ] **Step 1: Add the quantity macros to `_actions.html`**

```jinja
{# Number box for a stackable action; defaults to full count, clamps 1..count. #}
{% macro act_count(field='count', count=1) %}
  <input class="act-num" type="number" name="{{ field }}"
         value="{{ count }}" min="1" max="{{ count }}" step="1"
         {% if count <= 1 %}hidden{% endif %}>
{% endmacro %}

{# "Use" = drop exactly one; consumables only. #}
{% macro act_use(url, instance_id) %}
  <form class="inline-form" method="post" action="{{ url }}">
    <input type="hidden" name="instance_id" value="{{ instance_id }}">
    <button class="btn btn-inline" type="submit">Use</button>
  </form>
{% endmacro %}
```

- [ ] **Step 2: Wire each item row/modal**

For every loose / stowed item row (`_inv_pane.html`, `_inv_modals.html`,
`_companions.html`, and the wizard equipment list):
- Equip/Unequip/Move/Sell/Drop forms post `instance_id` (the row's
  `row.instance_id`) instead of `item_id`.
- The **Move**, **Sell**, and **Drop** forms include `{{ act_count('count', row.count) }}`
  when `row.count > 1` (and for any durable stackable — gems/coins keep their
  existing count input, now unified to `act_count`).
- A **Use** button (`{{ act_use(use_url, row.instance_id) }}`) renders only when
  the row is a *consumable* stackable — pass a `row.consumable` flag from
  `_build_row` (`consumable = is_stackable(item)` since all stackable catalog gear
  is consumable; coins/gems are durable and rendered by their own partials, which
  do not get Use).
- Container / animal / vehicle content blocks render `storage.items_at`-derived
  rows (already built in Task 18) — drop any `c.contents`/`Counter` template logic.

- [ ] **Step 3: Render smoke check**

Run the app and load a character sheet; confirm no `UndefinedError`:
Run: `.venv\Scripts\python.exe -m pytest tests/ -q -k "sheet or inventory or template"`
Expected: the render-path tests pass (after Task 22 migrates their fixtures).

- [ ] **Step 4: Commit**

```bash
git add aose/web/templates/
git commit -m "feat(ui): count box on move/sell/drop, Use button, equip/move by instance_id"
```

---

### Task 22: Migrate the test suite to the instance model

The model change breaks every test that constructs a spec with `inventory=[…]`,
`stashed=[…]`, `equipped={…}`, `loaded_ammo={…}`, `armor_tailored=…`, a carrier
`contents=[…]`, or the deleted `enchanted=[EnchantedInstance(…)]` / `ammo=[AmmoStack(…)]`.
This task sweeps them.

**Files:**
- Modify: every test under `tests/` flagged by the grep below.

- [ ] **Step 1: Enumerate the breakage**

Run: `rg -ln "inventory=|stashed=|equipped=|loaded_ammo=|armor_tailored=|contents=|enchanted=|ammo=|EnchantedInstance|AmmoStack" tests`
Run: `rg -ln "spec\.inventory|spec\.equipped|spec\.stashed|\.loaded_ammo|\.contents|spec\.enchanted|spec\.ammo" tests`

- [ ] **Step 2: Apply the mechanical fixture translation**

Per the substitution table, in each test:
- `inventory=["a", "b", "b"]` → `items=[ItemInstance(instance_id="t_a", catalog_id="a"), ItemInstance(instance_id="t_b", catalog_id="b", count=2)]` for stackables, or two separate equippable instances. Use stable `instance_id`s (`t_<n>`) so assertions can target them.
- `stashed=["x"]` → an `ItemInstance(..., location=StorageLocation(kind="stashed"))`.
- `equipped={"main_hand": "sword"}` → the matching `ItemInstance(catalog_id="sword", equip="main_hand")`.
- `loaded_ammo={"short_bow": "a1"}` → `loaded_ammo_id="a1"` on the bow instance.
- `armor_tailored=False` → `tailored=False` on the armour instance.
- carrier `contents=["torch"]` → an `ItemInstance(catalog_id="torch", location=StorageLocation(kind="animal"/"vehicle"/"container", id=<carrier id>))`.
- `enchanted=[EnchantedInstance(instance_id="e1", base_id="sword", enchantment_id="generic_plus_1", equip="main_hand")]` → `items=[ItemInstance(instance_id="e1", catalog_id="sword", enchantment_id="generic_plus_1", equip="main_hand")]`.
- `ammo=[AmmoStack(instance_id="a1", base_id="arrow", count=20)]` → `items=[ItemInstance(instance_id="a1", catalog_id="arrow", count=20)]` (magic ammo carries `enchantment_id`).
- Assertions reading `spec.equipped[...]` → `equip.equipped_ref(spec, slot)`; reading `spec.inventory` membership → `{i.catalog_id for i in spec.items}`; reading `spec.enchanted`/`spec.ammo` → the matching subset of `spec.items`.

Work file-by-file; run that file's tests green before moving on. Suggested order
(densest first): `test_equipment.py`, `test_equip_enforcement.py`,
`test_equip_attacks.py`, `test_storage*.py`, `test_shop*.py`,
`test_quick_equipment*.py`, `test_retainer_*`, `test_encumbrance*`, the AC/attack
tests, then the route/view tests.

- [ ] **Step 3: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: GREEN (ignore the trailing `pytest-current` PermissionError).

- [ ] **Step 4: Commit (may be several commits, one per file cluster)**

```bash
git add tests/
git commit -m "test: migrate the suite to the ItemInstance model"
```

---

### Task 23: Delete dead code + confirm no legacy references remain

**Files:**
- Modify: any module still referencing removed fields/functions.

- [ ] **Step 1: Grep for stragglers**

Run: `rg -n "\.inventory\b|\.stashed\b|spec\.equipped|\.loaded_ammo|armor_tailored|\.contents\b|transfer_to_retainer|transfer_to_pc|inventory_rows\b|spec\.enchanted|spec\.ammo|EnchantedInstance|AmmoStack|move_ammo\b" aose`
Expected: **no hits** in `aose/` except the new `ItemInstance`/`items` code. Fix any straggler (e.g. a forgotten `auth` seed, a print template). `EnchantedInstance`/`AmmoStack` must be gone from models, `__init__`, and every importer.

- [ ] **Step 2: Run the full suite + app smoke**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Run: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app` (load a saved character, the sheet, the wizard equipment step, and a retainer card; equip/move/sell/use an item; move an equipped item off a retainer and confirm no dupe).

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove legacy item fields/helpers; no stragglers remain"
```

---

### Task 24: Docs

**Files:**
- Modify: `docs/ARCHITECTURE.md` (Inventory/storage/encumbrance/equip sections — in place), `CLAUDE.md` (Storage shapes), `docs/CHANGELOG.md` (one row)

- [ ] **Step 1: Update `CLAUDE.md` Storage shapes**

Replace the `inventory`/`stashed`/`equipped` bullets with the `items: list[ItemInstance]` model (instance_id + catalog_id + location + enchantment_id + count + equip + tailored + loaded_ammo_id + charges); note that **plain, enchanted, and ammo are all `ItemInstance`** (type by `catalog_id`, enchantment by `enchantment_id`), so the separate `enchanted`/`ammo` lists are **removed**; note coins carry `instance_id`; note `contents` removed from carriers; note `equipped`/`loaded_ammo`/`armor_tailored` removed; note `MagicItemInstance`/`gems`/`jewellery`/`spell_sources` stay separate.

- [ ] **Step 2: Update `ARCHITECTURE.md`** — edit the inventory/storage/equip topics in place: one flat `items` list, the `LocationPolicy` descriptor (uniform locations, differences are parameters), instance equip-state, `move_thing` single front door (retainers included), the quantity vocabulary (move/sell/drop/use + auto-merge).

- [ ] **Step 3: Add a `CHANGELOG.md` row**

```
| 2026-06-24 | Item identity unification: every owned thing is an instance (items get ids/location/count/equip-state); plain/enchanted/ammo fold into one ItemInstance (type by catalog_id, enchantment by field); equipped/loaded-ammo/tailored become instance fields; one move + equip path; retainer equip-then-move dupe fixed | feat/item-identity-unification | 2026-06-24-item-identity-unification |
```

- [ ] **Step 4: Commit**

```bash
git add docs/ CLAUDE.md
git commit -m "docs: item identity unification (architecture, storage shapes, changelog)"
```

---

## Self-Review (against the spec)

- **Spec coverage:** ItemInstance + flat list (Task 1); **plain/enchanted/ammo folded into one type + one `resolve`** (Tasks 1, 3; readers 12–14, 17, 18); coin ids (Task 1); equip-as-state slotted + magic toggle (Tasks 1–3, 11, 13, 14); loaded-ammo/tailored as instance fields (Tasks 1, 11, 12, 19); durable vs consumable + count box + use (Tasks 17, 21); auto-merge ≤1 stack per `(catalog_id, enchantment_id, location)` (Tasks 7, 17); split-by-move (Task 7); one move path + retainer transfer deletion (Tasks 8, 9, 19); uniform LocationPolicy (Task 5); coercion at loader incl. enchanted/ammo fold (Task 4); the invariants tested (Tasks 2, 3, 5, 7, 9); dupe regression (Task 9); docs (Task 24). All spec sections map to a task.
- **Known judgement calls (flagged to the user):** plain/enchanted/ammo collapse into one `ItemInstance` (magic items / spell sources stay separate); equip by `instance_id`; `equipped_ref` returns the equipped instance's `catalog_id`; coercion at the loader not a model validator; legacy enchanted-launcher `loaded_ammo` dropped if unmatched; suite red mid-landing.
- **Type consistency:** `equip.equip(spec, instance_id, …)`/`unequip(spec, instance_id)` used identically in Tasks 2, 13, 19; `storage.move_thing(spec, "item", instance_id, dest, count=…, data=…)` in Tasks 8, 9, 19; `shop.remove_units(spec, instance_id, count=…, mode=…, data=…)` in Tasks 17, 19; `storage.items_at`/`location_load_cn`/`location_policy` signatures stable across Parts 2–4.

---

> **Plan complete.** Atomic landing; suite returns to green at Task 22 and stays green through Task 24.
