# Adventuring Gear Cleanup + Stackable Purchases + Container Consolidation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fabricated adventuring-gear data with book-faithful AOSE data (no weights, full descriptions), make stack-priced items grant N units per purchase, give sell a per-unit price and refund a whole-stack semantic, and consolidate all containers into their book-category files.

**Architecture:** A new `bundle_count` field on `AdventuringGear` drives a purchase-only expansion in `aose/engine/shop.py`. Sell becomes per-unit; refund removes a full shop stack. The data lives entirely in YAML: `adventuring_gear.yaml` is rewritten (gear + the three table containers), Bag of Holding moves to `magic_items.yaml`, and `containers.yaml` is deleted (the loader globs the directory, so no code references a filename).

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, pytest. Run tests with `.venv\Scripts\python.exe -m pytest`.

**Baseline:** 1020 tests pass before this work begins.

**Key decisions (from the spec):**
- `buy()` expands bundles; `add_free()` does **not** (a free grant is one unit).
- Sell = per-unit `int((cost_gp / bundle_count) / 2)` (may be 0 = worthless).
- Refund = remove a full `bundle_count` stack, return full `cost_gp`; refusing if fewer than a full stack is present.
- Backpack/Sacks keep `item_type: container` (stow/capacity preserved) but move to `adventuring_gear.yaml` with `category: adventuring_gear`. Container buy dispatch is by model type (`isinstance(item, Container)` in `routes.py`/`wizard.py`), so this is safe.
- `saddle_bags` is dropped (Transport table, out of scope).

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `aose/models/item.py` | Item discriminated union | Add `bundle_count` to `AdventuringGear` |
| `aose/engine/shop.py` | Buy/sell/refund + inventory rows | Bundle expansion in `buy`; per-unit sell + whole-stack refund in `remove`/`remove_from_stash`; new `InventoryRow`/`ShopItem` fields; `_bundle_count` helper |
| `aose/web/templates/_equipment_ui.html` | Shop + inventory UI | Shop "buys N" hint; per-unit sell label; whole-stack refund button gated on `can_refund` |
| `data/equipment/adventuring_gear.yaml` | Gear + table containers data | Full rewrite |
| `data/equipment/magic_items.yaml` | Magic-item catalog | Add Bag of Holding |
| `data/equipment/containers.yaml` | (removed) | **Deleted** |
| `tests/test_bundle_purchases.py` | New: bundle buy/sell/refund coverage | Create |
| `tests/test_equipment.py` | Shop engine + route tests | Repair torch-probe assertions |
| `tests/test_containers.py` | Container route tests | Repair weight-based capacity test + add data-shape checks |

---

## Task 1: Add `bundle_count` to the AdventuringGear model

**Files:**
- Modify: `aose/models/item.py:66-67`
- Test: `tests/test_bundle_purchases.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_bundle_purchases.py`:

```python
"""Bundle purchase / per-unit sell / whole-stack refund coverage."""
import pytest

from aose.data.loader import GameData
from aose.models import AdventuringGear


def test_adventuring_gear_has_bundle_count_default_one():
    g = AdventuringGear(
        id="crowbar", name="Crowbar", category="adventuring_gear",
        item_type="gear", cost_gp=10,
    )
    assert g.bundle_count == 1


def test_adventuring_gear_accepts_bundle_count():
    g = AdventuringGear(
        id="torch", name="Torch", category="adventuring_gear",
        item_type="gear", cost_gp=1, bundle_count=6,
    )
    assert g.bundle_count == 6
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_bundle_purchases.py -q`
Expected: FAIL — `AdventuringGear` rejects unknown field `bundle_count` (extra="forbid").

- [ ] **Step 3: Add the field**

In `aose/models/item.py`, change:

```python
class AdventuringGear(ItemBase):
    item_type: Literal["gear"]
```

to:

```python
class AdventuringGear(ItemBase):
    item_type: Literal["gear"]
    bundle_count: int = 1   # individual units granted per purchase
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_bundle_purchases.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/models/item.py tests/test_bundle_purchases.py
git commit -m "feat: add bundle_count to AdventuringGear model"
```

---

## Task 2: Bundle expansion in `buy()` (and add_free stays single)

**Files:**
- Modify: `aose/engine/shop.py:500-523` (`buy`, `add_free`)
- Test: `tests/test_bundle_purchases.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bundle_purchases.py`:

```python
from aose.engine.shop import buy, add_free
from aose.models import Container


def _fake_data():
    """Tiny GameData stand-in: one bundle gear item, one single gear item."""
    return GameData(items={
        "torch": AdventuringGear(
            id="torch", name="Torch", category="adventuring_gear",
            item_type="gear", cost_gp=1, bundle_count=6,
        ),
        "crowbar": AdventuringGear(
            id="crowbar", name="Crowbar", category="adventuring_gear",
            item_type="gear", cost_gp=10,  # bundle_count defaults to 1
        ),
    })


def test_buy_bundle_adds_bundle_count_units_one_charge():
    inv, gold = buy([], 10, "torch", _fake_data())
    assert inv == ["torch"] * 6
    assert gold == 9  # one 1 gp charge for the whole stack


def test_buy_single_item_unchanged():
    inv, gold = buy([], 10, "crowbar", _fake_data())
    assert inv == ["crowbar"]
    assert gold == 0


def test_add_free_bundle_adds_exactly_one():
    inv = add_free([], "torch", _fake_data())
    assert inv == ["torch"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_bundle_purchases.py::test_buy_bundle_adds_bundle_count_units_one_charge -q`
Expected: FAIL — `inv == ["torch"]` (only one added).

- [ ] **Step 3: Implement bundle expansion in `buy`**

In `aose/engine/shop.py`, add a helper near the top of the buy/remove section (just above `def buy(`):

```python
def _bundle_count(item) -> int:
    """Units granted per purchase. Only AdventuringGear carries a bundle;
    every other item type behaves as a single unit."""
    return getattr(item, "bundle_count", 1)
```

Then change the end of `buy()` from:

```python
    return ([*inventory, item_id], gold - cost)
```

to:

```python
    return ([*inventory, *([item_id] * _bundle_count(item))], gold - cost)
```

Leave `add_free()` unchanged (it already appends exactly one).

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_bundle_purchases.py -q`
Expected: PASS (all bundle tests pass).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/shop.py tests/test_bundle_purchases.py
git commit -m "feat: buy() grants bundle_count units per purchase"
```

---

## Task 3: Per-unit sell + whole-stack refund in `remove()`/`remove_from_stash()`

**Files:**
- Modify: `aose/engine/shop.py:529-593` (`_refund_amount`, `remove`, `remove_from_stash`)
- Test: `tests/test_bundle_purchases.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bundle_purchases.py`:

```python
from aose.engine.shop import remove, remove_from_stash


def test_sell_one_bundle_unit_uses_per_unit_price():
    # torch: cost 1 / bundle 6 -> per-unit 0.166, half 0.083 -> 0 (worthless)
    inv, gold, _eq, _wp = remove(["torch"] * 6, 0, "torch", "sell", _fake_data())
    assert inv == ["torch"] * 5      # only one unit removed
    assert gold == 0                 # worthless


def test_sell_single_item_half_price():
    inv, gold, _eq, _wp = remove(["crowbar"], 0, "crowbar", "sell", _fake_data())
    assert inv == []
    assert gold == 5                 # 10 // 2


def test_refund_removes_full_stack_and_returns_full_cost():
    inv, gold, _eq, _wp = remove(["torch"] * 6, 0, "torch", "refund", _fake_data())
    assert inv == []                 # whole stack of 6 removed
    assert gold == 1                 # full bundle price back


def test_refund_requires_full_stack():
    with pytest.raises(ValueError, match="full stack"):
        remove(["torch"] * 5, 0, "torch", "refund", _fake_data())


def test_drop_one_unit_no_refund():
    inv, gold, _eq, _wp = remove(["torch"] * 6, 0, "torch", "drop", _fake_data())
    assert inv == ["torch"] * 5
    assert gold == 0


def test_stash_refund_removes_full_stack():
    stashed, gold = remove_from_stash(["torch"] * 6, 0, "torch", "refund", _fake_data())
    assert stashed == []
    assert gold == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_bundle_purchases.py::test_refund_removes_full_stack_and_returns_full_cost -q`
Expected: FAIL — refund currently removes one unit and returns full cost.

- [ ] **Step 3: Implement the new semantics**

In `aose/engine/shop.py`, replace `_refund_amount` (lines ~529-534) with a per-mode gold helper:

```python
def _removal_gold(item_id: str, mode: str, data: GameData) -> int:
    """Gold returned for a removal mode.

    * ``sell``   — per-unit half price ``int((cost_gp / bundle_count) / 2)``
    * ``refund`` — the full bundle price ``int(cost_gp)``
    * ``drop``   — nothing
    """
    item = data.items.get(item_id)
    if item is None or mode == "drop":
        return 0
    cost = item.cost_gp
    if mode == "refund":
        return int(cost)
    # sell: per-unit, halved, floored
    return int((cost / _bundle_count(item)) / 2)
```

