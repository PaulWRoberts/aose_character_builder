# Inventory item modals + shop property expander — design

**Date:** 2026-06-08
**Status:** Approved (brainstorm)

## Problem

On the live character sheet, the Inventory section is inconsistent about what a
player can do with an item:

- Loose gear (carried / stashed / equipped weapons & armour) opens a per-item
  modal, but that modal shows only the raw `description` — none of the
  structured **properties** (damage, AC, range, qualities, cost, weight) that
  the management drawer already surfaces via its inline expanders.
- That same modal exposes the *dangerous* shop interactions — **Drop / Sell /
  Refund** — right next to the safe ones, with no confirmation. These belong in
  the deliberate context of the management drawer, not one tap away on the sheet.
- Several entries aren't clickable at all: containers/bags, ammunition, and worn
  magic items (the last open a description-only generic modal).
- Ranged weapons can only be loaded from the drawer's "Load Ammo" block, even
  though the natural place to load is the weapon itself.

In the **Shop**, rows show only name / cost / weight — there is no way to inspect
an item's full properties before buying, unlike the inventory rows in the
management drawer which expand to a detail card.

## Goal

Make every meaningful inventory entry on the sheet clickable into a modal that
shows its **properties and description** plus its **safe management actions**
(equip/move/load), while keeping the *destructive* actions (drop/sell/refund)
exclusively in the management drawer. Give the shop the same property expander
the drawer's inventory rows already have.

## Non-goals

- No change to gems & jewellery (abstract gp values with no catalog
  description/properties — left as-is).
- No new persistence shapes, engine modules, or routes. This is a
  view/template change that reuses existing derivations and POST endpoints.
- Charges, magic-item notes, and the destructive `remove`/`refund`/`sell`
  actions stay in the management drawer.

## Invariants

- **Markdown everywhere.** Any item description rendered anywhere goes through
  `| markdown | safe`. The shared `detail_card()` macro already does this; the
  bespoke magic-item modal must do it explicitly.
- **Destructive actions live only in the management drawer.** Drop, Sell, and
  Refund never appear in a sheet-side modal.
- **Single source of truth for actions.** Equip/stow/stash logic stays in the
  one `inv_row_actions` macro — no duplicated action markup.
- **Overlay model unchanged.** Per-item modals remain server-rendered, one
  overlay per item (the existing pattern), driven by `data-modal` /
  `sheet_overlays.js`. No new generic JS-populated modal.

## Design

### 1. `inv_row_actions` gains `show_remove=True`

`aose/web/templates/_inv_row_actions.html` — add a `show_remove` parameter
(default `True`). Wrap **only** the Drop/Sell/Refund `<form>` (lines 42–53) in
`{% if show_remove %}`. The equip/unequip, stow, stash/unstash branches are
unchanged.

- Management drawer (`_equipment_ui.html`) calls the macro as today → default
  `True`, keeps all actions.
- Sheet item modals call `inv_row_actions(row, url_prefix, state, show_remove=False)`
  → equip/move only.

### 2. Sheet item modal shows properties + description

`aose/web/templates/sheet.html`, the `item_modal` macro (lines 6–14):

- Replace the raw `{{ row.description | markdown | safe }}` body with
  `{{ detail_card(row.detail) }}` — `item_card()` already populates both the
  `stats` (Type, Damage, AC, Range, Qualities, Magic, Cost, Weight…) and the
  markdown description, so this gives properties **and** description in one call.
- Change the actions line to `inv_row_actions(row, url_prefix, state, show_remove=False)`.

The three existing modal loops (carried / stashed / equipped) are otherwise
unchanged.

### 3. Newly-clickable entries

Each gets a server-rendered modal following the same overlay pattern.

**Containers / bags** (carried + stashed columns, `sheet.html` lines 361–368 &
394–399): make the bag `<li>` clickable (`data-modal="modal-container-{{ c.instance_id }}"`).
Add one modal per container rendering `detail_card` built from the container's
**catalog item** (`item_card`), i.e. Type / Capacity / Cost / Weight + the
catalog description, plus the existing Stash/Unstash form (state-dependent).
Take-out of contents and container removal remain drawer-only.

- *View support:* `ContainerView` already carries `catalog_id`. The sheet view
  builds a `DetailCard` per container (via `item_card(data.items[catalog_id])`)
  and exposes it on the view model (new `detail: DetailCard | None` field on
  `ContainerView`, populated in `shop.inventory_view`). Capacity/used/weight are
  already on `ContainerView` and can be shown alongside or folded into the card.

