# Advancement UX redesign

**Status:** spec
**Date:** 2026-06-05
**Branch target:** `feature/advancement-ux`

## Problem

Three small but annoying issues with the live sheet's advancement controls:

1. **Level Up button is always present** in the Advancement modal, even when the
   character is far short of the next threshold. It's disabled, but the visual
   noise suggests action is available where there is none.
2. **The header progress bar measures from L1 0 XP** (`current_xp /
   next_threshold`), not progress *through the current level*. For a L3 fighter
   at 4 100/8 000 XP this shows ~51% when the player has actually only made it
   ~5% into L3 (the L3 floor being 4 000).
3. **Level Up is non-interactive** — pressing the button atomically advances
   the class and rolls HP in the same request, with the new total just
   appearing. The wizard's L1 HP roll is a deliberate two-step affair (roll,
   then commit by moving forward) and the level-up flow should match.

## Goals

- Show the per-class "Level Up" affordance only when that class actually has
  the XP for it.
- Replace the cumulative progress bar with one showing progress through the
  current level.
- Make HP at level-up an explicit Roll → Confirm interaction, honouring
  Strict Mode the same way the wizard does.
- Pull "Add XP" and "Energy Drain" out of the now-unnecessary Advance modal
  and into the header directly (XP) / a dedicated overlay (drain).

## Non-goals

- Selecting newly-unlocked weapon proficiency slots at level-up. The engine
  doesn't model unspent slots across levels yet; that's a follow-up.
- Any change to the multi-class XP split or prime-requisite adjustment.
- Any change to the energy-drain mechanics — only its UI location.

## Header layout (sheet.html)

Replace the existing `<div class="xp">` block with:

```
┌── Global advancement controls ──────────────────────┐
│ [ Add XP: ___ ] [Grant]              [Energy Drain] │
├── Per-class rows ───────────────────────────────────┤
│ Fighter L3   ████░░░░░░░░ 4 100 / 8 000             │
│ Magic-User L2  ████████████ 5 000 / 5 000   [Level Up → 3]
└─────────────────────────────────────────────────────┘
```

- **Add XP** is the existing `/xp` route, inlined.
- **Energy Drain** is a `<button>` that opens `modal-drain` (new), containing
  the same form that lives in `modal-advance` today.
- **Per-class progress bar** now fills based on
  `(current_xp − current_threshold) / (next_threshold − current_threshold)`,
  clamped to `[0, 1]`.
- **Level Up → N** button appears next to a class's progress row only when
  `adv.can_level` is true. It opens `modal-levelup-{class_id}`. At max level
  the row shows a "Max" pill instead.
- The single "Advance" button and `modal-advance` are removed.

## Engine changes

`aose/engine/leveling.py`:

- Add `current_threshold: int` to `ClassAdvancement`. Value:
  `cls.progression[entry.level].xp_required` if present, else `0` (L1
  characters have no L1 entry in some progressions, and 0 is the correct
  display floor).
- Split `level_up()` into two operations to support the Roll → Confirm UI
  without burying state in the route layer:

  ```python
  def roll_pending_hp(spec, data, class_id, rng=None) -> int:
      """Roll the new level's hit die and store the result on the spec's
      pending_level_up dict.  Raises ValueError if the class can't level,
      is at max, is at/beyond name level (no die rolled there), or if
      Strict Mode locks the existing pending roll."""

  def confirm_level_up(spec, data, class_id) -> int:
      """Apply the pending roll (sub-name-level) or just bump the level
      (at/beyond name level).  Returns the HP gained (0 at/beyond name
      level).  Raises ValueError if no pending roll is available when one
      is required, or if the class otherwise can't level."""

  def cancel_pending_level_up(spec, class_id) -> None:
      """Idempotently clear pending_level_up[class_id]."""
  ```

  Keep `level_up()` as a wrapper (`roll_pending_hp` then `confirm_level_up`)
  so existing callers and tests keep working without changes.

`aose/models/character.py`:

- Add `pending_level_up: dict[str, int] = Field(default_factory=dict)` to
  `CharacterSpec`. Maps `class_id` to the rolled HP awaiting confirmation.
  `extra="forbid"` is already on the model; defaulting empty means existing
  saved characters load unchanged.

The cycle-free boundary is preserved: `leveling.py` already imports
`engine.dice.roll_hp` and `engine.ability_mods`, so adding the two helpers
introduces no new dependencies.