Then rewrite `remove()` (lines ~537-580). Replace the body from the
`new_inv = list(inventory)` line through the `return` with:

```python
    item = data.items.get(item_id)
    bundle = _bundle_count(item)

    new_inv = list(inventory)
    if mode == "refund" and bundle > 1:
        if new_inv.count(item_id) < bundle:
            raise ValueError(
                f"Cannot refund {item_id!r}: need a full stack of {bundle}"
            )
        for _ in range(bundle):
            new_inv.remove(item_id)
    else:
        new_inv.remove(item_id)

    new_eq = dict(equipped or {})
    new_weapons = list(equipped_weapons or [])

    # If removal pushed equipped count past remaining inventory, free a slot.
    remaining = new_inv.count(item_id)
    eq_uses = sum(1 for v in new_eq.values() if v == item_id) + new_weapons.count(item_id)
    while eq_uses > remaining:
        for slot, eid in list(new_eq.items()):
            if eid == item_id:
                del new_eq[slot]
                break
        else:
            if item_id in new_weapons:
                new_weapons.remove(item_id)
            else:
                break
        eq_uses -= 1

    return new_inv, gold + _removal_gold(item_id, mode, data), new_eq, new_weapons
```

> Note: for `bundle == 1`, refund removes exactly one unit (the `else` branch),
> preserving today's behaviour. The `while` loop generalises the old single-slot
> cleanup to the (gear-only, so in practice never-equipped) multi-remove case.

Then update `remove_from_stash()` (lines ~583-593) to honour whole-stack refund:

```python
def remove_from_stash(stashed: list[str], gold: int, item_id: str, mode: str,
                      data: GameData) -> tuple[list[str], int]:
    """Drop / sell / refund a stashed item.  Refund removes a full bundle."""
    if item_id not in stashed:
        raise ValueError(f"{item_id!r} not in stash")
    if mode not in REMOVE_MODES:
        raise ValueError(f"Unknown remove mode {mode!r}; want one of {REMOVE_MODES}")
    item = data.items.get(item_id)
    bundle = _bundle_count(item)
    new_stashed = list(stashed)
    if mode == "refund" and bundle > 1:
        if new_stashed.count(item_id) < bundle:
            raise ValueError(
                f"Cannot refund {item_id!r}: need a full stack of {bundle}"
            )
        for _ in range(bundle):
            new_stashed.remove(item_id)
    else:
        new_stashed.remove(item_id)
    return new_stashed, gold + _removal_gold(item_id, mode, data)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_bundle_purchases.py -q`
Expected: PASS (all tests pass).

- [ ] **Step 5: Run the existing shop suite to confirm no single-item regressions**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equipment.py -q`
Expected: Some FAILS remain only in torch-probe tests (fixed in Task 7); single-item tests (`sword`/`plate_mail`) still pass. If any `sword`/`plate_mail` test fails, fix before continuing.

- [ ] **Step 6: Commit**

```bash
git add aose/engine/shop.py tests/test_bundle_purchases.py
git commit -m "feat: per-unit sell + whole-stack refund for bundles"
```

---

## Task 4: Surface `bundle_count` + `can_refund` on rows and shop items

**Files:**
- Modify: `aose/engine/shop.py:23-30` (`ShopItem`), `aose/engine/shop.py:38-48` (`InventoryRow`), `aose/engine/shop.py:96-105` (`shop_categories`), `aose/engine/shop.py:123-142` (`_build_row`)
- Test: `tests/test_bundle_purchases.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bundle_purchases.py`:

```python
from aose.engine.shop import shop_categories, inventory_view


def test_shop_item_exposes_bundle_count():
    cats = shop_categories(_fake_data())
    items = {i.id: i for c in cats for i in c.items}
    assert items["torch"].bundle_count == 6
    assert items["crowbar"].bundle_count == 1


def test_inventory_row_per_unit_sell_and_refund_flags():
    view = inventory_view(["torch"] * 6, [], {}, [], None, _fake_data())
    torch_row = next(r for r in view.carried if r.id == "torch")
    assert torch_row.bundle_count == 6
    assert torch_row.sell_gp == 0          # int((1/6)/2)
    assert torch_row.can_refund is True    # 6 >= 6


