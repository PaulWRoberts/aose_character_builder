# Inventory Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the inventory UI's top-level concepts (Carried, Stashed, each animal/vehicle/retainer) map 1:1 to data locations, with coins and treasure as location-aware stackable items that move between top-levels and into containers, and a shop that spends only on-person coins lowest-denomination-first.

**Architecture:** A new `StorageLocation` pointer model addresses where value-stacks (coins/gems/jewellery) sit; loose items keep their `list[str]` storage. A new `aose/engine/storage.py` owns all movement + per-stack conversion. `currency`/`encumbrance`/`shop` become location-aware; encumbrance counts only the Carried bucket. The shared `_equipment_ui.html` partial renders one reusable top-level-group macro for every location.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, pytest. Run tests with `.venv\Scripts\python.exe -m pytest tests/ -q`. Run the app with `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`.

**Conventions:**
- The trailing `PermissionError` on `pytest-current` is a known Windows pytest-9 quirk — ignore it.
- No data migrations are required (app is undeployed); coercion validators are a courtesy for existing saves and are tested.
- Engine modules stay cycle-free: `models → loader → magic → features`. The new `storage.py` imports only `models` + `loader`.

**Spec:** [`docs/superpowers/specs/2026-06-18-inventory-consolidation-design.md`](../specs/2026-06-18-inventory-consolidation-design.md)

---

## File structure

**Create:**
- `aose/models/storage.py` — `StorageLocation`, `CoinStack`.
- `aose/engine/storage.py` — movement + conversion engine (the single movement vocabulary).
- `tests/test_storage_location.py`, `tests/test_storage_engine.py`, `tests/test_shop_spend.py`, `tests/test_inventory_move_routes.py`.

**Modify:**
- `aose/models/__init__.py` — export `StorageLocation`, `CoinStack`.
- `aose/models/character.py` — replace 5 int coin fields with `coins`; refactor `ContainerInstance.location`; coercion validators.
- `aose/models/valuable.py` — add `location` to `GemStack`/`JewelleryPiece`.
- `aose/engine/currency.py` — location-aware value/weight; convert core extracted.
- `aose/engine/valuables.py` — carried-only weight; `location` on add helpers.
- `aose/engine/encumbrance.py` — carried-only weight; container contents include value-stacks.
- `aose/engine/shop.py` — `spend()`; buy/sell/refund onto carried gp; container helpers onto `StorageLocation`.
- `aose/engine/quick_equipment.py` — starting gold → carried gp stack.
- `aose/sheet/view.py` — top-level-group inventory view; wealth total.
- `aose/web/routes.py` — move/convert/add routes; buy/sell wiring; retire old coin/container routes.
- `aose/web/templates/_equipment_ui.html` — top-level-group macro, per-row Move/Convert, inline containers, removal of tracker/money-change.
- `aose/web/templates/sheet.html`, `sheet_print.html` — wealth readout; print groups.
- `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`, `CLAUDE.md` — on landing.

---

## STAGE 1 — Model + coercion validators

### Task 1: `StorageLocation` model

**Files:**
- Create: `aose/models/storage.py`
- Test: `tests/test_storage_location.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storage_location.py
import pytest
from pydantic import ValidationError
from aose.models.storage import StorageLocation, CoinStack


def test_storage_location_defaults_to_carried_with_no_id():
    loc = StorageLocation(kind="carried")
    assert loc.kind == "carried"
    assert loc.id is None


def test_storage_location_container_carries_an_id():
    loc = StorageLocation(kind="container", id="abc123")
    assert loc.id == "abc123"


def test_storage_locations_equal_by_kind_and_id():
    assert StorageLocation(kind="animal", id="x") == StorageLocation(kind="animal", id="x")
    assert StorageLocation(kind="animal", id="x") != StorageLocation(kind="animal", id="y")


def test_coin_stack_defaults_to_carried():
    s = CoinStack(denom="gp", count=5)
    assert s.location == StorageLocation(kind="carried")
    assert (s.denom, s.count) == ("gp", 5)


def test_coin_stack_rejects_unknown_denom():
    with pytest.raises(ValidationError):
        CoinStack(denom="zp", count=1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_location.py -q`
Expected: FAIL — `ModuleNotFoundError: aose.models.storage`.

- [ ] **Step 3: Write the model**

```python
# aose/models/storage.py
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LocationKind = Literal["carried", "stashed", "animal", "vehicle", "container"]


class StorageLocation(BaseModel):
    """Where a value-stack (coins/gems/jewellery) or a container sits.

    Pointer model: a stack inside a container stores ``kind="container"`` +
    the container's ``instance_id``; the container owns its own bucket
    (carried/stashed/animal/vehicle), so moving the container moves its
    contents for free. ``id`` is the carrier/container instance_id; None for
    the person-level carried/stashed buckets.

    A *container's own* location may only be carried/stashed/animal/vehicle
    (never ``container`` — no nesting); this is enforced on
    ``ContainerInstance``, not here, so a value-stack can still use all five.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: LocationKind
    id: str | None = None


class CoinStack(BaseModel):
    """A stack of one coin denomination at one location. At most one stack
    per (denom, location); empty stacks are pruned by the movement engine."""
    model_config = ConfigDict(extra="forbid")

    denom: Literal["pp", "gp", "ep", "sp", "cp"]
    count: int
    location: StorageLocation = Field(default_factory=lambda: StorageLocation(kind="carried"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_location.py -q`
Expected: PASS.

- [ ] **Step 5: Export the new models**

In `aose/models/__init__.py`, add after the `.character` import block:

```python
from .storage import StorageLocation, CoinStack
```

and add `"StorageLocation",` and `"CoinStack",` to `__all__`.

- [ ] **Step 6: Commit**

```bash
git add aose/models/storage.py aose/models/__init__.py tests/test_storage_location.py
git commit -m "feat(models): StorageLocation + CoinStack"
```

---

### Task 2: Located gems & jewellery

**Files:**
- Modify: `aose/models/valuable.py`
- Test: `tests/test_storage_location.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_storage_location.py
from aose.models import GemStack, JewelleryPiece
from aose.models.storage import StorageLocation


def test_gem_stack_defaults_to_carried_location():
    g = GemStack(instance_id="g1", value=100)
    assert g.location == StorageLocation(kind="carried")


def test_gem_stack_accepts_explicit_location():
    g = GemStack(instance_id="g1", value=100, location=StorageLocation(kind="vehicle", id="v1"))
    assert g.location.kind == "vehicle"


def test_jewellery_defaults_to_carried_location():
    j = JewelleryPiece(instance_id="j1", value=300)
    assert j.location == StorageLocation(kind="carried")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_location.py -q`
Expected: FAIL — `GemStack` has no `location`.

- [ ] **Step 3: Add `location` to both models**

In `aose/models/valuable.py`, add the import and a `location` field to each model:

```python
from pydantic import BaseModel, ConfigDict, Field

from .storage import StorageLocation
```

In `GemStack`, after `label`:

```python
    location: StorageLocation = Field(default_factory=lambda: StorageLocation(kind="carried"))
```

In `JewelleryPiece`, after `label`:

```python
    location: StorageLocation = Field(default_factory=lambda: StorageLocation(kind="carried"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_location.py -q`
Expected: PASS. (Old saves without `location` get the default — no migration needed.)

- [ ] **Step 5: Commit**

```bash
git add aose/models/valuable.py tests/test_storage_location.py
git commit -m "feat(models): located gems & jewellery"
```

---

### Task 3: `CharacterSpec.coins` replaces the five int fields

**Files:**
- Modify: `aose/models/character.py`
- Test: `tests/test_storage_location.py` (extend)

- [ ] **Step 1: Write the failing test (coercion of legacy saves)**

