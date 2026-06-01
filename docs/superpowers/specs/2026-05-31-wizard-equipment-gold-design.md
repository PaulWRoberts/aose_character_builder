# Wizard Overhaul — Slice 7: Equipment (remove starting-gold reroll)

**Date:** 2026-05-31
**Status:** Design approved, pending written-spec review

## Context

Seventh slice of the wizard overhaul. Implements the target spec's **P8 —
Equipment** change: **starting gold is rolled once and locked; no reroll.**
Everything else on the equipment step (buy / equip / stash / containers / magic
items / encumbrance) is already built and unchanged.

## Current behaviour

- `get_equipment` rolls `roll_starting_gold()` (3d6 × 10) on first visit and
  sets `draft["gold_locked"] = False`.
- A **"Re-roll Starting Gold"** button (`POST /{draft_id}/equipment/reroll-gold`,
  template block in `_equipment_ui.html` gated by `show_gold_reroll` +
  `gold_locked`) lets the player reroll until the first purchase.
- `gold_locked` flips to `True` on the first buy or on Continue.

## Goal

Roll starting gold exactly once, lock it immediately, and remove the reroll
affordance entirely. There is no admin/referee override in this app (no auth);
the only "reset" is cancelling the draft and starting over.

## Design

- **`wizard.py`**
  - `get_equipment`: on first visit set `draft["gold_locked"] = True` at the
    same time gold is rolled (replacing the `False` seed). Buy/Continue keep
    setting it `True` (now redundant but harmless).
  - **Remove** the `post_equipment_reroll_gold` route entirely.
  - Stop passing `show_gold_reroll` into the equipment context (remove the flag).
- **`templates/_equipment_ui.html`**: delete the `show_gold_reroll` reroll
  button block (both the active and the locked-message branches) and the
  `show_gold_reroll` reference in the header comment.
- **`templates/wizard/equipment.html`**: update the intro copy from
  "Re-roll until you make your first purchase; afterwards…" to state the
  starting gold is fixed (3d6 × 10, rolled once).
- The live character sheet (`routes.py`) already passes `gold_locked = True`
  and no reroll; unaffected.

## Tests

- `test_equipment.py`: remove the reroll-gold test(s).
- New: `POST /{draft_id}/equipment/reroll-gold` returns 404/405 (route gone);
  gold is present and `gold_locked` is `True` immediately on first visit to the
  equipment step (before any purchase).

## Risks / notes

- Trivial slice; the main risk is a stray template/test reference to
  `show_gold_reroll` or the removed route. Grep for both after the change.
- No migration (nothing deployed).
