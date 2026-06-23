# Inventory Box as Interaction Hub; Drawer as Acquisition-Only — Design

**Date:** 2026-06-22
**Status:** Approved (design)
**Branch:** _(tbd at implementation)_

## Problem

Owned-item interaction is split awkwardly across two surfaces. The live-sheet
**inventory box** (`_inv_pane.html`) shows items, containers, ammo, spell
sources, and *display-only* coins/treasure, but most management still happens in
the **Manage drawer** (`_equipment_ui.html`): equip, sell, drop, move, charges,
cast/copy, treasure operations, and coin convert/adjust. The drawer also mixes
acquisition (shop, add-enchanted, add-source, add-coins) with management.

Worse, the substrate is inconsistent. PC/animal/vehicle containers live in one
`spec.containers` list keyed by `StorageLocation`; **retainers** nest a full
`CharacterSpec` and store gear in `retainer.spec.inventory`, and the retainer
pane renders **no containers at all**. Container row controls diverge between the
two drawer render paths (PC containers get stash/sell/drop but no move; carrier
containers get move only). And a granted **container is born as a loose string**:
`quick_equipment.apply_kit` writes `"backpack"` into `inventory`, and there is no
action anywhere to promote a loose `Container` into a usable `ContainerInstance`
— so a companion's backpack can never be used as a container, even after transfer
to the PC. (This last point is the user-reported bug that motivated the work; it
is absorbed by this redesign.)

## Goals

- The **inventory box** is the single place to *view and act on* everything a
  character owns, across **every** top-level inventory (PC, Stashed, each animal,
  vehicle, retainer).
- The **Manage drawer** becomes **acquisition-only**.
- The box and drawer are built from **shared macros + view builders**
  parameterized by an owner **capability descriptor**, so each inventory reuses
  one code path and diverges only by capability ("dynamic divergence").
- **Containers work on every owner** through one set of helpers/views, a loose
  `Container` is **promotable** to a real container, and `apply_kit` no longer
  produces loose containers.
- The **wizard** equipment step reuses the inventory box for its owned-item view.
- After stripping the drawer, **no dead code paths** remain.

## Non-goals

- **No flat-pointer rewrite of retainer storage.** Retainers keep self-contained
  storage (`retainer.spec.*`); unification is at the helper/view level.
- **No new `StorageLocation` kind.** The vocabulary stays carried / stashed /
  animal / vehicle / container / retainer as today.
- **Magic items, enchanted gear, spell sources, and ammunition stay PC-bucket.**
  They render with rich modals but are **not** made carrier-movable in this pass
  (would require making those models `StorageLocation`-aware — a separate change).
- The dedicated print route (`sheet_print.html`) keeps its own rendering.
- No migrations (app is not deployed).

## Decisions (from brainstorming)

1. **Retainer storage:** self-contained in `retainer.spec.containers` /
   `retainer.spec.inventory`; PC/animals/vehicles keep `spec.containers` +
   `StorageLocation`. Unify via shared helpers, not one flat list.
2. **Owned-item management → box modals.** All management (equip, charges, notes,
   remove, cast/copy/read, treasure ops, coin convert/adjust) lives in per-item
   box modals. The drawer keeps only add/grant/scribe forms.
3. **Equip gating:** PC + retainers wield (inline + modal); animals show barding
   as an Equipped AC row only (the card's barding select stays the equip
   control); vehicles and Stashed never equip.
4. **Treasure split:** acquisition (add coins/gems/jewellery) in the drawer's
   **Treasure** tab; all management of existing stacks in box modals.
5. **Wizard** equipment step renders the inventory box (Carried + Stashed only —
   no carriers/retainers exist mid-creation) above the shop.
6. **Box structure:** every pane has at most three subsections —
   **Equipped · Coins · Carried** — where the third bucket is the catch-all for
   everything not equipped and not a coin, and is renamed **Stowed** when the
   inventory has no equipping (Stashed, vehicles). The PC's top-level pane is
   titled **"{Character name}"**.
7. **Custom items** (`other_possessions`) render in the box's Carried bucket with
   a remove action; their add form lives in the drawer.

## Architecture

### Owner capability descriptor

`build_inventory_groups` computes a small capability object per `TopLevelGroup`
and the templates gate on it (no per-owner template branches):

| owner    | `has_equipped` | `can_wield` | `can_stash` | bucket label | weight-bearing |
|----------|:---:|:---:|:---:|---|:---:|
| PC carried | ✓ | ✓ | ✓ | Carried | ✓ |
| Stashed    | ✗ | ✗ | (unstash) | **Stowed** | ✗ |
| animal     | ✓ (barding) | ✗ | — | Carried | own cap |
| vehicle    | ✗ | ✗ | — | **Stowed** | own cap |
| retainer   | ✓ | ✓ (no class filter) | — | Carried | n/a |