def test_inventory_row_cannot_refund_partial_stack():
    view = inventory_view(["torch"] * 5, [], {}, [], None, _fake_data())
    torch_row = next(r for r in view.carried if r.id == "torch")
    assert torch_row.can_refund is False   # 5 < 6
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_bundle_purchases.py::test_shop_item_exposes_bundle_count -q`
Expected: FAIL — `ShopItem` has no `bundle_count`.

- [ ] **Step 3: Add the fields and populate them**

In `aose/engine/shop.py`:

`ShopItem` (add field):

```python
class ShopItem(BaseModel):
    id: str
    name: str
    category: str
    cost_gp: float
    weight_cn: int = 0
    magic: bool = False
    bundle_count: int = 1
```

`InventoryRow` (add fields):

```python
class InventoryRow(BaseModel):
    id: str
    name: str
    count: int
    weight_cn: int = 0
    cost_gp: float = 0
    sell_gp: float = 0
    equippable: bool = False
    class_allowed: bool = True
    equipped_count: int = 0
    bundle_count: int = 1        # units the shop sells per purchase
    can_refund: bool = True      # True when count >= bundle_count
```

`shop_categories` — in the `ShopItem(...)` construction, add:

```python
                ShopItem(
                    id=i.id, name=i.name, category=i.category,
                    cost_gp=i.cost_gp, weight_cn=i.weight_cn,
                    magic=i.magic, bundle_count=_bundle_count(i),
                )
```

`_build_row` — compute the per-unit sell price and refund flag. Replace the
`return InventoryRow(...)` at the end of `_build_row` with:

```python
    bundle = _bundle_count(item)
    return InventoryRow(
        id=item_id,
        name=item.name,
        count=count,
        weight_cn=item.weight_cn,
        cost_gp=item.cost_gp,
        sell_gp=int((item.cost_gp / bundle) / 2),
        equippable=isinstance(item, (Weapon, Armor)),
        class_allowed=_class_allows(item, allowed_weapons, allowed_armor, allow_shields),
        bundle_count=bundle,
        can_refund=count >= bundle,
    )
```

> Note: `_build_row` is called once per *grouped* row (count = total of that id),
> so `can_refund` correctly reflects whether the carried/stashed pile holds a
> full stack. The equipped-row split (`eq_n`) can show `can_refund` based on the
> equipped subset — acceptable, since gear (the only bundled type) is never
> equipped.

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_bundle_purchases.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/shop.py tests/test_bundle_purchases.py
git commit -m "feat: expose bundle_count + can_refund on shop/inventory rows"
```

---

## Task 5: Template — shop "buys N" hint + per-unit sell + whole-stack refund

**Files:**
- Modify: `aose/web/templates/_equipment_ui.html:112-121` (`inv_row_actions`), `:469` (shop name cell)
- Test: covered by route tests in Task 7; manual render check here.

- [ ] **Step 1: Update the shop name cell**

In `_equipment_ui.html`, the shop table row name cell (currently `<td>{{ item.name }}</td>`, ~line 469), change to:

```html
            <td>{{ item.name }}{% if item.bundle_count > 1 %} <span class="muted small">(buys {{ item.bundle_count }})</span>{% endif %}</td>
```

- [ ] **Step 2: Update the inventory row actions macro**

Replace the Sell/Refund buttons block in `inv_row_actions` (lines ~117-120):

```html
        <button type="submit" name="mode" value="sell"
                title="Sell one for half its per-item price">Sell&nbsp;(+{{ row.sell_gp }}&nbsp;gp)</button>
        <button type="submit" name="mode" value="refund"
                title="Refund the full purchase price">Refund&nbsp;(+{{ row.cost_gp | int }}&nbsp;gp)</button>
```

with:

```html
        <button type="submit" name="mode" value="sell"
                title="Sell one for half its per-item price">Sell&nbsp;(+{{ row.sell_gp }}&nbsp;gp)</button>
        {% if row.can_refund %}
        <button type="submit" name="mode" value="refund"
                title="Refund a full purchased stack">Refund{% if row.bundle_count > 1 %}&nbsp;stack&nbsp;of&nbsp;{{ row.bundle_count }}{% endif %}&nbsp;(+{{ row.cost_gp | int }}&nbsp;gp)</button>
        {% endif %}
```

- [ ] **Step 3: Smoke-test the template renders**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equipment.py -k "render or sheet or shop" -q`
Expected: No new template/Jinja errors (torch-probe assertion failures still expected until Task 7).

- [ ] **Step 4: Commit**

```bash
git add aose/web/templates/_equipment_ui.html
git commit -m "feat: shop bundle hint + per-unit sell / whole-stack refund UI"
```

---

## Task 6: Rewrite `adventuring_gear.yaml` (gear + table containers)

**Files:**
- Modify (full rewrite): `data/equipment/adventuring_gear.yaml`
- Test: `tests/test_containers.py` (add data-shape assertions in Task 8); validated end-to-end in Task 9.

- [ ] **Step 1: Replace the entire file contents**

Overwrite `data/equipment/adventuring_gear.yaml` with:

```yaml
# Adventuring gear — faithful to the AOSE book table (cost only; no weights).
# Per-item weights are deliberately omitted: the encumbrance engine folds all
# adventuring gear into a flat 80 cn abstraction, so tracked weights would be
# dead data. Stack-priced rows carry bundle_count (units granted per purchase).

