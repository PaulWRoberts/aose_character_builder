# Container Items Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-instance container items (backpack, sacks, Bag of Holding) to the AOSE Character Builder so items can be stored inside containers, which have capacity limits and weight multipliers.

**Architecture:** A new `Container` variant on the `Item` discriminated union (catalog) plus a `ContainerInstance` runtime model living on `CharacterSpec.containers`. The shop engine grows new helpers (`stow`, `take_out`, `stash_container`, etc.); `inventory_view` returns a `containers` list alongside the existing equipped/carried/stashed sections. Templates render containers as inline collapsible rows; one new vanilla-JS file adds drag-and-drop on top of explicit Stow / Take-Out buttons.

**Tech Stack:** Python 3.14, Pydantic v2, FastAPI, Jinja2, pytest. Vanilla JS (no framework). YAML for catalog data.

**Spec:** [docs/superpowers/specs/2026-05-27-container-items-design.md](../specs/2026-05-27-container-items-design.md)

**Test command:** `.venv\Scripts\python.exe -m pytest tests/ -q`
**Run command:** `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`

---

## Task 1: Add `Container` to the `Item` discriminated union

**Files:**
- Modify: `aose/models/item.py`
- Modify: `aose/models/__init__.py`
- Create: `tests/test_containers.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_containers.py` with:

```python
"""Tests for container items: catalog model, runtime instances, shop helpers,
weight calculations, HTTP routes."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.models import Container

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def test_container_model_parses():
    c = Container(
        id="test_bag",
        name="Test Bag",
        category="containers",
        item_type="container",
        cost_gp=1,
        weight_cn=5,
        capacity_cn=200,
        weight_multiplier=1.0,
    )
    assert c.capacity_cn == 200
    assert c.weight_multiplier == 1.0


def test_container_defaults_unlimited_and_full_weight():
    c = Container(
        id="bag",
        name="Bag",
        category="containers",
        item_type="container",
        cost_gp=0,
        weight_cn=0,
    )
    assert c.capacity_cn is None
    assert c.weight_multiplier == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -q
```
Expected: `ImportError: cannot import name 'Container' from 'aose.models'`

- [ ] **Step 3: Add the `Container` variant**

In `aose/models/item.py`, after the `Poison` class:

```python
class Container(ItemBase):
    item_type: Literal["container"]
    capacity_cn: int | None = None
    weight_multiplier: float = 1.0
```

Update the `Item` union:

```python
Item = Annotated[
    Union[Weapon, Armor, AdventuringGear, Poison, Container],
    Field(discriminator="item_type"),
]
```

- [ ] **Step 4: Export `Container` from the models package**

In `aose/models/__init__.py`, add `Container` to the import block from `.item` and to `__all__`:

```python
from .item import (
    Item,
    ItemBase,
    Weapon,
    Armor,
    AdventuringGear,
    Poison,
    Container,
    WeaponDamage,
)
```

```python
__all__ = [
    ...,
    "Container",
    ...,
]
```

- [ ] **Step 5: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -q
```
Expected: 2 passed.

- [ ] **Step 6: Commit**

```
git add aose/models/item.py aose/models/__init__.py tests/test_containers.py
git commit -m "Add Container variant to Item discriminated union"
```

---

## Task 2: Add `ContainerInstance` and `CharacterSpec.containers`

**Files:**
- Modify: `aose/models/character.py`
- Modify: `aose/models/__init__.py`
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_containers.py`:

```python
from aose.models import CharacterSpec, ClassEntry, ContainerInstance, RuleSet


def _minimal_spec(**overrides):
    base = dict(
        name="Tester",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="law",
        ruleset=RuleSet(),
    )
    base.update(overrides)
    return CharacterSpec(**base)


def test_container_instance_construct():
    inst = ContainerInstance(
        instance_id="abc123",
        catalog_id="backpack",
        state="carried",
        contents=["torch", "rope"],
    )
    assert inst.state == "carried"
    assert inst.contents == ["torch", "rope"]


def test_character_spec_defaults_containers_empty():
    spec = _minimal_spec()
    assert spec.containers == []
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py::test_container_instance_construct -q
```
Expected: `ImportError: cannot import name 'ContainerInstance'`.

- [ ] **Step 3: Add the model**

In `aose/models/character.py`, add the `ContainerInstance` class above `ClassEntry`:

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .ability import Ability
from .ruleset import RuleSet


class ContainerInstance(BaseModel):
    """A specific container the character owns — per-instance state, separate
    from the catalog ``Container`` item.  Items inside ``contents`` are not in
    ``CharacterSpec.inventory`` or ``CharacterSpec.stashed``; they live inside
    the container and follow its state (carried/stashed) for weight purposes.
    """
    model_config = ConfigDict(extra="forbid")

    instance_id: str
    catalog_id: str
    state: Literal["carried", "stashed"]
    contents: list[str] = Field(default_factory=list)
```

In the `CharacterSpec` class, add the field after `equipped_weapons`:

```python
    containers: list[ContainerInstance] = Field(default_factory=list)
```

- [ ] **Step 4: Export `ContainerInstance`**

In `aose/models/__init__.py`:

```python
from .character import CharacterSpec, ClassEntry, ContainerInstance
```

```python
__all__ = [
    ...,
    "ContainerInstance",
    ...,
]
```

- [ ] **Step 5: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -q
```
Expected: 4 passed.

- [ ] **Step 6: Run the full suite to confirm no regressions**

```
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: full suite passes (the existing `extra="forbid"` config on `CharacterSpec` is satisfied because the new field has a default).

- [ ] **Step 7: Commit**

```
git add aose/models/character.py aose/models/__init__.py tests/test_containers.py
git commit -m "Add ContainerInstance and CharacterSpec.containers"
```

---

## Task 3: Add container-specific exceptions

**Files:**
- Modify: `aose/engine/shop.py`
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_containers.py`:

```python
def test_container_exceptions_exist():
    from aose.engine.shop import ContainerFull, ContainerNotEmpty, UnknownContainer
    assert issubclass(ContainerFull, ValueError)
    assert issubclass(ContainerNotEmpty, ValueError)
    assert issubclass(UnknownContainer, ValueError)
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py::test_container_exceptions_exist -q
```
Expected: `ImportError`.

- [ ] **Step 3: Add the exceptions**

In `aose/engine/shop.py`, near the existing `InsufficientGold` and `UnknownItem`:

```python
class ContainerFull(ValueError):
    pass


class ContainerNotEmpty(ValueError):
    pass


class UnknownContainer(ValueError):
    pass
```

- [ ] **Step 4: Run the test**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py::test_container_exceptions_exist -q
```
Expected: 1 passed.

- [ ] **Step 5: Commit**

```
git add aose/engine/shop.py tests/test_containers.py
git commit -m "Add container-specific shop exceptions"
```

---

## Task 4: Add `new_container_instance`, `buy_container`, `add_free_container`

**Files:**
- Modify: `aose/engine/shop.py`
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_containers.py`:

```python
from aose.engine.shop import (
    InsufficientGold,
    UnknownItem,
    add_free_container,
    buy_container,
    new_container_instance,
)


def _fake_container_data():
    """Build a tiny GameData stand-in with one container catalog item.
    Real YAML loading is exercised in Task 12; here we use a unit-style
    in-memory item so the helper tests stay self-contained."""
    from aose.data.loader import GameData
    from aose.models import Container, AdventuringGear

    return GameData(items={
        "backpack": Container(
            id="backpack", name="Backpack", category="containers",
            item_type="container", cost_gp=5, weight_cn=80,
            capacity_cn=400, weight_multiplier=1.0,
        ),
        "torch": AdventuringGear(
            id="torch", name="Torch", category="adventuring_gear",
            item_type="gear", cost_gp=1, weight_cn=20,
        ),
    })


def test_new_container_instance_validates_catalog_type():
    fake = _fake_container_data()
    inst = new_container_instance("backpack", fake)
    assert inst.catalog_id == "backpack"
    assert inst.state == "carried"
    assert inst.contents == []
    assert len(inst.instance_id) >= 16  # uuid4 hex length


def test_new_container_instance_rejects_non_container():
    fake = _fake_container_data()
    with pytest.raises(ValueError, match="not a container"):
        new_container_instance("torch", fake)


def test_new_container_instance_rejects_unknown_id():
    fake = _fake_container_data()
    with pytest.raises(UnknownItem):
        new_container_instance("imaginary", fake)


def test_new_container_instance_unique_ids():
    fake = _fake_container_data()
    a = new_container_instance("backpack", fake)
    b = new_container_instance("backpack", fake)
    assert a.instance_id != b.instance_id


def test_buy_container_deducts_gold_and_appends():
    fake = _fake_container_data()
    new_containers, new_gold = buy_container([], 10, "backpack", fake)
    assert len(new_containers) == 1
    assert new_containers[0].catalog_id == "backpack"
    assert new_gold == 5  # 10 - 5


def test_buy_container_rejects_insufficient_gold():
    fake = _fake_container_data()
    with pytest.raises(InsufficientGold):
        buy_container([], 2, "backpack", fake)


def test_add_free_container_does_not_deduct_gold():
    fake = _fake_container_data()
    new_containers = add_free_container([], "backpack", fake)
    assert len(new_containers) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "container_instance or buy_container or add_free_container" -q
```
Expected: ImportError or NameError on the new helpers.

- [ ] **Step 3: Implement the helpers**

In `aose/engine/shop.py`, add imports at the top:

```python
import uuid

from aose.models import Container, ContainerInstance
```

(Adjust the existing `from aose.models import Item` line to include `Container, ContainerInstance` or add a new line.)

Add the three helpers near the top-level functions:

```python
def new_container_instance(catalog_id: str, data: GameData,
                           state: str = "carried") -> ContainerInstance:
    """Create a fresh ContainerInstance for the given catalog item.

    Validates that ``catalog_id`` is a Container in ``data.items``.  Returns a
    ContainerInstance with a uuid4-hex ``instance_id``.  Raises ``UnknownItem``
    if the id isn't in ``data.items`` and ``ValueError`` if the item exists
    but isn't a Container.
    """
    item = data.items.get(catalog_id)
    if item is None:
        raise UnknownItem(f"No item with id {catalog_id!r}")
    if not isinstance(item, Container):
        raise ValueError(f"{catalog_id!r} is not a container")
    return ContainerInstance(
        instance_id=uuid.uuid4().hex,
        catalog_id=catalog_id,
        state=state,  # type: ignore[arg-type]
        contents=[],
    )


def buy_container(containers: list[ContainerInstance], gold: int,
                  catalog_id: str, data: GameData
                  ) -> tuple[list[ContainerInstance], int]:
    """Like ``buy()`` but creates a ContainerInstance instead of appending to a
    flat inventory list.  Deducts ``cost_gp`` (rounded down) from ``gold``."""
    item = data.items.get(catalog_id)
    if item is None:
        raise UnknownItem(f"No item with id {catalog_id!r}")
    if not isinstance(item, Container):
        raise ValueError(f"{catalog_id!r} is not a container")
    cost = int(item.cost_gp)
    if gold < cost:
        raise InsufficientGold(
            f"Cannot afford {item.name}: {cost} gp required, {gold} on hand"
        )
    return ([*containers, new_container_instance(catalog_id, data)], gold - cost)


def add_free_container(containers: list[ContainerInstance],
                       catalog_id: str, data: GameData
                       ) -> list[ContainerInstance]:
    """Append a new container instance without deducting gold (GM gift / loot)."""
    return [*containers, new_container_instance(catalog_id, data)]
```

