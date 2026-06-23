# Unified Item Movement + Shared Action Controls — Design

**Date:** 2026-06-23
**Status:** Approved (design)
**Branch:** feat/unified-item-movement

## Problem

Two cracks surfaced after the inventory-box interaction-hub landing:

1. **Not everything moves.** Instance-tracked magic items, enchanted gear, and
   ammunition cannot be relocated at all — they have no `location` and are
   hard-wired into the PC's carried bucket. Coins, gems, and jewellery *can* be
   moved between top-level inventories but **not into containers or onto
   retainers**: `move_coins`/`move_valuable` already accept those destinations,
   but nothing in the view renders a loose coin/gem/jewellery stack sitting
   inside a container, so such a move would silently orphan it. The result is an
   inconsistent mental model: some owned things move anywhere, some move between
   top-levels only, some don't move at all.

2. **No shared action control.** Every modal hand-rolls its own `<form>` +
   button. They don't even agree on classes: `inv_row_actions` renders **bare
   `<button type="submit">`** for Equip/Unequip (falling through to the legacy
   `button` CSS rule instead of `.btn`), the magic modal mixes bare buttons with
   `class="danger"`, Sell/Move use differently-sized `<select>`s, ammo uses
   `.btn tool dark`, and widths are set with ad-hoc inline `style="width:…"`.
   There are even two conflicting `.inline-form` rules and three interchangeable
   `.btn` font sizes. Each new "mild variety of item" reimplements the same
   controls slightly differently.

## North-star invariant

**Every owned thing has a home `StorageLocation`, and any thing can move to any
top-level inventory (carried · stashed · animal · vehicle · retainer) or any
container.** One Move control, one destination list, one set of action controls —
everywhere. Everything carried is an item; items move freely.

## Goals

- Make magic items, enchanted gear, and ammunition **location-aware and movable**
  to any top-level inventory or container, exactly like catalog items.
- Make coins, gems, and jewellery **movable into containers and onto retainers**,
  with a render path so they never orphan.
- Provide **one shared set of action-control macros** that every inventory/treasure
  modal routes through, and dedupe the conflicting control CSS.
- Preserve all existing behaviour (equip/charges/sell/convert/etc.); this unifies
  *where things can go* and *how controls look*, not what the actions do.

## Non-goals

- **No flat-pointer rewrite of catalog-item storage.** Loose catalog items stay
  identity-less strings in location-resolved lists (`inventory`/`stashed`/
  `container.contents`/carrier `contents`/`retainer.spec.inventory`); duplicates
  still count by multiplicity. Unification is behind one move front-door + one
  destination list, not one physical representation.
- **No nesting.** A container still cannot go inside another container.
- **The shared action *macros* are inventory-scoped.** Other sheet action buttons
  (level-up, rest, energy-drain, spell management, companions) are **not** rewritten
  onto the macros this pass — but they **do** adopt the sheet-wide button-size
  standard (via context/size classes), so sizing is consistent everywhere even
  where markup is untouched.
- **No spell-source relocation.** Spell books/scrolls stay PC-bucket; they have
  their own read/cast/copy lifecycle and are out of scope for movement here.
- No migrations (app is not deployed); `location` defaults to carried, so old
  saves load unchanged.

## Decisions (from brainstorming)

1. **Movability scope:** magic + enchanted + ammo become location-aware and
   movable; coins/gems/jewellery gain container + retainer destinations. No item
   type is left unable to reach every inventory and container.
2. **Equipped move:** moving an equipped magic item / enchanted piece (or a
   slot-resident weapon/armour) **auto-unequips first**, then relocates. One click.
3. **Controls — two layers, two radii.** (a) The shared *action macros* are
   adopted only by the inventory/treasure modals (the rest of the sheet keeps its
   markup). (b) A **sheet-wide button-size standard**, keyed to *use context*
   (inline · modal · toolbar · primary/CTA), is applied across the whole live
   sheet — every button conforms to a context size, replacing the current ad-hoc
   mix of three interchangeable `.btn` sizes, bare `<button>`s, and inline width
   styles.