- id: crowbar
  item_type: gear
  name: Crowbar
  category: adventuring_gear
  cost_gp: 10
  description: |-
    2–3' long and made of solid iron. Can be used for forcing doors and
    other objects open.

- id: garlic
  item_type: gear
  name: Garlic
  category: adventuring_gear
  cost_gp: 5

- id: grappling_hook
  item_type: gear
  name: Grappling Hook
  category: adventuring_gear
  cost_gp: 25
  description: Has 3 or 4 prongs. Can be used for anchoring a rope.

- id: hammer_small
  item_type: gear
  name: Hammer, Small
  category: adventuring_gear
  cost_gp: 2
  description: Can be used for construction or as a mallet with iron or wooden spikes.

- id: holy_symbol
  item_type: gear
  name: Holy Symbol
  category: adventuring_gear
  cost_gp: 25
  description: |-
    A divine spell caster is required to own a holy symbol of their deity,
    often worn as a necklace. Each religion has its own holy symbol.

- id: holy_water_vial
  item_type: gear
  name: Holy Water (vial)
  category: adventuring_gear
  cost_gp: 25
  description: |-
    Water that has been blessed by a holy person. It is used in some religious
    rituals and inflicts damage on undead monsters. Holy water does not retain
    its power if stored in any other container than the special vials it is
    blessed in.

- id: iron_spike
  item_type: gear
  name: Iron Spike
  category: adventuring_gear
  cost_gp: 1
  bundle_count: 12
  description: |-
    May be used for wedging doors open or shut, as an anchor to attach a rope
    to, and many other purposes. Sold in sets of 12.

- id: lantern
  item_type: gear
  name: Lantern
  category: adventuring_gear
  cost_gp: 10
  description: |-
    Can be closed to hide the light. Burns one oil flask every four hours
    (24 turns). Casts light in a 30' radius.

- id: mirror_small
  item_type: gear
  name: Mirror (hand-sized, steel)
  category: adventuring_gear
  cost_gp: 5
  description: Useful for looking around corners or for reflecting a gaze attack.

- id: flask_of_oil
  item_type: gear
  name: Oil (flask)
  category: adventuring_gear
  cost_gp: 2
  description: |-
    A flask of oil fuels a lantern for four hours (24 turns). In addition to
    fuelling lanterns, oil can be used as a weapon: an oil flask may be lit on
    fire and thrown, or poured on the ground and lit (covering a 3-foot diameter,
    burning for 1 turn and inflicting damage on any character or monster moving
    through the pool). Burning oil does not harm monsters that have a natural
    flame attack.

