# Wizard Overhaul — Slice 3: Race

**Date:** 2026-05-31
**Status:** Design approved, pending written-spec review

## Context

Third of the ~8-slice wizard overhaul (see Slice 1 spec for the decomposition
and cross-cutting decisions). Implements the target spec's **P3 — Race**.

Pre-resolved decision in play: **AOSE Advanced applies racial ability-score
modifiers** (Advanced-only; clamp bonuses at 18, penalties at 3).

## Findings that shape this slice

- The **display** of race data already exists: `sheet/view.py` renders
  `race.languages` and every `race.features` entry (including the "Ability
  Modifiers" feature's descriptive text).
- The **modifier data already exists** in every demihuman race YAML under
  `features[].mechanical.ability_modifiers` — but is **applied nowhere**:
  - dwarf, duergar: CHA −1, CON +1
  - elf, drow: CON −1, DEX +1
  - halfling: DEX +1, STR −1
  - half-orc: CHA −2, CON +1, STR +1
  - gnome, half-elf, svirfneblin: **none** (no modifier feature)
  - human: CHA +1, CON +1 but tagged `optional_rule: true` → **Slice 5**
- Human's other "racial abilities" (Blessed, Decisiveness, Leadership) are also
  features tagged `optional_rule` → **Slice 5**.

So the only genuinely new work here is **applying the unconditional demihuman
modifiers**, and wiring the modified scores into the downstream consumers.

## Goal of Slice 3

1. Promote racial ability modifiers to a typed field on `Race`.
2. Apply them at creation in **Advanced mode only**, with the 18/3 clamp.
3. Store the **creation-final** scores on the saved character and make the
   wizard's downstream steps use the modified scores.

### Out of scope

- Human's conditional modifiers + Blessed/Decisiveness/Leadership → **Slice 5**.
- The INT-based additional-language system → **Slice 6** (race languages already
  display today; nothing new here).
- P5 ability-score adjustments → **Slice 4** (this slice establishes the
  storage pattern Slice 4 plugs into).

## Design

### 1. Model + data

**`aose/models/race.py`** — add, mirroring the existing typed ability dicts:

```python
ability_modifiers: dict[Ability, int] = Field(default_factory=dict)
```

**Race YAMLs** — for each demihuman race that has the "Ability Modifiers"
feature, populate the new top-level `ability_modifiers` and remove the now
redundant `mechanical.ability_modifiers` sub-dict. **Keep the descriptive
feature** (id/name/text) so the sheet still lists "Ability Modifiers: –1 CHA,
+1 CON" — only the duplicated mechanical block goes. Races without modifiers
keep an empty field. **Do not** touch human's `optional_ability_modifiers`
feature (Slice 5 owns it).

### 2. Engine helper (pure, cycle-free)

Add to `aose/engine/ability_mods.py` (cohesive with `ability_modifier` and the
Slice-2 `ability_warnings`):

```python
def apply_racial_modifiers(base: dict[str, int], race) -> dict[str, int]:
    """base + race.ability_modifiers, each score clamped to [3, 18].
    Bonuses that would exceed 18 and penalties that would drop below 3 are
    ignored (i.e. clamped), per the Advanced creation rule."""
```

This is the single place the clamp lives. It does not consult the ruleset —
callers decide *whether* to apply it (Advanced only).

### 3. Score storage & flow

- **Draft** keeps the rolled base in `draft["abilities"]` unchanged. Race
  selection does **not** mutate it.
- A wizard helper derives the **effective creation abilities**:

  ```python
  def _effective_abilities(draft, data) -> dict[str, int]:
      base = draft["abilities"]
      rs = _ruleset_of(draft)
      if not rs.separate_race_class or "race_id" not in draft:
          return dict(base)                      # Basic, or race not yet chosen
      return apply_racial_modifiers(base, data.races[draft["race_id"]])
  ```

- **Finalize** (`_draft_to_spec`): `CharacterSpec.abilities = _effective_abilities(...)`
  — i.e. the saved character stores creation-final scores (Advanced ⇒ includes
  racial mods; Basic ⇒ equals the rolled base). The rolled base remains
  recoverable as `final − race.ability_modifiers`. **Slice 4 inserts P5
  adjustment deltas into this computation just before finalize.**
- Because `spec.abilities` is now creation-final, existing consumers need **no
  change**: `leveling.py` prime-requisite XP, `hp.py` CON, saves, and the magic
  `effective_abilities` (which composes magic mods on top of `spec.abilities`)
  all automatically use the modified scores.

### 4. Wizard step ripples (use modified scores in Advanced)

- **Race step** (`get_race` / `race.html`): display the rolled score, the
  racial modifier, and the resulting effective score per ability, so the player
  sees the adjustment. Race **minimum requirements continue to be checked
  against the rolled base** (`post_race` unchanged in that respect).
- **Class step** (`get_class` / `post_class`): class **minimum requirements are
  checked against the effective (post-racial) abilities**. Replace the
  `draft["abilities"]` argument to `_meets_ability_requirements` with
  `_effective_abilities(draft, data)`. (In Basic, effective == base, so the
  race-as-class flow is unchanged.)
- **HP step** (`get_hp`): the CON modifier shown/used comes from effective CON
  (`_effective_abilities(...)["CON"]`), so a dwarf's +1 CON counts toward HP.
  (The HP step is reworked in Slice 5; this is the minimal correctness fix.)

### 5. Tests

- `Race` accepts `ability_modifiers`; all demihuman YAMLs load with the
  expected modifiers; gnome/half-elf/svirfneblin load with an empty field;
  human's optional modifier feature is untouched.
- `apply_racial_modifiers`: dwarf base → CON +1 / CHA −1; clamp high (base
  CON 18 +1 → 18); clamp low (base CHA 3 −1 → 3); multi-stat (half-orc).
- Advanced finalize → `spec.abilities` includes racial mods; Basic
  race-as-class dwarf finalize → **no** racial mods.
- Race minimum requirement is checked pre-modifier (e.g. dwarf needs CON 9: a
  CON 8 roll fails even though +1 would reach 9).
- Class minimum requirement is checked post-modifier (a race +1 lets a
  borderline score qualify).
- HP step CON modifier reflects the racial +1.

## Risks / notes

- The "creation-final in `spec.abilities`" choice means the sheet shows the
  modified number with no per-source breakdown beyond the descriptive "Ability
  Modifiers" feature text. A sheet marker (like the magic-item `*`) is **not**
  added here; revisit if desired later.
- No migration (nothing deployed). Existing example characters
  (`examples/*.json`) that were authored with unmodified abilities will, on
  rebuild, reflect modifiers only if Advanced — verify the examples still load
  and update any asserted ability totals in tests.