```python
# append to tests/test_storage_location.py
from aose.models import CharacterSpec, CoinStack


def _minimal_spec_dict(**extra):
    base = dict(
        name="T", abilities={"str": 10, "dex": 10, "con": 10,
                             "int": 10, "wis": 10, "cha": 10},
        race_id="human", classes=[{"class_id": "fighter", "level": 1}],
        alignment="neutral",
    )
    base.update(extra)
    return base


def test_legacy_int_coins_coerced_to_carried_stacks():
    spec = CharacterSpec.model_validate(
        _minimal_spec_dict(gold=12, silver=3, platinum=0)
    )
    by_denom = {s.denom: s for s in spec.coins}
    assert by_denom["gp"].count == 12
    assert by_denom["gp"].location.kind == "carried"
    assert by_denom["sp"].count == 3
    assert "pp" not in by_denom            # zero denominations dropped
    # legacy attributes are gone
    assert not hasattr(spec, "gold")


def test_new_spec_defaults_to_empty_coins():
    spec = CharacterSpec.model_validate(_minimal_spec_dict())
    assert spec.coins == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_location.py -k coins -q`
Expected: FAIL — `gold` still an int field / `coins` missing.

- [ ] **Step 3: Replace the fields and add the validator**

In `aose/models/character.py`:

Add to the imports at top:

```python
from .storage import CoinStack
```

Replace the five coin lines in `CharacterSpec`:

```python
    gold: int = 0            # gp — the shop-spendable balance
    platinum: int = 0        # pp
    electrum: int = 0        # ep
    silver: int = 0          # sp
    copper: int = 0          # cp
```

with:

```python
    # Coins are located stackable items: at most one stack per (denom, location).
    # The shop spends only carried (on-person) stacks. See aose/engine/storage.py.
    coins: list[CoinStack] = Field(default_factory=list)
```

Add this validator inside `CharacterSpec` (next to the other `model_validator(mode="before")` methods):

```python
    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_int_coins(cls, data):
        """Coerce the pre-located int coin fields (gold/platinum/electrum/
        silver/copper) into carried CoinStacks. Zero denominations are dropped.
        Keeps old saves loadable under extra='forbid'."""
        if not isinstance(data, dict):
            return data
        _legacy = {"copper": "cp", "silver": "sp", "electrum": "ep",
                   "gold": "gp", "platinum": "pp"}
        present = [k for k in _legacy if k in data]
        if not present:
            return data
        existing = list(data.get("coins") or [])
        for attr, denom in _legacy.items():
            count = data.get(attr) or 0
            if count:
                existing.append({"denom": denom, "count": count,
                                 "location": {"kind": "carried"}})
        data = {k: v for k, v in data.items() if k not in _legacy}
        data["coins"] = existing
        return data
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_location.py -k coins -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/models/character.py tests/test_storage_location.py
git commit -m "feat(models): coins as located stacks; coerce legacy int coins"
```

---

### Task 4: `ContainerInstance.location` refactor

**Files:**
- Modify: `aose/models/character.py`
- Test: `tests/test_storage_location.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_storage_location.py
from aose.models import ContainerInstance


def test_container_new_shape_uses_storage_location():
    c = ContainerInstance(instance_id="c1", catalog_id="backpack",
                          location=StorageLocation(kind="stashed"))
    assert c.location.kind == "stashed"


def test_container_legacy_state_location_coerced():
    # old shape: state + location(person/animal/vehicle) + location_id
    c = ContainerInstance.model_validate({
        "instance_id": "c1", "catalog_id": "backpack",
        "state": "stashed", "location": "person", "location_id": None,
        "contents": ["torch"],
    })
    assert c.location == StorageLocation(kind="stashed")
    assert c.contents == ["torch"]


def test_container_legacy_on_animal_coerced():
    c = ContainerInstance.model_validate({
        "instance_id": "c1", "catalog_id": "saddlebags",
        "state": "carried", "location": "animal", "location_id": "a1",
    })
    assert c.location == StorageLocation(kind="animal", id="a1")


def test_container_rejects_nested_container_location():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ContainerInstance(instance_id="c1", catalog_id="backpack",
                          location=StorageLocation(kind="container", id="c2"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_location.py -k container -q`
Expected: FAIL — `ContainerInstance` still has `state`.

- [ ] **Step 3: Refactor `ContainerInstance`**

In `aose/models/character.py`, replace the `ContainerInstance` body's location fields. Replace:

```python
    instance_id: str
    catalog_id: str
    state: Literal["carried", "stashed"]
    contents: list[str] = Field(default_factory=list)
    location: Literal["person", "animal", "vehicle"] = "person"
    location_id: str | None = None
```

with:

```python
    instance_id: str
    catalog_id: str
    # carried/stashed/animal/vehicle only — never "container" (no nesting).
    location: StorageLocation = Field(default_factory=lambda: StorageLocation(kind="carried"))
    contents: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_location(cls, data):
        """Coerce old (state, location=person|animal|vehicle, location_id) into
        a single StorageLocation."""
        if not isinstance(data, dict):
            return data
        if "state" not in data and "location_id" not in data:
            return data  # already new shape (or default)
        state = data.pop("state", "carried")
        carrier = data.pop("location", "person")
        carrier_id = data.pop("location_id", None)
        if carrier == "person":
            data["location"] = {"kind": state}
        else:
            data["location"] = {"kind": carrier, "id": carrier_id}
        return data

    @model_validator(mode="after")
    def _no_nesting(self):
        if self.location.kind == "container":
            raise ValueError("a container cannot live inside another container")
        return self
```

Ensure `StorageLocation` is imported in `character.py`:

```python
from .storage import CoinStack, StorageLocation
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_location.py -k container -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/models/character.py tests/test_storage_location.py
git commit -m "feat(models): ContainerInstance.location as StorageLocation"
```

---

## STAGE 2 — Movement, currency, encumbrance & wealth engines

### Task 5: Currency rework (location-aware value + weight; extract convert core)

**Files:**
- Modify: `aose/engine/currency.py`
- Test: `tests/test_currency.py` (rewrite to new shapes)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_currency.py  (replace file contents)
import pytest
from aose.engine import currency
from aose.models import CharacterSpec, CoinStack
from aose.models.storage import StorageLocation


def _spec(coins):
    return CharacterSpec.model_validate(dict(
        name="T", abilities={"str":10,"dex":10,"con":10,"int":10,"wis":10,"cha":10},
        race_id="human", classes=[{"class_id":"fighter","level":1}],
        alignment="neutral", coins=coins,
    ))


def test_total_value_gp_sums_all_locations():
    spec = _spec([
        CoinStack(denom="gp", count=5),
        CoinStack(denom="sp", count=10, location=StorageLocation(kind="stashed")),
    ])
    assert currency.total_value_gp(spec) == 6   # 5gp + 100cp = 6gp


def test_coin_count_carried_only_is_the_encumbrance_weight():
    spec = _spec([
        CoinStack(denom="gp", count=5),                                           # carried
        CoinStack(denom="gp", count=99, location=StorageLocation(kind="stashed")),# off-person
    ])
    assert currency.coin_count(spec, carried_only=True) == 5
    assert currency.coin_count(spec) == 104


def test_carried_coins_returns_only_carried_kind():
    spec = _spec([
        CoinStack(denom="gp", count=5),
        CoinStack(denom="cp", count=7, location=StorageLocation(kind="container", id="c1")),
    ])
    carried = currency.carried_coins(spec)
    assert {c.denom for c in carried} == {"gp"}


def test_convert_amount_whole_coin_enforced():
    assert currency.convert_amount("gp", "sp", 2) == 20      # 2gp -> 20sp
    with pytest.raises(currency.CurrencyError):
        currency.convert_amount("cp", "sp", 5)               # 5cp != whole sp
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_currency.py -q`
Expected: FAIL — signatures changed / functions missing.

- [ ] **Step 3: Rewrite `currency.py`**

```python
# aose/engine/currency.py  (replace file contents)
"""Multi-coin currency — location-aware value & weight helpers.

Coins live as ``CoinStack``s on ``CharacterSpec.coins`` (denom/count/location).
This module computes value (all locations, for the wealth readout) and weight
(carried-only, for encumbrance), plus the pure ``convert_amount`` core that the
movement engine's per-stack conversion calls. Imports only models.
"""
from __future__ import annotations

