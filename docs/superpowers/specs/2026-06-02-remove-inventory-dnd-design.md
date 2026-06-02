# Remove inventory drag-and-drop

**Date:** 2026-06-02
**Status:** Approved

## Goal

Remove the inventory drag-and-drop (DnD) UX. Item order is not meaningful, and
DnD was a redundant second path layered on top of button/form controls that
already exist. Moving items between the main inventory and containers is already
served by the **Stow** control (a dropdown of carried containers + a button) and
the **Take Out** button. This is a pure-deletion cleanup — no new behavior.

## Why DnD is safe to delete

The shared equipment partial (`_equipment_ui.html`) already renders explicit
forms for every move:

- Equip / Unequip
- Stash / Unstash
- **Stow** — dropdown of carried containers + button (carried item → container)
- Take Out (container item → carried/stashed)
- container Stash / Unstash
- Drop / Sell / Refund

DnD only *additionally* allowed dragging an item directly from one container into
another. With DnD gone, that becomes a two-step Take Out → Stow. The user has
accepted this trade-off.

Weapon/armour equip restrictions are **not** lost: the `/equipment/equip` route
enforces `allowed_weapons` / `allowed_armor` / `allow_shields` independently of
the dispatcher (`routes.py`), and the wizard route does the same.

## Changes

### Delete
- `aose/web/move_dispatch.py` — the entire `dispatch_move` dispatcher.

### Edit — remove the `/move` route and DnD wiring
- `aose/web/routes.py` — remove the `equipment_move` route and the
  `from aose.web.move_dispatch import dispatch_move` import.
- `aose/web/wizard.py` — remove the `equipment_move` route and the
  `dispatch_move` import.
- `aose/web/templates/_equipment_ui.html` — strip `draggable="true"`,
  `data-source`, `data-target`, and the now-unused `data-equipment-url-prefix`
  wrapper attribute. **Keep** `data-instance-id` / `data-item-id` (the
  container-collapse toggle still reads them). Update the `<script src>` to the
  renamed JS file.
- `aose/web/static/inventory_dnd.js` → rename to `inventory.js`. Keep **only**
  the container-collapse toggle logic; delete every drag/drop handler and the
  `/move` fetch.
- `aose/web/static/sheet.css` — remove the "Drag-and-drop visual feedback"
  block (`[draggable="true"]` cursors and `.drag-over`).

### Tests
- `tests/test_containers.py` — delete the six `/equipment/move` route tests
  (`test_move_carried_to_equipped_equips`, `test_move_equipped_to_carried_unequips`,
  `test_move_carried_to_container_stows`,
  `test_move_container_row_to_stashed_section_stashes`,
  `test_move_container_to_carried_takes_out`, `test_move_invalid_combo_returns_400`)
  plus `test_sheet_includes_dnd_script_tag` and
  `test_sheet_inventory_rows_carry_dnd_attributes`. The collapse-button test and
  the `data-instance-id` capacity-badge assertion stay.
- `tests/test_equip_enforcement.py` — delete the three `test_dispatch_move_*`
  tests, the `dispatch_move` import, and the `_MoveState` helper. Equip
  enforcement remains covered by the route- and view-level tests.

### Not touched
All existing button forms, the Stow dropdown, the shop-search script, and every
engine helper (`stow` / `take_out` / `stash` / `unstash` / `stash_container` /
`unstash_container` / etc.) stay exactly as-is.

## Success criteria
- No `draggable`, `data-source`, `data-target`, `dispatch_move`, or `/move`
  references remain in `aose/` or `tests/`.
- The container-collapse toggle still works on the sheet and the wizard.
- The full test suite passes.
