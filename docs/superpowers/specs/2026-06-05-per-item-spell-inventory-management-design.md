# Per-item spell & inventory management on the sheet

**Date:** 2026-06-05
**Status:** Design — approved for planning

## Problem

On the live character sheet, managing a spell or an item forces a detour to a
big "Manage" drawer:

- **Spells** — clicking a spell opens a description-only modal (`modal-spell`)
  whose only affordance is a hint to press *Manage Spells*. Casting, restoring,
  and clearing all live in the drawer, keyed by slot index.
- **Inventory** — the full-width Inventory group renders plain items
  (Equipped / Carried / Stashed) as inert text. Only worn magic items are
  clickable. Every action (equip, stash, stow, drop, sell, refund) lives in the
  equipment drawer.

The user wants to **click a spell or item and manage it in place**, with the
drawers retained only for the bulk/creation work that does not map onto a single
row.

## Scope

In scope:

- Per-spell modal with **cast / restore / clear** (play-state only).
- Per-item modal for **plain** inventory rows (Equipped / Carried / Stashed)
  with that row's state-appropriate actions.
- Fix reversed arcane spells so a reversed memorisation is a **distinct,
  clickable, castable row** under its reverse name.

Out of scope (stays in the drawers, unchanged):

- Spells: memorise, memorise-reversed, forget, learn.
- Inventory: the shop, gold adjustment, GM grants, and the non-plain rows
  (gems, jewellery, spell-source scrolls, ammo, containers).
- Divine cast-time reversal (not currently wired; no behaviour change).

## Approach

**Render a dedicated overlay per clickable row, server-side** (chosen over a
single JS-populated shared modal). Each spell/item row gets its own
`<div class="overlay modal" id="…">` containing the description and pre-filled
real `<form>`s, triggered by `data-modal`. This matches every other management
surface in the app — all server-rendered forms; the only JS is the existing
overlay controller — and keeps the conditional "which buttons show" logic in
Jinja where the rest of it already lives. The extra hidden DOM (≈ one modal per
row) is negligible for a local single-user sheet.

The overlay controller (`sheet_overlays.js`) needs **no change**: it already
opens any modal by id, enforces single-open, and dismisses on scrim / `[data-close]`
/ Esc. The templated `fill()` path (`data-role` title/text) is simply unused by
these per-row modals, which carry their own static content.

## Spells

### View model (`aose/sheet/view.py`)

`spellbook_view` currently tallies ready/spent by `(level, spell_id)`, discarding
the slot's `reversed` flag. Change the tally key to **`(level, spell_id, reversed)`**
so a reversed memorisation becomes its own row.

`SpellbookRow` gains:

- `display_name: str` — reverse name when `reversed` (reuse the existing
  `_slot_display_name(spell, reversed)` helper), else the spell name.
- `reversed: bool` — whether this row represents the reversed casting.
- `ready_slots: list[int]` and `spent_slots: list[int]` — the slot indices behind
  this row's ready/spent counts, filtered to this row's `reversed`-ness. These let
  the modal forms submit a concrete `slot_index` to the existing routes.

Row generation:

- **Arcane** — for each level: emit one row per known book spell (normal name,
  `reversed=False`, `known=True`), plus one row per `(spell_id, reversed)`
  combination that has memorised copies but no matching book row. A spell
  memorised both normally and reversed yields two rows ("Light" and "Darkness"),
  each with its own pips and slot indices.
- **Divine** — one row per memorised `(spell_id, reversed)`; in practice
  `reversed` is always `False` because divine cannot memorise reversed.

Template render uses `row.display_name` for the row label (currently `row.name`).

### Per-spell modal (`sheet.html`, column 3)

Replace the static `modal-spell` with one rendered modal per spell row. Title =
`display_name`; body = description, then state-aware forms:

- **Cast** — shown when `ready_slots` is non-empty; submits the first ready slot
  index to `/spells/cast`.
- **Restore** — shown when `spent_slots` is non-empty; submits the first spent
  slot index to `/spells/restore`.
- **Clear** — shown when the row has any memorised copy; submits the first slot
  (ready preferred) to `/spells/clear`.

No engine or route changes — `cast_slot` / `restore_slot` / `clear_slot` and their
routes already take `class_id` + `slot_index`. The drawer is retained for
memorise / forget / learn.

## Inventory

### View model

Plain inventory rows do not carry a description. Add `description: str` to the
inventory row view model (the `InventoryView` rows for equipped / carried /
stashed), populated from the item's `description` (`ItemBase.description`),
falling back to the item name when empty. This is what the per-item modal shows.

### Shared row-action forms

The drawer's per-row action forms live in the `inv_row_actions(row, prefix, state)`
macro in `_equipment_ui.html`. Move this macro into a small shared partial (e.g.
`_inv_row_actions.html`) imported by both `_equipment_ui.html` and `sheet.html`
so the drawer and the new per-item modals render **identical** forms from one
source. The actions are unchanged:

- **equipped** → unequip, stash, drop / sell / refund
- **carried** → equip (if equippable & class-allowed), stow-into-container, stash,
  drop / sell / refund
- **stashed** → unstash, drop / sell / refund

### Per-item modal (`sheet.html`, full-width Inventory group)

Each plain Equipped / Carried / Stashed row becomes a `data-modal` trigger opening
its own rendered modal: title = item name; body = description; then the shared
action forms for that row + state. Worn magic items keep their current
`modal-feature` behaviour. Equipped weapons and armour are plain items and are in
scope (unequip / stash / drop). The "Manage" drawer is retained for shop, grant,
gold, and the non-plain rows.

## Invariants & non-goals

- One overlay open at a time; scrim / `[data-close]` / Esc all dismiss.
- Closed `.overlay.modal` keeps `pointer-events:none` (per the style-guide
  gotcha) — applies to every new per-row modal.
- Zine tokens/fonts only; `@media print` still degrades (overlays hidden,
  `.print-only` block unchanged).
- `STYLE-GUIDE.md` §4/§5 note that "stateful spell ops live in the drawer, not
  the detail modal" is **revised** — that is the behaviour being deliberately
  changed; update the guide.
- Web tests updated: the per-spell/per-item modals exist with the right forms;
  the wizard still renders only Carried + Shop (the shared action partial must
  not leak sheet-only context into the wizard).

## Testing

- `spellbook_view`: a spell memorised normally and reversed yields two rows with
  correct `display_name`, `reversed`, and disjoint slot-index lists.
- Sheet renders a per-spell modal whose cast/restore/clear forms post the right
  `class_id` + `slot_index`; reversed row casts the reversed slot.
- Sheet renders per-item modals for equipped/carried/stashed rows with the
  correct state-driven action forms; clicking through equips/stashes/drops.
- Wizard equipment step still shows only Carried + Shop and still passes
  `tests/test_wizard.py`.
- `GET /character/<id>` returns 200; no console errors; overlays dismiss.