- id: pole_10ft
  item_type: gear
  name: Pole (10' wooden)
  category: adventuring_gear
  cost_gp: 1
  description: |-
    A 2" thick wooden pole useful for poking and prodding suspicious items in
    a dungeon.

- id: iron_rations
  item_type: gear
  name: Rations, Iron (1 day)
  category: adventuring_gear
  cost_gp: 15
  bundle_count: 7
  description: |-
    Dried and preserved food to be carried on long voyages when securing fresh
    food may be uncertain. Sold as 7 days' worth.

- id: standard_rations
  item_type: gear
  name: Rations, Standard (1 day)
  category: adventuring_gear
  cost_gp: 5
  bundle_count: 7
  description: Fresh, unpreserved food. Sold as 7 days' worth.

- id: rope_50ft
  item_type: gear
  name: Rope (50')
  category: adventuring_gear
  cost_gp: 1
  description: Can hold the weight of approximately three human-sized beings.

- id: stakes_and_mallet
  item_type: gear
  name: Stakes (3) and Mallet
  category: adventuring_gear
  cost_gp: 3
  description: |-
    A wooden mallet and three 18" long stakes. Valuable when confronting
    vampires.

- id: thieves_tools
  item_type: gear
  name: Thieves' Tools
  category: adventuring_gear
  cost_gp: 25
  description: This kit contains all of the tools needed to pick locks.

- id: tinder_box
  item_type: gear
  name: Tinder Box (flint & steel)
  category: adventuring_gear
  cost_gp: 3
  description: |-
    Used to light fires, including torches. Using a tinder box takes one round.
    There is a 2-in-6 chance of success per round.

- id: torch
  item_type: gear
  name: Torch
  category: adventuring_gear
  cost_gp: 1
  bundle_count: 6
  description: |-
    A torch burns for 1 hour (6 turns), clearly illuminating a 30' radius.
    Torches may also be used in combat. Sold in sets of 6.

- id: waterskin
  item_type: gear
  name: Waterskin
  category: adventuring_gear
  cost_gp: 1
  description: This container, made of hide, will hold 2 pints (1 quart) of fluid.

- id: wine_pint
  item_type: gear
  name: Wine (1 pint)
  category: adventuring_gear
  cost_gp: 1
  bundle_count: 2
  description: A pint of wine. Sold by the 2-pint measure.

- id: wolfsbane
  item_type: gear
  name: Wolfsbane
  category: adventuring_gear
  cost_gp: 10
  description: |-
    This herb can be used to repel lycanthropes. The creature must be hit with
    the herb in melee combat.

# ── Containers from the Adventuring Gear table ───────────────────────────────
# Kept as item_type: container so the stow/capacity mechanic still applies; they
# live here (not a separate containers.yaml) and group under Adventuring Gear in
# the shop. No own weight (book lists cost only).

- id: backpack
  name: Backpack
  category: adventuring_gear
  item_type: container
  cost_gp: 5
  capacity_cn: 400
  weight_multiplier: 1.0
  description: |-
    Has two straps and can be worn on the back, keeping the hands free.
    Holds up to 400 coins.

- id: sack_small
  name: Sack, Small
  category: adventuring_gear
  item_type: container
  cost_gp: 1
  capacity_cn: 200
  weight_multiplier: 1.0
  description: Can hold up to 200 coins.

- id: sack_large
  name: Sack, Large
  category: adventuring_gear
  item_type: container
  cost_gp: 2
  capacity_cn: 600
  weight_multiplier: 1.0
  description: Can hold up to 600 coins.
```

- [ ] **Step 2: Verify the data loads**

Run: `.venv\Scripts\python.exe -c "from pathlib import Path; from aose.data.loader import GameData; d = GameData.load(Path('data')); print(d.items['torch'].bundle_count, d.items['backpack'].capacity_cn, 'bedroll' in d.items)"`
Expected: `6 400 False`

- [ ] **Step 3: Commit** (suite still red — repaired in Task 8)

```bash
git add data/equipment/adventuring_gear.yaml
git commit -m "data: rewrite adventuring_gear.yaml book-faithful + table containers"
```

---

## Task 7: Move Bag of Holding to magic_items.yaml; delete containers.yaml

**Files:**
- Modify: `data/equipment/magic_items.yaml` (append Bag of Holding)
- Delete: `data/equipment/containers.yaml`

- [ ] **Step 1: Append Bag of Holding to `magic_items.yaml`**

Add this block at the end of `data/equipment/magic_items.yaml`:

```yaml
- id: bag_of_holding
  name: Bag of Holding
  category: miscellaneous_magic_items
  item_type: container
  cost_gp: 0
  weight_cn: 0
  magic: true
  capacity_cn: 10000
  weight_multiplier: 0.06
  description: |-
    A normal-looking small sack that can magically hold large objects and
    weights.

    Size: Objects of up to 10'×5'×3' can fit inside the bag.

    Weight: Up to 10,000 coins of weight can be placed in the bag.
```

- [ ] **Step 2: Delete the old containers file**

```bash
git rm data/equipment/containers.yaml
```

- [ ] **Step 3: Verify the loader still finds the containers**

Run: `.venv\Scripts\python.exe -c "from pathlib import Path; from aose.data.loader import GameData; d = GameData.load(Path('data')); print(type(d.items['bag_of_holding']).__name__, 'saddle_bags' in d.items, type(d.items['backpack']).__name__)"`
Expected: `Container False Container`

- [ ] **Step 4: Commit**

```bash
git add data/equipment/magic_items.yaml
git commit -m "data: move Bag of Holding to magic_items.yaml; drop containers.yaml + saddle_bags"
```

---

## Task 8: Repair downstream tests broken by the data change

The data rewrite makes `torch` a weightless `bundle_count: 6` item. Tests that
used `torch` as a single-unit / weighted probe must move to a `bundle_count: 1`
item (`rope_50ft`, 1 gp) for generic cases, a weighted weapon (`dagger`, 10 cn)
for capacity cases, and keep `torch` only where bundle behaviour is the point.

**Files:**
- Modify: `tests/test_equipment.py`, `tests/test_containers.py`

- [ ] **Step 1: Fix `tests/test_equipment.py::test_buy_respects_existing_inventory`**

Replace (lines ~122-125):

```python
def test_buy_respects_existing_inventory(data):
    inv, gold = buy(["torch"], 5, "torch", data)
    assert inv == ["torch", "torch"]
    assert gold == 4
```

with:

```python
def test_buy_respects_existing_inventory(data):
    inv, gold = buy(["rope_50ft"], 5, "rope_50ft", data)
    assert inv == ["rope_50ft", "rope_50ft"]
    assert gold == 4


def test_buy_torch_grants_a_stack_of_six(data):
    inv, gold = buy([], 5, "torch", data)
    assert inv == ["torch"] * 6
    assert gold == 4  # one 1 gp charge for the stack
```

- [ ] **Step 2: Fix `test_buy_locks_starting_gold_roll`**

Replace the buy + assertions (lines ~238-242):

```python
    client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "torch"})
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["gold_locked"] is True
    assert draft["gold"] == 49
    assert draft["inventory"] == ["torch"]
