# Animal & Retainer Equip/Unequip in Inventory Box

**Date:** 2026-06-21  
**Status:** Approved

## Problem

The inventory box on the live sheet shows equipped items for animals (barding) and
retainers (weapons, armour) but:
1. Clicking those items does nothing — no modal appears.
2. There is no way to equip or unequip from within the inventory pane.

## Scope

Animals and retainers only. Vehicles carry cargo, not equipped gear — out of scope.

## Design Principle

Reuse existing modals, macros, and URL patterns between PC and non-PC characters where
the underlying operation is the same. Avoid parallel implementations.

---

## Routes (3 new)

### `POST /character/{id}/retainer/{ret_id}/equip`
- Form fields: `item_id` (required), `slot` (optional)
- Runs the same `_equip()` engine function against `ret.spec.inventory` /
  `ret.spec.equipped` — identical slot-detection logic to the PC
- No class-allowance check (retainers are NPCs; DM decides)
- 404 if retainer not found; 400 on ValueError from engine

### `POST /character/{id}/retainer/{ret_id}/unequip`
- Form field: `item_id`
- Runs `_unequip()` against `ret.spec.equipped`
- 404/400 same pattern

### `POST /character/{id}/animal/{inst_id}/unequip`
- No form fields (animal has at most one piece of worn gear)
- Thin wrapper around the existing `companions_engine.clear_armor()` call
- Gives animal barding the same `/unequip` URL shape as everything else so it can
  share the `item_modal` macro with `state="equipped"`

All three redirect to `/character/{id}` on success (existing convention).

---

## Template: `_inv_row_actions.html`

Add a `retainer` state branch (alongside the existing `equipped` / `carried` / `stashed`
branches):

```
elif state == "retainer" and row.equippable:
    POST url_prefix/equip  →  Equip button
    (off-hand slot picker not shown — retainers follow PC auto-detect logic,
     same as the basic carried branch)
```

---

## Template: `_inv_pane.html`

Currently, equipped-item `<li>` elements are only made clickable when
`group.kind == "carried"`. Replace the hardcoded kind check with a computed prefix:

```
{%- if   group.kind == "carried"  -%} eq_modal_prefix = "equipped"
{%- elif group.kind == "retainer" -%} eq_modal_prefix = "retainer-{group.id}-eq"
{%- elif group.kind == "animal"   -%} eq_modal_prefix = "animal-{group.id}-eq"
{%- else                           -%} eq_modal_prefix = ""
{%- endif -%}
```

Gate `class="clickable"` and `data-modal` on `eq_modal_prefix` being non-empty.

- `equipped_attacks` rows: target `modal-item-{eq_modal_prefix}-{atk.manageable_item_id}`
- `equipped_worn` rows: target `modal-item-{eq_modal_prefix}-{e.item_id}`
- `equipped_magic` rows: unchanged (already always clickable)

---

## Template: `sheet.html`

### Modals for retainer equipped items

After the existing PC equipped-item modals, add a loop over retainer groups:

```
for group in sheet.inventory_groups where group.kind == "retainer":
    ret_url = /character/{character_id}/retainer/{group.id}
    for row in group.equipped:
        item_modal(row, "equipped", "retainer-{group.id}-eq", ret_url)
```

This reuses the `item_modal` macro verbatim. `state="equipped"` causes
`inv_row_actions` to render an Unequip button posting to `ret_url/unequip`.
The modal id matches what `_inv_pane.html` targets.

Note: `group.equipped` is built in `build_inventory_groups` from
`retainer.spec.equipped.values()`. If the same catalog item occupies two slots
(e.g. two daggers), the same modal id would be emitted twice; the browser uses the
first. This edge case is acceptable for NPCs.

### Modals for animal barding

Similar loop over animal groups:

```
for group in sheet.inventory_groups where group.kind == "animal":
    animal_url = /character/{character_id}/animal/{group.id}
    for row in group.equipped:   # at most one row (the barding)
        item_modal(row, "equipped", "animal-{group.id}-eq", animal_url)
```

`state="equipped"` → Unequip button posts to `animal_url/unequip` (the new thin
wrapper route). Modal id matches `_inv_pane.html`.

### Retainer loose item modals

The existing block renders all three non-PC group kinds together with the PC's
`target_url_prefix`. Split it: handle `animal` / `vehicle` loose items as before,
and handle `retainer` loose items separately with a per-retainer URL prefix:

```
for group where kind == "retainer":
    ret_url = /character/{character_id}/retainer/{group.id}
    for row in group.loose:
        item_modal(row, "retainer", "retainer-{group.id}", ret_url, src_id=group.id)
```

`state="retainer"` → `inv_row_actions` shows the new Equip button.  
`url_prefix = ret_url` → Equip button posts to `ret_url/equip`.

---

## Data flow summary

```
Inventory pane (equipped row, retainer)
  → click → modal-item-retainer-{ret_id}-eq-{item_id}

sheet.html modal (item_modal, state="equipped", url=.../retainer/{ret_id})
  → Unequip → POST /character/{id}/retainer/{ret_id}/unequip

Inventory pane (loose row, retainer)
  → click → modal-item-retainer-{ret_id}-{item_id}

sheet.html modal (item_modal, state="retainer", url=.../retainer/{ret_id})
  → inv_row_actions "retainer" branch → Equip → POST /character/{id}/retainer/{ret_id}/equip

Inventory pane (equipped row, animal barding)
  → click → modal-item-animal-{inst_id}-eq-{armor_id}

sheet.html modal (item_modal, state="equipped", url=.../animal/{inst_id})
  → Unequip → POST /character/{id}/animal/{inst_id}/unequip → clear_armor()
```

---

## Files changed

| File | Change |
|---|---|
| `aose/web/routes.py` | Add 3 POST routes |
| `aose/web/templates/_inv_row_actions.html` | Add `retainer` state branch |
| `aose/web/templates/_inv_pane.html` | Replace kind-check with `eq_modal_prefix` logic |
| `aose/web/templates/sheet.html` | Add retainer/animal equipped modals; fix retainer loose modal URL prefix |

No engine changes needed. No model changes needed.