4. **One move route.** A single `POST /character/{id}/inventory/move` fronts
   `move_thing`; the eight deprecated typed move routes (PC + wizard) are deleted,
   not kept for back-compat (app is not deployed).

## Architecture

### Substrate (unchanged) and why two representations stay

`aose/engine/storage.py` already exposes a clean **location resolver**:
`loose_list(spec, loc)`, `containers_collection(spec, owner)`, `_carrier`,
`_retainer`, `_container`. Loose catalog items live in the list that resolver
returns; identity-bearing things (containers, coins, gems, jewellery) carry a
`location: StorageLocation` pointer. Catalog items are identity-less (a second
"torch" is just another string), so they cannot carry a per-instance pointer —
hence two representations. This is fine: they unify behind one front door.

### Engine — one movement front door (`storage.py`)

- **`move_thing(spec, category, ref_id, dest, *, data=None)`** — the single
  dispatch entry point. `category ∈ {item, container, coin, gem, jewellery,
  magic, enchanted, ammo}`.
  - `item` → `move_item` (loose-list → loose-list; already supports container,
    carrier, and retainer locations).
  - `container` → `move_container` (already; rejects container dest — no nesting).
  - `coin` → `move_coins` (already; container/retainer dest now exercised).
  - `gem` / `jewellery` → `move_valuable` (already; container/retainer dest now
    exercised).
  - `magic` / `enchanted` / `ammo` → **new** `move_instance(spec, kind, id, dest)`:
    auto-unequip if equipped, then either re-point `.location` (same owner-world)
    or list-to-list move into `retainer.spec.*` for a retainer dest. Equipped state
    is cleared on any cross-bucket move (a thing in a backpack / on a mule is not
    worn).
- **`move_targets(spec)`** — yields the canonical destination set: every
  top-level inventory + every container (PC and retainer), each as
  `(kind, id, label)`, for the shared Move control. Callers exclude the current
  location.
- **Coin/gem/jewellery into containers** already validated by the existing
  `dest.kind == "container"` guards; no engine change beyond exercising them.
- **Sell/refund credit** continues to land in the PC's carried coins.

### Models (`aose/models/character.py`)

Add `location: StorageLocation = carried` to `MagicItemInstance`,
`EnchantedInstance`, and `AmmoStack`. Equipped magic/enchanted imply carried
(enforced by `move_instance`, not the model — keeps the model dumb). No
validators needed beyond the default (old saves coerce to carried).

### View (`aose/sheet/view.py`, `shop.py`)

- **`build_inventory_groups`** buckets `magic_items` / `enchanted` / `ammo` by
  `.location` into the owning group (today they are appended unconditionally to
  the PC carried group). A magic ring on a mule renders under the mule.
- **`ContainerView`** gains stowed sub-lists: coins, gems, jewellery, magic,
  enchanted, ammo gathered by the container's own `StorageLocation`. Built in
  `_container_views_from` from the same per-location filters used for top-level
  groups.
- The capability descriptor (`OwnerCaps`) is unchanged; movability is universal,
  not capability-gated.

### Encumbrance (`aose/engine/encumbrance.py`)

`equipment_weight_cn` currently sums `spec.magic_items` / `spec.enchanted`
unconditionally. Filter them (and ammo) to **carried-location only**, matching how
coins/gems/containers already filter. Container-on-carried stowed treasure weight
is already handled and now also covers stowed magic/enchanted/ammo via the same
container loop.

### Shared action controls (`aose/web/templates/_actions.html` — new)

One macro set, the single source of truth for an action control:

