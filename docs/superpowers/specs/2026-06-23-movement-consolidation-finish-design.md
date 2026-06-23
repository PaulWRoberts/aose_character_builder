# Finish the Movement Consolidation — Design

**Date:** 2026-06-23
**Status:** Approved (design)
**Branch:** _TBD at plan time_ (suggest `feat/movement-consolidation-finish`)
**Follows:** `2026-06-23-unified-item-movement-and-shared-controls-design.md`

## Problem

The unified-item-movement landing established one move front door
(`storage.move_thing`) and one destination list (`move_targets`), but it drew the
line too conservatively and left bugs and divergent paths behind:

1. **Spell books / scrolls cannot move or drop.** `SpellSource` is the only owned
   thing with no `location` field; the prior spec explicitly scoped spell-source
   relocation out. Their modal offers cast/copy/read but no Move and no Drop.
2. **Magic / enchanted items say "Remove", not "Drop".** Those modals hand-roll
   their own form posting to `equipment/remove-magic` instead of routing through the
   shared `act_*` action macros that loose items use. The route already accepts a
   `mode` (drop/sell/refund), so the divergence is purely template-side — the "not
   truly consolidated" smell.
3. **A wielded weapon renders twice in Equipped.** `_equipped` emits an
   `EquippedRow` for *every* slot including `main_hand`/`off_hand`; those weapons
   also appear as attack profiles, so a wielded weapon shows once with stats and
   once as a worn row labelled "Main Hand".
4. **Three redundant movement families.** `move_thing` (no capacity checks),
   shop's `stash`/`unstash`/`stow`/`take_out`/`stash_container`/`unstash_container`,
   and companions' `load_onto_animal`/`unload_from_animal`/`load_onto_vehicle`/
   `unload_from_vehicle` all move things between the same buckets. Worse, the latter
   two are the *only* places capacity is enforced (`ContainerFull`,
   `AnimalOverloaded`, `VehicleOverloaded`), so the canonical `move_thing` path
   silently bypasses every capacity limit.
5. **Scrolls are castable from anywhere.** A scroll's spells surface into the
   holder's castable spell list regardless of where the scroll sits — stash, a
   container, a mule, a retainer. You should only cast/decipher/copy from a
   document carried on the player character's person.

## North-star invariant

**One front door for all movement; capacity enforced once, centrally; a document
is only usable when carried on the PC.** Every owned thing — loose items,
containers, coins, gems, jewellery, magic, enchanted, ammo, *and spell sources* —
moves through `move_thing`, which validates destination capacity in one place. The
shop/companions movement helpers and their routes are deleted. Stash is just
another top-level inventory; loading a mule or stowing in a sack is just a move.

## Decisions (from brainstorming)

1. **Scope:** all five items in one pass.
2. **Instance removal controls:** magic / enchanted / spell-source modals route
   through the shared action macros — **Drop** (no refund) plus **Sell ▾**
   (half / refund) **when the catalog item has a `cost_gp`**. Spell sources are
   unpriced → **Drop** only.
3. **Capacity enforcement on all moves:**
   - **container / animal / vehicle** carry **hard caps**
     (`capacity_cn` / `max_load_encumbered_cn` / `cargo_capacity_cn`); a move that
     would exceed the cap is rejected.
   - **carried (PC) / retainer** have **no hard cap** — they *suffer the
     encumbrance rules* (a movement-rate penalty via the existing engine), never a
     block.
   - **stashed** is weightless / uncapped (off-person abstraction).
4. **Spellbook / scroll weights preserved** (scroll 1 cn, spellbook untracked) —
   re-weighting documents is a rules question outside this consolidation.
5. **Document use requires carried-on-PC.** Cast, decipher (Read Magic), and copy
   are all gated on the source's `location.kind == "carried"`. (Same physical-access
   principle for all three, not casting alone.)

## Non-goals

- No flat-pointer rewrite of catalog-item storage (loose items stay identity-less
  strings in location-resolved lists; duplicates count by multiplicity).
- No nesting (a container still cannot go inside another container).
- No migrations — `location` defaults to carried, so old saves load unchanged.
- No re-weighting of spell documents.
- The pure capacity helpers (`animal_capacity`, `animal_load_cn`,
  `vehicle_capacity`, `vehicle_load_cn`) are **kept** and reused; only the
  load/unload *mutators* are deleted.

## Architecture

### Models (`aose/models/character.py`)

- Add `location: StorageLocation = carried` to `SpellSource`. No validator needed
  beyond the default; equipped/owned semantics unchanged.

### Engine — movement front door (`aose/engine/storage.py`)

- **`move_thing`** gains a `source` category → new **`move_spell_source(spec,
  instance_id, dest)`**: same-world re-point of `.location`, or list-to-list into
  `retainer.spec.spell_sources` for a retainer dest (mirrors `move_instance`).
