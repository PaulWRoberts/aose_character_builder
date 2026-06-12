# Combat Talents + Level-Up Choices — Design

**Date:** 2026-06-11
**Status:** Approved (brainstorm), pending implementation plan
**Branch (proposed):** `feat/combat-talents`

## Summary

Add the **Combat Talents** optional rule for fighters (Carcass Crawler #1, by Gavin
Norman): a fighter may select one combat talent at **1st, 5th, and 10th** level.
Six talents: Cleave, Defender, Leader, Main gauche, Slayer, Weapon specialist.

Because the wizard always creates characters at level 1, the level-1 talent is
picked at creation (existing feature-choice plumbing) while the level-5 and
level-10 talents must be picked **after creation, during level-up**. No such
post-creation "spend a slot you just earned" flow exists today — and the same gap
already exists for **weapon proficiency** slots (the slot count grows with level
but there has never been a UI to spend the new slots). So this work also builds
the **shared level-up choice mechanism** and uses it to close the proficiency gap.

## Goals

1. Combat Talents as a fighter-only, rule-gated talent table with a level-scaled
   pick count (1 @ L1, +1 @ L5, +1 @ L10).
2. Two talents drive real sheet mechanics via existing plumbing:
   - **Slayer** — conditional `+1 attack / +1 damage vs <chosen enemy type>`.
   - **Weapon specialist** — `+1 attack / +1 damage` with a chosen weapon type,
     reusing the existing weapon-specialisation automation.
3. The other four talents (Cleave, Defender, Leader, Main gauche) are descriptive
   text on the sheet — they require a specific in-play action and cannot be folded
   into a static sheet number.
4. A **shared "unspent capacity" level-up choice mechanism**, used by both combat
   talents and weapon proficiencies, surfaced in the level-up modal and as an
   inline safety-net on the sheet.

## Non-goals

- Automating the four action-driven talents (bonus attacks on a kill, foe
  penalties, retainer morale, per-round AC/attack toggle). They stay text.
- Re-validating the existing weapon-proficiency base slot counts / penalties
  (martial 4/−2, semi 3/−3, non-martial 1/−5). Reused unchanged; confirmed correct
  by the user on 2026-06-11.