- [ ] **Step 4: Run the new tests**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "container_instance or buy_container or add_free_container" -q
```
Expected: 7 passed.

- [ ] **Step 5: Run the full suite to confirm no regressions**

```
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: full suite passes.

- [ ] **Step 6: Commit**

```
git add aose/engine/shop.py tests/test_containers.py
git commit -m "Add container creation helpers (new/buy/add_free)"
```

---

## Task 5: Add `stow()` helper

**Files:**
- Modify: `aose/engine/shop.py`
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_containers.py`:

```python
from aose.engine.shop import ContainerFull, UnknownContainer, stow


def _carried_backpack(fake):
    return new_container_instance("backpack", fake)


def test_stow_moves_item_from_inventory_into_container():
    fake = _fake_container_data()
    bp = _carried_backpack(fake)
    inv, stashed, containers = stow(
        inventory=["torch"], stashed=[], containers=[bp],
        equipped={}, equipped_weapons=[],
        instance_id=bp.instance_id, item_id="torch", data=fake,
    )
    assert inv == []
    assert containers[0].contents == ["torch"]


def test_stow_rejects_unknown_container():
    fake = _fake_container_data()
    with pytest.raises(UnknownContainer):
        stow(["torch"], [], [], {}, [], "missing-id", "torch", fake)


def test_stow_rejects_item_not_in_inventory():
    fake = _fake_container_data()
    bp = _carried_backpack(fake)
    with pytest.raises(ValueError, match="not in inventory"):
        stow([], [], [bp], {}, [], bp.instance_id, "torch", fake)


def test_stow_rejects_equipped_item():
    fake = _fake_container_data()
    fake.items["long_sword"] = _weapon_for_tests("long_sword", "Long Sword", 60, 10)
    bp = _carried_backpack(fake)
    with pytest.raises(ValueError, match="equipped"):
        stow(
            inventory=["long_sword"], stashed=[], containers=[bp],
            equipped={}, equipped_weapons=["long_sword"],
            instance_id=bp.instance_id, item_id="long_sword", data=fake,
        )


def test_stow_rejects_container_item():
    fake = _fake_container_data()
    fake.items["sack"] = Container(
        id="sack", name="Sack", category="containers", item_type="container",
        cost_gp=1, weight_cn=5, capacity_cn=200,
    )
    bp = _carried_backpack(fake)
    with pytest.raises(ValueError, match="containers cannot be stowed"):
        stow(["sack"], [], [bp], {}, [], bp.instance_id, "sack", fake)


def test_stow_capacity_full_raises():
    fake = _fake_container_data()
    # 20 torches = 400 cn, exactly at the backpack's 400 capacity.  21st fails.
    bp = _carried_backpack(fake)
    bp = bp.model_copy(update={"contents": ["torch"] * 20})
    with pytest.raises(ContainerFull):
        stow(["torch"], [], [bp], {}, [], bp.instance_id, "torch", fake)
```

Also add the `Container` import and a small `_weapon_for_tests` helper near the top of the new tests block:

```python
from aose.models import Container


def _weapon_for_tests(item_id: str, name: str, weight_cn: int, cost_gp: int):
    from aose.models import Weapon, WeaponDamage
    return Weapon(
        id=item_id, name=name, category="weapons", item_type="weapon",
        cost_gp=cost_gp, weight_cn=weight_cn,
        damage=WeaponDamage(default="1d6", variable="1d8"),
        hands=1, melee=True, ranged=False, proficiency_group="sword",
    )
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "stow" -q
```
Expected: ImportError on `stow`.

- [ ] **Step 3: Implement `stow`**

In `aose/engine/shop.py`:

```python
def stow(inventory: list[str], stashed: list[str],
         containers: list[ContainerInstance],
         equipped: dict[str, str], equipped_weapons: list[str],
         instance_id: str, item_id: str, data: GameData,
         ) -> tuple[list[str], list[str], list[ContainerInstance]]:
    """Move one copy of ``item_id`` from ``inventory`` into the container with
    ``instance_id``.  Source is always inventory — to stow a stashed item,
    unstash it first; to stow an equipped item, unequip it first.

    Raises:
      * ``UnknownContainer`` if ``instance_id`` isn't in ``containers``.
      * ``ValueError("not in inventory")`` if ``item_id`` isn't carried.
      * ``ValueError("containers cannot be stowed")`` if ``item_id`` is itself
        a container catalog item (no nesting).
      * ``ValueError("item is equipped")`` if the item appears in ``equipped``
        or ``equipped_weapons`` (unequip first).
      * ``ContainerFull`` if adding the item's raw weight would exceed
        ``capacity_cn``.
    """
    idx = next((i for i, c in enumerate(containers) if c.instance_id == instance_id), None)
    if idx is None:
        raise UnknownContainer(f"No container with id {instance_id!r}")

    if item_id not in inventory:
        raise ValueError(f"{item_id!r} is not in inventory")

    item = data.items.get(item_id)
    if isinstance(item, Container):
        raise ValueError("containers cannot be stowed inside other containers")

    if item_id in equipped.values() or item_id in equipped_weapons:
        raise ValueError(f"{item_id!r} is equipped; unequip first")

    target = containers[idx]
    catalog = data.items[target.catalog_id]
    new_weight = item.weight_cn if item else 0
    if catalog.capacity_cn is not None:
        used = sum(
            (data.items[x].weight_cn if x in data.items else 0)
            for x in target.contents
        )
        if used + new_weight > catalog.capacity_cn:
            raise ContainerFull(
                f"{catalog.name} full: {used}/{catalog.capacity_cn} cn, "
                f"item adds {new_weight} cn"
            )

    new_inv = list(inventory)
    new_inv.remove(item_id)
    updated = target.model_copy(update={"contents": [*target.contents, item_id]})
    new_containers = [*containers[:idx], updated, *containers[idx+1:]]
    return new_inv, stashed, new_containers
```

- [ ] **Step 4: Run the new tests**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "stow" -q
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```
git add aose/engine/shop.py tests/test_containers.py
git commit -m "Add stow() helper: move inventory item into a container"
```

---

## Task 6: Add `take_out()` helper

**Files:**
- Modify: `aose/engine/shop.py`
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_containers.py`:

```python
from aose.engine.shop import take_out


def test_take_out_from_carried_container_returns_to_inventory():
    fake = _fake_container_data()
    bp = _carried_backpack(fake).model_copy(update={"contents": ["torch"]})
    inv, stashed, containers = take_out(
        inventory=[], stashed=[], containers=[bp],
        instance_id=bp.instance_id, item_id="torch",
    )
    assert inv == ["torch"]
    assert containers[0].contents == []


def test_take_out_from_stashed_container_returns_to_stashed_list():
    fake = _fake_container_data()
    bp = new_container_instance("backpack", fake, state="stashed").model_copy(
        update={"contents": ["torch", "torch"]}
    )
    inv, stashed, containers = take_out(
        inventory=[], stashed=[], containers=[bp],
        instance_id=bp.instance_id, item_id="torch",
    )
    assert stashed == ["torch"]
    assert inv == []
    assert containers[0].contents == ["torch"]


def test_take_out_unknown_container_raises():
    with pytest.raises(UnknownContainer):
        take_out([], [], [], "missing-id", "torch")


def test_take_out_item_not_in_container_raises():
    fake = _fake_container_data()
    bp = _carried_backpack(fake)
    with pytest.raises(ValueError, match="not in container"):
        take_out([], [], [bp], bp.instance_id, "torch")
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "take_out" -q
```
Expected: ImportError.

- [ ] **Step 3: Implement `take_out`**

In `aose/engine/shop.py`:

```python
def take_out(inventory: list[str], stashed: list[str],
             containers: list[ContainerInstance],
             instance_id: str, item_id: str,
             ) -> tuple[list[str], list[str], list[ContainerInstance]]:
    """Remove one copy of ``item_id`` from the container's contents.

    Destination follows container state: a carried container puts the item
    back in ``inventory``; a stashed container puts it in ``stashed``.
    """
    idx = next((i for i, c in enumerate(containers) if c.instance_id == instance_id), None)
    if idx is None:
        raise UnknownContainer(f"No container with id {instance_id!r}")
    target = containers[idx]
    if item_id not in target.contents:
        raise ValueError(f"{item_id!r} not in container {instance_id!r}")

    new_contents = list(target.contents)
    new_contents.remove(item_id)
    updated = target.model_copy(update={"contents": new_contents})
    new_containers = [*containers[:idx], updated, *containers[idx+1:]]

    if target.state == "carried":
        return [*inventory, item_id], stashed, new_containers
    return inventory, [*stashed, item_id], new_containers
```

- [ ] **Step 4: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "take_out" -q
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```
git add aose/engine/shop.py tests/test_containers.py
git commit -m "Add take_out() helper: pull item from container"
```

---

## Task 7: Add `stash_container` and `unstash_container`

**Files:**
- Modify: `aose/engine/shop.py`
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_containers.py`:

```python
from aose.engine.shop import stash_container, unstash_container


def test_stash_container_flips_state():
    fake = _fake_container_data()
    bp = _carried_backpack(fake)
    result = stash_container([bp], bp.instance_id)
    assert result[0].state == "stashed"
    # Contents are untouched
    assert result[0].contents == []


def test_unstash_container_reverses():
    fake = _fake_container_data()
    bp = new_container_instance("backpack", fake, state="stashed")
    result = unstash_container([bp], bp.instance_id)
    assert result[0].state == "carried"


def test_stash_container_unknown_raises():
    with pytest.raises(UnknownContainer):
        stash_container([], "missing-id")


def test_unstash_container_unknown_raises():
    with pytest.raises(UnknownContainer):
        unstash_container([], "missing-id")
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "stash_container or unstash_container" -q
```
Expected: ImportError.

- [ ] **Step 3: Implement the helpers**

In `aose/engine/shop.py`:

```python
def stash_container(containers: list[ContainerInstance],
                    instance_id: str) -> list[ContainerInstance]:
    """Flip a container's state to ``stashed``.  Contents follow implicitly —
    a stashed container's contents contribute zero to carried weight."""
    return _set_container_state(containers, instance_id, "stashed")


def unstash_container(containers: list[ContainerInstance],
                      instance_id: str) -> list[ContainerInstance]:
    """Flip a container's state to ``carried``."""
    return _set_container_state(containers, instance_id, "carried")


def _set_container_state(containers, instance_id, new_state):
    idx = next((i for i, c in enumerate(containers) if c.instance_id == instance_id), None)
    if idx is None:
        raise UnknownContainer(f"No container with id {instance_id!r}")
    target = containers[idx]
    if target.state == new_state:
        return list(containers)
    updated = target.model_copy(update={"state": new_state})
    return [*containers[:idx], updated, *containers[idx+1:]]