- `has_equipped` drives both the **Equipped** subsection and the Carried/Stowed
  label (Stowed iff `not has_equipped`).
- `can_wield` drives the inline + modal **Equip** affordance on loose rows. PC
  equip is class/slot-filtered (existing `class_allowed` / `can_off_hand` /
  `off_hand_blocked`); retainer equip omits class filtering (NPC, DM-controlled).
- Animals: `has_equipped` true (barding AC row) but `can_wield` false — barding is
  set via the existing animal card select, surfaced here as a read-only AC row.

### Box structure (`_inv_pane.html`, `sheet.html`)

One `<details class="inv-pane">` per top-level group. Pane label = group label,
with the PC's "Carried" group titled `{{ sheet.name }}`. Pane body renders, each
only when non-empty:

1. **Equipped** — rich rows (attacks: to-hit/damage/range/tags; worn armour/shield
   as AC rows; worn magic). Present iff `has_equipped`. PC reuses existing data;
   retainers via `attack_profiles(retainer.spec, data)`; animals = barding AC row.
2. **Coins** — its own subsection; each stack is a clickable row → coin modal.
3. **Carried / Stowed** — the catch-all bucket holding **everything else**: loose
   catalog items, containers (nested collapsibles + contents), magic items,
   enchanted gear, spell books/scrolls, ammunition, gems, jewellery. Every row is
   clickable → its per-item modal; equippable rows additionally show an inline
   Equip/Off-hand button when `can_wield`.

The legacy three-column box (`inventory_view` driven) is fully replaced by this
group-driven render for the live sheet.

### Per-item modals — relocated action sets

Each type's modal hosts **the same actions it has in the drawer today**, moved
into the box and gated by the capability descriptor. A shared `item_modal`-family
macro keys each modal by `(owner_kind, owner_id, row_id)` (container variant by
`(container_instance, row_id)`) to keep ids unique across inventories.

| type | actions in modal |
|---|---|
| catalog item | Move-to ▾ · Sell ▾ · Drop · Equip/Unequip/Off-hand/Unstash (gated) |
| container | Move-to ▾ · Sell ▾ (empty only) · Drop · stow/take-out of contents |
| coin stack | Convert ▾ · Move ▾ · Adjust (signed) |
| gem | Sell one · Sell all · Move ▾ · ±1 · Remove |
| jewellery | Mark damaged/intact · Sell · Move ▾ · Remove |
| magic item | Equip/Unequip · Use charge · Reset · Note · Remove |
| enchanted | Equip/Unequip · Use charge · Reset · Note · Remove |
| spell source | Read (decipher) · Cast · Copy-to-book · Remove |
| ammunition | ±adjust · Load/Unload · Remove |

Move-to applies only to location-aware types (catalog items, containers, coins,
gems, jewellery). Magic/enchanted/sources/ammo are PC-bucket: their modals carry
their type-specific actions but no Move-to (scope line above).

### Engine — owner-agnostic helpers (`shop.py`, `storage.py`, `quick_equipment.py`)

- **Owner resolver:** a helper maps an owner `(kind, id)` to the relevant
  `(containers_list, loose_list)` — `spec.*` for PC/animal/vehicle (containers via
  `StorageLocation`), `retainer.spec.*` for a retainer. Container helpers
  (`move_container`, `sell_container`/drop/refund, `stow`, `take_out`,
  `new_container_instance`) are refactored to take resolved lists rather than
  reaching into `spec.containers` directly.
- **`use_as_container(owner, item_id, data)`** — new: removes one loose copy of a
  `Container` item from the owner's loose list and appends a fresh
  `ContainerInstance` located at that owner. Rejects non-`Container` items and
  items currently inside a container (no nesting).
- **PC↔retainer container moves** are a list-to-list move (pop from one
  `containers` list, append to the other, relocate to the destination owner's
  carried bucket); animal/vehicle moves remain a `location` pointer change.
- **Grant-path hardening:** `apply_kit` routes any `Container` id in the rolled
  kit into the spec's `containers` (carried `ContainerInstance`) instead of
  leaving it loose — covers `_BASIC` and the random adventuring-gear table.
- **Sell/refund credit** always lands in the PC's **carried** coins.

### Retainer containers (view)

