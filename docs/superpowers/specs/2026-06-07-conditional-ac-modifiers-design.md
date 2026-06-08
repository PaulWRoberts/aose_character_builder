# Conditional AC Modifiers — Design

**Date:** 2026-06-07
**Status:** Approved (design)

## Overview

A system for recording conditional modifiers to Armour Class and surfacing them
on the character sheet, mirroring the existing *situational save bonuses*
feature (`save:vs:<thing>` → footnotes + per-save conditional lines).

A conditional AC modifier is any `ac` modifier that carries a `condition` the
headline AC computation cannot evaluate. Such modifiers **never** fold into the
headline AC. Instead, a `★` (asterisk) appears on the Armour Class block; clicking
it opens a **full AC breakdown modal** showing the headline composition plus each
conditional modifier with its bonus/penalty and source.

The system works for magic items automatically: equipped magic items already emit
`ac` modifiers through the same `all_modifiers` pipeline, so any magic item with a
conditional `ac` modifier surfaces with no extra code.

Scope is AC only. The −2 attack-in-bright-light penalty that shares a condition
with the −1 AC light-sensitivity penalty is explicitly out of scope (a future
conditional-attack feature).

## Motivation

Several AOSE Advanced races have conditional AC effects that the headline AC
cannot represent because they depend on circumstance:

| Feature | Races | Effect |
|---|---|---|
| Light Sensitivity | drow, duergar, svirfneblin | −1 AC (and −2 attack, out of scope) in bright light / daylight / continual light |
| Defensive Bonus | gnome, svirfneblin, halfling | +2 AC when attacked by opponents larger than human-sized |

(Svirfneblin has both.) Today these live only as descriptive `mechanical:` blocks
in the race YAML — they are not mechanically active or displayed anywhere.

## Data — no model changes

Reuse the existing `GrantedModifier` grammar (`target: ac`, `op: add`, `value`,
`condition`). The sign convention is already correct: `armor_class()` computes
`descending = base − ac_add`, so a positive `value` improves AC (bonus) and a
negative `value` worsens it (penalty).

Encode on the existing race features (alongside the descriptive `mechanical:`
block, exactly as svirfneblin's Illusion Resistance already pairs a
`mechanical:` block with a `granted_modifiers:` list):

- **Light Sensitivity** (drow, duergar, svirfneblin):
  `{target: ac, op: add, value: -1, condition: bright_light}`
- **Defensive Bonus** (gnome, svirfneblin, halfling):
  `{target: ac, op: add, value: 2, condition: large_attacker}`

Exact wording and values will be verified against the AOSE PDF
(`import/pdfs`, via PyMuPDF) before encoding, per project rule.

## Engine — `aose/engine/armor_class.py`

### Headline unchanged

`armor_class()` keeps its current condition handling: only the `unarmored`
condition is evaluated; every other condition returns `False` from
`ac_add_applies` and is therefore excluded from the headline. The new conditions
(`bright_light`, `large_attacker`) are situational and never inflate or deflate
the headline number.

### Shared component computation

Refactor the per-component AC computation (armour base, DEX, shield, the `ac set`
candidates, and the partition of `ac add` modifiers into applies / situational)
into a shared helper so the breakdown and the headline cannot diverge.
`armor_class()` continues to expose the same `(descending, ascending)` signature
and the `use_armor` / `use_shield` parameters used by `unarmored_ac()`.

### New: `armor_class_detail(spec, data) -> ACBreakdown`

```python
class ACModLine(BaseModel):
    source: str          # "Plate Mail", "Dexterity", "Shield", feature/item name
    effect: str          # display string, e.g. "+1", "−1", "AC 3"
    conditional: bool     # True for situational modifiers
    note: str            # condition description ("" when unconditional)

class ACBreakdown(BaseModel):
    descending: int
    ascending: int
    unarmored_descending: int
    unarmored_ascending: int
    lines: list[ACModLine]   # unconditional contributions first, then conditional
    has_conditional: bool
```