| macro | renders |
|---|---|
| `act_button(label, url, hidden={}, variant="default")` | a POST form + one consistently-styled `.btn` (variants: default / solid / danger) |
| `act_move(url, ref, cur_kind, cur_id)` | the universal **Move ▾** select over `move_targets`, minus current; auto-submit on change |
| `act_sell(url, ref, row)` | **Sell ▾** (half price / refund) |
| `act_stepper(url, ref, field="delta")` | **+ / −** adjust pair |
| `act_select(url, label, options, hidden={})` | generic dropdown-action (e.g. coin Convert) |

`ref` is `{category, id, src_kind, src_id}` so one Move form serves every type, and
every macro posts to the single `/inventory/move` route. `inv_row_actions` and the
coin/gem/jewellery/magic/enchanted/ammo/catalog/container modals are refactored onto
these macros.

### Sheet-wide button-size standard (`sheet.css`)

Size is decided by **use context**, not by ad-hoc per-button classes. One scale,
driven by CSS variables on a base `.btn`, with the *variant* (solid / danger /
link) orthogonal to *size*:

| context | class | use | rough metrics |
|---|---|---|---|
| **inline** | `.btn.btn-inline` | controls living in a list row / `.inline-form` (equip, move, ±, take-out) | ~9px, tight padding |
| **modal** | `.btn` (default) | action buttons in a modal `.row-actions` / `.ov-section` | ~10px, standard padding |
| **toolbar** | `.btn.btn-tool` | buttons on dark group bars (Rest, Thresholds, Manage) — supersedes today's `.btn.tool` | ~9px, light-on-dark |
| **primary/CTA** | `.btn.btn-cta` | wizard "Next", Roll, confirm — supersedes `.solid` sizing | ~11px, roomy |

Rules of the standard:
- The two conflicting `.inline-form` definitions collapse into one.
- The bare-`<button>` action fall-through is removed; an action button is always a
  `.btn` with a size class. Legacy `button`/`.button` recolouring stays only for
  genuinely unstyled controls.
- Input/`select` widths in action controls come from classes
  (`.act-num`, `.act-select`), not inline `style="width:…"`.
- The size classes are applied **sheet-wide** (inventory modals via the macros;
  other areas via their existing markup + the class), so every button matches its
  context even where the markup is otherwise untouched. Existing `.btn.tool` /
  `.solid` call-sites are renamed/aliased to the new context classes.

### Move route + destination control (`routes.py`, `_move_dest.html`)

- **Single route:** `POST /character/{id}/inventory/move` reads `category`, the
  relevant id field (`item_id` for catalog items, `instance_id` otherwise,
  `denom`+`count` for coins), and `dest_kind`/`dest_id` (+ `src_kind`/`src_id` for
  loose items), and calls `storage.move_thing`. `_loc` maps bad kinds to HTTP 400
  as today.
- **Deleted (deprecated):** `/inventory/move-item`, `/inventory/move-coins`,
  `/inventory/move-valuable`, `/inventory/move-container` and the matching wizard
  routes. Every call site (templates + tests) moves to the single route. The Sell /
  Convert / Adjust / charge routes are **not** move routes and are untouched.
- **`move_dest_control`** drives off `move_targets` and emits the unified `ref`;
  the `allow_containers` / `allow_retainers` flags are removed (every type allows
  both). The only exclusions are the current location and — for a container being
  moved — other containers (no nesting).

## Data flow

```
spec ─► build_inventory_groups(spec, data)
          per TopLevelGroup, bucketed by StorageLocation:
            loose · coins · gems · jewellery · magic · enchanted · ammo · containers
          per ContainerView (location = container instance):
            stowed coins · gems · jewellery · magic · enchanted · ammo · loose
                    ▼
       sheet.html / _inv_pane.html
          every row → per-item modal
          every modal → _actions.html macros (uniform controls)
          every Move ▾ → move_targets(spec) minus current
                    ▼
       POST /character/{id}/inventory/move  (or existing typed routes)
          → storage.move_thing(spec, category, id, dest)
```

