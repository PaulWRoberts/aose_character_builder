# Wizard Overhaul — Slice 1: Rules Page & Creation Method

**Date:** 2026-05-31
**Status:** Design approved, pending written-spec review

## Context

This is the first of an ~8-slice overhaul of the AOSE character-creation
wizard (full target described in the user's wizard-flow specification). Each
slice is an independent spec → plan → implement cycle. The agreed decomposition:

1. **Rules page + creation method** ← *this slice*
2. Abilities (lock to 3d6-in-order, sub-par flag)
3. Race (racial ability modifiers, languages, granted abilities)
4. Ability Score Adjustments (new P5 page)
5. Class Setup (merge HP + proficiencies + spells; HP rolling restrictions; Human Blessed + Human Racial Abilities flag)
6. Identity & Background (name/alignment/languages/skill; alignment filtering; INT languages)
7. Equipment (remove gold reroll)
8. Final Review + validation gate

### Pre-resolved cross-cutting decisions

- **Racial ability modifiers are real** in AOSE *Advanced* (Advanced-only;
  e.g. Dwarf −1 CHA / +1 CON; clamp bonuses at 18, penalties at 3). Handled in
  Slice 3, not here.
- **Alternate ability-roll methods removed entirely** (Slice 2): the wizard
  always rolls 3d6 in order.
- **The app is not deployed** — no backward-compat migrations for any
  data-shape change in any slice.

## Goal of Slice 1

Make "character creation method" a visible top-level choice and reorganise the
rules page (wizard + global settings) to match the target spec's groupings,
while merging the two demihuman optional rules into one and dropping the unused
"Max HP at 1st level" rule. This slice is primarily **presentation plus two
small `RuleSet` changes** — not a refactor of the creation flow.

Explicitly **out of scope** for this slice:

- The Human Racial Abilities flag and Blessed HP (Slice 5).
- Removing `ability_roll_method` / the arrange UI (Slice 2) — it continues to
  render on the rules page until then.
- Any change to how Basic vs Advanced actually drives the race/class steps —
  that behaviour already exists via `separate_race_class`.

## Design

### 1. `RuleSet` model (`aose/models/ruleset.py`)

- **Remove** `max_hp_at_l1`.
- **Replace** `demihuman_class_restrictions` and `demihuman_level_limits` with a
  single field:

  ```python
  lift_demihuman_restrictions: bool = False
  ```

  Default `False` ⇒ class restrictions **and** level caps apply (today's
  default). `True` ⇒ both are lifted together.
- **Keep** `separate_race_class: bool = True` unchanged as the storage for the
  creation method. Advanced ⇔ `True` (separate race & class); Basic ⇔ `False`
  (race-as-class). No new field is introduced — the method is purely a
  presentation layer over this boolean.
- No migration code.

### 2. Rules-page presentation

Both the wizard rules step (`templates/wizard/rules.html`) and the global
settings page (`templates/settings.html`) render from the shared structures in
`settings_routes.py` (`RULE_GROUPS`, `CHOICE_GROUPS`, `RULE_LABELS`,
`IMPLEMENTED_RULES`). Both pages get the same new layout.

**Character Creation Method** — a dedicated section rendered *above* the rule
groups (not part of `RULE_GROUPS`): a two-option radio.

- `Basic` — "Choose a class; the class determines race. No separate race step.
  Multi-class and lifting demihuman restrictions are unavailable."
- `Advanced` — "Choose race and class separately. Advanced optional rules become
  available."

The radio is bound to `separate_race_class` (Advanced = checked/True).

**Regrouped `RULE_GROUPS`** (order as listed):

| Group | Flags (in order) | Notes |
|---|---|---|
| Advanced Options | `multiclassing`, `lift_demihuman_restrictions` | disabled in Basic |
| Character Options | `weapon_proficiency`, `secondary_skills` | |
| Survivability & Logistics | `reroll_1s_2s_hp_l1` | + `encumbrance` choice group renders here |
| Magic | `advanced_spell_books` | |
| Combat | `variable_weapon_damage`, `ascending_ac` | |

**Render order (firm for this slice):** the method section, then the five
rule-group fieldsets in the table order, then the choice-group fieldsets
(`encumbrance`, and `ability_roll_method` until Slice 2 removes it). The
Survivability & Logistics rule group contains `reroll_1s_2s_hp_l1`;
`encumbrance` belongs to it conceptually but renders as its own choice-group
fieldset immediately after the rule groups. Fully interleaving `encumbrance`
into the Survivability group is cosmetic and explicitly not required here —
keeping the existing "rule groups then choice groups" rendering avoids
restructuring the shared template machinery.

The "Advanced Options" group is marked (e.g. a flag in the `RULE_GROUPS` tuple
or a known group name) so the template can attach the disabling hook.

### 3. Gating behaviour

- **Display:** the Advanced Options group is *always rendered* but its inputs
  are **disabled and visually greyed when Basic is selected**. A small
  vanilla-JS handler (consistent with the project's existing
  progressive-enhancement JS) toggles the `disabled` attribute on those inputs
  whenever the method radio changes. With JS off, the inputs remain enabled and
  the server still enforces correctness.
- **Server is the source of truth:** `parse_ruleset_from_form` reads the method
  radio, sets `separate_race_class` accordingly, and — when Basic — forces
  `multiclassing = False` and `lift_demihuman_restrictions = False` regardless
  of posted values.

### 4. Engine / wizard touch-points (mechanical rename + deletion)

- `aose/engine/leveling.py` (~L65): `if spec.ruleset.demihuman_level_limits:` →
  `if not spec.ruleset.lift_demihuman_restrictions:`.
- `aose/web/wizard.py`:
  - `_class_allowed_for_race` (~L511): `if not ruleset.demihuman_class_restrictions: return True`
    → `if ruleset.lift_demihuman_restrictions: return True`.
  - level-cap lookup (~L550): `if ruleset.demihuman_level_limits` →
    `if not ruleset.lift_demihuman_restrictions`.
  - HP step (~L870, L908, L923) and `_apply_rule_changes` (~L339, L355):
    delete all `max_hp_at_l1` handling. HP at 1st level is always rolled (with
    the optional reroll-1s/2s). The `roll_hp(..., take_max=...)` call sites
    drop the `take_max` path for L1 creation.
  - `_apply_rule_changes`: add a defensive clear — when
    `lift_demihuman_restrictions` changes, clear class and downstream
    (`_clear_after_race`-style), mirroring a race change, so an on→off flip
    can't leave a now-illegal class/level pick on the draft.
- `aose/sheet/view.py` (~L39): rules-summary label map — drop `max_hp_at_l1`,
  replace the two demihuman labels with one for `lift_demihuman_restrictions`.

### 5. `settings_routes.py` updates

- `RULE_LABELS`: drop `max_hp_at_l1`; replace the two demihuman labels with
  `"lift_demihuman_restrictions": "Lift Demihuman Class & Level Restrictions"`.
- `IMPLEMENTED_RULES`: drop `max_hp_at_l1` and the two demihuman entries; add
  `lift_demihuman_restrictions` (it is fully wired by this slice).
- `RULE_GROUPS`: rebuild to the table in §2.
- `parse_ruleset_from_form`: method-radio handling + Basic enforcement (§3).

### 6. Tests

- Update for the new flag set / parsing: `test_demihuman_rules.py`,
  `test_settings.py`, `test_wizard_rules_step.py`, `test_dice.py` (max-HP
  paths), `test_storage.py`/`test_models.py` if they assert ruleset fields, and
  `examples/thorin.json` if it carries any removed/renamed flag.
- New tests:
  - Selecting **Basic forces `multiclassing` and `lift_demihuman_restrictions`
    to `False`** server-side even if posted true.
  - `lift_demihuman_restrictions=True` lifts both class restrictions and level
    caps (one test replacing the two old separate-flag tests).
  - Changing `lift_demihuman_restrictions` mid-wizard clears class + downstream.
  - The "no pending badge" regression passes with the new `IMPLEMENTED_RULES`.

## Risks / notes

- The method radio breaks the page's pure checkbox/radio-from-data pattern with
  one bespoke section; kept deliberately small and shared by both pages.
- Dropping `max_hp_at_l1` removes a `roll_hp(take_max=True)` code path at
  creation; confirm no other caller depends on it (level-up HP is unaffected).
- Basic + multiclassing is already rejected downstream in `post_class`; the new
  server enforcement makes it impossible to *set* the flag in Basic, which is
  the stronger guarantee the spec wants.