- Surfacing conditional *damage* as a new headline breakdown (see "Known display
  scope" below).

## The rule (verbatim intent)

A fighter may select one talent at 1st, 5th, and 10th levels (distinct picks):

1. **Cleave** — on a killing blow in melee with multiple foes, immediately make a
   second attack at −2 vs another foe. *(text)*
2. **Defender** — foes in melee with the fighter attack other characters at −2.
   *(text)*
3. **Leader** — commanded mercenaries/retainers within 60′ get +1 morale/loyalty;
   all allies within 60′ get +1 to saves vs fear. *(text)*
4. **Main gauche** — when wielding a dagger off-hand (in place of a shield), each
   round choose +1 AC **or** +1 attack. *(text)*
5. **Slayer** — +1 attack and damage vs a chosen enemy type (undead, dragons,
   giants, …), chosen when the talent is taken. *(automated, conditional)*
6. **Weapon specialist** — +1 attack and damage with a chosen weapon type.
   **Disallowed when the optional weapon proficiency rule is active.** *(automated,
   reuses specialisation)*

## Architecture

### Data model

`aose/models/ruleset.py`
- `combat_talents: bool = False` — new optional flag.

`aose/models/choice.py`
- `FeatureChoice` gains:
  - `requires_rule: str | None = None` — group applies only when that RuleSet flag
    is true. Combat talents: `requires_rule: "combat_talents"`.
  - `pick_by_level: dict[int, int] | None = None` — banded **total** pick count by
    the granting class's level (reuses `_band_lookup`). Combat talents:
    `{1: 1, 5: 2, 10: 3}`. When set, overrides the flat `pick`.
- `ChoiceOption` gains:
  - `excluded_when_rule: str | None = None` — option hidden when that flag is on.
    Weapon specialist: `excluded_when_rule: "weapon_proficiency"`.
  - `param: OptionParam | None = None` — new small model:
    `OptionParam{kind: Literal["text", "weapon"], label: str}`.

`aose/models/character.py`
- `CharacterSpec.choice_params: dict[str, str] = {}` — option_id → free-text param.
  Stores Slayer's enemy type. Weapon specialist's weapon reuses the existing
  `weapon_specialisations` list (no new field).

### Engine

`aose/engine/features.py`
- When resolving a parameterised **text** option's `granted_modifiers`, substitute
  `{param}` from `spec.choice_params` into the modifier `condition` string. Slayer
  declares `attack +1` and `damage +1` with `condition: "vs {param}"`, resolving to
  e.g. `"vs undead"`. Flows through the existing situational-attack display in
  `attack_modifiers_detail`.
- Group resolution (`_active_choice_groups` / wherever groups are enumerated) must
  honor `requires_rule` and `pick_by_level`.

`aose/engine/attacks.py`
- Widen the specialisation gate (currently `if spec.ruleset.weapon_proficiency:` at
  ~line 150): apply `spec_hit`/`spec_dmg` when `weapon_proficiency` **or**
  `combat_talents` is on. The non-proficiency **penalty** stays
  `weapon_proficiency`-only. The two rules are mutually exclusive for
  specialisation (Weapon specialist is hidden under proficiency), so no
  double-counting.

**Unspent-capacity providers** (new — module TBD during planning, likely a small
`engine/level_choices.py` or extensions to `proficiency.py` + `feature_choices.py`):
- **Talents:** `earned = _band_lookup(fighter_level, pick_by_level)`,
  `spent = len(spec.feature_choices.get("combat_talents", []))` (group id =
  `combat_talents`).
- **Proficiencies:** `earned = total_proficiency_slots(pairs)`,
  `spent = slots_spent(spec)` — both already exist in `proficiency.py`.
- Each provider exposes what a picker needs: remaining count, the option/weapon
  source, the validation rule, and the apply endpoint. A subsystem contributes a
  picker whenever `spent < earned`.

> **When are slots/talents earned?** Proficiencies: each time the class's THAC0
> improves (fighter: levels 4, 7, 10, 13 → 4/5/6/7/8 slots). Talents: the
> `pick_by_level` bands (1/5/10). Different schedules — hence the generic
> capacity model rather than hardcoded thresholds.

### Automation hooks

- **Slayer** → `OptionParam{kind: "text", label: "Enemy type"}` → free-text →
  conditional `attack/damage +1 vs {type}` via the modifier pipeline → shows as a
  conditional attack line.
- **Weapon specialist** → `OptionParam{kind: "weapon", label: "Weapon"}` → dropdown
  of the fighter's allowed base weapons → chosen weapon id written to
  `spec.weapon_specialisations` → existing `_profile_for` +1/+1 fires via the
  widened gate. Hidden entirely when `weapon_proficiency` is on.
- **Cleave / Defender / Leader / Main gauche** → descriptive text under the
  fighter's features (chosen options already render through `iter_reached`).

### Web / UI

`aose/web/` (routes + templates)
- A shared **choice-picker partial**: pick-or-roll a talent (with the param input
  when the option has one) / add a proficiency (weapon + optional specialise).
  Mirrors the wizard's `roll_choice` / `validate_choice` logic.
- Rendered in **two** places sharing the partial + endpoints:
  1. Inside the **level-up modal** after the HP roll/confirm, when the new level
     unlocked capacity.
  2. **Inline on the sheet** whenever `spent < earned` (safety net for deferral,
     multi-level jumps, and max-level characters who cannot open the level-up
     modal).
- New endpoints: spend a talent (option id + param), spend a proficiency slot
  (weapon id + optional specialise). Validation: distinct picks; weapon class-
  allowed; specialise requires a martial class; Weapon specialist refused when
  `weapon_proficiency` is on.

### Settings / wizard

- `combat_talents` checkbox in `/settings` and the wizard `/rules` step, fully
  integrated end-to-end (no "pending" badge — the existing regression test that
  guards this is extended to the new flag).
- **Cascading clear** in `wizard.py` `_apply_rule_changes`: toggling
  `combat_talents` off clears `feature_choices["combat_talents"]`, the related
  `choice_params`, and any talent-granted `weapon_specialisations`.
- The **level-1 talent** flows through the existing feature-choices UI at the
  `class_setup` wizard step: `_active_choice_groups` filters by `requires_rule`,
  pick count honors `pick_by_level`, and the param inputs (Slayer text field,
  Weapon specialist weapon dropdown) are added to that template.

### Data

`data/classes/fighter.yaml`
- Add a `feature_choices` entry: the combat-talents group with
  `requires_rule: combat_talents`, `pick_by_level: {1: 1, 5: 2, 10: 3}`, and six
  `options` (Slayer with a text param + conditional granted_modifiers; Weapon
  specialist with a weapon param + `excluded_when_rule: weapon_proficiency`; the
  other four text-only). Fighter-only because it lives on the fighter class
  (data, not code).

## Known display scope

`attack_modifiers_detail` surfaces situational **attack** modifiers as conditional
lines, but there is no equivalent headline for conditional **damage**. Slayer
emits both `attack +1` and `damage +1 vs <type>`; the attack side shows as a
conditional line, and the talent's descriptive sheet text states the full
"+1 attack and damage vs <type>". We will **not** invent a new conditional-damage
breakdown for this feature.

## Edge cases

- `combat_talents` + `weapon_proficiency` both on: combat talents still available;
  only the Weapon specialist option is hidden.
- Multi-class fighter: the talent group lives on the fighter class, so pick count
  resolves against the fighter entry's level via `iter_reached`.
- Distinct picks: a fighter cannot take the same talent twice (existing
  `validate_choice` distinctness).
- Weapon specialist under combat talents grants specialisation **without** a
  matching `weapon_proficiencies` entry (no proficiency system active);
  `_profile_for` checks `is_specialised` independently of `is_proficient`, so the
  +1/+1 applies and no non-proficiency penalty is levied.

## Testing

- **Engine:** pick-count banding (1/5/10); `{param}` substitution into condition;
  specialisation gate across rule combinations (proficiency-only, talents-only,
  both, neither); Weapon-specialist exclusion under proficiency.
- **Web:** wizard L1 talent pick (incl. param inputs); level-up L5/L10 talent
  pickers; weapon-proficiency slot spending at L4/L7/L10/L13; cascading clear on
  rule toggle-off; the settings "no pending badge" regression guard extended to
  `combat_talents`.

## Phasing (for the implementation plan)

- **Phase A** — shared unspent-capacity mechanism + weapon-proficiency level-up
  spending retrofit.
- **Phase B** — combat-talents content (model fields, fighter data) + the two
  automation hooks (Slayer conditional, Weapon specialist specialisation) + wizard
  L1 + settings/rules integration.

(The planning step sequences this.)