- Headline numbers (`descending`/`ascending`) delegate to `armor_class()`;
  unarmoured numbers to `unarmored_ac()`. They are authoritative — the lines are
  explanatory and are derived from the same shared helper so they stay consistent.
- Unconditional contribution lines: armour (worn armour name or "Unarmoured"),
  Dexterity (when the DEX mod is nonzero), Shield (when a shield is equipped), and
  each unconditional feature/magic `ac` modifier (`add`, and any applicable
  `unarmored`-conditioned `add`, plus `ac set` sources).
- Conditional lines: each `ac add` modifier whose condition is **not** a
  headline-evaluated condition (i.e. not `unarmored`), flagged `conditional=True`
  with a readable `note`.

### Condition-display registry

```python
_AC_CONDITION_NOTES = {
    "bright_light": "in bright light",
    "large_attacker": "vs attackers larger than human-sized",
}
```

Unregistered conditions fall back to `condition.replace("_", " ")` — same pattern
as `_VS_DISPLAY` / `_CONDITION_NOTES` in `saves.py`.

### Excluded from the conditional list

`unarmored`-conditioned bonuses (e.g. barbarian Agile Fighting) are **not** listed
as conditional modifiers — they are already represented by the armoured-vs-
unarmoured AC display. Only conditions the headline cannot evaluate appear in the
conditional lines.

## Sheet — `aose/sheet/view.py`

`CharacterSheet` gains the AC breakdown for the modal. Concretely:

- `ac_lines: list[SheetACLine]` (or reuse `ACModLine` directly) — the breakdown
  lines.
- `ac_has_conditional: bool` — drives the `★` marker.

`build_sheet` populates these from `armor_class_detail(spec, data)`. Existing
`ac_descending` / `ac_ascending` / `unarmored_*` fields are unchanged.

## Templates + CSS

### `sheet.html`

- The Armour Class block (`.shield`) shows a `★` (reusing the existing
  `.cond-mark` style) when `sheet.ac_has_conditional`, and becomes clickable
  (`data-modal="modal-ac"`), matching the per-save / per-ability click pattern.
- New `modal-ac` overlay: shows the AC value (and other-notation value), the
  unconditional contribution lines, then the conditional lines with bonus/penalty
  styling consistent with the per-save modal (`+N` bonus / `−N` penalty,
  conditional lines flagged with their note).

### `sheet_print.html`

Conditional AC lines render as footnotes beneath the AC stat (mirroring
`save-notes-print`), since the print sheet cannot open modals.

### CSS

Reuse existing `.cond-mark`, `.muted`, and overlay/modal styles. Add minimal new
CSS only if the AC modal layout needs it.

## Testing (TDD)

**Engine** (`tests/engine/`):
- A conditional `ac` modifier (e.g. `condition: bright_light`) does not change the
  headline `armor_class()` value.
- `armor_class_detail` produces correct conditional lines: drow (−1 bright_light),
  gnome (+2 large_attacker), svirfneblin (both).
- A magic item with a conditional `ac add` modifier surfaces in the conditional
  lines.
- An `unarmored`-conditioned bonus is **excluded** from the conditional lines.
- Unknown condition falls back to the underscore-replaced display string.
- Unconditional contribution lines (armour, DEX, shield) reconcile with the
  headline number.

**View** (`tests/sheet/`):
- `ac_has_conditional` is `True` for an affected race and `False` otherwise.
- `ac_lines` are populated with the expected sources and notes.

**Data** (`tests/data/`):
- Each affected race feature grants the expected `ac` modifier (target, op, value,
  condition).

## Out of scope

- The −2 attack-in-bright-light penalty (future conditional-attack feature).
- Any new headline condition evaluation — all new conditions are situational.
- Encoding conditional AC modifiers onto the magic-item catalog (the engine
  supports it; no catalog data is added in this work).