from aose.models import CharacterSpec, CoinStack

DENOMINATIONS = ("pp", "gp", "ep", "sp", "cp")
RATES = {"pp": 500, "gp": 100, "ep": 50, "sp": 10, "cp": 1}   # cp-equivalents


class CurrencyError(ValueError):
    """Currency validation / conversion errors (routes map to HTTP 400)."""


def carried_coins(spec: CharacterSpec) -> list[CoinStack]:
    """Coin stacks on the person (Carried bucket) — the only shop-spendable
    coins. Excludes stashed, on-carrier, and coins packed in containers."""
    return [s for s in spec.coins if s.location.kind == "carried"]


def total_value_cp(spec: CharacterSpec) -> int:
    """cp-worth of every coin the character holds, all locations."""
    return sum(s.count * RATES[s.denom] for s in spec.coins)


def total_value_gp(spec: CharacterSpec) -> int:
    """Whole-gp worth of the purse (floors any sub-gp remainder)."""
    return total_value_cp(spec) // RATES["gp"]


def coin_count(spec: CharacterSpec, carried_only: bool = False) -> int:
    """Number of coins (1 cn each). ``carried_only`` gives the encumbrance
    weight (Carried bucket only); else every coin."""
    stacks = carried_coins(spec) if carried_only else spec.coins
    return sum(s.count for s in stacks)


def convert_amount(frm: str, to: str, count: int) -> int:
    """Pure: how many ``to`` coins ``count`` ``frm`` coins convert to, at
    official rates. Raises ``CurrencyError`` on unknown/identical denom,
    non-positive count, or a non-whole-coin result."""
    if frm not in RATES or to not in RATES:
        raise CurrencyError(f"unknown denomination: {frm!r} / {to!r}")
    if frm == to:
        raise CurrencyError("cannot convert a coin to itself")
    if count <= 0:
        raise CurrencyError("convert count must be positive")
    value_cp = count * RATES[frm]
    if value_cp % RATES[to] != 0:
        raise CurrencyError(f"{count}{frm} does not convert to a whole number of {to}")
    return value_cp // RATES[to]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_currency.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/currency.py tests/test_currency.py
git commit -m "feat(engine): location-aware currency; extract convert core"
```

---

### Task 6: Movement & conversion engine — `aose/engine/storage.py`

This is the heart of the feature. Build it incrementally across sub-tasks 6a–6f.

**Files:**
- Create: `aose/engine/storage.py`
- Test: `tests/test_storage_engine.py`

#### Task 6a: location resolution helpers + loose-list accessor

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storage_engine.py
import pytest
from aose.engine import storage
from aose.models import (CharacterSpec, CoinStack, ContainerInstance,
                         AnimalInstance, GemStack, JewelleryPiece)
from aose.models.storage import StorageLocation


def _spec(**extra):
    base = dict(
        name="T", abilities={"str":10,"dex":10,"con":10,"int":10,"wis":10,"cha":10},
        race_id="human", classes=[{"class_id":"fighter","level":1}],
        alignment="neutral",
    )
    base.update(extra)
    return CharacterSpec.model_validate(base)


def test_loose_list_for_carried_is_inventory():
    spec = _spec(inventory=["torch"])
    assert storage.loose_list(spec, StorageLocation(kind="carried")) is spec.inventory


def test_loose_list_for_stashed_is_stashed():
    spec = _spec(stashed=["rope"])
    assert storage.loose_list(spec, StorageLocation(kind="stashed")) is spec.stashed


def test_loose_list_for_container_is_its_contents():
    c = ContainerInstance(instance_id="c1", catalog_id="backpack", contents=["torch"])
    spec = _spec(containers=[c])
    got = storage.loose_list(spec, StorageLocation(kind="container", id="c1"))
    assert got is spec.containers[0].contents


def test_loose_list_for_animal_is_its_contents():
    a = AnimalInstance(instance_id="a1", catalog_id="mule", contents=["sack"])
    spec = _spec(animals=[a])
    assert storage.loose_list(spec, StorageLocation(kind="animal", id="a1")) is spec.animals[0].contents


def test_loose_list_unknown_id_raises():
    spec = _spec()
    with pytest.raises(storage.StorageError):
        storage.loose_list(spec, StorageLocation(kind="animal", id="nope"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_engine.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Create `storage.py` with the helpers**

```python
# aose/engine/storage.py
"""The single movement vocabulary for the inventory: move loose items,
containers, coins, and treasure between StorageLocations, and convert coins
per-stack. All functions mutate ``spec`` in place (many collections are
touched at once, so the pure-return style of shop.py would be unwieldy).

Imports only models + currency. Nothing imports it back into the magic/feature
DAG, so no cycle risk.
"""
from __future__ import annotations

from aose.engine.currency import RATES, CurrencyError, convert_amount
from aose.models import CharacterSpec, CoinStack, GemStack, JewelleryPiece
from aose.models.storage import StorageLocation


class StorageError(ValueError):
    """Movement validation errors (routes map to HTTP 400)."""


def _carrier(spec: CharacterSpec, kind: str, id_: str):
    coll = spec.animals if kind == "animal" else spec.vehicles
    for inst in coll:
        if inst.instance_id == id_:
            return inst
    raise StorageError(f"no {kind} with id {id_!r}")


def _container(spec: CharacterSpec, id_: str):
    for c in spec.containers:
        if c.instance_id == id_:
            return c
    raise StorageError(f"no container with id {id_!r}")


