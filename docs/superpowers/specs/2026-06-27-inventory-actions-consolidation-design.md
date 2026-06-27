# Inventory actions consolidation — design

**Date:** 2026-06-27
**Status:** approved (design)
**Branch (planned):** `feat/inventory-actions-consolidation`

## Problem

The items refactor (Parts 1–5) made the inventory **instance-keyed**: `spec.items`
is a flat list of `ItemInstance`, and the engine (`equip.equip`, `equip.unequip`,
`storage.move_item`) plus the routes now take an `instance_id`. But the shared
row-action **templates were never migrated** — they still POST `item_id` (the
catalog id). On the live sheet (and the wizard equipment step, which reuses the
same partials) this means:

| Action | Form sends | Route wants | Result |
|---|---|---|---|
| Equip | `item_id` (catalog) | `instance_id` | HTTP 422, silent no-op |
| Unequip | `item_id` | `instance_id` | HTTP 422 |
| Move (item) | `item_id` | instance lookup in `move_item` | HTTP 400 StorageError |
| Sell/Drop | `item_id` | catalog-keyed `shop.sell_item` | **works** — the lone exception |

Sell is the only per-item action whose route is still catalog-keyed, which is the
inconsistency at the root of the maintenance pain.

### Underlying maintainability smells (the real target)

1. **Mixed keying** — 3 of 4 actions are instance-keyed, sell is catalog-keyed;
   templates blindly pass `row.id` (catalog) everywhere.
2. **Action rendering duplicated three ways** — `_inv_row_actions.html` (plain +
   enchanted `ItemInstance`), the inline magic block in `sheet.html:996–1051`, and
   a near-verbatim copy for container-stowed magic at `sheet.html:1053–1090`. Each
   hand-codes the forms and branches route names on `is_ench`.
3. **Route sprawl** — `equip` ≡ `equip-enchanted`; `unequip` ≡ `unequip-enchanted`;
   `remove`/`remove-enchanted`/`remove-magic` parallel; `use-charge`/
   `enchanted/use-charge` parallel; note variants parallel. Plus per-owner copies
   (retainer/animal/wizard equip+unequip).
4. **Two row-building paths that must agree** — `shop.inventory_view` feeds the
   modals (via the route context) and `build_inventory_groups` feeds the panes;
   both aggregate by catalog id and keep only the *first* instance's id, so buying
   two daggers yields one row whose Equip only ever equips dagger #1.

## Decisions (locked)

- **Scope:** full consolidation — unify keying, the action layer, the route
  family, the row source, and the templates; bring magic-item actions under the
  same shared layer.
- **Structure:** composition / dispatcher, mirroring `storage.move_thing`. No new
  class hierarchy (the engine is pure functions + data).
- **Old routes:** deleted outright (no migrations; templates are the only callers).

## Target architecture

### A. Engine — one dispatcher: `aose/engine/inventory_actions.py` (new)

The single front door for per-item actions, composing existing engine functions.
`category ∈ {"item", "enchanted", "magic"}` (item & enchanted are both
`ItemInstance`; magic is `MagicItemInstance`).

```
equip_thing(spec, category, instance_id, *, data, owner, slot=None,
            two_weapon, eligible, gargantua_1h_2h,
            allowed_weapons, allowed_armor, allow_shields)
unequip_thing(spec, category, instance_id, *, owner)
sell_thing(spec, category, instance_id, mode, data)
use_charge_thing(spec, category, instance_id)
reset_charges_thing(spec, category, instance_id)
set_note_thing(spec, category, instance_id, note)
```

Dispatch table:

| category | equip/unequip | sell/remove | charge/note |
|---|---|---|---|
| `item` | `equip.equip` / `equip.unequip` | `shop.sell_instance` | n/a (plain items have no charges/notes) |
| `enchanted` | `equip.equip` / `equip.unequip` | `enchant.remove` (drop) | `enchant.use_charge` / `reset_charges` / `set_note` |
| `magic` | `magic.equip_magic` / `magic.unequip_magic` | `magic.remove_magic` (credits coins) | `magic.use_charge` / `reset_charges` / `set_magic_note` |

`owner: StorageLocation`-style selector (PC, `retainer/<id>`, `animal/<id>`)
resolves the spec the action runs against — the same owner indirection
`storage.move_thing` already uses. A bad category raises
`InventoryActionError(ValueError)` → routes map to HTTP 400.

This module is the only place that encodes substrate differences. It imports the
existing engines; nothing imports it back (no cycle).

### B. Shop — instance-keyed sell

Add `shop.sell_instance(spec, instance_id, mode, data)`. The instance carries its
own `location`, so one function covers carried **and** stashed (no separate
`sell_from_stash`). Behaviour matches today's `sell_item` per mode
(`drop`/`sell`/`refund`), but operates on the exact instance the user clicked.
Retire `shop.sell_item` and `shop.sell_from_stash` once callers move over.

