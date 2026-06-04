# Adventuring Gear data cleanup + stackable purchases + container consolidation — design

**Date:** 2026-06-04
**Status:** Approved (pending spec review)

## Problem

The current `data/equipment/adventuring_gear.yaml` contains fabricated data:
per-item `weight_cn` values that do not appear in the AOSE book (the book table
lists *cost only*), plus invented items (`bedroll`, `candle`) and inconsistent
descriptions. The encumbrance engine already ignores gear weight entirely (any
adventuring gear contributes a flat 80 cn — see
`aose/engine/encumbrance.py:120-174`), so the per-item weights are not just
fabricated, they are dead data.

We want to replace the file wholesale with book-faithful data pulled from the
PDF (`import/markdown/items/advanced-fantasy_adventuring-gear.md`), carry every
description across, and drop the fabricated weights.

Several book entries are priced as a *stack* ("Torches (6)", "Iron spikes (12)",
"Rations ... 7 days", "Wine (2 pints)"). Purchasing one of these should bring
the buyer the whole stack as individual, separately-trackable units.

Finally, the container data is fragmented and partly non-canonical:
`containers.yaml` mixes the three adventuring-gear-table containers (Backpack,
Sacks) with a Transport-table item (`saddle_bags`) and a magic item (Bag of
Holding). We consolidate so that every container lives in the file matching its
book category, and no non-official container remains.

## Goals

1. `data/equipment/adventuring_gear.yaml` becomes faithful to the book table.
2. No fabricated `weight_cn` on gear (field omitted → defaults to 0).
3. Every description from the book source is included.
4. Stack-priced items grant N individual units on purchase.
5. Sell handles per-unit pricing; refund operates on whole shop-sold stacks.
6. Containers consolidated: `containers.yaml` deleted; only official containers
   remain, each in its book-category file.

## Non-goals

- No changes to encumbrance behaviour (gear is already a flat 80 cn; the
  carried-container weight formula is unchanged).
- No Transport/Tack-&-Harness table import (so `saddle_bags` is dropped for now).
- No change to the container stow/capacity mechanic itself.

## Design

### 1. Model — `aose/models/item.py`

Add one field to `AdventuringGear`, mirroring `Ammunition.bundle_count`:

```python
class AdventuringGear(ItemBase):
    item_type: Literal["gear"]
    bundle_count: int = 1   # individual units granted per purchase
```

Default `1` keeps every existing gear item and every other item type unchanged.

### 2. Buy logic — `aose/engine/shop.py`

- `buy(inventory, gold, item_id, data)`: when the resolved item is an
  `AdventuringGear`, append `bundle_count` copies of `item_id` (one `cost_gp`
  charge covers the whole bundle). `bundle_count == 1` is identical to today.
  Non-gear items are unaffected. Container/Ammunition buys are dispatched
  *before* `buy()` is reached (routes branch on `isinstance`), so this change is
  confined to the loose-inventory path.
- `add_free(inventory, item_id, data)`: same bundle expansion (GM grant of a
  stack item yields the full stack).
- `ShopItem` gains `bundle_count: int = 1`; `shop_categories` copies it so the
  template can render a "buys N" hint.

### 3. Sell / refund semantics — `aose/engine/shop.py`

Per the agreed model, the three removal modes diverge for bundles:

| Mode | Units removed | Gold returned |
|---|---|---|
| `drop` | 1 | 0 |
| `sell` | 1 | `int((cost_gp / bundle_count) / 2)` — per-unit half, may be 0 (worthless) |
| `refund` | `bundle_count` (a full shop stack) | `cost_gp` (full stack price) |

For `bundle_count == 1` every row reduces to today's behaviour
(`sell = cost_gp // 2`, `refund` removes 1 and returns `cost_gp`).