def loose_list(spec: CharacterSpec, loc: StorageLocation) -> list[str]:
    """Return the actual ``list[str]`` that holds loose item ids at ``loc``."""
    if loc.kind == "carried":
        return spec.inventory
    if loc.kind == "stashed":
        return spec.stashed
    if loc.kind == "container":
        return _container(spec, loc.id).contents
    if loc.kind in ("animal", "vehicle"):
        return _carrier(spec, loc.kind, loc.id).contents
    raise StorageError(f"no loose list for location {loc!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_storage_engine.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/storage.py tests/test_storage_engine.py
git commit -m "feat(engine): storage.loose_list + carrier/container resolution"
```

#### Task 6b: `move_item`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_storage_engine.py
def test_move_item_carried_to_stashed():
    spec = _spec(inventory=["torch", "rope"])
    storage.move_item(spec, "torch",
                      StorageLocation(kind="carried"), StorageLocation(kind="stashed"))
    assert spec.inventory == ["rope"]
    assert spec.stashed == ["torch"]


def test_move_item_into_container():
    c = ContainerInstance(instance_id="c1", catalog_id="backpack")
    spec = _spec(inventory=["torch"], containers=[c])
    storage.move_item(spec, "torch",
                      StorageLocation(kind="carried"),
                      StorageLocation(kind="container", id="c1"))
    assert spec.inventory == []
    assert spec.containers[0].contents == ["torch"]


def test_move_item_not_at_source_raises():
    spec = _spec(inventory=["torch"])
    with pytest.raises(storage.StorageError):
        storage.move_item(spec, "rope",
                          StorageLocation(kind="carried"), StorageLocation(kind="stashed"))
```

- [ ] **Step 2: Run to verify failure** — `move_item` missing.

- [ ] **Step 3: Implement**

```python
# append to aose/engine/storage.py
def move_item(spec: CharacterSpec, item_id: str,
              src: StorageLocation, dest: StorageLocation) -> None:
    """Move one copy of ``item_id`` from ``src``'s loose list to ``dest``'s."""
    src_list = loose_list(spec, src)
    if item_id not in src_list:
        raise StorageError(f"{item_id!r} not at {src.kind}")
    dest_list = loose_list(spec, dest)
    src_list.remove(item_id)
    dest_list.append(item_id)
```

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit**

```bash
git add aose/engine/storage.py tests/test_storage_engine.py
git commit -m "feat(engine): storage.move_item"
```

#### Task 6c: `move_container`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_storage_engine.py
def test_move_container_to_vehicle_carries_contents():
    from aose.models import VehicleInstance
    c = ContainerInstance(instance_id="c1", catalog_id="backpack", contents=["torch"])
    v = VehicleInstance(instance_id="v1", catalog_id="cart", hull_max=10)
    spec = _spec(containers=[c], vehicles=[v])
    storage.move_container(spec, "c1", StorageLocation(kind="vehicle", id="v1"))
    assert spec.containers[0].location == StorageLocation(kind="vehicle", id="v1")
    assert spec.containers[0].contents == ["torch"]   # contents follow for free


def test_move_container_rejects_container_destination():
    c = ContainerInstance(instance_id="c1", catalog_id="backpack")
    spec = _spec(containers=[c])
    with pytest.raises(storage.StorageError):
        storage.move_container(spec, "c1", StorageLocation(kind="container", id="c2"))
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement**

```python
# append to aose/engine/storage.py
def move_container(spec: CharacterSpec, container_id: str,
                   dest: StorageLocation) -> None:
    """Re-home a container. ``dest`` may not be a container (no nesting)."""
    if dest.kind == "container":
        raise StorageError("a container cannot go inside another container")
    c = _container(spec, container_id)
    if dest.kind in ("animal", "vehicle"):
        _carrier(spec, dest.kind, dest.id)   # validate existence
    c.location = dest
```

- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** `feat(engine): storage.move_container`.

#### Task 6d: `move_coins` (split/merge)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_storage_engine.py
def test_move_coins_splits_and_merges():
    spec = _spec(coins=[CoinStack(denom="gp", count=10)])
    storage.move_coins(spec, "gp",
                       StorageLocation(kind="carried"),
                       StorageLocation(kind="stashed"), 4)
    by = {(c.denom, c.location.kind): c.count for c in spec.coins}
    assert by[("gp", "carried")] == 6
    assert by[("gp", "stashed")] == 4


def test_move_coins_whole_stack_prunes_source():
    spec = _spec(coins=[CoinStack(denom="gp", count=4)])
    storage.move_coins(spec, "gp",
                       StorageLocation(kind="carried"),
                       StorageLocation(kind="stashed"), 4)
    assert all(c.location.kind == "stashed" for c in spec.coins)
    assert len(spec.coins) == 1


def test_move_coins_more_than_available_raises():
    spec = _spec(coins=[CoinStack(denom="gp", count=2)])
    with pytest.raises(storage.StorageError):
        storage.move_coins(spec, "gp",
                           StorageLocation(kind="carried"),
                           StorageLocation(kind="stashed"), 5)
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement helpers + `move_coins`**

```python
# append to aose/engine/storage.py
def _find_coin(spec, denom, loc):
    for s in spec.coins:
        if s.denom == denom and s.location == loc:
            return s
    return None


def _add_coins(spec, denom, count, loc):
    if count <= 0:
        return
    existing = _find_coin(spec, denom, loc)
    if existing is not None:
        existing.count += count
    else:
        spec.coins.append(CoinStack(denom=denom, count=count, location=loc))


def _take_coins(spec, denom, count, loc):
    s = _find_coin(spec, denom, loc)
    if s is None or s.count < count:
        have = s.count if s else 0
        raise StorageError(f"only {have} {denom} at {loc.kind}, need {count}")
    s.count -= count
    if s.count == 0:
        spec.coins.remove(s)


def move_coins(spec: CharacterSpec, denom: str,
               src: StorageLocation, dest: StorageLocation, count: int) -> None:
    if count <= 0:
        raise StorageError("move count must be positive")
    _take_coins(spec, denom, count, src)
    _add_coins(spec, denom, count, dest)
```

- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** `feat(engine): storage.move_coins`.

#### Task 6e: `convert_coins` (per-stack, in place) + `add_coins`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_storage_engine.py
def test_convert_coins_in_place_at_location():
    spec = _spec(coins=[CoinStack(denom="gp", count=3,
                                  location=StorageLocation(kind="stashed"))])
    storage.convert_coins(spec, StorageLocation(kind="stashed"), "gp", "sp", 2)
    by = {c.denom: c.count for c in spec.coins}
    assert by["gp"] == 1
    assert by["sp"] == 20
    assert all(c.location.kind == "stashed" for c in spec.coins)


def test_convert_coins_non_whole_raises():
    spec = _spec(coins=[CoinStack(denom="cp", count=5)])
    with pytest.raises(CurrencyError):
        storage.convert_coins(spec, StorageLocation(kind="carried"), "cp", "sp", 5)


def test_add_coins_grants_into_location():
    spec = _spec()
    storage.add_coins(spec, "gp", 7, StorageLocation(kind="carried"))
    assert spec.coins[0].count == 7
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement**

```python
# append to aose/engine/storage.py
def add_coins(spec: CharacterSpec, denom: str, count: int,
              loc: StorageLocation) -> None:
    """GM grant of coins into a location's stack."""
    if count <= 0:
        raise StorageError("grant count must be positive")
    _add_coins(spec, denom, count, loc)


def convert_coins(spec: CharacterSpec, loc: StorageLocation,
                  frm: str, to: str, count: int) -> None:
    """Convert ``count`` ``frm`` coins into ``to`` coins, in place at ``loc``.
    Raises CurrencyError on a non-whole-coin result (no implicit rounding)."""
    gained = convert_amount(frm, to, count)   # raises CurrencyError
    _take_coins(spec, frm, count, loc)        # raises StorageError if short
    _add_coins(spec, to, gained, loc)
```

- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** `feat(engine): storage.convert_coins + add_coins`.

#### Task 6f: `move_valuable` (gems & jewellery, merge gems)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_storage_engine.py
def test_move_gem_stack_merges_at_destination():
    spec = _spec(gems=[
        GemStack(instance_id="g1", value=100, count=2),
        GemStack(instance_id="g2", value=100,
                 location=StorageLocation(kind="stashed")),
    ])
    storage.move_valuable(spec, "g1", StorageLocation(kind="stashed"))
    stashed = [g for g in spec.gems if g.location.kind == "stashed"]
    assert sum(g.count for g in stashed) == 3
    assert all(g.location.kind == "stashed" for g in spec.gems)


def test_move_jewellery_sets_location():
    spec = _spec(jewellery=[JewelleryPiece(instance_id="j1", value=300)])
    storage.move_valuable(spec, "j1", StorageLocation(kind="vehicle", id="v1"),
                          )  # existence of carrier not required for jewellery test
    assert spec.jewellery[0].location == StorageLocation(kind="vehicle", id="v1")
```

> Note: for the gem-merge test the destination has a same-(value,label) stack;
> the moved stack folds in and the now-empty source id disappears.

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement**

```python
# append to aose/engine/storage.py
def move_valuable(spec: CharacterSpec, instance_id: str,
                  dest: StorageLocation) -> None:
    """Move a gem stack or jewellery piece (by instance_id) to ``dest``.
    Gems merge into a same-(value,label,dest) stack if one exists."""
    if dest.kind in ("animal", "vehicle"):
        _carrier(spec, dest.kind, dest.id)
    if dest.kind == "container":
        _container(spec, dest.id)
    for i, g in enumerate(spec.gems):
        if g.instance_id == instance_id:
            target = next((o for o in spec.gems
                           if o is not g and o.value == g.value
                           and o.label == g.label and o.location == dest), None)
            if target is not None:
                target.count += g.count
                spec.gems.pop(i)
            else:
                g.location = dest
            return
    for j in spec.jewellery:
        if j.instance_id == instance_id:
            j.location = dest
            return
    raise StorageError(f"no gem/jewellery with id {instance_id!r}")
```

- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** `feat(engine): storage.move_valuable`.

---

### Task 7: Valuables engine — carried-only weight; `location` on add helpers

**Files:**
- Modify: `aose/engine/valuables.py`
- Test: `tests/test_valuables.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_valuables.py
from aose.models.storage import StorageLocation
from aose.engine import valuables


def _spec(**extra):
    from aose.models import CharacterSpec
    base = dict(name="T", abilities={"str":10,"dex":10,"con":10,"int":10,"wis":10,"cha":10},
                race_id="human", classes=[{"class_id":"fighter","level":1}], alignment="neutral")
    base.update(extra); return CharacterSpec.model_validate(base)


def test_valuables_weight_carried_only():
    from aose.models import GemStack, JewelleryPiece
    spec = _spec(
        gems=[GemStack(instance_id="g1", value=50, count=3)],                      # carried: 3cn
        jewellery=[JewelleryPiece(instance_id="j1", value=300,
                   location=StorageLocation(kind="stashed"))],                     # stashed: 0
    )
    assert valuables.valuables_weight_cn(spec) == 3


def test_total_value_counts_all_locations():
    from aose.models import GemStack
    spec = _spec(gems=[
        GemStack(instance_id="g1", value=100, count=1),
        GemStack(instance_id="g2", value=100, count=1,
                 location=StorageLocation(kind="vehicle", id="v1")),
    ])
    assert valuables.total_value(spec) == 200
```

- [ ] **Step 2: Run to verify failure** — `valuables_weight_cn` still counts all gems.

- [ ] **Step 3: Update `valuables.py`**

Change `valuables_weight_cn` to carried-only:

```python
def valuables_weight_cn(spec: CharacterSpec) -> int:
    """Encumbrance weight of CARRIED gems + jewellery: 1 cn per gem, 10 cn per
    piece. Stashed / on-carrier treasure weighs nothing for the PC."""
    gems = sum(g.count for g in spec.gems if g.location.kind == "carried")
    jewel = 10 * sum(1 for j in spec.jewellery if j.location.kind == "carried")
    return gems + jewel
```

`total_value` stays as-is (sums all). Update `add_gem`/`add_jewellery` to accept an optional `location` so routes can grant into a specific bucket (default carried):

```python
def add_gem(gems, value, count=1, label="", location=None):
    ...
    location = location or StorageLocation(kind="carried")
    for i, g in enumerate(gems):
        if g.value == value and g.label == label and g.location == location:
            ...
    return [*gems, GemStack(instance_id=uuid.uuid4().hex, value=value,
                            count=count, label=label, location=location)]
```

Add `from aose.models.storage import StorageLocation` to the imports, and the analogous `location` parameter on `add_jewellery`. Update the gem stack-match in `add_gem` to also compare `location` (shown above).

- [ ] **Step 4: Run to verify pass.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_valuables.py -q`

- [ ] **Step 5: Commit** `feat(engine): carried-only valuables weight; located add`.

---

### Task 8: Encumbrance — carried-only, container contents include value-stacks

**Files:**
- Modify: `aose/engine/encumbrance.py`
- Test: `tests/test_encumbrance.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_encumbrance.py
from aose.models import CoinStack, ContainerInstance
from aose.models.storage import StorageLocation


def test_stashed_coins_do_not_weigh(data):
    from aose.models import CharacterSpec
    spec = CharacterSpec.model_validate(dict(
        name="T", abilities={"str":10,"dex":10,"con":10,"int":10,"wis":10,"cha":10},
        race_id="human", classes=[{"class_id":"fighter","level":1}], alignment="neutral",
        coins=[CoinStack(denom="gp", count=500, location=StorageLocation(kind="stashed"))],
        ruleset={"encumbrance": "detailed"},
    ))
    from aose.engine import encumbrance
    assert encumbrance.treasure_weight_cn(spec, data) == 0


def test_coins_in_carried_container_weigh_via_container(data):
    # backpack (weight_multiplier 1) holding 100 carried coins -> +100 cn through the container
    from aose.models import CharacterSpec
    c = ContainerInstance(instance_id="c1", catalog_id="backpack",
                          location=StorageLocation(kind="carried"))
    spec = CharacterSpec.model_validate(dict(
        name="T", abilities={"str":10,"dex":10,"con":10,"int":10,"wis":10,"cha":10},
        race_id="human", classes=[{"class_id":"fighter","level":1}], alignment="neutral",
        containers=[c],
        coins=[CoinStack(denom="cp", count=100,
                         location=StorageLocation(kind="container", id="c1"))],
        ruleset={"encumbrance": "detailed"},
    ))
    from aose.engine import encumbrance
    # treasure line excludes container-located coins (counted via the container)
    assert encumbrance.treasure_weight_cn(spec, data) == 0
    eq = encumbrance.equipment_weight_cn(spec, data)
    backpack_own = data.items["backpack"].weight_cn
    assert eq == backpack_own + 100
```

> If `backpack` isn't the catalog id in this dataset, use whatever container id
> the existing `tests/test_containers.py` uses (e.g. `sack`); keep the weight math
> consistent with that item's `weight_cn` and `weight_multiplier`.

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Update `encumbrance.py`**

In `treasure_weight_cn`, change the coin/valuable lines to carried-only:

```python
    total = currency.coin_count(spec, carried_only=True) + valuables.valuables_weight_cn(spec)
```

(`valuables_weight_cn` is already carried-only from Task 7.)

In `equipment_weight_cn`, change the container loop guard and add value-stack contents:

```python
    from aose.models import Container as _Container
    for c in spec.containers:
        if c.location.kind != "carried":
            continue
        catalog = data.items.get(c.catalog_id)
        if not isinstance(catalog, _Container):
            continue
        total += catalog.weight_cn
        raw = sum(
            (data.items[x].weight_cn if x in data.items else 0)
            for x in c.contents
        )
        # coins (1cn) + gems (1cn) + jewellery (10cn) stowed in this container
        here = StorageLocation(kind="container", id=c.instance_id)
        raw += sum(s.count for s in spec.coins if s.location == here)
        raw += sum(g.count for g in spec.gems if g.location == here)
        raw += 10 * sum(1 for j in spec.jewellery if j.location == here)
        total += int(catalog.weight_multiplier * raw)
```

Add the import at the top of `encumbrance.py`:

```python
from aose.models.storage import StorageLocation
```

- [ ] **Step 4: Run to verify pass.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py -q`

- [ ] **Step 5: Commit** `feat(engine): carried-only encumbrance incl. container value-stacks`.

---

### Task 9: Wealth total helper

**Files:**
- Modify: `aose/sheet/view.py` (add `total_wealth_gp`) — or `aose/engine/valuables.py` if cleaner; place it where the sheet reads it.
- Test: `tests/test_valuables.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_valuables.py
def test_total_wealth_excludes_retainers():
    from aose.models import CoinStack, GemStack, Retainer
    from aose.engine.valuables import total_wealth_gp
    retainer_spec = _spec(coins=[CoinStack(denom="gp", count=999)])
    spec = _spec(
        coins=[CoinStack(denom="gp", count=10),
               CoinStack(denom="sp", count=10, location=StorageLocation(kind="stashed"))],
        gems=[GemStack(instance_id="g1", value=50, count=2)],
        retainers=[Retainer(id="r1", spec=retainer_spec, loyalty=7)],
    )
    # 10gp + 100cp(=1gp) + 100gp gems = 111 gp, retainer's 999 excluded
    assert total_wealth_gp(spec) == 111
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement in `valuables.py`**

```python
# append to aose/engine/valuables.py
def total_wealth_gp(spec) -> int:
    """Whole-gp wealth across all PC buckets (coins + gems + jewellery),
    excluding retainers (they own their own purse)."""
    from aose.engine import currency
    return currency.total_value_gp(spec) + total_value(spec)
```

- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** `feat(engine): total_wealth_gp (excludes retainers)`.

---

## STAGE 3 — Shop spend

### Task 10: `shop.spend` — lowest-first exact payment with gp-change exception

**Files:**
- Modify: `aose/engine/shop.py`
- Test: `tests/test_shop_spend.py`

- [ ] **Step 1: Write the failing tests (the worked examples + edges)**

```python
# tests/test_shop_spend.py
import pytest
from aose.engine import shop
from aose.models import CharacterSpec, CoinStack
from aose.models.storage import StorageLocation


def _spec(coins):
    return CharacterSpec.model_validate(dict(
        name="T", abilities={"str":10,"dex":10,"con":10,"int":10,"wis":10,"cha":10},
        race_id="human", classes=[{"class_id":"fighter","level":1}],
        alignment="neutral", coins=coins,
    ))


def _carried(spec):
    return {c.denom: c.count for c in spec.coins if c.location.kind == "carried"}


def test_spend_example_102cp_2gp_buy_2gp():
    spec = _spec([CoinStack(denom="cp", count=102), CoinStack(denom="gp", count=2)])
    shop.spend(spec, 2)
    assert _carried(spec) == {"cp": 2, "gp": 1}


def test_spend_example_250cp_2gp_buy_3gp():
    spec = _spec([CoinStack(denom="cp", count=250), CoinStack(denom="gp", count=2)])
    shop.spend(spec, 3)
    assert _carried(spec) == {"cp": 50, "gp": 1}


def test_spend_insufficient_raises():
    spec = _spec([CoinStack(denom="gp", count=1)])
    with pytest.raises(shop.InsufficientFunds):
        shop.spend(spec, 5)


def test_spend_change_exception_pays_pp_returns_gp():
    # only a platinum (5gp); buy a 1gp item -> pay pp, get 4gp change
    spec = _spec([CoinStack(denom="pp", count=1)])
    shop.spend(spec, 1)
    assert _carried(spec) == {"gp": 4}


def test_spend_ignores_non_carried_coins():
    spec = _spec([
        CoinStack(denom="gp", count=1),
        CoinStack(denom="gp", count=99, location=StorageLocation(kind="stashed")),
    ])
    with pytest.raises(shop.InsufficientFunds):
        shop.spend(spec, 5)   # stashed 99gp can't be spent
```

- [ ] **Step 2: Run to verify failure** — `spend` / `InsufficientFunds` missing.

- [ ] **Step 3: Implement the algorithm**

```python
# append to aose/engine/shop.py (near the other exceptions)
from aose.engine.currency import RATES, DENOMINATIONS
from aose.engine import storage as _storage
from aose.models.storage import StorageLocation


class InsufficientFunds(ValueError):
    pass


_ORDER_LOW = ["cp", "sp", "ep", "gp", "pp"]   # ascending value
_VALS = [RATES[d] for d in _ORDER_LOW]        # [1, 10, 50, 100, 500]


def _exact_payment(avail: dict[str, int], cost_cp: int):
    """Largest-low-coin exact payment of ``cost_cp`` from ``avail`` (denom->count),
    or None if no exact payment exists. Prefers spending lower denominations."""
    n = len(_ORDER_LOW)
    maxval = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        maxval[i] = maxval[i + 1] + avail.get(_ORDER_LOW[i], 0) * _VALS[i]

    def rec(i, remaining, chosen):
        if remaining == 0:
            return dict(chosen)
        if i == n:
            return None
        v = _VALS[i]
        hi = min(avail.get(_ORDER_LOW[i], 0), remaining // v)
        for k in range(hi, -1, -1):            # high->low => prefer low denoms
            rem2 = remaining - k * v
            if rem2 <= maxval[i + 1]:
                chosen[_ORDER_LOW[i]] = k
                got = rec(i + 1, rem2, chosen)
                if got is not None:
                    return got
        chosen[_ORDER_LOW[i]] = 0
        return None

    return rec(0, cost_cp, {})


def _payment_plan(avail: dict[str, int], cost_cp: int):
    """Return (spend_by_denom, change_cp). Tries exact (change 0) first, then the
    smallest whole-gp overshoot (change paid back in gp). Raises InsufficientFunds."""
    total = sum(avail.get(d, 0) * RATES[d] for d in DENOMINATIONS)
    if total < cost_cp:
        raise InsufficientFunds(f"need {cost_cp // 100} gp; only "
                                f"{total // 100} gp on hand")
    j = 0
    while cost_cp + 100 * j <= total:
        sol = _exact_payment(avail, cost_cp + 100 * j)
        if sol is not None:
            return sol, 100 * j
        j += 1
    raise InsufficientFunds("cannot pay without breaking coins — convert first")


def spend(spec, cost_gp: int) -> None:
    """Spend ``cost_gp`` from CARRIED (on-person) loose coins, lowest denomination
    first with no implicit conversion. If exact payment is impossible, pays the
    smallest whole-gp overshoot and returns the change as carried gp. Mutates
    ``spec.coins`` in place. Raises InsufficientFunds."""
    carried = StorageLocation(kind="carried")
    avail = {c.denom: c.count for c in spec.coins if c.location == carried}
    spend_by, change_cp = _payment_plan(avail, cost_gp * 100)
    for denom, k in spend_by.items():
        if k:
            _storage._take_coins(spec, denom, k, carried)
    if change_cp:
        _storage._add_coins(spec, "gp", change_cp // 100, carried)
```

- [ ] **Step 4: Run to verify pass.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_shop_spend.py -q`

- [ ] **Step 5: Commit** `feat(engine): shop.spend lowest-first with gp-change`.

---

### Task 11: Wire buy/sell/refund + containers + quick-equipment onto carried coins

**Files:**
- Modify: `aose/engine/shop.py`, `aose/engine/quick_equipment.py`
- Test: `tests/test_shop_spend.py` (extend), existing `tests/test_containers.py`

The existing `buy`/`buy_container`/`remove`/`remove_from_stash`/`remove_container` take a `gold: int` and return a new gold. Replace that ledger with carried-coin mutation via `spend` (debits) and `_storage._add_coins(..., "gp", ...)` (credits). Keep signatures spec-mutating.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_shop_spend.py
def test_buy_spends_carried_coins(data):
    spec = _spec([CoinStack(denom="gp", count=50)])
    shop.buy_item(spec, "torch", data)          # new spec-mutating entry point
    assert "torch" in spec.inventory
    assert {c.denom: c.count for c in spec.coins}["gp"] == 50 - int(data.items["torch"].cost_gp)


def test_sell_credits_carried_gp(data):
    spec = _spec([CoinStack(denom="gp", count=0)])
    spec.inventory.append("torch")
    shop.sell_item(spec, "torch", "sell", data)
    assert "torch" not in spec.inventory
    # half of torch cost lands in carried gp (may be 0 for cheap items)
```

> Use a `data` pytest fixture matching the existing shop/container tests
> (`tests/test_containers.py` shows the fixture import). Pick `torch` or any
> low-cost catalog id present in the dataset.

- [ ] **Step 2: Run to verify failure** — `buy_item`/`sell_item` missing.

- [ ] **Step 3: Implement spec-mutating wrappers**

Add to `shop.py` thin wrappers that the routes call, delegating to `spend` and the existing list logic:

```python
def buy_item(spec, item_id: str, data) -> None:
    """Buy one bundle of ``item_id`` onto carried inventory, spending carried coins."""
    if item_id not in data.items:
        raise UnknownItem(f"No item with id {item_id!r}")
    item = data.items[item_id]
    spend(spec, int(item.cost_gp))                 # raises InsufficientFunds
    spec.inventory.extend([item_id] * _bundle_count(item))


def sell_item(spec, item_id: str, mode: str, data) -> None:
    """Remove one instance from carried inventory; credit carried gp per mode."""
    new_inv, credit, new_eq = remove(spec.inventory, 0, item_id, mode, data, spec.equipped)
    spec.inventory[:] = new_inv
    spec.equipped.clear(); spec.equipped.update(new_eq)
    if credit:
        _storage._add_coins(spec, "gp", credit, StorageLocation(kind="carried"))
```

> The existing `remove(...)` already returns the gold delta; here we feed it
> `gold=0` and route the returned credit into a carried gp stack. Do the same
> shape for `buy_container`/`remove_container`/`remove_from_stash` as the routes
> need them (add `buy_container_item`, `sell_container`, `sell_from_stash`
> wrappers), reusing the existing pure list logic and crediting/debiting carried gp.

- [ ] **Step 4: Update `quick_equipment.py`**

Find where starting gold is set (search `gold`) and replace the integer assignment with a carried gp stack, e.g.:

```python
from aose.models import CoinStack
spec.coins.append(CoinStack(denom="gp", count=starting_gp))
```

- [ ] **Step 5: Run to verify pass.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_shop_spend.py tests/test_containers.py -q`

- [ ] **Step 6: Commit** `feat(engine): buy/sell/quick-equip onto carried coins`.

---

## STAGE 4 — View, routes, UI

### Task 12: Top-level inventory view model

**Files:**
- Modify: `aose/engine/shop.py` (extend `InventoryView`/`ContainerView`) and `aose/sheet/view.py`
- Test: `tests/test_inventory_view.py` (extend)

Build a `TopLevelGroup` view model so the template iterates groups, each carrying `equipped`, `loose`, `coins`, `treasure`, `containers` plus a `move_targets` list (the destinations the Move dropdown should offer for rows in this group). `ContainerView` gains `location` and its own `coins`/`treasure` child rows.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_inventory_view.py
def test_top_level_groups_include_carried_and_carriers(data):
    from aose.models import CharacterSpec, AnimalInstance, CoinStack
    from aose.sheet.view import build_sheet
    spec = CharacterSpec.model_validate(dict(
        name="T", abilities={"str":10,"dex":10,"con":10,"int":10,"wis":10,"cha":10},
        race_id="human", classes=[{"class_id":"fighter","level":1}], alignment="neutral",
        inventory=["torch"], coins=[CoinStack(denom="gp", count=5)],
        animals=[AnimalInstance(instance_id="a1", catalog_id="mule")],
    ))
    sheet = build_sheet(spec, data)
    kinds = {g.kind for g in sheet.inventory_groups}
    assert "carried" in kinds and "stashed" in kinds and "animal" in kinds
    carried = next(g for g in sheet.inventory_groups if g.kind == "carried")
    assert any(r.id == "torch" for r in carried.loose)
    assert any(c.denom == "gp" and c.count == 5 for c in carried.coins)


def test_wealth_total_on_sheet(data):
    from aose.models import CharacterSpec, CoinStack
    from aose.sheet.view import build_sheet
    spec = CharacterSpec.model_validate(dict(
        name="T", abilities={"str":10,"dex":10,"con":10,"int":10,"wis":10,"cha":10},
        race_id="human", classes=[{"class_id":"fighter","level":1}], alignment="neutral",
        coins=[CoinStack(denom="gp", count=42)],
    ))
    assert build_sheet(spec, data).total_wealth_gp == 42
```

- [ ] **Step 2: Run to verify failure** — `inventory_groups`/`total_wealth_gp` missing.

- [ ] **Step 3: Implement the view models + builder**

In `aose/engine/shop.py`, add Pydantic models:

```python
class CoinRow(BaseModel):
    denom: str
    count: int


class TopLevelGroup(BaseModel):
    kind: str                       # carried | stashed | animal | vehicle | retainer
    id: str | None = None           # carrier/retainer instance id
    label: str                      # display name (e.g. "Mule", retainer name)
    has_equipped: bool = False
    equipped: list[InventoryRow] = []
    loose: list[InventoryRow] = []
    coins: list[CoinRow] = []
    treasure_gems: list = []        # reuse existing gem/jewellery view rows
    treasure_jewellery: list = []
    containers: list[ContainerView] = []
```

Extend `ContainerView` with `location_kind: str`, `location_id: str | None`, and `coins`/`treasure_*` child lists.

In `aose/sheet/view.py`, add a `build_inventory_groups(spec, data)` that:
- builds the **carried** group from `spec.inventory`/`equipped` + carried coins/gems/jewellery + carried containers;
- the **stashed** group (no equipped) from `spec.stashed` + stashed value-stacks + stashed containers;
- one group per animal (with equipped = barding) / vehicle (no equipped) / retainer (recurse via existing `build_sheet`/`_retainer_cards` data — reuse the retainer's own inventory groups);
- attaches each group's value-stacks by filtering `spec.coins`/`spec.gems`/`spec.jewellery` on `location`.

Add `inventory_groups: list[TopLevelGroup]` and `total_wealth_gp: int` to `CharacterSheet`, and populate them in `build_sheet` (call `valuables.total_wealth_gp(spec)` for the latter).

- [ ] **Step 4: Run to verify pass.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_view.py -q`

- [ ] **Step 5: Commit** `feat(sheet): top-level inventory groups + wealth total`.

---

### Task 13: Movement / convert / add routes

**Files:**
- Modify: `aose/web/routes.py`
- Test: `tests/test_inventory_move_routes.py`

Add POST routes (mirroring the wizard equipment prefix where relevant), each `_load_spec_or_404 → storage.* → save_character → 303`. A `dest` is parsed from form fields `dest_kind` + `dest_id`; a `retainer:<id>` destination dispatches to a retainer-transfer helper instead of `storage.*`.

Routes:
- `POST /character/{id}/inventory/move-item` (`item_id`, `src_kind`, `src_id`, `dest_kind`, `dest_id`)
- `POST /character/{id}/inventory/move-container` (`container_id`, `dest_kind`, `dest_id`)
- `POST /character/{id}/inventory/move-coins` (`denom`, `src_kind`, `src_id`, `dest_kind`, `dest_id`, `count`)
- `POST /character/{id}/inventory/move-valuable` (`instance_id`, `dest_kind`, `dest_id`)
- `POST /character/{id}/coins/convert` (`loc_kind`, `loc_id`, `frm`, `to`, `count`) — replaces the old global convert
- `POST /character/{id}/coins/add` (`denom`, `count`, `loc_kind`, `loc_id`) — replaces the global gold grant

Retire: the old `/coins/add` (global), `/coins/convert` (global), `/equipment/stash-container`, `/unstash-container`, `/stow`, `/take-out` (folded into move-*). Keep buy/sell/refund URLs but call `shop.buy_item`/`shop.sell_item`/etc.

- [ ] **Step 1: Write the failing route tests**

```python
# tests/test_inventory_move_routes.py
from tests.helpers import client_with_character   # match the helper used by test_companion_routes.py


def test_move_item_route_carried_to_stashed(tmp_path):
    client, cid = client_with_character(tmp_path, inventory=["torch"])
    r = client.post(f"/character/{cid}/inventory/move-item", data={
        "item_id": "torch", "src_kind": "carried", "src_id": "",
        "dest_kind": "stashed", "dest_id": "",
    })
    assert r.status_code in (200, 303)
    spec = load_spec(client, cid)             # helper to reload
    assert spec.stashed == ["torch"] and spec.inventory == []


def test_convert_route_per_stack(tmp_path):
    client, cid = client_with_character(tmp_path, coins=[{"denom":"gp","count":3,"location":{"kind":"carried"}}])
    r = client.post(f"/character/{cid}/coins/convert", data={
        "loc_kind":"carried","loc_id":"","frm":"gp","to":"sp","count":"2",
    })
    assert r.status_code in (200, 303)
    spec = load_spec(client, cid)
    by = {c.denom: c.count for c in spec.coins}
    assert by["gp"] == 1 and by["sp"] == 20
```

> Match the actual helpers in `tests/test_companion_routes.py` (how it builds a
> client + seeds a character + reloads the spec). Mirror that exact pattern;
> don't invent new fixtures.

- [ ] **Step 2: Run to verify failure** — routes 404.

- [ ] **Step 3: Implement the routes**

For each route, parse the form, build `StorageLocation(kind=dest_kind, id=dest_id or None)`, dispatch:

```python
@router.post("/character/{cid}/inventory/move-item")
async def inventory_move_item(cid: str, request: Request):
    spec = _load_spec_or_404(request, cid)
    form = await request.form()
    src = StorageLocation(kind=form["src_kind"], id=form.get("src_id") or None)
    dest_kind = form["dest_kind"]
    try:
        if dest_kind == "retainer":
            _transfer_item_to_retainer(spec, form["dest_id"], form["item_id"], src)
        else:
            storage.move_item(spec, form["item_id"], src,
                              StorageLocation(kind=dest_kind, id=form.get("dest_id") or None))
    except (storage.StorageError, ValueError) as e:
        return _redirect_with_error(request, cid, str(e))
    save_character(request, spec)
    return RedirectResponse(_sheet_url(cid), status_code=303)
```

`_transfer_item_to_retainer` removes from `storage.loose_list(spec, src)` and appends to `retainer.spec.inventory` (carried). Add analogous retainer helpers for coins (`storage._take_coins` from src → `retainer.spec.coins` carried) and valuables. Keep these helpers small and local to `routes.py` (or in `retainers.py` if it already hosts transfer logic — check `transfer_to_retainer`).

- [ ] **Step 4: Run to verify pass.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_move_routes.py -q`

- [ ] **Step 5: Commit** `feat(routes): inventory move/convert/add; retire old coin/container routes`.

---

### Task 14: UI — top-level-group macro, per-row Move/Convert, inline containers

**Files:**
- Modify: `aose/web/templates/_equipment_ui.html`, `aose/web/templates/sheet.html`
- Modify: `aose/web/static/sheet.css` (group/subsection styling), `aose/web/static/inventory.js` (Move dropdown submit if needed)
- Test: drive via `tests/test_inventory_move_routes.py` rendering assertions (status 200 + key strings present)

**Read `docs/STYLE-GUIDE.md` before touching templates/CSS.** Reuse existing
zine tokens, the `.dtable` table styling, the `row-detail`/`container-toggle`
patterns, and the overlay model. Do not introduce drag-and-drop.

- [ ] **Step 1: Replace the Carried pane with a group loop**

In `_equipment_ui.html`, replace the `inv_table`/`container_table` calls (the equipped/carried/stashed blocks and the standalone gold/coin block) with a single loop over `inventory_view.groups` (passed from the route as `sheet.inventory_groups`). Define one macro `inv_group(group)` that renders, for the group:
- an inked group bar with `group.label`;
- **Equipped** subsection (only when `group.has_equipped`) — reuse the existing equipped row rendering;
- **Loose** subsection — the existing `inv_table` rows, but each row's action cell gains a **Move** `<select>` (options built from `group.move_targets`) posting to `/inventory/move-item` with hidden `src_kind`/`src_id`;
- **Coins** subsection — one row per `group.coins` entry with **Move**, **Convert** (a small form: denom `<select>` + count + submit to `/coins/convert`), and add/remove;
- **Treasure** subsection — gems/jewellery rows with Move + the existing sell/adjust/damage forms (moved here from the old Treasure pane);
- **Containers** subsection — the existing inline-collapsible container rows, now showing `used/capacity` + `effective_weight_cn`, expanded to list loose items **and** coin/treasure child stacks, each with take-out/move.

- [ ] **Step 2: Remove the coin tracker + money-change UI**

Delete the `show_gold_grant` gold form block and the standalone treasure pane's "change money" affordance. Keep the Magic / Documents / Shop panes unchanged (the Treasure pane's add-gem/add-jewellery forms move into the per-group Treasure subsections, or stay as an "add" affordance on the Carried group).

- [ ] **Step 3: Add the read-only wealth readout**

In `sheet.html` where the coin tracker used to render, show `sheet.total_wealth_gp` (read-only), e.g. `Total wealth: {{ sheet.total_wealth_gp }} gp`.

- [ ] **Step 4: Verify in the browser**

Start the app: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
Use the preview tools: load a character sheet, open the equipment drawer, confirm the Carried/Stashed/Animal groups render with Equipped/Loose/Coins/Treasure/Containers subsections, that Move dropdowns list the right destinations, and that Convert works. Screenshot for proof. Check `preview_console_logs` for errors.

- [ ] **Step 5: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing pytest-current PermissionError).

