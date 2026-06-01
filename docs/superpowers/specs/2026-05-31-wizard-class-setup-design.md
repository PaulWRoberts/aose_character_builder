# Wizard Overhaul — Slice 5: Class Setup (P6)

**Date:** 2026-05-31
**Status:** Design approved, pending written-spec review

## Context

Fifth of the ~8-slice wizard overhaul (see Slice 1 spec for the decomposition).
Implements the target spec's **P6 — Class Setup**: merge HP + weapon
proficiencies + spells onto one page, implement Human **Blessed** HP, and
introduce the deferred **Human Racial Abilities** flag (gating + Human's
conditional ability modifiers).

### Rules correction recorded here

The optional **"Reroll 1s and 2s for 1st-level HP"** rule means **reroll the
die until it shows at least 3** — *not* "reroll exactly once and keep it." This
is already exactly what `roll_hp(min_die=3)` does, so **no dice change is
needed**. (The earlier "reroll exactly once" reading was mistaken.)

## Goal of Slice 5

1. Introduce the `human_racial_abilities` RuleSet flag with correct dependency
   gating, plus Human's conditional ability modifiers (+1 CHA / +1 CON).
2. Implement **Blessed** HP (roll twice, keep the better — single- and
   multi-class), gated on Human + the flag.
3. Lock HP to a single roll (consistent with abilities and gold).
4. Consolidate HP / proficiencies / spells into one **Class Setup** page.

The HP *derivation* (`aose/engine/hp.py`) is unchanged: it consumes the stored
per-class rolls and applies effective CON once. Blessed and the reroll rule are
purely **roll-time** logic; the winning rolls are what get stored.

## Design

### 1. Human Racial Abilities flag

**`aose/models/ruleset.py`** — add `human_racial_abilities: bool = False`.