**Ammunition** (carried column, `sheet.html` lines 381–383): make the ammo
`<li>` clickable (`data-modal="modal-ammo-{{ a.instance_id }}"`). Modal renders
`detail_card` from the ammo's base catalog item (Type / Groups / Bundle / Cost /
Weight + description). Read-only re: equipping — loading happens from the
launcher (§4). Count adjust / remove stay in the drawer.

- *View support:* `AmmoRow` gains a `detail: DetailCard | None` field, populated
  in `ammo_view` from `data.items[s.base_id]` via `item_card`.

**Worn magic items** (equipped column, `sheet.html` lines 342–349): replace the
generic `modal-feature` link with a dedicated `modal-magic-{{ mi.instance_id }}`
modal showing the modifier chips (`mi.modifier_summary`), the description
rendered with `| markdown | safe`, and Equip/Unequip
(`/equip-magic` / `/unequip-magic`, keyed by `instance_id`). Charges, note, and
remove stay in the drawer.

- *View support:* the sheet already passes `magic_items` with `name`,
  `modifier_summary`, `description`, `equipped`, and the instance id. Confirm the
  instance id and an `equippable` flag are available on the sheet-side view model;
  add to the view model if missing.

### 4. Ranged weapons load ammo from their modal

In the equipped-weapon modal (the `equipped` branch of `item_modal`), when
`row.id` is a key in `sheet.ammo_load_options`:

- Show current load: the matching attack profile's `loaded_ammo_name`, or an
  "Unloaded" badge when `unloaded`.
- Render a Load `<select>` of `sheet.ammo_load_options[row.id]` + a Load button
  posting to `{{ url_prefix }}/ammo/load` with `weapon_key={{ row.id }}`, and an
  Unload button posting to `{{ url_prefix }}/ammo/unload`.

`manageable_item_id` (which keys the equipped modals) and `ammo_load_options`
(keyed by `prof.weapon_id`) are both the catalog weapon id, so they line up with
no new plumbing. The macro needs read access to `sheet.ammo_load_options` and a
lookup of the loaded-ammo name; pass these through (or reference `sheet`
directly, consistent with the rest of `sheet.html`).

### 5. Shop property expander

`aose/engine/shop.py`:

- Add `detail: DetailCard | None = None` to `ShopItem`.
- In `shop_categories`, populate `detail=item_card(i)` when building each
  `ShopItem`.

`aose/web/templates/_equipment_ui.html`, the Shop pane (lines 629–650):

- Make each `shop-row` a `data-detail-toggle="shop-<category>-<item.id>"`
  trigger and add a sibling `<tr class="row-detail collapsed" data-detail-for=…>`
  whose cell renders `{{ detail_card(item.detail) }}`.
- No JS change: `inventory.js`'s delegated row-detail toggle already ignores
  clicks originating inside `form, button, a, select`, so the Buy/add controls
  keep working while a click elsewhere on the row toggles the expander.

## Data flow / dependencies

No new engine cycles. `detail.py` (`item_card`, `DetailCard`) is already shared
by `aose/engine/shop.py` and `aose/sheet/view.py`. New `detail` fields on
`ContainerView`, `AmmoRow`, and `ShopItem` are populated where those models are
already built. `ammo_load_options` is already computed by the sheet view. The
only new POST usage reuses the existing `/ammo/load`, `/ammo/unload`,
`/equip-magic`, `/unequip-magic`, `/stash`, `/unstash` routes.

## Testing

Web/template tests (FastAPI test client rendering the sheet & drawer):

1. **Properties in sheet modal** — an equipped weapon's modal contains a
   property label (e.g. `Damage`) and the markdown-rendered description.
2. **No destructive actions on the sheet** — a sheet item modal does **not**
   contain `Sell` / `Refund` / `Drop` buttons.
3. **Drawer still destructive** — the management drawer's inventory rows still
   render Sell/Refund/Drop (guards against over-broad suppression).
4. **Shop expander** — a shop row exposes a `data-detail-toggle` with a
   `row-detail` containing a property label.
5. **Launcher load control** — an equipped ammo-accepting weapon's modal
   contains a Load control / ammo `<select>`.
6. **New clickable entries** — container, ammo, and worn-magic-item modals exist
   and render their descriptions as markdown.

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`.

## Docs to update on landing

- `docs/CHANGELOG.md` — one-line row (date, feature, branch, this spec slug).
- `docs/ARCHITECTURE.md` — update the inventory/sheet subsystem section in place
  to note the enriched per-item modals, the destructive-action boundary
  (drawer-only), launcher load-from-modal, and the shop expander.