- [ ] **Step 6: Commit** `feat(ui): top-level inventory groups, per-row move/convert, inline containers`.

---

### Task 15: Print sheet + wizard equipment step

**Files:**
- Modify: `aose/web/templates/sheet_print.html`, the wizard equipment template/route
- Test: existing wizard tests + `tests/` full run

- [ ] **Step 1: Update the print sheet** to render the new groups as static text blocks (coins/treasure per location, containers with contents), mirroring the live grouping; drop the standalone coin block.

- [ ] **Step 2: Update the wizard equipment step** — it shares `_equipment_ui.html`. Ensure starting gold renders as the carried gp stack and the buy path uses `shop.buy_item`. The wizard shows only Carried + Shop (no animals/retainers yet), so the group loop naturally yields just the Carried group.

- [ ] **Step 3: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 4: Verify the wizard in the browser** (preview tools): walk to the equipment step, confirm starting gp shows, buy an item, confirm coins debit lowest-first. Screenshot.

- [ ] **Step 5: Commit** `feat(ui): print sheet + wizard equipment on located coins`.

---

### Task 16: Docs

**Files:**
- Modify: `docs/CHANGELOG.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md`

- [ ] **Step 1:** Add a one-line row to the top of `docs/CHANGELOG.md`:
  `2026-06-18 · Inventory consolidation (located coins/treasure, top-level groups, lowest-first shop spend) · feat/companions-and-holdings · inventory-consolidation`.

