# Wizard Overhaul — Slice 2: Abilities

**Date:** 2026-05-31
**Status:** Design approved, pending written-spec review

## Context

Second of the ~8-slice wizard overhaul (see Slice 1 spec,
`2026-05-31-wizard-rules-creation-method-design.md`, for the full
decomposition and the pre-resolved cross-cutting decisions). This slice
implements the target spec's **P2 — Abilities**.

Recall the relevant pre-resolved decision: **alternate ability-roll methods are
removed entirely** — the wizard always rolls **3d6 in order**.

## Goal of Slice 2

1. Lock ability generation to **3d6 down the line** and rip out the
   `ability_roll_method` rule and all its supporting code (4d6 roller, arrange
   mode + UI, settings radio, reroll affordance).
2. Add a **sub-par character flag** and a softer **extremely-low-score
   warning**, surfaced on the abilities page. Both are warnings only — never an
   automatic discard or reroll.

The ability order is unchanged and already correct:
**STR, INT, WIS, DEX, CON, CHA** (`ABILITY_ORDER` in `wizard.py`).

### Out of scope (other slices)

- The character **name** continues to be collected on this page; moving it to
  P7 Identity & Background is **Slice 6**.
- Aggregating these warnings into the Final Review page is **Slice 8** — this
  slice only surfaces them on the abilities step. The engine helper added here
  is what Slice 8 will reuse.

## Design

### 1. Lock to 3d6 in order — removals

**`aose/models/ruleset.py`**
- Remove the `ability_roll_method` field and the `AbilityRollMethod` type alias.

**`aose/engine/dice.py`**
- Remove `roll_4d6_drop_lowest_in_order`. `roll_3d6_in_order` is the only
  ability roller. (`roll_hp` is untouched here; its `take_max` path is removed
  by Slice 1, not this slice.)

**`aose/web/wizard.py`**
- Remove `_METHOD_LABELS` and `_roll_ability_values`; `_seed_draft_abilities`
  reduces to: roll `roll_3d6_in_order`, store into `draft["abilities"]`, and
  drop all `abilities_pool` / arrange handling.
- `new_wizard` keeps seeding abilities once at draft creation (unchanged call).
- `_apply_rule_changes`: the first branch becomes simply
  `if "abilities" not in draft:` (a safety re-seed) — the
  `ability_roll_method`-change trigger is gone.
- `get_abilities`: drop `arrange_mode`, `pool`, and `method_label` from the
  context; add the warning context (see §2).
- `post_abilities`: delete the entire arrange-mode validation block (the
  permutation/pool check). It now only reads and stores `name`.
- **Remove the reroll route** `post_reroll` (`POST /{draft_id}/reroll`)
  entirely. Abilities are rolled once at draft creation and locked; the only
  way to get a different roll is to cancel and start a new character.

**`aose/web/settings_routes.py`**
- Remove `ability_roll_method` from `CHOICE_GROUPS` and
  `IMPLEMENTED_CHOICE_GROUPS`. (`parse_ruleset_from_form` derives choice fields
  from `CHOICE_GROUPS`, so it needs no separate edit.) `encumbrance` remains the
  only choice group.

**`aose/web/templates/wizard/abilities.html`**
- Remove the arrange-mode banner, the `<select>` dropdowns + their `arrange-mod`
  spans, the live-update `<script>`, and the **"Re-roll All"** form/button.
- The page becomes a static read-only table of the six rolled scores + mods,
  plus the name field and the Next button. Keep the title
  "Abilities & Name" (name moves out in Slice 6).
- Add the warning banner(s) from §2.

### 2. Sub-par flag + low-score warning

**Engine helper (pure).** Add to `aose/engine/ability_mods.py` (cohesive — it
already owns ability-score logic) a function that derives warnings from a score
map, e.g.:

```python
def ability_warnings(abilities: dict[str, int]) -> dict:
    """Non-blocking creation warnings derived purely from ability scores."""
    subpar = all(v <= 8 for v in abilities.values())          # all six ≤ 8
    rock_bottom = [name for name, v in abilities.items() if v == 3]
    return {"subpar": subpar, "rock_bottom": rock_bottom}
```

- **Sub-par flag:** `True` when *all six* scores are 8 or lower (the AOSE
  "may start over" condition). Surface as a prominent but non-blocking warning.
- **Low-score warning:** lists any ability that rolled exactly **3**.

Computed on render from `draft["abilities"]` — not persisted on the draft.

**Surfacing.** `get_abilities` passes the warnings into the context;
`abilities.html` renders:
- If `subpar`: a warning banner — "All six scores are 8 or lower. This is a
  sub-par character; the rules let you start over." Since reroll is removed, the
  remedy is the existing Cancel action → start a new character. (Non-blocking;
  the player may proceed.)
- If `rock_bottom` non-empty: a softer note naming the affected ability/ies
  ("Strength is 3 — extremely low.").

Neither warning blocks the Next button.

### 3. Tests

- **Remove/replace:** the 4d6 test in `test_dice.py`; the
  `ability_roll_method` cases in `test_choice_rules.py` and `test_settings.py`;
  any arrange-mode assertions in `test_wizard.py`; the reroll-route test in
  `test_wizard.py` / `test_wizard_back_nav.py`; the field in `test_models.py`
  and `examples/thorin.json` if present.
- **Add:**
  - `ability_warnings`: all-≤8 → `subpar True`; a single 3 → listed in
    `rock_bottom`; a normal spread → both empty.
  - The abilities page renders the sub-par banner when all scores ≤ 8, and the
    low-score note when an ability is 3.
  - `POST /{draft_id}/reroll` returns 404/405 (route removed).
  - The settings/rules pages render with no ability-method choice group and no
    arrange UI.

## Risks / notes

- Several test files reference the removed pieces; expect broad but shallow test
  churn. None of it touches saved-character data (no migration — nothing
  deployed).
- Locking abilities at draft creation means a player only sees the roll after
  clearing the rules step. Acceptable and intended (strict 3d6-in-order); not
  changing *when* the roll happens avoids disturbing `new_wizard` and the
  draft-seeding tests.
- After this slice, abilities are immutable per draft (no method change, no
  reroll, no arrange), so `_clear_after_abilities` is only ever reached via the
  Slice-1 `separate_race_class` toggle path — still correct, just narrower.
