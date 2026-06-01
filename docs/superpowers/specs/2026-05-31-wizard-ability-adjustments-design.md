# Wizard Overhaul — Slice 4: Ability Score Adjustments (P5)

**Date:** 2026-05-31
**Status:** Design approved, pending written-spec review

## Context

Fourth of the ~8-slice wizard overhaul (see Slice 1 spec for the decomposition).
Implements the target spec's **P5 — Ability Score Adjustments**, a brand-new
wizard page. It plugs into the score-storage pattern established by Slice 3
(spec stores creation-final; the draft keeps the rolled base).

## The rule (as resolved)

After race and class are chosen, a player **may** trade points down from
eligible abilities to raise a prime requisite:

- **Raise:** only prime-requisite abilities (union of prime reqs across all
  selected classes), each capped at **18**.
- **Lower base set:** only **STR / INT / WIS** that are *not* a prime requisite
  of any selected class.
- **Per-class restriction layer:** a class may forbid lowering specific
  abilities on top of the base set. In the current data, **acrobat, assassin,
  and thief forbid lowering STR** (documented today only as the prose feature
  `adjust_ability_scores`).
- **Conversion:** exactly **2 points lowered → 1 point raised, no waste**
  (`lowered_total == 2 × raised_total`). Raised points may be distributed across
  multiple prime requisites.
- **Floor:** a lowered ability may not drop below `max(9, the highest selected
  class's requirement for that ability)`.
- The page is **always shown** (Basic and Advanced); making zero adjustments
  and continuing is valid. No new RuleSet flag.

Adjustments operate on the **post-racial** scores (the Advanced sequence:
roll → racial mods → choose class → adjust).

## Design

### 1. Model + data

**`aose/models/character_class.py`** — add:

```python
non_reducible_abilities: list[Ability] = Field(default_factory=list)
```

Abilities this class forbids lowering, layered on top of the base derivation.
Populate `[STR]` for **acrobat, assassin, thief**; keep their descriptive
`adjust_ability_scores` feature text for the sheet (only the enforcement moves
to the typed field). All other classes default to empty.

### 2. Engine helpers (pure, in `aose/engine/ability_mods.py`)

```python
def adjustable_abilities(classes) -> dict:
    """{'raisable': set[str], 'lowerable': set[str]} from the selected classes.
    raisable = union of prime_requisites.
    lowerable = {STR,INT,WIS} − raisable − union(non_reducible_abilities)."""

def validate_ability_adjustments(post_racial: dict[str,int], classes,
                                  adjustments: dict[str,int]) -> None:
    """Raise AdjustmentError unless every rule holds:
      - raised abilities ⊆ raisable; lowered ⊆ lowerable
      - lowered_total == 2 * raised_total  (exact, no waste)
      - each lowered post-value ≥ max(9, class requirement for that ability)
      - each raised post-value ≤ 18"""

def apply_ability_adjustments(scores: dict[str,int],
                              adjustments: dict[str,int]) -> dict[str,int]:
    """scores + adjustments (no clamping here — validation already bounded it)."""
```

`AdjustmentError(ValueError)` mirrors the existing `SpellError` pattern.

### 3. Score-flow helpers (wizard) — extends Slice 3

Slice 3 introduced `_effective_abilities` (= base + racial). Slice 4 splits it
into two named helpers to make the "before vs after adjustment" boundary
explicit:

- `_post_racial_abilities(draft, data)` — base, plus racial mods when Advanced.
  *(This is the renamed Slice-3 helper.)* Used by the **class step** requirement
  check and as the input/baseline for the **adjust step**.
- `_creation_abilities(draft, data)` — `_post_racial_abilities` then
  `apply_ability_adjustments(..., draft.get("ability_adjustments", {}))`. Used
  by the **HP step** CON modifier, **finalize**, and **review**.

`_draft_to_spec`: `CharacterSpec.abilities = _creation_abilities(draft, data)`.
Because the saved scores are post-adjustment, `leveling.py`'s prime-requisite
XP multiplier automatically reflects the raised prime requisite — which is the
whole point of the adjustment. No leveling change needed.

### 4. New wizard step `adjust`

- **Order:** inserted **after `class`, before `alignment`** in `_wizard_steps`
  and `_next_incomplete_step`; add to `STEP_LABELS` (e.g. "Ability Adjustments").
  (Later slices reshuffle the surrounding steps; this is correct for the
  current flow.)
- **Completion marker:** the step is "done" once `"ability_adjustments"` is a
  key on the draft (set to `{}` when the player continues without adjusting).
- **Downstream clears:** add `ability_adjustments` to `_clear_after_abilities`,
  `_clear_after_race`, and `_clear_after_class` — any change to abilities, race,
  or the class set invalidates a stored adjustment (raisable/lowerable and the
  floors all depend on them).
- **GET `/{draft_id}/adjust`:** show each ability's post-racial score, mark
  raisable vs lowerable, and provide an allocation form. A small vanilla-JS
  preview may show the running raised/lowered totals and disable illegal moves;
  the **server `validate_ability_adjustments` is the source of truth**.
- **POST `/{draft_id}/adjust`:** parse the per-ability deltas, call
  `validate_ability_adjustments` (400 on failure), store
  `draft["ability_adjustments"] = {ability: delta}` (omit zeros), and continue.

### 5. Tests

- `CharClass` accepts `non_reducible_abilities`; acrobat/assassin/thief load
  with `[STR]`; others empty.
- `adjustable_abilities`: fighter → raisable {STR}, lowerable {INT,WIS};
  magic-user → raisable {INT}, lowerable {STR,WIS}; thief → raisable {DEX},
  lowerable {INT,WIS} (STR removed by the restriction layer); multi-class
  fighter/magic-user → raisable {STR,INT}, lowerable {WIS}.
- `validate_ability_adjustments`: exact 2:1 passes; 3-down/1-up fails (waste);
  lowering below 9 fails; lowering below a class requirement fails; raising
  above 18 fails; lowering a prime fails; raising a non-prime fails; lowering a
  class-restricted STR fails.
- `_creation_abilities` / finalize: spec.abilities reflects the adjustment; the
  class-requirement check is evaluated **pre**-adjustment (post-racial only).
- Step gating: `adjust` appears after `class`, before `alignment`, in both
  Basic and Advanced; it clears when race or class changes.
- Prime-req XP: raising a prime requisite increases the saved character's
  prime-requisite XP multiplier (one focused `leveling` test).

## Risks / notes

- The allocation UI is the fiddliest part; keep the page server-validated so a
  JS-light implementation is still correct. Exact widget choice (steppers vs
  number inputs) is an implementation detail, not a spec requirement.
- The restriction layer is modelled as **forbid-only** (classes can remove
  abilities from the lowerable set, never add). That covers the entire current
  dataset; revisit only if a future class needs to *expand* the set.
- No migration (nothing deployed).