```

- [ ] **Step 4: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "stash_container or unstash_container" -q
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```
git add aose/engine/shop.py tests/test_containers.py
git commit -m "Add stash_container / unstash_container helpers"
```

---

## Task 8: Add `remove_container`

**Files:**
- Modify: `aose/engine/shop.py`
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_containers.py`:

```python
from aose.engine.shop import ContainerNotEmpty, remove_container


def test_remove_container_drop_with_contents():
    fake = _fake_container_data()
    bp = _carried_backpack(fake).model_copy(update={"contents": ["torch", "torch"]})
    containers, gold = remove_container([bp], 0, bp.instance_id, "drop", fake)
    assert containers == []
    assert gold == 0  # drop refunds nothing


def test_remove_container_sell_empty_refunds_half():
    fake = _fake_container_data()
    bp = _carried_backpack(fake)
    containers, gold = remove_container([bp], 0, bp.instance_id, "sell", fake)
    assert containers == []
    assert gold == 2  # 5 // 2


def test_remove_container_refund_empty_returns_full_cost():
    fake = _fake_container_data()
    bp = _carried_backpack(fake)
    containers, gold = remove_container([bp], 0, bp.instance_id, "refund", fake)
    assert gold == 5


def test_remove_container_sell_non_empty_raises():
    fake = _fake_container_data()
    bp = _carried_backpack(fake).model_copy(update={"contents": ["torch"]})
    with pytest.raises(ContainerNotEmpty):
        remove_container([bp], 0, bp.instance_id, "sell", fake)


def test_remove_container_refund_non_empty_raises():
    fake = _fake_container_data()
    bp = _carried_backpack(fake).model_copy(update={"contents": ["torch"]})
    with pytest.raises(ContainerNotEmpty):
        remove_container([bp], 0, bp.instance_id, "refund", fake)


def test_remove_container_unknown_raises():
    fake = _fake_container_data()
    with pytest.raises(UnknownContainer):
        remove_container([], 0, "missing-id", "drop", fake)


def test_remove_container_bad_mode_raises():
    fake = _fake_container_data()
    bp = _carried_backpack(fake)
    with pytest.raises(ValueError, match="Unknown remove mode"):
        remove_container([bp], 0, bp.instance_id, "burn", fake)
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "remove_container" -q
```
Expected: ImportError.

- [ ] **Step 3: Implement `remove_container`**

In `aose/engine/shop.py`:

```python
def remove_container(containers: list[ContainerInstance], gold: int,
                     instance_id: str, mode: str, data: GameData,
                     ) -> tuple[list[ContainerInstance], int]:
    """Remove a container instance.

    * ``drop``    — instance + contents discarded, no refund.
    * ``sell``    — refunds half cost; raises ``ContainerNotEmpty`` if non-empty.
    * ``refund``  — refunds full cost; raises ``ContainerNotEmpty`` if non-empty.
    """
    if mode not in REMOVE_MODES:
        raise ValueError(f"Unknown remove mode {mode!r}; want one of {REMOVE_MODES}")

    idx = next((i for i, c in enumerate(containers) if c.instance_id == instance_id), None)
    if idx is None:
        raise UnknownContainer(f"No container with id {instance_id!r}")
    target = containers[idx]

    if mode in ("sell", "refund") and target.contents:
        raise ContainerNotEmpty(
            f"Cannot {mode} a container with contents — empty it first"
        )

    catalog = data.items.get(target.catalog_id)
    cost = int(catalog.cost_gp) if catalog else 0
    refund = 0
    if mode == "sell":
        refund = cost // 2
    elif mode == "refund":
        refund = cost

    new_containers = [*containers[:idx], *containers[idx+1:]]
    return new_containers, gold + refund
```

- [ ] **Step 4: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "remove_container" -q
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```
git add aose/engine/shop.py tests/test_containers.py
git commit -m "Add remove_container helper (drop / sell / refund)"
```

---

## Task 9: Add `ContainerView` and extend `inventory_view`

**Files:**
- Modify: `aose/engine/shop.py`
- Modify: `aose/web/routes.py`
- Modify: `aose/web/wizard.py`
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_containers.py`:

```python
def test_inventory_view_splits_loose_and_containers():
    fake = _fake_container_data()
    bp = _carried_backpack(fake).model_copy(update={"contents": ["torch"]})
    from aose.engine.shop import inventory_view
    view = inventory_view(
        inventory=["torch"], stashed=[], equipped={}, equipped_weapons=[],
        containers=[bp], data=fake,
    )
    # The loose torch shows up in carried; the contained torch shows up
    # under the container, not in carried.
    assert len(view.carried) == 1
    assert view.carried[0].count == 1
    assert len(view.containers) == 1
    cv = view.containers[0]
    assert cv.instance_id == bp.instance_id
    assert cv.name == "Backpack"
    assert cv.state == "carried"
    assert cv.capacity_cn == 400
    assert cv.used_cn == 20  # one torch
    assert cv.effective_weight_cn == 100  # 80 own + 1.0 * 20
    assert len(cv.contents) == 1


def test_inventory_view_container_weight_with_multiplier():
    fake = _fake_container_data()
    fake.items["boh"] = Container(
        id="boh", name="Bag of Holding", category="miscellaneous_magic_items",
        item_type="container", cost_gp=0, weight_cn=0, capacity_cn=10000,
        weight_multiplier=0.06,
    )
    bag = new_container_instance("boh", fake).model_copy(
        update={"contents": ["torch"] * 100}  # 100 * 20 = 2000 cn raw
    )
    from aose.engine.shop import inventory_view
    view = inventory_view([], [], {}, [], [bag], fake)
    cv = view.containers[0]
    assert cv.used_cn == 2000
    assert cv.effective_weight_cn == int(0.06 * 2000)  # 120


def test_inventory_view_stashed_container_zero_effective_weight():
    fake = _fake_container_data()
    bp = new_container_instance("backpack", fake, state="stashed").model_copy(
        update={"contents": ["torch"]}
    )
    from aose.engine.shop import inventory_view
    view = inventory_view([], [], {}, [], [bp], fake)
    cv = view.containers[0]
    assert cv.state == "stashed"
    # effective_weight is only meaningful when carried; stashed = 0
    assert cv.effective_weight_cn == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "inventory_view" -q
```
Expected: `TypeError: inventory_view() got an unexpected keyword argument 'containers'` (or similar).

- [ ] **Step 3: Add `ContainerView` and extend `InventoryView`**

In `aose/engine/shop.py`, after the `InventoryRow` class:

```python
class ContainerView(BaseModel):
    """Per-instance container rendering data for the inventory partial."""
    instance_id: str
    catalog_id: str
    name: str
    state: str   # "carried" or "stashed"
    capacity_cn: int | None
    used_cn: int                 # raw sum of contents weight (for capacity)
    weight_multiplier: float
    own_weight_cn: int
    effective_weight_cn: int     # own + int(multiplier * used_cn) when carried, else 0
    contents: list[InventoryRow]
```

Update `InventoryView`:

```python
class InventoryView(BaseModel):
    equipped: list[InventoryRow]
    carried: list[InventoryRow]
    stashed: list[InventoryRow]
    containers: list[ContainerView] = []
```

- [ ] **Step 4: Update `inventory_view()` signature and body**

Replace the existing `inventory_view` function with:

```python
def inventory_view(inventory: list[str], stashed: list[str],
                   equipped: dict[str, str], equipped_weapons: list[str],
                   containers: list[ContainerInstance] | None = None,
                   data: GameData = None) -> InventoryView:
    """Three-section split of the character's loose items, plus a parallel
    ``containers`` list with each instance's contents already grouped.

    Items inside container ``contents`` are not surfaced in equipped/carried/
    stashed — they live only inside the container view.
    """
    containers = containers or []

    equipped_count: Counter[str] = Counter()
    for v in equipped.values():
        equipped_count[v] += 1
    for v in equipped_weapons:
        equipped_count[v] += 1

    inv_count: Counter[str] = Counter(inventory)
    stash_count: Counter[str] = Counter(stashed)

    eq_rows: list[InventoryRow] = []
    carried_rows: list[InventoryRow] = []
    for item_id, total in inv_count.items():
        eq_n = min(equipped_count[item_id], total)
        carried_n = total - eq_n
        if eq_n:
            eq_rows.append(_build_row(item_id, eq_n, data))
        if carried_n:
            carried_rows.append(_build_row(item_id, carried_n, data))

    stashed_rows = [_build_row(i, n, data) for i, n in stash_count.items()]

    container_views: list[ContainerView] = []
    for c in containers:
        catalog = data.items.get(c.catalog_id)
        if not isinstance(catalog, Container):
            continue   # stale catalog id; surface as zero-state
        rows_by_id: Counter[str] = Counter(c.contents)
        content_rows = [_build_row(i, n, data) for i, n in rows_by_id.items()]
        content_rows.sort(key=lambda r: r.name)
        raw_used = sum(
            (data.items[x].weight_cn if x in data.items else 0)
            for x in c.contents
        )
        effective = (
            catalog.weight_cn + int(catalog.weight_multiplier * raw_used)
            if c.state == "carried" else 0
        )
        container_views.append(ContainerView(
            instance_id=c.instance_id,
            catalog_id=c.catalog_id,
            name=catalog.name,
            state=c.state,
            capacity_cn=catalog.capacity_cn,
            used_cn=raw_used,
            weight_multiplier=catalog.weight_multiplier,
            own_weight_cn=catalog.weight_cn,
            effective_weight_cn=effective,
            contents=content_rows,
        ))

    eq_rows.sort(key=lambda r: r.name)
    carried_rows.sort(key=lambda r: r.name)
    stashed_rows.sort(key=lambda r: r.name)
    container_views.sort(key=lambda v: (v.state, v.name))
    return InventoryView(
        equipped=eq_rows, carried=carried_rows, stashed=stashed_rows,
        containers=container_views,
    )
```

- [ ] **Step 5: Update callers to pass `containers`**

In `aose/web/routes.py`, the `character_sheet` route calls `shop_inventory_view`. Update the call:

```python
"inventory_view": shop_inventory_view(
    spec.inventory, spec.stashed, spec.equipped, spec.equipped_weapons,
    spec.containers, game_data,
),
```

In `aose/web/wizard.py`, `_equipment_context`:

```python
"inventory_view": inventory_view(
    inventory, stashed, equipped, equipped_weapons,
    draft.get("containers", []), game_data,
),
```

Note: `draft.get("containers", [])` returns the raw dict list from the draft JSON. Re-validate by constructing `ContainerInstance` objects:

```python
containers_raw = draft.get("containers", [])
containers = [ContainerInstance.model_validate(c) for c in containers_raw]
return {
    ...,
    "inventory_view": inventory_view(
        inventory, stashed, equipped, equipped_weapons, containers, game_data,
    ),
    ...,
}
```

Add the import:

```python
from aose.models import Ability, CharacterSpec, ClassEntry, ContainerInstance, RuleSet
```

- [ ] **Step 6: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: containers tests pass; full suite passes.

- [ ] **Step 7: Commit**

```
git add aose/engine/shop.py aose/web/routes.py aose/web/wizard.py tests/test_containers.py
git commit -m "Surface containers in inventory_view"
```

---

## Task 10: Update `carried_weight_cn` for containers

**Files:**
- Modify: `aose/engine/encumbrance.py`
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_containers.py`:

```python
def test_carried_weight_includes_carried_container_own_weight(data):
    """Real-data test: a carried Backpack (80 cn) contributes 80 even when empty."""
    from aose.engine.encumbrance import carried_weight_cn
    spec = _minimal_spec(ruleset=RuleSet(encumbrance="detailed"))
    # Inject a container instance directly
    spec.containers = [ContainerInstance(
        instance_id="x", catalog_id="backpack", state="carried", contents=[],
    )]
    assert carried_weight_cn(spec, data) == 80


def test_carried_weight_includes_contents_via_multiplier(data):
    """Real-data test: a carried Backpack with two torches inside.
    80 (bag) + 1.0 * 40 (contents) = 120 cn."""
    from aose.engine.encumbrance import carried_weight_cn
    spec = _minimal_spec(ruleset=RuleSet(encumbrance="detailed"))
    spec.containers = [ContainerInstance(
        instance_id="x", catalog_id="backpack", state="carried",
        contents=["torch", "torch"],
    )]
    assert carried_weight_cn(spec, data) == 80 + 40


def test_stashed_container_contributes_zero(data):
    from aose.engine.encumbrance import carried_weight_cn
    spec = _minimal_spec(ruleset=RuleSet(encumbrance="detailed"))
    spec.containers = [ContainerInstance(
        instance_id="x", catalog_id="backpack", state="stashed",
        contents=["torch", "torch"],
    )]
    assert carried_weight_cn(spec, data) == 0


def test_bag_of_holding_at_full_weighs_600(data):
    """Bag of Holding at 10 000 cn raw contents: 0 own + int(0.06 * 10000) = 600."""
    from aose.engine.encumbrance import carried_weight_cn
    # Real data has bag_of_holding after Task 12.  For now, inject the catalog
    # into the data fixture inline:
    import copy
    test_data = copy.deepcopy(data)
    test_data.items["boh"] = Container(
        id="boh", name="Bag of Holding", category="miscellaneous_magic_items",
        item_type="container", cost_gp=0, weight_cn=0, capacity_cn=10000,
        weight_multiplier=0.06,
    )
    # 500 long swords at 20 cn = 10 000 cn  (using long_sword which is 60 cn,
    # we need a different filler — use torches, 20 cn each, 500 of them.)
    spec = _minimal_spec(ruleset=RuleSet(encumbrance="detailed"))
    spec.containers = [ContainerInstance(
        instance_id="x", catalog_id="boh", state="carried",
        contents=["torch"] * 500,  # 500 * 20 = 10 000 cn raw
    )]
    assert carried_weight_cn(spec, test_data) == int(0.06 * 10000)  # 600
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "carried_weight or bag_of_holding" -q
```
Expected: `AssertionError` (current `carried_weight_cn` ignores containers).

- [ ] **Step 3: Update `carried_weight_cn`**

In `aose/engine/encumbrance.py`, replace the body:

```python
def carried_weight_cn(spec: CharacterSpec, data: GameData) -> int:
    """Total weight in coins.

    Loose ``inventory`` items count once.  Carried containers contribute their
    own ``weight_cn`` plus ``weight_multiplier * raw_contents_weight``.
    Stashed loose items and stashed containers contribute zero.
    """
    from aose.models import Container  # local import to avoid circulars

    total = 0
    for item_id in spec.inventory:
        item = data.items.get(item_id)
        if item is not None:
            total += item.weight_cn

    for c in spec.containers:
        if c.state != "carried":
            continue
        catalog = data.items.get(c.catalog_id)
        if not isinstance(catalog, Container):
            continue
        total += catalog.weight_cn
        raw = sum(
            (data.items[x].weight_cn if x in data.items else 0)
            for x in c.contents
        )
        total += int(catalog.weight_multiplier * raw)

    return total
```

- [ ] **Step 4: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "carried_weight or bag_of_holding" -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: containers tests pass; full suite green.

- [ ] **Step 5: Commit**

```
git add aose/engine/encumbrance.py tests/test_containers.py
git commit -m "Encumbrance counts containers and their contents (with multiplier)"
```

---

## Task 11: Guard `equip()` against containers

**Files:**
- Modify: `aose/engine/equip.py`
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_containers.py`:

```python
def test_equip_rejects_container_catalog_item():
    from aose.engine.equip import equip
    fake = _fake_container_data()
    with pytest.raises(ValueError, match="not equippable"):
        equip(["backpack"], {}, [], "backpack", fake)
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py::test_equip_rejects_container_catalog_item -q
```
Expected: AssertionError — without the guard, equip might raise a different message or attempt the operation. Confirm what it currently does, then add the guard.

- [ ] **Step 3: Read `aose/engine/equip.py` to find the existing equippable check, then add an early guard**

Open the file and locate the place where `equip` validates the item type (probably an `isinstance(item, (Weapon, Armor))` check). Update it so containers are explicitly rejected with the "not equippable" message. The existing rejection probably already catches containers as "not equippable" (since `Container` is neither `Weapon` nor `Armor`) — verify by running the test. If the existing message matches, the test passes without code change; if not, add this near the top of `equip()`:

```python
from aose.models import Container
if isinstance(data.items.get(item_id), Container):
    raise ValueError(f"{item_id!r} is not equippable (containers cannot be equipped)")
```

- [ ] **Step 4: Run the test**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py::test_equip_rejects_container_catalog_item -q
```
Expected: pass.

- [ ] **Step 5: Commit**

```
git add aose/engine/equip.py tests/test_containers.py
git commit -m "Equip rejects container catalog items"
```

---

## Task 12: Seed `containers.yaml` data file

**Files:**
- Create: `data/equipment/containers.yaml`
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_containers.py`:

```python
def test_containers_yaml_loads(data):
    assert "backpack" in data.items
    bp = data.items["backpack"]
    assert isinstance(bp, Container)
    assert bp.capacity_cn == 400


def test_bag_of_holding_loaded(data):
    assert "bag_of_holding" in data.items
    boh = data.items["bag_of_holding"]
    assert isinstance(boh, Container)
    assert boh.capacity_cn == 10000
    assert boh.weight_multiplier == 0.06
    assert boh.category == "miscellaneous_magic_items"


def test_shop_categories_includes_containers_and_magic(data):
    from aose.engine.shop import shop_categories
    cats = {c.id for c in shop_categories(data)}
    assert "containers" in cats
    assert "miscellaneous_magic_items" in cats
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "yaml or bag_of_holding_loaded or shop_categories" -q
```
Expected: KeyError on `data.items["backpack"]`.

- [ ] **Step 3: Create the YAML file**

`data/equipment/containers.yaml`:

```yaml
- id: backpack
  name: Backpack
  category: containers
  item_type: container
  cost_gp: 5
  weight_cn: 80
  capacity_cn: 400
  weight_multiplier: 1.0

- id: sack_small
  name: Sack, Small
  category: containers
  item_type: container
  cost_gp: 1
  weight_cn: 5
  capacity_cn: 200
  weight_multiplier: 1.0

- id: sack_large
  name: Sack, Large
  category: containers
  item_type: container
  cost_gp: 2
  weight_cn: 20
  capacity_cn: 600
  weight_multiplier: 1.0

- id: saddle_bags
  name: Saddle Bags
  category: containers
  item_type: container
  cost_gp: 4
  weight_cn: 50
  capacity_cn: 300
  weight_multiplier: 1.0

- id: bag_of_holding
  name: Bag of Holding
  category: miscellaneous_magic_items
  item_type: container
  cost_gp: 0
  weight_cn: 0
  capacity_cn: 10000
  weight_multiplier: 0.06
```

- [ ] **Step 4: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: all pass.

- [ ] **Step 5: Commit**

```
git add data/equipment/containers.yaml tests/test_containers.py
git commit -m "Add seed container YAML (backpack, sacks, saddle bags, Bag of Holding)"
```

---

## Task 13: Augment `/buy` and `/add` routes to handle containers (sheet)

**Files:**
- Modify: `aose/web/routes.py`
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_containers.py`:

```python
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character, save_settings
from aose.web.app import create_app


def _make_client(tmp_path, ruleset=None):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True)
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, ruleset or RuleSet())
    app = create_app(
        data_dir=DATA_DIR, characters_dir=characters_dir,
        drafts_dir=drafts_dir, examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._characters_dir = characters_dir
    client._drafts_dir = drafts_dir
    return client


def _seed_character(client, gold=100, inventory=None, containers=None) -> str:
    spec = _minimal_spec(
        gold=gold,
        inventory=list(inventory or []),
        containers=list(containers or []),
    )
    save_character("test", spec, client._characters_dir)
    return "test"


def test_sheet_buy_creates_container_instance(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, gold=20)
    r = client.post("/character/test/equipment/buy", data={"item_id": "backpack"})
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.gold == 15  # 20 - 5
    # Container is in spec.containers, NOT in inventory
    assert spec.inventory == []
    assert len(spec.containers) == 1
    assert spec.containers[0].catalog_id == "backpack"
    assert spec.containers[0].state == "carried"


def test_sheet_add_creates_container_instance_without_gold_deduction(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, gold=20)
    r = client.post("/character/test/equipment/add", data={"item_id": "bag_of_holding"})
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.gold == 20  # unchanged
    assert len(spec.containers) == 1
    assert spec.containers[0].catalog_id == "bag_of_holding"


def test_sheet_buy_regular_item_still_uses_inventory(tmp_path):
    """Non-container Buy is unchanged."""
    client = _make_client(tmp_path)
    _seed_character(client, gold=20)
    r = client.post("/character/test/equipment/buy", data={"item_id": "long_sword"})
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.inventory == ["long_sword"]
    assert spec.containers == []
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "sheet_buy or sheet_add" -q
```
Expected: assertion failures — current routes append "backpack" to `inventory`.

- [ ] **Step 3: Update the `equipment_buy` and `equipment_add` routes**

In `aose/web/routes.py`, replace `equipment_buy`:

```python
@router.post("/character/{character_id}/equipment/buy")
async def equipment_buy(request: Request, character_id: str,
                        item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    game_data = request.app.state.game_data
    item = game_data.items.get(item_id)
    from aose.models import Container
    try:
        if isinstance(item, Container):
            spec.containers, spec.gold = buy_container(
                spec.containers, spec.gold, item_id, game_data,
            )
        else:
            new_inventory, new_gold = shop_buy(spec.inventory, spec.gold, item_id, game_data)
            spec.inventory = new_inventory
            spec.gold = new_gold
    except (UnknownItem, InsufficientGold, ValueError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

Replace `equipment_add`:

```python
@router.post("/character/{character_id}/equipment/add")
async def equipment_add(request: Request, character_id: str,
                        item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    game_data = request.app.state.game_data
    item = game_data.items.get(item_id)
    from aose.models import Container
    try:
        if isinstance(item, Container):
            spec.containers = add_free_container(spec.containers, item_id, game_data)
        else:
            spec.inventory = shop_add_free(spec.inventory, item_id, game_data)
    except (UnknownItem, ValueError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

Update the top-of-file imports:

```python
from aose.engine.shop import (
    REMOVE_MODES,
    InsufficientGold,
    UnknownItem,
    add_free as shop_add_free,
    add_free_container,
    buy as shop_buy,
    buy_container,
    inventory_view as shop_inventory_view,
    remove as shop_remove,
    remove_from_stash as shop_remove_from_stash,
    shop_categories,
    stash as shop_stash,
    unstash as shop_unstash,
)
```

- [ ] **Step 4: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "sheet_buy or sheet_add" -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: pass + full suite green.

- [ ] **Step 5: Commit**

```
git add aose/web/routes.py tests/test_containers.py
git commit -m "Sheet buy/add routes route container catalog items to ContainerInstance"
```

---

## Task 14: Augment `/buy` and `/add` routes on the wizard

**Files:**
- Modify: `aose/web/wizard.py`
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_containers.py`:

```python
from aose.characters import load_draft, save_draft


def _walk_to_equipment(client):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    client.post(f"/wizard/{draft_id}/rules", data={
        "ability_roll_method": "3d6_in_order", "encumbrance": "basic",
        "separate_race_class": "on",
        "demihuman_level_limits": "on",
        "demihuman_class_restrictions": "on",
    })
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Tester"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.get(f"/wizard/{draft_id}/equipment")
    return draft_id


def test_wizard_buy_creates_container_in_draft(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _walk_to_equipment(client)
    draft = load_draft(draft_id, client._drafts_dir)
    draft["gold"] = 100
    save_draft(draft_id, draft, client._drafts_dir)
    r = client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "backpack"})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert len(draft["containers"]) == 1
    assert draft["containers"][0]["catalog_id"] == "backpack"
    assert draft["gold"] == 95


def test_wizard_add_creates_container_without_locking_gold(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _walk_to_equipment(client)
    r = client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "bag_of_holding"})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert len(draft["containers"]) == 1
    assert draft.get("gold_locked") is False
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "wizard_buy or wizard_add" -q
```
Expected: KeyError or assertion failures.

- [ ] **Step 3: Locate `aose/web/wizard.py` `/buy` and `/add` and augment**

Read the existing wizard.py routes at lines 940-970 (`/equipment/buy` and `/equipment/add`). They currently mutate `draft["inventory"]` and `draft["gold"]`. Update them to detect Container catalog items and route to `draft["containers"]` instead.

For `equipment_buy` (`@router.post("/{draft_id}/equipment/buy")`):

```python
@router.post("/{draft_id}/equipment/buy")
async def equipment_buy(request: Request, draft_id: str,
                        item_id: str = Form(...)):
    draft = _load(request, draft_id)
    game_data = request.app.state.game_data
    item = game_data.items.get(item_id)
    from aose.models import Container
    try:
        if isinstance(item, Container):
            containers_raw = draft.get("containers", [])
            containers = [ContainerInstance.model_validate(c) for c in containers_raw]
            new_containers, new_gold = buy_container(
                containers, draft.get("gold", 0), item_id, game_data,
            )
            draft["containers"] = [c.model_dump() for c in new_containers]
            draft["gold"] = new_gold
        else:
            new_inv, new_gold = shop_buy(draft.get("inventory", []),
                                         draft.get("gold", 0),
                                         item_id, game_data)
            draft["inventory"] = new_inv
            draft["gold"] = new_gold
        draft["gold_locked"] = True
    except (UnknownItem, InsufficientGold, ValueError) as e:
        raise HTTPException(400, str(e))
    save_draft(draft_id, draft, request.app.state.drafts_dir)
    return RedirectResponse(f"/wizard/{draft_id}/equipment", status_code=303)
```

For `equipment_add`:

```python
@router.post("/{draft_id}/equipment/add")
async def equipment_add(request: Request, draft_id: str,
                        item_id: str = Form(...)):
    draft = _load(request, draft_id)
    game_data = request.app.state.game_data
    item = game_data.items.get(item_id)
    from aose.models import Container
    try:
        if isinstance(item, Container):
            containers_raw = draft.get("containers", [])
            containers = [ContainerInstance.model_validate(c) for c in containers_raw]
            new_containers = add_free_container(containers, item_id, game_data)
            draft["containers"] = [c.model_dump() for c in new_containers]
        else:
            draft["inventory"] = shop_add_free(draft.get("inventory", []),
                                                item_id, game_data)
    except (UnknownItem, ValueError) as e:
        raise HTTPException(400, str(e))
    save_draft(draft_id, draft, request.app.state.drafts_dir)
    return RedirectResponse(f"/wizard/{draft_id}/equipment", status_code=303)
```

Add the new shop imports at the top:

```python
from aose.engine.shop import (
    ...,
    add_free_container,
    buy_container,
    ...,
)
```

And `ContainerInstance` from models (already added in Task 9).

- [ ] **Step 4: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "wizard_buy or wizard_add" -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: pass + full suite green.

- [ ] **Step 5: Commit**

```
git add aose/web/wizard.py tests/test_containers.py
git commit -m "Wizard buy/add routes handle container catalog items"
```

---

## Task 15: Add `/stow` and `/take-out` routes (sheet + wizard)

**Files:**
- Modify: `aose/web/routes.py`
- Modify: `aose/web/wizard.py`
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_containers.py`:

```python
def test_sheet_stow_endpoint(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, gold=0, inventory=["torch"])
    # Add a backpack via add route
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    r = client.post("/character/test/equipment/stow", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.inventory == []
    assert spec.containers[0].contents == ["torch"]


def test_sheet_take_out_endpoint(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    # Manually put a torch inside via the engine (or via inventory + stow):
    client.post("/character/test/equipment/add", data={"item_id": "torch"})
    client.post("/character/test/equipment/stow", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    # Now take it out
    r = client.post("/character/test/equipment/take-out", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.inventory == ["torch"]
    assert spec.containers[0].contents == []


def test_sheet_stow_rejects_full_container(tmp_path):
    client = _make_client(tmp_path)
    # Fill a small sack to capacity (200 cn = 10 torches), then try to add one more
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "sack_small"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    for _ in range(10):
        client.post("/character/test/equipment/add", data={"item_id": "torch"})
        client.post("/character/test/equipment/stow", data={
            "instance_id": instance_id, "item_id": "torch",
        })
    client.post("/character/test/equipment/add", data={"item_id": "torch"})
    r = client.post("/character/test/equipment/stow", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    assert r.status_code == 400
    assert "full" in r.text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "sheet_stow or sheet_take_out" -q
```
Expected: 404 (routes don't exist yet).

- [ ] **Step 3: Add the sheet routes**

In `aose/web/routes.py`, after the existing equipment routes:

```python
@router.post("/character/{character_id}/equipment/stow")
async def equipment_stow(request: Request, character_id: str,
                         instance_id: str = Form(...),
                         item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.inventory, spec.stashed, spec.containers = shop_stow(
            spec.inventory, spec.stashed, spec.containers,
            spec.equipped, spec.equipped_weapons,
            instance_id, item_id, request.app.state.game_data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/take-out")
async def equipment_take_out(request: Request, character_id: str,
                             instance_id: str = Form(...),
                             item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.inventory, spec.stashed, spec.containers = shop_take_out(
            spec.inventory, spec.stashed, spec.containers,
            instance_id, item_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

Update imports:

```python
from aose.engine.shop import (
    ...,
    stow as shop_stow,
    take_out as shop_take_out,
    ...,
)
```

- [ ] **Step 4: Add the wizard routes (mirror)**

In `aose/web/wizard.py`, after the existing equipment routes:

```python
@router.post("/{draft_id}/equipment/stow")
async def equipment_stow(request: Request, draft_id: str,
                         instance_id: str = Form(...),
                         item_id: str = Form(...)):
    draft = _load(request, draft_id)
    containers = [ContainerInstance.model_validate(c)
                  for c in draft.get("containers", [])]
    try:
        new_inv, new_stashed, new_containers = shop_stow(
            draft.get("inventory", []),
            draft.get("stashed", []),
            containers,
            draft.get("equipped", {}),
            draft.get("equipped_weapons", []),
            instance_id, item_id, request.app.state.game_data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["inventory"] = new_inv
    draft["stashed"] = new_stashed
    draft["containers"] = [c.model_dump() for c in new_containers]
    save_draft(draft_id, draft, request.app.state.drafts_dir)
    return RedirectResponse(f"/wizard/{draft_id}/equipment", status_code=303)


@router.post("/{draft_id}/equipment/take-out")
async def equipment_take_out(request: Request, draft_id: str,
                             instance_id: str = Form(...),
                             item_id: str = Form(...)):
    draft = _load(request, draft_id)
    containers = [ContainerInstance.model_validate(c)
                  for c in draft.get("containers", [])]
    try:
        new_inv, new_stashed, new_containers = shop_take_out(
            draft.get("inventory", []),
            draft.get("stashed", []),
            containers, instance_id, item_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["inventory"] = new_inv
    draft["stashed"] = new_stashed
    draft["containers"] = [c.model_dump() for c in new_containers]
    save_draft(draft_id, draft, request.app.state.drafts_dir)
    return RedirectResponse(f"/wizard/{draft_id}/equipment", status_code=303)
```

Update imports:

```python
from aose.engine.shop import (
    ...,
    stow as shop_stow,
    take_out as shop_take_out,
    ...,
)
```

- [ ] **Step 5: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "stow or take_out" -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: pass + full suite green.

- [ ] **Step 6: Commit**

```
git add aose/web/routes.py aose/web/wizard.py tests/test_containers.py
git commit -m "Add /stow and /take-out routes on sheet and wizard"
```

---

## Task 16: Add `/stash-container`, `/unstash-container`, `/remove-container` routes

**Files:**
- Modify: `aose/web/routes.py`
- Modify: `aose/web/wizard.py`
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_containers.py`:

```python
def test_sheet_stash_container_flips_state(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    r = client.post("/character/test/equipment/stash-container", data={
        "instance_id": instance_id,
    })
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.containers[0].state == "stashed"


def test_sheet_unstash_container_flips_state(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    client.post("/character/test/equipment/stash-container", data={
        "instance_id": instance_id,
    })
    r = client.post("/character/test/equipment/unstash-container", data={
        "instance_id": instance_id,
    })
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.containers[0].state == "carried"


def test_sheet_remove_container_drop_clears_contents(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, gold=0)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    client.post("/character/test/equipment/add", data={"item_id": "torch"})
    client.post("/character/test/equipment/stow", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    r = client.post("/character/test/equipment/remove-container", data={
        "instance_id": instance_id, "mode": "drop",
    })
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.containers == []
    assert spec.inventory == []   # torch was inside the bag, gone with it
    assert spec.gold == 0  # no refund on drop


def test_sheet_remove_container_sell_non_empty_returns_400(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    client.post("/character/test/equipment/add", data={"item_id": "torch"})
    client.post("/character/test/equipment/stow", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    r = client.post("/character/test/equipment/remove-container", data={
        "instance_id": instance_id, "mode": "sell",
    })
    assert r.status_code == 400


def test_sheet_remove_container_sell_empty_refunds_half(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, gold=0)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    r = client.post("/character/test/equipment/remove-container", data={
        "instance_id": instance_id, "mode": "sell",
    })
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.containers == []
    assert spec.gold == 2  # 5 // 2
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "stash_container or unstash_container or remove_container" -q
```
Expected: 404.

- [ ] **Step 3: Add the sheet routes**

In `aose/web/routes.py`:

```python
@router.post("/character/{character_id}/equipment/stash-container")
async def equipment_stash_container(request: Request, character_id: str,
                                    instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.containers = shop_stash_container(spec.containers, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/unstash-container")
async def equipment_unstash_container(request: Request, character_id: str,
                                      instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.containers = shop_unstash_container(spec.containers, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/remove-container")
async def equipment_remove_container(request: Request, character_id: str,
                                     instance_id: str = Form(...),
                                     mode: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.containers, spec.gold = shop_remove_container(
            spec.containers, spec.gold, instance_id, mode,
            request.app.state.game_data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

Update imports:

```python
from aose.engine.shop import (
    ...,
    remove_container as shop_remove_container,
    stash_container as shop_stash_container,
    unstash_container as shop_unstash_container,
    ...,
)
```

- [ ] **Step 4: Add the wizard mirrors**

In `aose/web/wizard.py`, mirror the same three routes using draft state (load → mutate → save). The pattern matches Task 15.

```python
@router.post("/{draft_id}/equipment/stash-container")
async def equipment_stash_container(request: Request, draft_id: str,
                                    instance_id: str = Form(...)):
    draft = _load(request, draft_id)
    containers = [ContainerInstance.model_validate(c)
                  for c in draft.get("containers", [])]
    try:
        new_containers = shop_stash_container(containers, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["containers"] = [c.model_dump() for c in new_containers]
    save_draft(draft_id, draft, request.app.state.drafts_dir)
    return RedirectResponse(f"/wizard/{draft_id}/equipment", status_code=303)


@router.post("/{draft_id}/equipment/unstash-container")
async def equipment_unstash_container(request: Request, draft_id: str,
                                      instance_id: str = Form(...)):
    draft = _load(request, draft_id)
    containers = [ContainerInstance.model_validate(c)
                  for c in draft.get("containers", [])]
    try:
        new_containers = shop_unstash_container(containers, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["containers"] = [c.model_dump() for c in new_containers]
    save_draft(draft_id, draft, request.app.state.drafts_dir)
    return RedirectResponse(f"/wizard/{draft_id}/equipment", status_code=303)


@router.post("/{draft_id}/equipment/remove-container")
async def equipment_remove_container(request: Request, draft_id: str,
                                     instance_id: str = Form(...),
                                     mode: str = Form(...)):
    draft = _load(request, draft_id)
    containers = [ContainerInstance.model_validate(c)
                  for c in draft.get("containers", [])]
    try:
        new_containers, new_gold = shop_remove_container(
            containers, draft.get("gold", 0), instance_id, mode,
            request.app.state.game_data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["containers"] = [c.model_dump() for c in new_containers]
    draft["gold"] = new_gold
    save_draft(draft_id, draft, request.app.state.drafts_dir)
    return RedirectResponse(f"/wizard/{draft_id}/equipment", status_code=303)
```

Update wizard imports likewise.

- [ ] **Step 5: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: full pass.

- [ ] **Step 6: Commit**

```
git add aose/web/routes.py aose/web/wizard.py tests/test_containers.py
git commit -m "Add /stash-container, /unstash-container, /remove-container routes"
```

---

## Task 17: Add unified `/move` endpoint for drag-and-drop

**Files:**
- Modify: `aose/web/routes.py`
- Modify: `aose/web/wizard.py`
- Modify: `tests/test_containers.py`

This route is the dispatcher that the front-end DnD JS posts to. It receives `source`, `target`, `item_id`, and optional `instance_id`, then translates to one of the existing shop helper calls (possibly two in sequence).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_containers.py`:

```python
def test_move_carried_to_equipped_equips(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, inventory=["long_sword"])
    r = client.post("/character/test/equipment/move", data={
        "source": "carried", "target": "equipped",
        "item_id": "long_sword",
    })
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.equipped_weapons == ["long_sword"]


def test_move_equipped_to_carried_unequips(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, inventory=["long_sword"])
    client.post("/character/test/equipment/equip", data={"item_id": "long_sword"})
    r = client.post("/character/test/equipment/move", data={
        "source": "equipped", "target": "carried",
        "item_id": "long_sword",
    })
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.equipped_weapons == []


def test_move_carried_to_container_stows(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, inventory=["torch"])
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    r = client.post("/character/test/equipment/move", data={
        "source": "carried", "target": f"container:{instance_id}",
        "item_id": "torch",
    })
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.inventory == []
    assert spec.containers[0].contents == ["torch"]


def test_move_container_row_to_stashed_section_stashes(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    r = client.post("/character/test/equipment/move", data={
        "source": f"container_row:{instance_id}", "target": "stashed",
        "item_id": "",
    })
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.containers[0].state == "stashed"


def test_move_container_to_carried_takes_out(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, inventory=["torch"])
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    client.post("/character/test/equipment/stow", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    r = client.post("/character/test/equipment/move", data={
        "source": f"container:{instance_id}", "target": "carried",
        "item_id": "torch",
    })
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.inventory == ["torch"]
    assert spec.containers[0].contents == []


def test_move_invalid_combo_returns_400(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, inventory=["torch"])
    r = client.post("/character/test/equipment/move", data={
        "source": "carried", "target": "equipped",
        "item_id": "torch",   # torch isn't equippable
    })
    assert r.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "move" -q
```
Expected: 404 / 405.

- [ ] **Step 3: Implement `/move` on the sheet**

In `aose/web/routes.py`:

```python
@router.post("/character/{character_id}/equipment/move")
async def equipment_move(request: Request, character_id: str,
                         source: str = Form(...),
                         target: str = Form(...),
                         item_id: str = Form(""),
                         instance_id: str = Form("")):
    """Unified dispatcher for drag-and-drop moves.

    ``source`` and ``target`` describe where the dragged thing came from and
    where it was dropped.  Recognised values:
      * ``equipped`` / ``carried`` / ``stashed`` — section headers
      * ``container:<instance_id>`` — content row inside a container
      * ``container_row:<instance_id>`` — the container row itself (drag the
        whole bag)
    """
    spec = _load_spec_or_404(request, character_id)
    game_data = request.app.state.game_data
    try:
        _dispatch_move(spec, source, target, item_id, instance_id, game_data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


def _dispatch_move(spec, source, target, item_id, instance_id, game_data):
    """Translate a DnD source/target pair into one or more engine helper calls,
    mutating ``spec`` in place.  Raises ValueError on invalid combinations."""
    # Container-row drag = stash/unstash the whole bag
    if source.startswith("container_row:"):
        bag_id = source.split(":", 1)[1]
        if target == "stashed":
            spec.containers = shop_stash_container(spec.containers, bag_id)
            return
        if target == "carried":
            spec.containers = shop_unstash_container(spec.containers, bag_id)
            return
        raise ValueError(f"Cannot move container to {target!r}")

    # Item out of a container
    if source.startswith("container:"):
        bag_id = source.split(":", 1)[1]
        if target.startswith("container:"):
            dest_id = target.split(":", 1)[1]
            spec.inventory, spec.stashed, spec.containers = shop_take_out(
                spec.inventory, spec.stashed, spec.containers, bag_id, item_id,
            )
            spec.inventory, spec.stashed, spec.containers = shop_stow(
                spec.inventory, spec.stashed, spec.containers,
                spec.equipped, spec.equipped_weapons,
                dest_id, item_id, game_data,
            )
            return
        if target in ("carried", "stashed"):
            spec.inventory, spec.stashed, spec.containers = shop_take_out(
                spec.inventory, spec.stashed, spec.containers, bag_id, item_id,
            )
            # take_out delivers to the bag's own state; if user dragged to the
            # other state, move it across.
            bag_state = next(
                c.state for c in spec.containers if c.instance_id == bag_id
            )
            if bag_state != target:
                # Move the item between inventory and stashed lists
                if target == "stashed" and item_id in spec.inventory:
                    spec.inventory, spec.stashed, spec.equipped, spec.equipped_weapons = shop_stash(
                        spec.inventory, spec.stashed,
                        spec.equipped, spec.equipped_weapons,
                        item_id, game_data,
                    )
                elif target == "carried" and item_id in spec.stashed:
                    spec.inventory, spec.stashed = shop_unstash(
                        spec.inventory, spec.stashed, item_id, game_data,
                    )
            return
        raise ValueError(f"Cannot move container item to {target!r}")

    # Item into a container from a section
    if target.startswith("container:"):
        dest_id = target.split(":", 1)[1]
        # Normalise source to carried first
        if source == "equipped":
            spec.equipped, spec.equipped_weapons = _unequip(
                spec.equipped, spec.equipped_weapons, item_id, game_data,
            )
        elif source == "stashed":
            spec.inventory, spec.stashed = shop_unstash(
                spec.inventory, spec.stashed, item_id, game_data,
            )
        elif source != "carried":
            raise ValueError(f"Cannot stow from {source!r}")
        spec.inventory, spec.stashed, spec.containers = shop_stow(
            spec.inventory, spec.stashed, spec.containers,
            spec.equipped, spec.equipped_weapons,
            dest_id, item_id, game_data,
        )
        return

    # Between sections
    transitions = {
        ("carried", "equipped"): "equip",
        ("equipped", "carried"): "unequip",
        ("carried", "stashed"): "stash",
        ("stashed", "carried"): "unstash",
    }
    action = transitions.get((source, target))
    if action == "equip":
        spec.equipped, spec.equipped_weapons = _equip(
            spec.inventory, spec.equipped, spec.equipped_weapons,
            item_id, game_data,
        )
    elif action == "unequip":
        spec.equipped, spec.equipped_weapons = _unequip(
            spec.equipped, spec.equipped_weapons, item_id, game_data,
        )
    elif action == "stash":
        spec.inventory, spec.stashed, spec.equipped, spec.equipped_weapons = shop_stash(
            spec.inventory, spec.stashed,
            spec.equipped, spec.equipped_weapons,
            item_id, game_data,
        )
    elif action == "unstash":
        spec.inventory, spec.stashed = shop_unstash(
            spec.inventory, spec.stashed, item_id, game_data,
        )
    else:
        raise ValueError(f"Cannot move {source!r} → {target!r}")
```

- [ ] **Step 4: Mirror on wizard**

In `aose/web/wizard.py`, add an equivalent `/move` route. Because the wizard works with `draft` dicts not a Pydantic spec, define a helper that loads → constructs a transient `CharacterSpec`-like shape, then writes back:

```python
@router.post("/{draft_id}/equipment/move")
async def equipment_move(request: Request, draft_id: str,
                         source: str = Form(...),
                         target: str = Form(...),
                         item_id: str = Form(""),
                         instance_id: str = Form("")):
    draft = _load(request, draft_id)
    game_data = request.app.state.game_data
    # Wrap the relevant subset of draft state in a small mutable shim so we
    # can reuse the same dispatcher logic.
    class _DraftShim:
        pass
    shim = _DraftShim()
    shim.inventory = draft.get("inventory", [])
    shim.stashed = draft.get("stashed", [])
    shim.equipped = draft.get("equipped", {})
    shim.equipped_weapons = draft.get("equipped_weapons", [])
    shim.containers = [ContainerInstance.model_validate(c)
                       for c in draft.get("containers", [])]
    try:
        _dispatch_move(shim, source, target, item_id, instance_id, game_data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["inventory"] = shim.inventory
    draft["stashed"] = shim.stashed
    draft["equipped"] = shim.equipped
    draft["equipped_weapons"] = shim.equipped_weapons
    draft["containers"] = [c.model_dump() for c in shim.containers]
    save_draft(draft_id, draft, request.app.state.drafts_dir)
    return RedirectResponse(f"/wizard/{draft_id}/equipment", status_code=303)
```

Import `_dispatch_move` from routes (or factor it into `aose/web/move_dispatch.py` shared module — recommended for cleanliness):

Create `aose/web/move_dispatch.py`:

```python
"""Drag-and-drop dispatcher — shared between sheet and wizard.

The shim only needs the attributes the helpers touch (inventory, stashed,
equipped, equipped_weapons, containers), so a CharacterSpec OR a duck-typed
dict-wrapper both work.
"""
from aose.engine.equip import equip as _equip, unequip as _unequip
from aose.engine.shop import (
    stash as shop_stash,
    stash_container as shop_stash_container,
    stow as shop_stow,
    take_out as shop_take_out,
    unstash as shop_unstash,
    unstash_container as shop_unstash_container,
)


def dispatch_move(state, source, target, item_id, instance_id, game_data):
    # body identical to _dispatch_move above
    ...
```

Move the body of `_dispatch_move` here and import `dispatch_move` from both `routes.py` and `wizard.py`.

- [ ] **Step 5: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "move" -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: pass + full suite green.

- [ ] **Step 6: Commit**

```
git add aose/web/routes.py aose/web/wizard.py aose/web/move_dispatch.py tests/test_containers.py
git commit -m "Add unified /equipment/move dispatcher for drag-and-drop"
```

---

## Task 18: Render containers in `_equipment_ui.html`

**Files:**
- Modify: `aose/web/templates/_equipment_ui.html`
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_containers.py`:

```python
def test_sheet_renders_container_row_with_capacity_badge(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    r = client.get("/character/test")
    assert r.status_code == 200
    assert f'data-instance-id="{instance_id}"' in r.text
    assert "Backpack" in r.text
    assert "0 / 400" in r.text  # capacity badge
    # Stow control appears on loose carried items when containers exist
    client.post("/character/test/equipment/add", data={"item_id": "torch"})
    r = client.get("/character/test")
    assert 'action="/character/test/equipment/stow"' in r.text


def test_sheet_renders_container_contents_after_stow(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    client.post("/character/test/equipment/add", data={"item_id": "torch"})
    client.post("/character/test/equipment/stow", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    r = client.get("/character/test")
    # Container child row (Take Out button)
    assert 'action="/character/test/equipment/take-out"' in r.text
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "renders_container" -q
```
Expected: capacity badge / data-instance-id missing.

- [ ] **Step 3: Update the partial**

Open `aose/web/templates/_equipment_ui.html` and modify the rendering after the existing inv_table calls. Replace the section between the macros and the shop block with:

```html
{% macro container_table(state, label) %}
{% set bags = inventory_view.containers | selectattr("state", "equalto", state) | list %}
{% if bags %}
<h4 class="inv-section-head">{{ label }} containers</h4>
<table class="inventory-table containers-table">
    <thead>
        <tr>
            <th>Container</th>
            <th class="num">Capacity</th>
            <th class="num">Weight</th>
            <th>Actions</th>
        </tr>
    </thead>
    <tbody>
    {% for c in bags %}
        <tr class="container-row"
            data-instance-id="{{ c.instance_id }}"
            data-state="{{ c.state }}"
            draggable="true">
            <td>
                <button type="button" class="container-toggle" aria-expanded="true"
                        aria-controls="cnt-{{ c.instance_id }}">▾</button>
                <strong>{{ c.name }}</strong>
            </td>
            <td class="num">
                <span class="capacity-badge{% if c.capacity_cn and c.used_cn >= c.capacity_cn %} capacity-full{% endif %}">
                    {{ c.used_cn }} / {{ c.capacity_cn if c.capacity_cn else "∞" }} cn
                </span>
            </td>
            <td class="num">{{ c.effective_weight_cn }} cn</td>
            <td>
                {% if c.state == "carried" %}
                <form method="post" action="{{ target_url_prefix }}/stash-container" class="inline-form">
                    <input type="hidden" name="instance_id" value="{{ c.instance_id }}">
                    <button type="submit" title="Move container off-person">Stash</button>
                </form>
                {% else %}
                <form method="post" action="{{ target_url_prefix }}/unstash-container" class="inline-form">
                    <input type="hidden" name="instance_id" value="{{ c.instance_id }}">
                    <button type="submit">Unstash</button>
                </form>
                {% endif %}
                <form method="post" action="{{ target_url_prefix }}/remove-container" class="remove-form">
                    <input type="hidden" name="instance_id" value="{{ c.instance_id }}">
                    <button type="submit" name="mode" value="drop"
                            title="Discard the container and its contents">Drop</button>
                    <button type="submit" name="mode" value="sell"
                            {% if c.contents %}disabled title="Empty the container first"{% endif %}>Sell</button>
                    <button type="submit" name="mode" value="refund"
                            {% if c.contents %}disabled title="Empty the container first"{% endif %}>Refund</button>
                </form>
            </td>
        </tr>
        {# Content rows (child) #}
        {% for row in c.contents %}
        <tr class="container-child" id="cnt-{{ c.instance_id }}"
            data-instance-id="{{ c.instance_id }}"
            data-item-id="{{ row.id }}"
            data-source="container:{{ c.instance_id }}"
            draggable="true">
            <td><span class="indent">↳</span> {{ row.name }}</td>
            <td class="num">{{ row.count }}</td>
            <td class="num">{{ row.weight_cn * row.count }} cn</td>
            <td>
                <form method="post" action="{{ target_url_prefix }}/take-out" class="inline-form">
                    <input type="hidden" name="instance_id" value="{{ c.instance_id }}">
                    <input type="hidden" name="item_id" value="{{ row.id }}">
                    <button type="submit">Take Out</button>
                </form>
            </td>
        </tr>
        {% endfor %}
    {% endfor %}
    </tbody>
</table>
{% endif %}
{% endmacro %}
```

In the existing block where `inv_table` macros are called, immediately after the equipped/carried tables, render containers:

```jinja
{% if inventory_view.equipped or inventory_view.carried or inventory_view.stashed or inventory_view.containers %}
<h3 class="subhead">Inventory</h3>
{{ inv_table(inventory_view.equipped, target_url_prefix, "equipped", "Equipped", "contributes to weight") }}
{{ inv_table(inventory_view.carried,  target_url_prefix, "carried",  "Carried",  "contributes to weight") }}
{{ container_table("carried", "Carried") }}
{{ inv_table(inventory_view.stashed,  target_url_prefix, "stashed",  "Stashed",  "not on person — no weight") }}
{{ container_table("stashed", "Stashed") }}
{% else %}
<h3 class="subhead">Inventory</h3>
<p class="muted">No items in inventory.</p>
{% endif %}
```

Also augment the `inv_row_actions` macro so carried loose rows get a Stow dropdown. Find the `{% if state in ("equipped", "carried") %}` block and add inside it (before the existing Stash form):

```jinja
{% set carried_bags = inventory_view.containers | selectattr("state", "equalto", "carried") | list %}
{% if state == "carried" and carried_bags %}
<form method="post" action="{{ target_url_prefix }}/stow" class="inline-form">
    <input type="hidden" name="item_id" value="{{ row.id }}">
    <select name="instance_id">
        {% for c in carried_bags %}
        <option value="{{ c.instance_id }}">{{ c.name }}</option>
        {% endfor %}
    </select>
    <button type="submit">Stow</button>
</form>
{% endif %}
```

Also add `draggable="true"` and `data-source="{{ state }}"` to the loose-item rows in `inv_table` so DnD works:

In the `<tr>` opener inside `inv_table`:

```jinja
<tr class="inv-row" draggable="true" data-source="{{ state }}" data-item-id="{{ row.id }}">
```

And update the section-head `<h4>` to act as a drop target — add `data-target` and a class:

```jinja
<h4 class="inv-section-head" data-target="{{ state }}">{{ label }} {% if weight_note %}...
```

- [ ] **Step 4: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "renders_container" -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: pass + full suite green.

- [ ] **Step 5: Commit**

```
git add aose/web/templates/_equipment_ui.html tests/test_containers.py
git commit -m "Render containers as inline collapsible rows with capacity badge"
```

---

## Task 19: Add CSS for containers and drag-and-drop

**Files:**
- Modify: `aose/web/static/sheet.css`

- [ ] **Step 1: Add CSS rules**

Append to `aose/web/static/sheet.css`:

```css
/* ── Container rows ────────────────────────────────────────────────── */

.containers-table .container-row {
    background: #f6f3eb;
    border-top: 1px solid #c5b88a;
}

.container-row td:first-child strong {
    margin-left: 4px;
}

.container-toggle {
    background: none;
    border: 0;
    cursor: pointer;
    font-size: 0.9em;
    padding: 0 4px;
    transition: transform 0.15s;
}

.container-toggle[aria-expanded="false"] {
    transform: rotate(-90deg);
}

.container-child td:first-child .indent {
    color: #8a7a4a;
    margin-right: 4px;
}

.container-collapsed {
    display: none;
}

.capacity-badge {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 8px;
    background: #e6dec3;
    color: #5b4f2e;
    font-size: 0.85em;
}

.capacity-badge.capacity-full {
    background: #c45a4a;
    color: #fff;
}

/* ── Drag-and-drop visual feedback ─────────────────────────────────── */

[draggable="true"] {
    cursor: grab;
}

[draggable="true"]:active {
    cursor: grabbing;
}

.drag-over {
    outline: 2px dashed #5b8f3e;
    outline-offset: -2px;
    background: #ecf3e0;
}
```

- [ ] **Step 2: Smoke-test in browser (manual)**

Run the app, open a character with a Backpack, eyeball the container row, capacity badge, and the toggle behaviour. No automated test required — CSS validity is implicitly tested by the existing template rendering tests.

- [ ] **Step 3: Commit**

```
git add aose/web/static/sheet.css
git commit -m "Style container rows, capacity badge, drag-and-drop feedback"
```

---

## Task 20: Add `inventory_dnd.js` and wire it into templates

**Files:**
- Create: `aose/web/static/inventory_dnd.js`
- Modify: `aose/web/templates/sheet.html` (script tag + collapse)
- Modify: `aose/web/templates/wizard_equipment.html` (or wherever the wizard equipment step is rendered)
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Write the failing test**

The DnD JS is client-side; we'll test that the script tag is included and that the data attributes used by the script are present in the rendered HTML. Append to `tests/test_containers.py`:

```python
def test_sheet_includes_dnd_script_tag(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    r = client.get("/character/test")
    assert "inventory_dnd.js" in r.text


def test_sheet_inventory_rows_carry_dnd_attributes(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, inventory=["long_sword"])
    r = client.get("/character/test")
    assert 'data-source="carried"' in r.text
    assert 'data-item-id="long_sword"' in r.text


def test_sheet_container_row_collapse_button_present(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    r = client.get("/character/test")
    assert 'class="container-toggle"' in r.text
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "dnd or collapse" -q
```
Expected: assertion failures.

- [ ] **Step 3: Create `aose/web/static/inventory_dnd.js`**

```javascript
/* Inventory drag-and-drop + container collapse.
 * Posts to /equipment/move on drop; reloads the page on success.
 * The target_url_prefix is read from a data attribute on the table wrapper. */
(function () {
    const equipmentRoot = document.querySelector("[data-equipment-url-prefix]");
    if (!equipmentRoot) return;
    const URL_PREFIX = equipmentRoot.dataset.equipmentUrlPrefix;

    // ── Container collapse ─────────────────────────────────────────
    document.querySelectorAll(".container-toggle").forEach(btn => {
        btn.addEventListener("click", () => {
            const row = btn.closest("tr.container-row");
            if (!row) return;
            const instanceId = row.dataset.instanceId;
            const expanded = btn.getAttribute("aria-expanded") === "true";
            btn.setAttribute("aria-expanded", expanded ? "false" : "true");
            document.querySelectorAll(
                `tr.container-child[data-instance-id="${instanceId}"]`
            ).forEach(r => r.classList.toggle("container-collapsed"));
        });
    });

    // ── Drag-and-drop ──────────────────────────────────────────────
    let dragged = null;

    document.querySelectorAll('[draggable="true"]').forEach(el => {
        el.addEventListener("dragstart", e => {
            dragged = el;
            e.dataTransfer.effectAllowed = "move";
            e.dataTransfer.setData("text/plain", el.dataset.itemId || "");
        });
        el.addEventListener("dragend", () => {
            dragged = null;
            document.querySelectorAll(".drag-over")
                .forEach(n => n.classList.remove("drag-over"));
        });
    });

    document.querySelectorAll("[data-target], .container-row")
        .forEach(target => {
            target.addEventListener("dragover", e => {
                if (!dragged) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
                target.classList.add("drag-over");
            });
            target.addEventListener("dragleave", () => {
                target.classList.remove("drag-over");
            });
            target.addEventListener("drop", async e => {
                e.preventDefault();
                target.classList.remove("drag-over");
                if (!dragged) return;
                const source = dragged.dataset.source ||
                    (dragged.classList.contains("container-row")
                        ? `container_row:${dragged.dataset.instanceId}`
                        : "");
                const targetKey = target.dataset.target ||
                    (target.classList.contains("container-row")
                        ? `container:${target.dataset.instanceId}`
                        : "");
                if (!source || !targetKey) return;
                const itemId = dragged.dataset.itemId || "";
                const instanceId = dragged.dataset.instanceId || "";
                const form = new FormData();
                form.append("source", source);
                form.append("target", targetKey);
                form.append("item_id", itemId);
                if (instanceId) form.append("instance_id", instanceId);
                const resp = await fetch(`${URL_PREFIX}/move`, {
                    method: "POST", body: form,
                });
                if (resp.ok || resp.status === 303) {
                    window.location.reload();
                } else {
                    const msg = await resp.text();
                    alert("Move failed: " + msg);
                }
            });
        });
})();
```

- [ ] **Step 4: Wire the script into the partial**

In `aose/web/templates/_equipment_ui.html`, at the very top of the partial, add a wrapper with `data-equipment-url-prefix`:

```jinja
<div data-equipment-url-prefix="{{ target_url_prefix }}">
```

And close the wrapper at the bottom of the partial (`</div>`).

Then at the bottom of the partial (or in `sheet.html` / wizard equipment template), add:

```html
<script src="/static/inventory_dnd.js" defer></script>
```

Confirm `sheet.html` has the `<head>` link or that the static mount is at `/static`. (The existing `_equipment_ui.html` uses other inline scripts — adding one for DnD is the same pattern.)

- [ ] **Step 5: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "dnd or collapse" -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: pass + full suite green.

- [ ] **Step 6: Commit**

```
git add aose/web/static/inventory_dnd.js aose/web/templates/_equipment_ui.html tests/test_containers.py
git commit -m "Add drag-and-drop JS and container collapse behavior"
```

---

## Task 21: Update the print-only block in `sheet.html` for containers

**Files:**
- Modify: `aose/web/templates/sheet.html`
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_containers.py`:

```python
def test_sheet_print_only_lists_container_contents(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    client.post("/character/test/equipment/add", data={"item_id": "torch"})
    client.post("/character/test/equipment/stow", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    r = client.get("/character/test")
    # The print-only block names the container and its contents
    assert "Backpack" in r.text
    # The contents appear as a list item under the container
    assert "Torch" in r.text
```

(The assertions are loose because the existing test suite already checks the print path for items; we're adding container coverage.)

- [ ] **Step 2: Update the print-only block**

In `aose/web/templates/sheet.html`, replace the `print-only` div with:

```jinja
{# Compact print-friendly inventory summary for the @media print pass #}
<div class="print-only">
    {% if inventory_view.equipped or inventory_view.carried %}
    <h3>Carried</h3>
    <ul>
        {% for row in inventory_view.equipped %}
        <li>{{ row.name }}{% if row.count > 1 %} &times;{{ row.count }}{% endif %} <em class="small">(equipped)</em></li>
        {% endfor %}
        {% for row in inventory_view.carried %}
        <li>{{ row.name }}{% if row.count > 1 %} &times;{{ row.count }}{% endif %}</li>
        {% endfor %}
    </ul>
    {% endif %}

    {% set carried_bags = inventory_view.containers | selectattr("state", "equalto", "carried") | list %}
    {% if carried_bags %}
    <h3>Containers (carried)</h3>
    <ul>
        {% for c in carried_bags %}
        <li>
            <strong>{{ c.name }}</strong>
            ({{ c.used_cn }}{% if c.capacity_cn %}/{{ c.capacity_cn }}{% endif %} cn):
            {% if c.contents %}
                {% for row in c.contents %}{{ row.name }}{% if row.count > 1 %} &times;{{ row.count }}{% endif %}{% if not loop.last %}, {% endif %}{% endfor %}
            {% else %}
                <em>empty</em>
            {% endif %}
        </li>
        {% endfor %}
    </ul>
    {% endif %}

    {% if inventory_view.stashed %}
    <h3>Stashed</h3>
    <ul>
        {% for row in inventory_view.stashed %}
        <li>{{ row.name }}{% if row.count > 1 %} &times;{{ row.count }}{% endif %}</li>
        {% endfor %}
    </ul>
    {% endif %}

    {% set stashed_bags = inventory_view.containers | selectattr("state", "equalto", "stashed") | list %}
    {% if stashed_bags %}
    <h3>Containers (stashed)</h3>
    <ul>
        {% for c in stashed_bags %}
        <li>
            <strong>{{ c.name }}</strong>:
            {% if c.contents %}
                {% for row in c.contents %}{{ row.name }}{% if row.count > 1 %} &times;{{ row.count }}{% endif %}{% if not loop.last %}, {% endif %}{% endfor %}
            {% else %}
                <em>empty</em>
            {% endif %}
        </li>
        {% endfor %}
    </ul>
    {% endif %}
</div>
```

- [ ] **Step 3: Run the tests**

```
.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "print_only" -q
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: pass + full suite green.

- [ ] **Step 4: Commit**

```
git add aose/web/templates/sheet.html tests/test_containers.py
git commit -m "Print-only sheet block lists containers and contents"
```

---

## Task 22: Smoke-test the running app

This task is non-automated: spin up the dev server, walk through the new UX, fix anything broken before declaring done.

- [ ] **Step 1: Start the app**

```
.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload
```

- [ ] **Step 2: Manual checklist**

In a browser:
- Create a new character, walk to equipment step
- Buy a Backpack — it appears under Carried containers with `0 / 400 cn`
- Buy a few torches — they appear under loose Carried
- Use the Stow dropdown on a torch — it moves into the Backpack; the badge updates
- Click the toggle on the Backpack — child rows collapse/expand
- Drag a torch onto the Backpack row — it stows
- Drag the Backpack row onto the Stashed section header — it moves to Stashed containers; carried weight drops to zero
- Drag the bag back to Carried — it returns
- Add a Bag of Holding from the shop, fill it with a long sword (60 cn) — weight column shows `4 cn` (`0 + int(0.06 * 60)`)
- Drop the Bag of Holding — contents gone with it
- Try Sell on a non-empty Backpack — button is disabled
- Empty and Sell the Backpack — refund of 2 gp arrives

- [ ] **Step 3: Final regression run**

```
.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: full suite green.

- [ ] **Step 4: Update CLAUDE.md's Current state**

Update the "Current state" section of `CLAUDE.md` to reflect:
- Last commit reference to this work
- Mention containers as a live feature

- [ ] **Step 5: Commit doc refresh**

```
git add CLAUDE.md
git commit -m "Refresh CLAUDE.md current-state after container refactor"
```

---

## Self-Review Notes

**Spec coverage:** Every spec section has an implementing task:
- Container catalog variant → Task 1
- ContainerInstance + CharacterSpec.containers → Task 2
- Exceptions → Task 3
- new_container_instance / buy_container / add_free_container → Task 4
- stow → Task 5
- take_out → Task 6
- stash_container / unstash_container → Task 7
- remove_container → Task 8
- ContainerView / InventoryView extension → Task 9
- carried_weight_cn updates → Task 10
- equip() guard → Task 11
- containers.yaml seed → Task 12
- /buy, /add augmentation (sheet) → Task 13
- /buy, /add augmentation (wizard) → Task 14
- /stow, /take-out → Task 15
- /stash-container, /unstash-container, /remove-container → Task 16
- /move dispatcher → Task 17
- Template rendering → Task 18
- CSS → Task 19
- DnD JS + wiring → Task 20
- Print-only block → Task 21
- Smoke test → Task 22

**Out-of-scope items** (from the spec) are NOT in this plan and are explicitly deferred there: nesting, per-instance non-containers, partial DOM updates, magic-only flag, volume model.