Implementation:
- `InventoryRow` gains `bundle_count: int = 1` and `can_refund: bool` (True when
  the row's `count >= bundle_count`). `sell_gp` becomes the per-unit half price
  `int((cost_gp / bundle_count) / 2)`.
- `remove(...)` mode `refund`: remove `bundle_count` copies; raise `ValueError`
  if fewer than `bundle_count` are present (UI hides the button in that case).
  Mode `sell`: remove 1, return per-unit half. Mode `drop`: remove 1, return 0.
- `remove_from_stash(...)`: same per-mode logic.
- `_refund_amount` is reworked / split to express the per-unit-sell vs
  whole-stack-refund distinction.
- Equipped-cleanup in `remove()` is unaffected in practice: only `AdventuringGear`
  carries `bundle_count > 1`, and gear is never equippable.

### 4. Templates — `aose/web/templates/_equipment_ui.html`

- Shop row (~line 466): when `item.bundle_count > 1`, append a "(buys N)" hint to
  the name cell. Weight column will read `0 cn` for gear — acceptable.
- Inventory `inv_row_actions` macro (lines 112-121):
  - `Sell (+{{ row.sell_gp }} gp)` is now the per-unit price.
  - `Refund` button rendered only when `row.can_refund`; relabelled
    `Refund stack of {{ row.bundle_count }} (+{{ row.cost_gp | int }} gp)` when
    `bundle_count > 1` (plain `Refund (+… gp)` when 1).

### 5. Container consolidation

- **Delete** `data/equipment/containers.yaml`. The loader globs
  `data/equipment/*.yaml`, so removal needs no code change (no `ITEM_FILES`
  list). Buy/add dispatch is by `isinstance(item, Container)` (routes.py:408,
  routes.py:436; wizard.py:1438, 1471) — independent of filename/category.
- **Bag of Holding** → moved verbatim into `data/equipment/magic_items.yaml`.
  Keeps `item_type: container` + `magic: true` + `category:
  miscellaneous_magic_items`; it already renders in the magic shop section and
  is acquired via add-free-container. Pure file move, no field changes.
- **Backpack / Sack (large) / Sack (small)** → moved into
  `adventuring_gear.yaml`, keeping `item_type: container` (capacity/stow
  mechanic preserved) but **re-categorised** `category: adventuring_gear` so the
  shop groups them with the book's Adventuring Gear list. Capacity values stay
  (Backpack 400, Sack small 200, Sack large 600 — book-faithful). `weight_cn`
  removed (they fold into the flat-80 gear abstraction like other gear, and the
  carried-container formula uses `own_weight + multiplier*contents`; own_weight
  defaults to 0).
- **`saddle_bags`** → dropped (Transport table, out of scope; re-add when that
  table is imported).

> Note: `test_containers.py` / `test_encumbrance.py` may assert the old
> `category: containers` or `saddle_bags`/`bag_of_holding` locations or non-zero
> container `weight_cn`. Those assertions are updated to the new shapes as part
> of this work.

### 6. Data — rewrite `data/equipment/adventuring_gear.yaml`

Gear items (21), sourced from the book table, no `weight_cn`, descriptions from
the source, singular unit names + `bundle_count` for stacks:

| id | name | cost_gp | bundle_count |
|---|---|---:|---:|
| `crowbar` | Crowbar | 10 | 1 |
| `garlic` | Garlic | 5 | 1 |
| `grappling_hook` | Grappling Hook | 25 | 1 |
| `hammer_small` | Hammer, Small | 2 | 1 |
| `holy_symbol` | Holy Symbol | 25 | 1 |
| `holy_water_vial` | Holy Water (vial) | 25 | 1 |
| `iron_spike` | Iron Spike | 1 | 12 |
| `lantern` | Lantern | 10 | 1 |
| `mirror_small` | Mirror (hand-sized, steel) | 5 | 1 |
| `flask_of_oil` | Oil (flask) | 2 | 1 |
| `pole_10ft` | Pole (10' wooden) | 1 | 1 |
| `iron_rations` | Rations, Iron (1 day) | 15 | 7 |
| `standard_rations` | Rations, Standard (1 day) | 5 | 7 |
| `rope_50ft` | Rope (50') | 1 | 1 |
| `stakes_and_mallet` | Stakes (3) and Mallet | 3 | 1 |
| `thieves_tools` | Thieves' Tools | 25 | 1 |
| `tinder_box` | Tinder Box (flint & steel) | 3 | 1 |
| `torch` | Torch | 1 | 6 |
| `waterskin` | Waterskin | 1 | 1 |
| `wine_pint` | Wine (1 pint) | 1 | 2 |
| `wolfsbane` | Wolfsbane | 10 | 1 |

Plus the three relocated containers (`item_type: container`,
`category: adventuring_gear`): `backpack` (cap 400), `sack_small` (cap 200),
`sack_large` (cap 600), descriptions from the source table.

Notes:
- **Garlic** has no description in the book table → no `description`.
- **Dropped** from the old gear file: `bedroll`, `candle` (not in the book
  table). Grep-verified: no test or starting-equipment references.
- Stakes-and-mallet stays a single kit item (`bundle_count: 1`) — the "(3)"
  refers to stakes within the kit, not three purchasable units.
- Renamed ids: `iron_spikes → iron_spike`, `wine_skin → wine_pint`. No external
  references (grep-verified); app is not deployed (no migration needed).

### 7. Tests

- `buy()`/`add_free()` of `torch` → 6 inventory entries for one 1 gp charge;
  `iron_spike` → 12; a `bundle_count == 1` item still adds exactly one.
- Sell one torch → 0 gp (worthless) and one unit removed; sell one `iron_rations`
  → `int(15/7/2) = 1` gp; sell a `bundle_count == 1` item → `cost_gp // 2`.
- Refund a full torch stack → removes 6 units, returns 1 gp; refund with fewer
  than `bundle_count` present → `ValueError` (and `can_refund` is False).
- Data-validation: new gear file loads; each gear item has expected
  `bundle_count`; `bedroll`/`candle`/`saddle_bags` absent; backpack/sacks are
  `Container` under `category: adventuring_gear`; Bag of Holding present and a
  `Container` after the move; `containers.yaml` no longer exists.

## Files touched

- `aose/models/item.py` — add `bundle_count`
- `aose/engine/shop.py` — bundle expansion in `buy`/`add_free`; new sell/refund
  semantics in `remove`/`remove_from_stash`; `ShopItem` + `InventoryRow` fields
- `aose/web/templates/_equipment_ui.html` — "buys N" hint; per-unit sell label;
  whole-stack refund button
- `data/equipment/adventuring_gear.yaml` — full rewrite (gear + 3 containers)
- `data/equipment/magic_items.yaml` — add Bag of Holding
- `data/equipment/containers.yaml` — **deleted**
- `tests/` — bundle/sell/refund coverage + data-validation updates
