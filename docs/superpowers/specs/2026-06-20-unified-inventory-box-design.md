# Unified Expandable Inventory Box — Design

**Date:** 2026-06-20
**Status:** Approved (design)
**Branch:** _(tbd at implementation)_

## Problem

The live character sheet's inventory box is a fixed three-column grid
(Equipped / Carried / Stashed). It only ever shows the PC's own person buckets.
Everything else that holds items — animals, vehicles, retainers, containers —
either appears elsewhere (the separate "Companions & Vehicles" card section) or
only inside the Manage drawer. Coins are buried as tiny line items and absent
from carrier inventories. The user wants the box to show **every** top-level
inventory, each expandable, with an equipped sub-section where appropriate,
containers nested inside their owning inventory, and coins visible anywhere.

The underlying data already exists: `build_inventory_groups(spec, data)` in
`aose/sheet/view.py` produces a `TopLevelGroup` for Carried, Stashed, every
animal, every vehicle, and every retainer, each already carrying its equipped /
loose / coins / treasure / container views. The print sheet (`sheet_print.html`)
and the Manage drawer (`_equipment_ui.html`) already render these groups. The
**live sheet box is the only holdout**, still rendering the legacy three-column
view from `inventory_view`.

So this is primarily a **template + CSS redesign of the live inventory box**,
with three bounded supporting changes in the view layer and shared partials.

## Goals

- Live inventory box renders **all** top-level inventories as a vertical stack of
  collapsible panes: Carried, Stashed, **Other Possessions** (new), each animal,
  each vehicle, each retainer.
- Each pane has an **equipped** sub-section where appropriate (PC, retainers,
  animals — **not** vehicles, **not** Stashed, **not** Other Possessions), and
  equipped rows are **rich** (weapon to-hit/damage/range; worn armour as an AC
  row; worn magic).
- **Containers** render inside their owning inventory, their contents
  individually collapsible.
- **Coins** show inside any inventory that holds them.
- Free-text **custom items** move out of Carried into their own "Other
  Possessions" inventory, whose add-item form lives inside the collapsible.
- The box's **shape suits the data**: the tall-and-narrow accordion moves to a
  layout column; Spells move to full width.

## Non-goals

- No change to the storage data model or the movement vocabulary
  (`aose/engine/storage.py`), routes, or `StorageLocation` shape.
- No migrations (per project convention — app is not deployed).
- The dedicated print route (`sheet_print.html`) keeps its own group rendering;
  we do not unify print and live templates here.

## Decisions (from brainstorming)

1. **Equipped is rich for every group.** Not a uniform plain list, and not
   PC-only. PC reuses existing attack/AC/magic display; retainers get combat
   rows computed from their own spec; animals show barding as an AC row.
2. **Inventory box absorbs all storage.** The Companions & Vehicles cards keep
   creature stats and management (HP, morale, loyalty, role, promote, dismiss)
   but **lose** their load/cargo/inventory `<details>` — storage lives only in
   the inventory box.
3. **Default expand state:** Carried open; Stashed, Other Possessions, and all
   carriers/retainers collapsed. Containers collapsed by default.
4. **Clickable everywhere:** every item row in every inventory opens a per-item
   modal with move / take-out actions (not display-only).
5. **Coins shown in any inventory.**
6. **New "Other Possessions" top-level inventory** holds the free-text custom
   items; its add-item text box lives inside the collapsible.
7. **Layout:** Inventory accordion becomes layout **column 3**; Spells / Mental
   Powers / Innate move to a **full-width section below the grid**.

## Architecture

### Live-sheet layout (`sheet.html` + `sheet.css`)

The page grid `.layout` (`grid-template-columns:300px 1fr 1fr`) keeps its three
columns:

- **Col 1:** Combat (prominent) + Abilities & Saves — unchanged.
- **Col 2:** Class & Race Features + Languages/Notes/Skills — unchanged.
- **Col 3:** now the **Inventory** accordion `.group` — always present (every
  character has inventory; this also fills col 3 for non-casters, which is empty
  today).

Below the grid, in order:

- **Spells / Mental Powers / Innate** — relocated here as a **full-width**
  `.group.full` region, gated to casters (`{% if sheet.spellbook or
  sheet.mental_powers or sheet.innate_abilities %}`). The existing per-block
  `<section class="group">` blocks are preserved; they sit side-by-side within a
  full-width flex/grid wrapper so a multiclass caster reads across, not down.
- **Companions & Vehicles** — unchanged position (minus storage details, §
  Companions).
- **Footer** — unchanged.

The relocation is a move of existing markup, not a rewrite of the spell blocks.
Their overlays/drawers (`drawer-spells`, `drawer-powers`, per-spell modals) are
unaffected — they live in the overlay block at the bottom of `sheet.html`.

### The inventory box (`sheet.html`)

A single `.group` titled **Inventory** with the existing bar (carried weight /
wealth / Thresholds / Manage actions retained). Its `.gbody.scroll` contains a
vertical stack of **panes**, one per group in a render list:

```
render_list = sheet.inventory_groups + [synthetic Other Possessions group]
```