## Routes (aose/web/routes.py)

Three new endpoints, all under the existing pattern:

- `POST /character/{character_id}/level-up/{class_id}/roll`
  Calls `roll_pending_hp`; 400 on engine `ValueError`. Saves and redirects to
  the sheet.
- `POST /character/{character_id}/level-up/{class_id}/confirm`
  Calls `confirm_level_up`; 400 on engine `ValueError`. Saves and redirects.
- `POST /character/{character_id}/level-up/{class_id}/cancel`
  Calls `cancel_pending_level_up`; always succeeds. Saves and redirects.

Existing routes retained:

- `POST /character/{character_id}/level-up/{class_id}` — kept for backward
  compatibility; now wraps `roll_pending_hp + confirm_level_up`. Some tests
  use this directly.
- `POST /character/{character_id}/xp` and `/energy-drain` — unchanged.

## Strict Mode semantics

Mirrors the wizard's HP step:

- **Strict on** (default): pressing "Roll HP" once stores the roll; the button
  is then removed and replaced with the pending result + a "Confirm Level Up"
  button. Re-roll is not offered. A second "Roll HP" POST returns 400.
- **Strict off**: a "Re-roll" button appears alongside the pending result,
  letting the player roll again before confirming. Re-rolls overwrite the
  pending value.

At/beyond name level there is no HP roll, so Strict Mode is irrelevant — the
modal shows the flat HP gain and a single "Confirm Level Up" button.

## Modal contents

One `modal-levelup-{class_id}` per class. Body shows:

- Class name + target level: "Fighter — Level 4"
- CON modifier line: "CON modifier: +1" (sub-name-level only)
- The active L1-only rule toggles do **not** apply at level-up (max-HP-at-L1,
  re-roll 1s & 2s); the modal doesn't mention them.
- Hit Die (sub-name-level): "Rolls 1d8"
- Flat-HP notice (at/beyond name level): "Past name level — gains a flat
  +{hp_after_name_level} HP, no Hit Die rolled."
- Action row:
  - No pending roll, sub-name-level: `[Roll HP]` `[Cancel]`
  - Pending roll, sub-name-level, Strict on: `Rolled: 6` `[Confirm Level Up]`
    `[Cancel]`
  - Pending roll, sub-name-level, Strict off: `Rolled: 6` `[Re-roll]`
    `[Confirm Level Up]` `[Cancel]`
  - At/beyond name level: `[Confirm Level Up]` `[Cancel]`

Cancel clears any pending roll for that class and closes the overlay.

## Tests

New (`tests/test_leveling.py` + `tests/test_advancement_routes.py`):

- `current_threshold` is 0 for a fresh L1 character; matches the
  progression entry for higher levels.
- `roll_pending_hp` stores into `pending_level_up`; refuses at max; refuses
  when XP short; refuses at/beyond name level; under Strict Mode refuses a
  second roll while a pending one exists; under Strict off allows it.
- `confirm_level_up` sub-name-level: requires a pending roll; appends it to
  `hp_rolls`; clears the pending entry; bumps `entry.level`.
- `confirm_level_up` at/beyond name level: succeeds with no pending roll;
  bumps `entry.level`; doesn't touch `hp_rolls`.
- `cancel_pending_level_up` clears one class's entry without affecting others
  and is idempotent.
- The legacy `level_up()` wrapper still works (existing tests cover this).
- Route smoke tests: roll → 303 + pending populated; confirm → 303 + level +1
  + hp_rolls appended; cancel → 303 + pending cleared; lock returns 400.

Update where needed:

- `tests/test_sheet_routes.py` (or equivalent) — assertions about the header
  Advance button / modal-advance presence must be updated to the new layout.
- The new progress-bar math (current-level-relative) gets a Jinja-level test
  if there's an existing template-render test pattern; otherwise it's covered
  by the engine `current_threshold` test plus a manual smoke check.

## Open follow-ups

- **Weapon-proficiency slots at level-up.** Engine needs to track unspent
  slots across levels; the modal would gain a slot picker when `adv.can_level`
  surfaces one. Out of scope for this change.
- **Spell progression at level-up.** Today new spell slots become available
  automatically (slot capacity is derived from class progression). New L1
  spells in the spellbook under `advanced_spell_books` are still copy-only;
  no UI change needed here.