### C. Routes — thin shims, one family

Replace the per-item management routes with one family on **both** sheet and
wizard (same handler bodies, different prefix + persistence):

```
POST  …/inventory/equip     (category, instance_id, slot?)
POST  …/inventory/unequip   (category, instance_id)
POST  …/inventory/sell      (category, instance_id, mode)
POST  …/inventory/charge    (category, instance_id, op=use|reset)
POST  …/inventory/note      (category, instance_id, note)
POST  …/inventory/move      (already unified — unchanged)
```

Each handler: load spec → call dispatcher → save → 303 redirect. Retainer/animal
keep their own URL prefixes (`…/retainer/{rid}/…`, `…/animal/{aid}/…`) but their
handlers call the same dispatcher with `owner` set, so no equip/unequip logic is
duplicated per owner.

**Deleted** (sheet) — `/equipment/equip`, `/unequip`, `/remove`,
`/equip-magic`, `/unequip-magic`, `/use-charge`, `/reset-charges`, `/remove-magic`,
`/magic-note`, `/equip-enchanted`, `/unequip-enchanted`, `/enchanted/use-charge`,
`/enchanted/reset-charges`, `/remove-enchanted`, `/enchanted-note`. Wizard's
`/equipment/equip`, `/equipment/unequip`, and remove equivalents likewise.

**Kept** (not per-row management): `/equipment/buy`, `/equipment/add`,
`/equipment/add-enchanted` (acquisition), `/equipment/remove-container`,
`/equipment/tailored`, `/inventory/use-as-container`, all coin/gem/jewellery/ammo
routes.

### D. View — single row source, per-instance rows

`build_inventory_groups` becomes the **only** inventory row builder. Each row in a
`TopLevelGroup` (loose / equipped / stashed / magic / enchanted) carries a real
`instance_id` **and** a `category`. Equippables render one row per instance (no
catalog collapse); stackables stay one merged stack. The character/wizard routes
stop passing a separate `inventory_view`; the modals iterate the *same* groups the
panes do. Removes smell #4 and the first-instance bug.

`InventoryRow` gains `category: str = "item"`. `_build_row` accepts the instance
(or its id + category) so the field is populated at the source.

### E. Templates — one macro, one modal, for all three categories

A single `inv_row_actions(row)` macro renders equip / unequip / sell / drop / move /
charge / note for item, enchanted, and magic, driven by `row.category` and the
row's gating flags (`equippable`, `class_allowed`, `can_off_hand`,
`charges_remaining`, `cost_gp`). It posts to the unified `/inventory/*` family with
hidden `category` + `instance_id`. The inline magic block in `sheet.html:996–1091`
and its container-stowed duplicate collapse into this macro; `item_modal` becomes
the single modal for all three categories. `act_move` for items switches its hidden
field from `item_id` to `instance_id`.

### F. Tests

- **Dispatcher unit tests** — each category × each action, including the bad-category
  error and the owner indirection (PC vs retainer vs animal).
- **`shop.sell_instance`** — carried + stashed × drop/sell/refund; multi-instance
  (two daggers: selling one leaves the other).
- **Contract test (closes the gap)** — render the inventory box for a character with
  equipped + carried + stashed + enchanted + magic items, parse every action
  `<form>`, and assert its `action` target and hidden field names match the live
  route's expected parameters. This is the test that would have caught the original
  break.
- **Existing suites kept green**, repointed to the new endpoints:
  `test_sheet_inventory_box`, `test_enchanted_equip_routes`,
  `test_inventory_move_routes`, `test_equip_core`, `test_equipment`,
  `test_magic_items`, `test_retainer_routes`, `test_wizard`.

## Sequencing

1. `inventory_actions` dispatcher + `shop.sell_instance` — engine only, fully
   unit-tested (TDD).
2. Add `category` to `InventoryRow`; make `build_inventory_groups` the single source
   with per-instance rows.
3. New `/inventory/*` route family (sheet + wizard); retainer/animal handlers call
   the dispatcher.
4. Unified `inv_row_actions` macro + `item_modal`; collapse the magic blocks; switch
   `act_move` to `instance_id`.
5. Contract test; repoint existing tests; delete dead routes, macros, and
   `shop.sell_item`/`sell_from_stash`.

## Non-goals

- No change to the visual design of the inventory box (same panes, same modals).
- No data migrations (app isn't deployed).
- Containers, coins, gems, jewellery, ammo, and spell-sources keep their existing
  dedicated routes/macros — they aren't part of the equip/sell/charge triad. (Move
  already unifies them via `move_thing`.)
```