The single `/inventory/move` route fronts `move_thing` (category in the form); the
four deprecated typed move routes (and their wizard twins) are deleted. The template
side calls one `act_move` macro everywhere.

## Phasing (cohesive spec → phased plan)

1. **Models + engine:** `location` on magic/enchanted/ammo; `move_instance`;
   `move_thing` dispatch; `move_targets`; encumbrance per-location filter.
2. **View:** bucket magic/enchanted/ammo by location; `ContainerView` stowed
   sub-lists; render stowed contents in `_inv_pane.html` container blocks.
3. **Single move route:** add `move_thing` + `move_targets`; add
   `POST /inventory/move`; delete the four typed move routes (PC + wizard); migrate
   every template call site and update `tests/test_inventory_move_routes.py`.
4. **Shared action macros:** `_actions.html`; refactor `inv_row_actions` + every
   inventory/treasure modal onto them; generalise `_move_dest.html` onto
   `move_targets` + the unified `ref`.
5. **Button-size standard (sheet-wide):** add the size scale + context classes;
   collapse the duplicate `.inline-form`; remove the bare-button fall-through; move
   action input/select widths to classes; re-point existing `.tool`/`.solid`
   call-sites to the new context classes.
6. **Docs + verification:** update `ARCHITECTURE.md` (inventory/treasure/encumbrance
   + a new controls note, in place), `CHANGELOG.md` row; verify print parity and the
   wizard path.

## Testing

- **Engine:** `move_thing` for every category, incl. magic→container,
  enchanted→retainer, ammo→animal, gem→container, coin→container; equipped magic
  auto-unequips on move; `move_targets` lists every inventory + container minus
  current; encumbrance counts a carried magic ring but not one on a mule, and
  counts treasure/magic stowed in a carried container.
- **View:** a magic item / coin / gem placed in a container renders inside that
  container's view; magic on a carrier buckets under the carrier; nothing
  double-renders in the PC carried group.
- **Web:** every inventory/treasure modal exposes a Move ▾ targeting the full
  destination list and posting to the single `/inventory/move`; that route moves an
  item, a coin partial, a gem, and a magic instance to a container; the deprecated
  typed move routes are gone (404); modals render uniform control classes (no bare
  `<button>` in action rows; one `.inline-form`; size class per context); the drawer
  stays acquisition-only.
- **Regression:** full suite green; PC equipped/attack display unchanged; settings
  page renders no "pending" badge; print sheet still lists all groups.

## Risks / open implementation notes

- **Equipped-on-move semantics.** Auto-unequip must clear both the
  `MagicItemInstance.equipped` bool *and* any `CharacterSpec.equipped` slot that
  references the same item, so a moved weapon/armour leaves its slot cleanly.
- **Container double-count.** Stowed magic/enchanted/ammo must be counted by the
  container loop only (carried-container), and skipped by the top-level magic/
  enchanted/ammo weight pass — verify no item is weighed twice.
- **Retainer world boundary.** Moving an instance to a retainer is a list-to-list
  move into `retainer.spec.*` with `location` reset to carried (the retainer's own
  world); moving back is the reverse. Mirrors `move_container`'s retainer handling.
- **Single-route churn.** Folding the typed move routes into one is the chosen
  (cleaner) path but touches every move call site at once: PC + wizard templates,
  `test_inventory_move_routes.py`, and any helper that posted to a typed route. The
  migration must be exhaustive — a missed call site 404s. Mitigate by grepping all
  `move-item|move-coins|move-valuable|move-container` references before deleting.
- **Sheet-wide sizing blast radius.** The size standard touches buttons outside
  inventory (`.tool`, `.solid`, bare `button` on dark bars). Re-pointing call-sites
  must be verified visually per context (inline / modal / toolbar / CTA) so no
  button shrinks or grows unexpectedly; prefer aliasing old classes to the new size
  vars over deleting them outright where a call-site can't be hand-checked.