- **`move_item`** gains the auto-unequip cleanup `stash` had: when the moved copy
  was the last carried copy of an item occupying a `spec.equipped` slot, free that
  slot (and `unload_if_loaded`). The unified path must not leave a dangling
  equipped reference.
- **Central capacity gate.** New `_check_capacity(spec, dest, added_cn, data)`
  called by every `move_*` (item, container, coin, gem, jewellery, magic,
  enchanted, ammo, source) **before** committing the mutation:
  - `dest.kind in {carried, stashed, retainer}` → return (no hard cap).
  - `dest.kind == "container"` → cap = catalog `capacity_cn` (None = unlimited).
  - `dest.kind == "animal"` → cap = `animal_capacity` (`max_load_encumbered_cn`;
    None ⇒ not a beast of burden ⇒ carries nothing ⇒ any load rejected).
  - `dest.kind == "vehicle"` → cap = `vehicle_capacity`.
  - Reject with `StorageError` when `location_load_cn(dest) + added_cn > cap`.
  - `added_cn` is the weight the *specific* move adds, count-aware (a 50-coin move
    adds 50 cn; a gem stack adds `count` cn; jewellery 10 cn; a catalog item its
    `weight_cn`; an enchanted/magic item its resolved weight).
- **`location_load_cn(spec, loc, data)`** — single definition of "current load at a
  location", summing every substrate present there: loose contents + coins + gems +
  jewellery + magic + enchanted + ammo + spell sources, using each substrate's
  encumbrance weight. This is the one helper both the capacity gate and
  `encumbrance.py`'s container-stowed loop call.

### Encumbrance (`aose/engine/encumbrance.py`)

- Refactor the existing container-stowed weight summation to call the shared
  `location_load_cn` rather than re-deriving per-substrate weights inline — one
  definition, two callers.
- Scroll spell sources already contribute 1 cn when carried; preserve that.
  Confirm stashed / container / carrier scrolls are **not** double-counted (they
  now have a real location).

### Delete the redundant movement families

- **shop.py:** delete `stash`, `unstash`, `stow`, `take_out`, `stash_container`,
  `unstash_container`, `_set_container_state`.
- **companions.py:** delete `load_onto_animal`, `unload_from_animal`,
  `load_onto_vehicle`, `unload_from_vehicle`. **Keep** `animal_capacity`,
  `animal_load_cn`, `vehicle_capacity`, `vehicle_load_cn` (reused by the gate and
  the sheet display).
- **Routes (PC, `routes.py`):** delete `/equipment/stash`, `/equipment/unstash`,
  `/equipment/stow`, `/equipment/take-out`, `/equipment/stash-container`,
  `/equipment/unstash-container`, `/animal/{id}/load`, `/animal/{id}/unload`,
  `/vehicle/{id}/load`, `/vehicle/{id}/unload`.
- **Routes (wizard, `wizard.py`):** delete the matching `stow`/`take-out`/
  `stash-container`/`unstash-container` twins (exact set enumerated by grep at plan
  time). A missed call site 404s, so the grep must be exhaustive
  (`stash|unstash|stow|take-out|/load|/unload|load_onto|unload_from`).
- The Sell / Convert / Adjust / charge / ammo-load-into-weapon routes are **not**
  movement routes and are untouched. (Ammo *load/unload* here means
  loading a launcher, not moving a stack — distinct from carrier load.)

### Spell-source casting gate (`aose/engine/spell_sources.py`)

