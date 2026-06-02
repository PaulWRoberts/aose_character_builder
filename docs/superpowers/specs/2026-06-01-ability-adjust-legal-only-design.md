# Ability Score Adjustments — legal-only choices

**Date:** 2026-06-01
**Area:** Character creation wizard → Adjust Ability Scores step
**Status:** Approved (brainstorming) — ready for implementation plan

## Problem

The Adjust Ability Scores page lets a player lower ability scores in
increments of 1, which is not legal under AOSE. Two defects underlie this:

1. **Engine** — `validate_ability_adjustments` only enforces that the *total*
   points lowered equals `2 × total raised`. It accepts spreading a reduction
   across abilities by odd amounts (e.g. `STR +1, INT −1, WIS −1`), which
   produces a configuration (`INT 12, WIS 12`) that the rules cannot reach.
2. **UI** — the template renders freeform `<input type="number" step="1">`
   controls for both raise and lower, exposing the illegal single-point steps.

## Rule (as enforced after this change)

Each prime-requisite `+1` costs `−2` from a **single** lowerable ability.
Resulting invariants:

- Each individual lowered ability drops by an **even** amount (2, 4, …).
- **Total points lowered = 2 × total points raised** (no waste).
- A lowered ability may not drop below `max(9, class requirement)`.
- Only prime requisites are raisable (max 18); only STR/INT/WIS that are not a
  prime and not class-restricted are lowerable.

The first invariant is new enforcement; the rest already hold.

## Design

### 1. Engine — `aose/engine/ability_mods.py`

Add one check to `validate_ability_adjustments`: every individual lowered
amount must be even, else raise `AdjustmentError`. The existing total-balance,
floor, raisable/lowerable, and ceiling checks are unchanged. This closes the
`INT−1, WIS−1` loophole independently of the UI.

### 2. UI context — `_adjust_context` (`aose/web/wizard.py`)

Per row, additionally compute:

- `lower_options` — resulting scores stepping by 2 from `score` down to
  `floor` (e.g. score 13, floor 9 → `[13, 11, 9]`), paired with the delta
  (points lowered) each represents.
- `raise_options` — resulting scores stepping by 1 from `score` up to 18,
  paired with the delta (points raised).

The form-field contract is unchanged: fields stay `raise_<name>` /
`lower_<name>` carrying the **points moved** (delta), so `post_adjust` and the
engine need no signature changes.

### 3. Template — `aose/web/templates/wizard/adjust.html`

Replace the two `<input type="number">` controls with `<select>` elements:

- Visible option label = the resulting score (e.g. "11"); a "no change" option
  for the current score.
- Option value = the delta in points.

Illegal values (odd single-ability reductions, anything below floor / above 18)
are simply never rendered as options.

### 4. Live balance helper (vanilla JS, progressive enhancement)

A small inline script (matching the app's existing no-framework JS style)
recomputes on every `change`:

- **Points freed** = Σ of selected lower deltas.
- **Points spent** = Σ of selected raise deltas.

It shows a running tally, flags imbalance when `freed ≠ 2 × spent`, and disables
the **Next** button until balanced. With JS disabled the dropdowns still submit
and server-side `validate_ability_adjustments` is the backstop.

## Testing (TDD)

- **Engine:** odd single-ability lower (`{"STR":1,"INT":-1}`) raises
  `AdjustmentError`; even lower (`{"STR":1,"INT":-2}`) passes. Floor and
  total-balance tests retained.
- **Updated existing tests:** the tests that encode the now-illegal spread
  (`lower_INT:1, lower_WIS:1` / `{"STR":1,"INT":-1,"WIS":-1}`) move to a single
  `−2` (`lower_INT:2` / `{"STR":1,"INT":-2}`). Finalize assertions become
  STR 14 / INT 11 / WIS 13.
- **Route:** POST with an odd `lower_INT:1` is rejected (400). GET renders
  `<select>` options for the resulting scores and omits the illegal in-between
  values.

## Out of scope / notes

- No data, model, or storage-shape changes; no migrations (app is local,
  single-user).
- Wizard step ordering, breadcrumb, and cascading-clear behaviour are untouched.