Each pane is a native **`<details>`** styled as a zine sub-bar:

```html
<details class="inv-pane" {open if group.kind == "carried"}>
  <summary class="inv-pane-head">
    <span class="inv-pane-name">{{ group.label }}</span>
    <span class="tag faint">{{ group.kind }}</span>
    <span class="inv-pane-summary">… count · weight|— · coins/wealth …</span>
  </summary>
  <div class="inv-pane-body">
    … subsections …
  </div>
</details>
```

Subsections render in this order, each only when it has content:

1. **Equipped** (rich; see below) — PC, retainers, animals only.
2. **Items** (loose) — clickable rows → per-item modal.
3. **Containers** — each a **nested `<details class="inv-container">`** (closed),
   header = name + capacity badge, body = contents rows (clickable).
4. **Coins** — labelled sub-block listing denominations + this group's coin total.
5. **Treasure** — gems / jewellery rows (clickable where a modal exists).

**Summary line** is computed in-template from the group's own fields
(loose+equipped+container item counts; carried weight where the group counts
toward encumbrance, `—` otherwise; a short coins note when coins present).

### Rich equipped data (`aose/sheet/view.py`, `aose/engine/shop.py`)

`TopLevelGroup` currently exposes `equipped: list[InventoryRow]`. Extend it so
each group can render the **same rich equipped block** the PC has today:

- `equipped_attacks: list[...]` — weapon rows with `to_hit_ascending`, `damage`,
  `range_ft`, and the tag set (magic / specialised / non-prof / ammo / hand).
- `equipped_worn: list[...]` — worn armour/shield rows (name + slot/AC effect).
- `equipped_magic: list[...]` — worn magic-item rows (name + modifier summary).

Population in `build_inventory_groups`:

- **Carried (PC):** reuse the already-built `sheet.attacks`, `sheet.equipped`,
  and equipped `sheet.magic_items`. To avoid recomputation, `build_sheet` passes
  these (or the shared formatters) into `build_inventory_groups`, or
  `build_inventory_groups` calls the same formatter helpers. A shared helper
  `format_attack_rows(profiles, …)` is factored out of the existing PC attack
  assembly so it can serve both PC and retainers.
- **Retainer:** run `attack_profiles(retainer.spec, data)` (pure; already takes
  an arbitrary spec) → `format_attack_rows(...)`; worn armour/shield from
  `retainer.spec.equipped`. Retainer's own retainers are always empty, so no
  recursion.
- **Animal:** the barding (`animal.armor_id`) becomes one `equipped_worn` AC row
  (its AC contribution), replacing the plain `_build_row` barding entry.
- **Vehicle / Stashed:** none (`has_equipped` stays false).

`has_equipped` is recomputed from "any of the three rich lists non-empty".

### Other Possessions group

`build_inventory_groups` (or `build_sheet`) appends a synthetic `TopLevelGroup`:

```
TopLevelGroup(kind="other", id=None, label="Other Possessions",
              loose=<rows built from spec.other_possessions>, …)
```

Custom items are free text, not catalog ids — they need a lightweight row shape
(name only; index for removal) distinct from `InventoryRow`. Render them with an
`index`-based remove form (the existing `/possessions/remove` route) and the
add-item form (`/possessions/add`) **inside** this pane's body. Remove the
custom-item add box and the `other_possessions` loop from the Carried view in
`sheet.html`. `other_possessions` no longer appears in Carried.

> Note: `spec.other_possessions` items currently route to "carried" only and are
> not `StorageLocation`-aware. They are not movable between inventories (they are
> not catalog items); their pane is items + add/remove only — no move control.

### Interaction & modals (`_inv_row_actions.html`, `_move_dest.html`, `sheet.html`)

- **Generalize the move form.** `inv_row_actions` today emits a move form only
  for `state in ("carried","stashed")` with an empty `src_id`. Generalize to any
  source: accept `src_kind` + `src_id` and always offer `move_dest_control`. The
  per-item modal for a row in an animal/vehicle/retainer/container passes that
  group's `(kind, id)` (or `container` + instance id) as the source. The
  existing `/inventory/move-item` route already accepts arbitrary
  src/dest kind+id.
- **Per-item modals for every location.** Generalize the `item_modal` macro so
  its `id_prefix` encodes the location
  (`modal-item-{group.kind}-{group.id|''}-{row.id}`, container variant
  `modal-item-container-{instance}-{row.id}`). The overlay block loops over
  every group (and every container) to render one modal per (location, row).
  PC carried/stashed/equipped keep their current behaviour (equip / unequip /
  unstash / ammo-load) — those branches in `inv_row_actions` are unchanged; only
  the move branch widens.
- **Per-container modal for every location.** The existing per-container modal
  (`modal-container-{instance}`) currently offers carried-only stash/unstash.
  Replace those two buttons with a `move_dest_control` (the `/inventory/
  move-container` route already re-homes a container to any non-container
  location), so containers on animals/vehicles can be relocated from the live
  sheet too.