`_carrier_container_views` is generalized to build `ContainerView`s from any
containers list. The retainer group in `build_inventory_groups` gains
`containers` built from `retainer.spec.containers` (carried/stashed within the
retainer's own world), rendered by the same nested-container template.

### Drawer after the change (`_equipment_ui.html`)

Tabs, in order: **Shop** (first) · **Enchant** (only the add-enchanted / GM-grant
form) · **Scribe** (only the add spell-book/scroll form) · **Treasure** (add
coins / gems / jewellery — absorbs the old carried "add coins"). **Deleted:** the
Carried tab and `inv_table` for owned items, `container_table`, `inv_group_panel`,
the coin/treasure management tables, the magic/enchanted owned tables, the
document management table, and the ammo section. Acquisition deposits to
**carried** only. Custom-item add form moves here.

### Wizard (`wizard/equipment.html`, `wizard.py`)

The equipment step renders the inventory box for the draft's in-progress spec
(Carried + Stashed groups only) above the shop, reusing `_inv_pane.html`, the
shared modals, and the capability descriptor. It wires to existing wizard
equipment routes (equip/unequip/stash/unstash/stow/take-out/move/promote),
adding only those the box exposes that do not yet exist (e.g. `use-as-container`,
generalized move-item/move-container if absent in the wizard).

### Cleanup

After stripping the drawer, sweep for dead code: legacy `inventory_view` and its
view models (if `inventory_groups` fully replaces it for both sheet and wizard),
unused `_equipment_ui.html` macros, and any context fields no longer passed.
Routes still used by the box (equip, sell, move, charges, cast/copy, treasure
ops, coin convert/adjust) are retained. `sheet_print.html` is untouched.

## Data flow

```
spec ─► build_sheet(spec, data)
          ├─ format_attack_rows(...)        ◄ shared: PC + retainers
          ├─ build_inventory_groups(spec, data)
          │     each TopLevelGroup carries:
          │       capability descriptor (has_equipped, can_wield, …)
          │       Equipped (rich) · Coins · Carried/Stowed bucket
          │         (loose · containers · magic · enchanted · sources ·
          │          ammo · gems · jewellery), each row capability-tagged
          └─ CharacterSheet.inventory_groups
                    ▼
          sheet.html ─► <details> pane per group
                         Equipped / Coins / Carried|Stowed
                         every row clickable → per-(owner,row) modal
                         equippable rows → inline Equip when can_wield
```

## Phasing (one cohesive spec → phased plan)

1. **Engine + view foundation:** owner resolver, `use_as_container`, `apply_kit`
   hardening, retainer containers populated + generalized
   `_carrier_container_views`, capability descriptor, `TopLevelGroup` extended to
   carry magic/enchanted/sources/ammo/treasure per applicable owner.
2. **Box becomes the interaction hub:** shared row/modal macros gated by the
   descriptor; three-subsection layout (Equipped · Coins · Carried/Stowed); PC
   pane titled by name; inline equip; all type-specific actions relocated into box
   modals; container row move/sell/drop parity.
3. **Drawer → acquisition-only:** tabs reorder (Shop first) + rename
   (Magic→Enchant, Documents→Scribe); Treasure tab absorbs add-coins; delete all
   owned-item UI; move custom-item add form in.
4. **Wizard** reuses the box for Carried/Stashed; wire any missing routes.
5. **Dead-code sweep + docs + verification:** remove orphaned code/view models;
   update `ARCHITECTURE.md`, `CHANGELOG.md`, and `CLAUDE.md` (if orientation
   shifts); verify print parity and the wizard path.

## Testing

- **Engine:** `use_as_container` happy path + rejects (non-container, in-container,
  missing); `apply_kit` yields a `ContainerInstance`, not a loose backpack;
  owner-resolved container move/sell/drop including a retainer; PC↔retainer
  container list-to-list move; sell credit lands in carried coins.
- **View:** every owner exposes correctly-shaped, capability-tagged rows; retainer
  group renders its container; the Carried/Stowed label flips with `has_equipped`;
  magic/treasure/coin rows carry their per-item action data; PC pane label is the
  character name.
- **Web:** box modal exposes each type's action set; inline equip works for
  PC/retainer and is absent for animals/vehicles/stashed; drawer renders only the
  four acquisition tabs and no owned items; wizard equipment step shows the box
  with Carried/Stashed.
- **Regression:** settings page renders no "pending" badge (existing guard); PC
  attack-row output unchanged (snapshot before/after the shared formatter extract).

## Risks / open implementation notes

- **Modal volume.** One modal per (owner, row). Catalog items × owners multiply
  (already true today); PC-bucket types (magic/enchanted/sources/coins/treasure)
  are single-owner, so they do not explode. Keep pre-rendered per existing overlay
  pattern; a single JS-populated modal is a possible future optimization, not in
  scope.
- **Shared attack formatter.** Extracting `format_attack_rows` from the PC
  assembly must not change the PC's existing Combat/equipped display — snapshot
  before/after.
- **Wizard draft spec.** Running `build_inventory_groups` on the in-progress draft
  must tolerate a partial spec (no race/class edge cases at the equipment step).
- **Capability flags vs. animals.** `has_equipped` true but `can_wield` false for
  animals is intentional; tests must pin the Carried label and barding-only equip.
- **Dead-code scope.** Confirm `inventory_view` has no remaining consumer (sheet
  and wizard both on `inventory_groups`) before deletion; `sheet_print.html` may
  still use its own path and is out of scope.