```

with (use `rope_50ft` so the gold-lock assertion isn't about bundles):

```python
    client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "rope_50ft"})
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["gold_locked"] is True
    assert draft["gold"] == 49
    assert draft["inventory"] == ["rope_50ft"]
```

- [ ] **Step 3: Fix `test_remove_modes_via_wizard`**

Replace the whole function body (lines ~255-282) to use `rope_50ft`
(bundle 1, so drop/sell/refund are per-unit and identical to the old intent):

```python
def test_remove_modes_via_wizard(client):
    draft_id = _walk_to_equipment(client)
    client.get(f"/wizard/{draft_id}/equipment")
    draft = load_draft(draft_id, client._drafts_dir)
    draft["gold"] = 100
    save_draft(draft_id, draft, client._drafts_dir)
    # Buy three ropes (1 gp each, bundle_count 1)
    for _ in range(3):
        client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "rope_50ft"})

    # Drop one (no refund)
    r = client.post(f"/wizard/{draft_id}/equipment/remove",
                    data={"item_id": "rope_50ft", "mode": "drop"})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["inventory"].count("rope_50ft") == 2
    gold_after_drop = draft["gold"]

    # Sell next (half of 1 gp floors to 0)
    client.post(f"/wizard/{draft_id}/equipment/remove",
                data={"item_id": "rope_50ft", "mode": "sell"})
    # Refund the last (full price, bundle of 1)
    client.post(f"/wizard/{draft_id}/equipment/remove",
                data={"item_id": "rope_50ft", "mode": "refund"})
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["inventory"].count("rope_50ft") == 0
    # 0 (drop) + 0 (sell floor) + 1 (refund) = +1 from drop point
    assert draft["gold"] == gold_after_drop + 0 + 1