- [ ] **Step 2:** Edit `docs/ARCHITECTURE.md` **in place**:
  - **Inventory, containers & encumbrance**: `StorageLocation` pointer model, located coins/treasure, `ContainerInstance.location`, carried-only encumbrance (container contents include value-stacks), the `storage.py` movement engine.
  - **Currency, treasure & valuables**: coins as `CoinStack`s, location-aware value (all buckets) vs weight (carried-only), per-stack convert, `total_wealth_gp` excluding retainers, shop `spend` algorithm.

- [ ] **Step 3:** Update `CLAUDE.md` **Storage shapes** bullets: five int coin fields retired → `coins: list[CoinStack]`; `gems`/`jewellery` gain `location`; `ContainerInstance.location` is a `StorageLocation` (carried/stashed/animal/vehicle); add `storage` to the engine module list.

- [ ] **Step 4: Commit** `docs: inventory consolidation landed`.

---

## Self-review checklist (completed during planning)

- **Spec coverage:** model shapes (Tasks 1–4), movement+convert engine (Task 6), currency/encumbrance/wealth (Tasks 5,7,8,9), shop spend incl. gp-change exception (Tasks 10–11), UI groups + per-row Move/Convert + inline containers + removed tracker/money-change + wealth readout (Tasks 12–14), routes (Task 13), print + wizard (Task 15), docs (Task 16). Every spec section maps to a task.
- **Type consistency:** `StorageLocation`/`CoinStack` (Task 1) reused verbatim downstream; `storage._take_coins`/`_add_coins` defined in Task 6d and reused by Tasks 6e, 10, 11; `shop.spend`/`InsufficientFunds` defined Task 10 used Task 11; `inventory_groups`/`total_wealth_gp`/`TopLevelGroup`/`CoinRow` defined Task 12 used Tasks 13–15.
- **No placeholders:** engine/model tasks carry full code; UI/route tasks carry concrete code plus a driving test and explicit "match the existing helper" notes (templates aren't unit-tested in this codebase — route status + rendered-string assertions are the contract).