- **Equipped rows** open a read-only detail modal (item card); equip management
  for non-PC stays in the drawer/companions flow. PC equipped rows keep their
  current `modal-item-equipped-*` behaviour (incl. ammo loading).
- **Coins** are display-only in the box; managed in the Manage drawer (which
  already has full per-stack coin controls for every location).

### Collapse mechanism & print

- Native `<details>`/`<summary>`, matching the companions `companion-load`
  precedent. Panes are independent (more than one open at once is allowed — this
  is not the "one overlay open at a time" rule, which governs overlays).
- `@media print`: force every `<details>` open (`.inv-pane, .inv-container {
  display:block } summary { … }` / `details[open]`-equivalent override) and hide
  toggles, so a browser print of the live sheet shows everything. The existing
  `.print-only` inventory fallback in `sheet.html` is extended to cover all
  groups (or kept as the canonical print list). The dedicated `sheet_print.html`
  route is untouched.

### Companions cards lose storage (`_companions.html`)

Remove these `<details>` blocks and their load/unload/cargo/give/take forms:

- Animal `companion-load` (Load N / capacity + load/unload).
- Vehicle `companion-load` (Cargo + load/unload).
- Retainer `companion-load` (Inventory + give/take).

Keep card stats and the management controls (animal HP & barding select, vehicle
hull & extra-animals, retainer loyalty/role/promote/dismiss). Storage for these
entities now lives solely in the inventory box. (The barding select stays on the
animal card as an equip control; the inventory box shows the *result* as the
animal's equipped AC row.)

### CSS (`aose/web/static/sheet.css`)

New zine rules, above the `LEGACY / SITE-WIDE` banner, tokens only:

- `.inv-pane` / `.inv-pane-head` (summary) — a sub-bar lighter than `.bar`
  (e.g. `--box-sunk` fill, Oswald uppercase label, a disclosure caret rotating
  on `[open]`).
- `.inv-pane-summary` — faint right-aligned meta (count · weight · coins).
- `.inv-pane-body` — padding + the per-subsection sub-heads (reuse `.subhead`).
- `.inv-container` nested disclosure + capacity badge (reuse
  `.capacity-badge`); indented contents.
- Equipped rich rows reuse the existing equipped/attack row styling from the
  current box (`.eqhead`, `.st`, `.tag` variants).
- Full-width spells region wrapper (flex/grid so blocks sit side-by-side).
- `@media print` overrides for forced-open details.
- Remove now-dead `.inv-cols` three-column rules if unused elsewhere.

## Data flow

```
spec ──► build_sheet(spec, data)
            │
            ├─ format_attack_rows(...)  ◄── shared by PC + retainers
            │
            ├─ build_inventory_groups(spec, data)
            │     ├─ Carried   (rich equipped from PC attacks/armour/magic)
            │     ├─ Stashed
            │     ├─ animals    (rich equipped = barding AC row)
            │     ├─ vehicles   (no equipped)
            │     ├─ retainers  (rich equipped via attack_profiles(retainer.spec))
            │     └─ Other Possessions (synthetic; loose = custom items)
            │
            └─ CharacterSheet.inventory_groups
                      │
                      ▼
            sheet.html  ──►  <details> pane per group
                              equipped / items / containers / coins / treasure
                              every row clickable → per-(location,row) modal
```

## Testing

- **`tests/test_inventory_view.py`** — extend: synthetic Other Possessions group
  present and carries `spec.other_possessions`; retainer group's equipped exposes
  computed attack rows (to-hit/damage); animal group's equipped is the barding AC
  row; coins populate on a carrier group.
- **Web test** (`tests/` route test) — `GET /character/<id>` returns 200 for a
  character with: a retainer holding a weapon (combat row renders), an animal
  with coins and a container (coins visible on a carrier; nested container
  collapsible), and a custom item (appears only in Other Possessions, not in
  Carried). Assert the Carried pane no longer contains the custom-item add box.
- **Companions** — update/repoint any test asserting the removed load/cargo/
  inventory `<details>`; assert stats/management controls remain.
- **`tests/test_wizard.py`** — unchanged expectation: the shared
  `_equipment_ui.html` still renders Carried + Shop only in the wizard (we touch
  `inv_row_actions`' move branch, which is gated on `inv_move_groups is
  defined`; verify the wizard path still passes).
- **Regression** — settings page renders no "pending" badge (existing guard,
  untouched but in the shared partial's blast radius).

## Risks / open implementation notes

- **Modal volume.** "Clickable everywhere" renders one modal per (location, row).
  Mechanical but numerous; ids must be unique per location to avoid collisions
  (a same item id can sit in several inventories).
- **Shared attack formatter.** Factoring `format_attack_rows` out of the current
  PC assembly must not change the PC's existing attack display (Combat block and
  the equipped weapon rows). Snapshot/period the PC attack rows before/after.
- **Other Possessions row shape.** Custom items are not catalog items; keep their
  row minimal (name + index) and do not give them move controls.
- **Print parity.** Verify a browser "Print" of the live sheet shows all panes
  expanded (forced-open details) and the dedicated PDF route is unaffected.
```