**Rules/settings page** (extends Slice 1's "Advanced Options" group + JS):
- Renders in **Advanced Options**, with a **nested dependency**: enabled only
  when **Advanced is selected AND `lift_demihuman_restrictions` is checked**.
  The Slice-1 JS is extended to also disable `human_racial_abilities` whenever
  `lift_demihuman_restrictions` is unchecked.
- **Server enforcement** (`parse_ruleset_from_form`): force
  `human_racial_abilities = False` unless `separate_race_class` *and*
  `lift_demihuman_restrictions` are both true.
- Add to `RULE_LABELS`, `IMPLEMENTED_RULES` (fully wired this slice), and the
  Advanced Options entry in `RULE_GROUPS`. The "no pending badge" invariant
  holds because the effects below land in the same slice.

### 2. Human's conditional ability modifiers

**`aose/models/race.py`** — add
`optional_ability_modifiers: dict[Ability, int] = Field(default_factory=dict)`
(mirrors Slice 3's `ability_modifiers`). Populate **human** with CHA +1, CON +1;
keep human's descriptive `optional_ability_modifiers` feature text for the
sheet. All other races empty.

**Application** — extend the Slice-3/4 racial-application path so that
`optional_ability_modifiers` are folded into the modifiers **only when the
`human_racial_abilities` rule is on** (and naturally only humans carry them).
The combined modifier set is still clamped to [3, 18]. Concretely,
`_post_racial_abilities(draft, data)` adds `race.ability_modifiers` plus, when
the flag is on, `race.optional_ability_modifiers`, then clamps.

Because creation-final abilities flow into `spec.abilities`, the +1 CON
automatically increases HP (via effective CON in `hp.py`) and the +1 CHA shows
on the sheet — no extra wiring.

### 3. Blessed HP (roll twice, keep better)

**Eligibility:** `race_id == "human"` AND `human_racial_abilities` is on.
(The flag requires Advanced + lift, so Blessed is transitively Advanced-only;
Basic never gets it.)

**Roll-time logic** in the HP roll handler (each individual die uses
`roll_hp(hit_die, min_die=3 if reroll_1s_2s_hp_l1 else 1)` — unchanged):

- **Single-class, Blessed:** roll value A and value B; store the **higher** as
  `draft["hp_roll"]`.
- **Single-class, not Blessed:** one roll, stored as today.
- **Multi-class, Blessed:** roll **two complete sets** — set = one die per class
  — and keep the set with the larger **sum of rolls** (N and CON are identical
  across sets, so summed rolls is the correct comparison). Store the winning
  set's per-class rolls as `draft["hp_rolls"]`. **No per-class cherry-picking
  across sets.**
- **Multi-class, not Blessed:** one roll per class, as today.

Blessed is **automatic** — no UI choice. The page may note "Blessed: rolled
twice, kept the better result."

### 4. HP locked to one roll

HP is rolled **once and locked** (matching abilities and gold). The Class Setup
page shows a "Roll HP" action only while HP is unrolled; once rolled, it shows
the result and no re-roll affordance. To change it, the player cancels and
starts over. (The old `max_hp_at_l1` auto-population is already removed in
Slice 1.)

### 5. Page consolidation — the `class_setup` step

Replace the separate `hp`, `proficiencies`, and `spells` wizard steps with one
**`class_setup`** step (label "Class Setup"):

- `_wizard_steps`: drop `hp`/`proficiencies`/`spells`; insert a single
  `class_setup` step in their former position (after `[skill]`, before
  `equipment`). It is **always present**; proficiencies and spells are
  **sections within it**, shown only when `weapon_proficiency` /
  `draft["spellcasting"]` apply.
- `_next_incomplete_step`: `class_setup` is incomplete until HP is rolled AND
  (proficiencies chosen, if required) AND (spells chosen, if a caster).
- Routes: `GET /{draft_id}/class-setup` renders the page with sections in order
  **HP → Proficiencies → Spells**. The HP roll remains its own small server
  action (`POST .../class-setup/roll-hp`); proficiency and spell selections keep
  their existing validation (reuse the Slice-era handlers/engine), submitted
  from this page; a single **Continue** advances to `equipment` only when every
  applicable section is complete.
- The existing per-section engine logic (`proficiency`, `spells`) is unchanged
  — only the page/route wrapping is consolidated. STEP_LABELS updated; the
  breadcrumb now shows one "Class Setup" entry instead of three.

### 6. Downstream clears

`_apply_rule_changes`: when `human_racial_abilities` changes, clear `hp_roll` /
`hp_rolls` (Blessed eligibility changed) and `ability_adjustments` (post-racial
scores changed). Existing `weapon_proficiency` and class/race clears continue to
cover proficiencies and spells.

### 7. Tests

- Flag gating: `human_racial_abilities` forced off unless Advanced + lift;
  enabled otherwise; renders in Advanced Options; no pending badge.
- `Race.optional_ability_modifiers` loads for human; applied only when flag on
  AND race human; combined clamp at 18; non-humans unaffected.
- Blessed single-class (seeded RNG): keeps the higher of two rolls; non-Blessed
  rolls once.
- Blessed multi-class (seeded RNG): keeps the better **complete set**; a
  constructed case proves the cross-set cherry-pick total is *not* taken.
- HP effective CON reflects Human +1 CON when the flag is on.
- HP is locked after the first roll (no second roll possible via the route).
- `class_setup` step: breadcrumb shows one step; incomplete until HP + (prof) +
  (spells) done; sections appear/disappear with the proficiency/caster
  conditions; Continue gated correctly.
- `_apply_rule_changes` clears HP + adjustments when the flag toggles.

## Risks / notes

- Consolidating three steps into one is the bulk of the diff but is mostly
  route/template plumbing over unchanged engine logic — keep the proficiency and
  spell validators intact and only re-host their forms.
- Multi-class Blessed comparison is by summed rolls; document the tie rule
  (keep set A on a tie — arbitrary but deterministic).
- No migration (nothing deployed).
