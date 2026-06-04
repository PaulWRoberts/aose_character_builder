# Adventuring Gear data cleanup + stackable purchases — design

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

Separately, several book entries are priced as a *stack* ("Torches (6)", "Iron
spikes (12)", "Rations ... 7 days", "Wine (2 pints)"). Purchasing one of these
should bring the buyer the whole stack as individual, separately-trackable
units.

## Goals

1. `data/equipment/adventuring_gear.yaml` becomes faithful to the book table.
2. No fabricated `weight_cn` on gear (field omitted → defaults to 0).
3. Every description from the book source is included.
4. Stack-priced items grant N individual units on purchase.

## Non-goals

- No changes to encumbrance behaviour (gear is already a flat 80 cn).
- No per-unit price math for partial-bundle sell/refund (see Known limitation).
- No changes to containers — Backpack / Sacks stay as `Container` items.

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
  `AdventuringGear`, append `bundle_count` copies of `item_id` to the inventory
  (one `cost_gp` charge covers the whole bundle). For `bundle_count == 1` this
  is identical to today's behaviour. Non-gear items are unaffected.
- `add_free(inventory, item_id, data)`: same bundle expansion (GM grant of a
  stack item yields the full stack).
- `ShopItem` gains `bundle_count: int = 1`; `shop_categories` copies it from the
  catalog item so the template can render a "buys N" hint.

**Known limitation (accepted):** `cost_gp` remains the book *bundle* price
(e.g. 1 gp buys 6 torches). The per-unit sell/refund/remove paths
(`_refund_amount`, `_build_row.sell_gp`) treat `cost_gp` as a per-unit value, so
selling/refunding a *single* unit of a bundle uses the bundle price as if it
were per-unit. For the cheap consumables affected this is negligible (a single
torch sells for `1 // 2 = 0`; a single standard ration would refund the full
5 gp). We accept this rather than introduce per-unit price arithmetic. Revisit
only if it becomes a real annoyance.

### 3. Shop template — `aose/web/templates/_equipment_ui.html`

In the shop table row (~line 466), when `item.bundle_count > 1`, append a small
hint to the item name cell (e.g. `Torch <span class="hint">(buys 6)</span>`).
The weight column will read `0 cn` for gear — acceptable and consistent with the
"no weight" decision.

### 4. Data — rewrite `data/equipment/adventuring_gear.yaml`

21 items, sourced from the book table. No `weight_cn` field on any. Descriptions
copied from the source. Singular unit names for stack items, with `bundle_count`.

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

Notes:
- **Garlic** has no description in the book table → no `description`.
- **Excluded** (already `Container` items in `containers.yaml`): Backpack, Sack
  (large), Sack (small). Not duplicated here.
- **Dropped** from the old file: `bedroll`, `candle` (not in the book table).
  Verified there are no test or starting-equipment references to them.
- Stakes-and-mallet stays a single kit item (`bundle_count: 1`) — the "(3)"
  refers to stakes within the kit, not three separate purchasable units.
- `iron_spike` is a renamed id (was `iron_spikes`); `wine_pint` replaces
  `wine_skin`. Old ids had no external references (grep-verified), and the app
  is not deployed (no migration needed).

### 5. Tests

- `buy()` of `torch` adds 6 inventory entries for one 1 gp charge; `iron_spike`
  adds 12; a `bundle_count == 1` item still adds exactly one.
- `add_free()` of a bundle item yields the full stack.
- Data-validation: the new file loads, every gear item has the expected
  `bundle_count`, and the dropped/excluded ids are absent from
  `data.items` under the gear category.

## Files touched

- `aose/models/item.py` — add `bundle_count`
- `aose/engine/shop.py` — bundle expansion in `buy`/`add_free`; `ShopItem` field
- `aose/web/templates/_equipment_ui.html` — "buys N" hint
- `data/equipment/adventuring_gear.yaml` — full rewrite
- `tests/` — new bundle + data coverage