```

- [ ] **Step 4: Fix the wizard add-button test (`test_*` around line 403)**

The add route does not expand bundles, so `add` of `torch` yields one unit —
this test already expects `["torch"]` and stays correct. **No change needed.**
Confirm by reading lines ~400-406; only edit if it asserts a count other than 1.

- [ ] **Step 5: Fix `tests/test_containers.py::test_sheet_stow_rejects_full_container`**

`torch` is now weightless, so it can never fill a sack. Replace the function
(lines ~677-694) to fill `sack_small` (200 cn) with daggers (10 cn each):

```python
def test_sheet_stow_rejects_full_container(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "sack_small"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    # 20 daggers at 10 cn = 200 cn = sack_small capacity
    for _ in range(20):
        client.post("/character/test/equipment/add", data={"item_id": "dagger"})
        client.post("/character/test/equipment/stow", data={
            "instance_id": instance_id, "item_id": "dagger",
        })
    client.post("/character/test/equipment/add", data={"item_id": "dagger"})
    r = client.post("/character/test/equipment/stow", data={
        "instance_id": instance_id, "item_id": "dagger",
    })
    assert r.status_code == 400
    assert "full" in r.text.lower()
```

- [ ] **Step 6: Run the two repaired suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equipment.py tests/test_containers.py -q`
Expected: PASS. If any remaining failure references a removed/weightless gear id,
apply the same probe-swap pattern (generic → `rope_50ft`; weighted → `dagger`;
bundle-specific → keep `torch` and assert ×6).

- [ ] **Step 7: Commit**

```bash
git add tests/test_equipment.py tests/test_containers.py
git commit -m "test: migrate probe items off weightless/bundled torch"
```

---

## Task 9: Data-validation tests + full-suite green

**Files:**
- Modify: `tests/test_containers.py` (append data-shape assertions)
- Test: full suite

- [ ] **Step 1: Add data-shape assertions**

Append to `tests/test_containers.py`:

```python
# ── Post-cleanup data shape ──────────────────────────────────────────────────

def test_table_containers_are_adventuring_gear_category(data):
    for cid, cap in (("backpack", 400), ("sack_small", 200), ("sack_large", 600)):
        item = data.items[cid]
        assert isinstance(item, Container)
        assert item.category == "adventuring_gear"
        assert item.capacity_cn == cap


def test_bag_of_holding_still_a_container(data):
    boh = data.items["bag_of_holding"]
    assert isinstance(boh, Container)
    assert boh.magic is True
    assert boh.capacity_cn == 10000


def test_dropped_and_renamed_ids_absent(data):
    for gone in ("bedroll", "candle", "saddle_bags", "iron_spikes", "wine_skin"):
        assert gone not in data.items


def test_gear_bundle_counts(data):
    assert data.items["torch"].bundle_count == 6
    assert data.items["iron_spike"].bundle_count == 12
    assert data.items["iron_rations"].bundle_count == 7
    assert data.items["standard_rations"].bundle_count == 7
    assert data.items["wine_pint"].bundle_count == 2
    assert data.items["crowbar"].bundle_count == 1


def test_containers_yaml_deleted():
    from pathlib import Path
    assert not (Path("data") / "equipment" / "containers.yaml").exists()
```

- [ ] **Step 2: Run the new assertions**

Run: `.venv\Scripts\python.exe -m pytest tests/test_containers.py -k "table_containers or bag_of_holding_still or dropped or bundle_counts or yaml_deleted" -q`
Expected: PASS (5 passed).

- [ ] **Step 3: Run the FULL suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: All pass (≥ 1020 + the new tests; only the known Windows-tempdir
`PermissionError` on `pytest-current` may trail — ignore it per CLAUDE.md).
Fix any remaining failure using the probe-swap pattern from Task 8.

- [ ] **Step 4: Commit**

```bash
git add tests/test_containers.py
git commit -m "test: data-shape guards for gear cleanup + container consolidation"
```

---

## Task 10: Manual verification + docs

**Files:**
- Modify: `CLAUDE.md` (Current state note)

- [ ] **Step 1: Launch the app and spot-check**

Run: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
Check: create a character, open the shop — Adventuring Gear group lists gear +
Backpack/Sacks; Torch shows "(buys 6)"; buying a Torch adds 6 to inventory;
selling one Torch returns 0 gp; the Refund button shows "stack of 6" and only
when ≥ 6 are held; Bag of Holding appears under the magic section.

- [ ] **Step 2: Add a CLAUDE.md "Current state" entry**

Add a dated bullet under the current-state section summarising: gear data
rewritten book-faithful (no weights, descriptions in), `bundle_count` on
`AdventuringGear` (buy grants N, add grants 1), per-unit sell + whole-stack
refund, `containers.yaml` deleted (Backpack/Sacks → `adventuring_gear.yaml` as
containers under the gear category; Bag of Holding → `magic_items.yaml`;
`saddle_bags` dropped). Reference this plan + the spec.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: note adventuring-gear cleanup + bundle purchases in CLAUDE.md"
```

---

## Self-Review

**Spec coverage:**
- Goal 1 (book-faithful gear) → Task 6.
- Goal 2 (no weights) → Task 6 (weights omitted); encumbrance unaffected (engine already flat-80).
- Goal 3 (descriptions) → Task 6.
- Goal 4 (stack grants N) → Tasks 2, 6.
- Goal 5 (per-unit sell, whole-stack refund) → Tasks 3, 4, 5.
- Goal 6 (container consolidation, no non-official) → Tasks 6, 7 (saddle_bags dropped, Bag of Holding moved, containers.yaml deleted).

**Type consistency:** `_bundle_count` (Task 2) reused in Tasks 3-4; `_removal_gold` replaces `_refund_amount` consistently in `remove` + `remove_from_stash` (Task 3); `bundle_count`/`can_refund` added in Task 4 are consumed by the template in Task 5; data ids in Task 6 match the test ids in Tasks 8-9 (`rope_50ft`, `dagger`, `torch`, `iron_spike`, `wine_pint`, `iron_rations`, `standard_rations`, `crowbar`).

**Placeholder scan:** none — every code/data/test step carries full content.

**Known acceptable states:** the suite is red between Task 6 and Task 8 (data changed before probe tests migrated); commits in 6/7 are intentionally pre-repair. Full green is restored in Task 9.