- `scroll_cast_block_reason` returns a reason (e.g. `"not on your person"`) as its
  **first** check when `source.location.kind != "carried"`. This propagates to
  `can_cast_scroll` (used by the cast route and the view's `can_cast` flag) for
  free.
- `ready_read_magic_slot`/`read_scroll` (decipher) and `copyable_spell_ids`/
  `copy_spell` (copy) gain the same carried-on-PC guard so a non-carried document
  can be neither deciphered nor copied from.

### View (`aose/sheet/view.py`, `shop.py`)

- **Double-render fix:** `_equipped` skips weapon slots (`main_hand`, `off_hand`);
  `equipped_worn` becomes armour / shield / barding only. Weapons render solely as
  attack profiles.
- **Spell sources bucketed by location:** `build_inventory_groups` filters
  `spec.spell_sources` by `.location` into the owning group (today hard-wired to
  PC carried); `ContainerView` gains `stowed_spell_sources`, gathered by the
  container's own location like the other stowed sub-lists.
- `spell_sources_view` continues to drive cast/copy/read flags; with the engine
  gate above, a non-carried scroll simply reports `can_cast=False` (and read/copy
  false).

### Templates

- **Shared action macros for instances.** The magic / enchanted / spell-source
  modals replace their bespoke "Remove" forms with `act_move` + `act_*` removal
  (Drop, plus Sell ▾ where `cost_gp` exists). The `remove-magic` /
  `remove-enchanted` routes already accept `mode`. Spell-source **Drop reuses the
  existing `spell-sources/remove` route** — `remove_spell_source` already deletes
  the document with no refund, which *is* a drop; no new route and no Sell
  (documents are unpriced).
- **Stash / Unstash / Take-out / Stow / Load buttons → `act_move`.** In
  `_inv_row_actions.html` and the carrier/container modals, these convenience
  buttons become Move-to-destination forms posting to `/inventory/move`:
  - "Stash" → move to `stashed`; "Unstash" → move to `carried`.
  - "Take out" → move to the container owner's location.
  - "Stow" / "Load" → move to the chosen container / animal / vehicle.
  They keep their familiar labels but share the one route + capacity gate.
- Spell-source modal ([sheet.html]) gains **Move ▾** + **Drop**; container view
  renders `stowed_spell_sources`.
- Wizard equipment step reaches the same controls (move_targets already in wizard
  context from the prior pass) — verify parity.

## Data flow

```
spec ─► build_inventory_groups(spec, data)
          per TopLevelGroup bucketed by StorageLocation:
            loose · coins · gems · jewellery · magic · enchanted · ammo
            · spell_sources · containers
          per ContainerView (location = container instance):
            stowed * (incl. stowed_spell_sources)
                    ▼
       sheet.html / _inv_pane.html
          every row → modal → _actions.html macros (uniform controls)
          every Move/Stash/Take-out/Load → POST /inventory/move
                    ▼
       storage.move_thing(spec, category, id, dest, count=…, src=…, data=…)
          → _check_capacity(spec, dest, added_cn, data)   ← one gate
          → move_<category>(…)                            ← one mutation
```

## Phasing

1. **Model + engine core:** `location` on `SpellSource`; `move_spell_source`;
   `move_item` auto-unequip; `location_load_cn`; `_check_capacity`; wire the gate
   into every `move_*`.
2. **Casting gate:** carried-on-PC guard in `scroll_cast_block_reason`, decipher,
   and copy.
3. **Encumbrance refactor:** container-stowed loop calls `location_load_cn`;
   verify no double-count.
4. **View:** `_equipped` weapon-slot fix; spell sources bucketed by location;
   `ContainerView.stowed_spell_sources`.
5. **Delete redundant families:** shop + companions mutators and their PC + wizard
   routes (grep-enumerated); migrate templates' Stash/Take-out/Load buttons onto
   `act_move`.
6. **Instance removal onto macros:** magic / enchanted / spell-source modals →
   Drop + Sell ▾ (where priced); spell-source Move ▾ + Drop.
7. **Docs + verification:** `ARCHITECTURE.md` (storage / encumbrance / movement /
   spell sources, in place); `CHANGELOG.md` row; print parity; wizard path.

## Testing

- **Engine — movement:** `move_thing("source", …)` to stashed / container /
  retainer; spell source on a mule renders under the mule; equipped weapon moved
  to stash auto-unequips and frees its slot.
- **Engine — capacity:** moving any category into a full container / animal /
  vehicle is rejected (`StorageError`); a partial coin/gem/ammo move that fits is
  accepted and the one that overflows is rejected; non-beast animals (cap None)
  reject all load; a move onto a retainer is **never** blocked; `location_load_cn`
  matches the encumbrance container loop for the same location.
- **Engine — casting gate:** a scroll not carried → `can_cast_scroll` False and the
  cast route 400s; a stashed/mule spellbook cannot be deciphered or copied from; a
  carried scroll behaves exactly as today.
- **View:** Equipped section shows a wielded weapon **once** (regression for the
  double-render bug); instance modals expose Move + Drop/Sell.
- **Web:** deleted routes 404; Stash / Unstash / Take-out / Stow / Load buttons
  post to `/inventory/move`; wizard parity; magic/enchanted/spell-source modals use
  the shared macros (no bespoke Remove form).
- **Regression:** full suite green; PC attack/equipped display otherwise unchanged;
  settings page renders no "pending" badge; print sheet lists all groups.

## Risks / implementation notes

- **Exhaustive route deletion.** Folding stash/stow/load into `/inventory/move`
  touches PC + wizard templates and `tests/`. Grep all of
  `stash|unstash|stow|take-out|/load|/unload|load_onto|unload_from` before deleting;
  a missed call site 404s. (Exclude `ammo/load`/`ammo/unload` — those load a
  launcher, not a carrier.)
- **One definition of load.** `location_load_cn` must agree with the encumbrance
  container loop, or capacity and displayed weight diverge. Refactor encumbrance to
  call it, don't duplicate.
- **Capacity weight per category.** `added_cn` must use each substrate's
  encumbrance weight (coins/gems 1, jewellery 10, items by `weight_cn`, enchanted
  by resolved weight) and be count-aware for stacking moves.
- **Carried-only document use.** The gate lives in the engine functions, not the
  templates, so the cast route, the view flags, decipher, and copy all inherit it
  from one place.
- **Auto-unequip on loose move.** Clearing the `spec.equipped` slot must only fire
  when the *last* carried copy leaves (duplicates: an equipped copy can remain).
