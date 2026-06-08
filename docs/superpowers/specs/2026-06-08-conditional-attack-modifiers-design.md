# Conditional Attack Modifiers — Design

**Date:** 2026-06-08
**Status:** Approved (brainstorming)

## Summary

Surface character-wide conditional attack-roll modifiers — bonuses or penalties
to *all* attack rolls that depend on a circumstance the per-weapon to-hit math
cannot evaluate (e.g. `bright_light`, `mounted`). These are carried but excluded
from the headline THAC0/attack-bonus and from every weapon's to-hit number, then
shown as conditional lines in a breakdown surfaced from the Attack stat. A `★`
indicator marks the Attack box when any conditional attack modifier is present,
and clicking the box opens a modal containing the full attack-modifier breakdown
plus (under descending AC only) the existing to-hit matrix.

This is a direct mirror of the existing **conditional AC modifiers**
(`armor_class.armor_class_detail` / `ACBreakdown`) and **situational save
bonuses** features. The engine plumbing already exists: `_atk_dmg` in
`attacks.py` already *carries but excludes* any `attack`/`damage` modifier whose
condition is outside `{None, ranged, melee}`. This feature only surfaces what is
already silently dropped — **no existing number changes**.

## Motivation

Two book mechanics are currently unrepresented:

- **Light Sensitivity** (drow, duergar, svirfneblin): "−2 penalty to attack
  rolls" in bright light. The matching `ac -1 condition:bright_light` already
  landed with the conditional-AC feature; the attack penalty was explicitly
  deferred to this feature.
- **Knight, Mounted Combat** (level 1): "+1 bonus to attack rolls when mounted."

Both are passive, character-wide, circumstance-gated attack modifiers — exactly
the shape this feature handles.

## Scope

### In scope

- An engine breakdown function over character-wide `attack` add-modifiers.
- Sheet `★` indicator + merged Attack modal (breakdown + matrix).
- Matrix gated to descending AC only (no THAC0 under ascending).
- Print-sheet conditional-attack footnotes.
- Data: light-sensitivity attack penalty (3 race files only — race-as-class is
  covered via `race_locked`) + knight mounted bonus.

### Out of scope (documented, with rationale)

- **Action/positioning-gated bonuses** — Acrobat Tumbling Attack (+4 vs unaware
  when tumbling), Acrobat Tumbling Defence (negates a foe's +2 to-hit when
  retreating), Assassin Assassination (+4 vs unaware from behind). These require
  the player to *choose* a specific action/position, so a passive sheet
  indicator would be noise. Same rationale the user gave for the acrobat.
- **Per-weapon conditional bonuses** (Sword +1, Giant Slayer–style `vs giants`).
  Already modelled via `Weapon.conditional_bonus` → `ConditionalAttack` and
  rendered as a per-weapon sub-line. Only matters for that weapon while equipped,
  so the existing per-weapon line + item description text suffice. **No change.**
- **`damage`-target conditional modifiers.** None of the in-scope features touch
  damage; this feature is attack-roll only. The `Modifier` grammar supports
  `damage` conditions if a future feature needs them, but the breakdown here does
  not collect them.
- **Halfling missile bonus and other `ranged`/`melee` modifiers.** These are
  weapon-type-automatic: `_atk_dmg` already applies them to the relevant weapons'
  to-hit numbers. They are excluded from the character-level breakdown to avoid
  redundancy and to keep the `★` from lighting up for them.

## Engine design — `aose/engine/attacks.py`

No change to `_atk_dmg`, `_profile_for`, or `attack_profiles` — the existing
per-weapon math already excludes unrecognised conditions. Add a parallel
breakdown path:

```python
_ATTACK_CONDITION_NOTES = {
    "bright_light": "in bright light",
    "mounted": "while mounted",
}
# Unregistered conditions fall back to condition.replace("_", " ")
# (mirrors _AC_CONDITION_NOTES and _VS_DISPLAY).

# Conditions the per-weapon to-hit math evaluates itself; excluded from the
# character-level breakdown.
_HEADLINE_ATTACK_CONDITIONS = frozenset({"ranged", "melee"})


class AttackModLine(BaseModel):
    source: str          # feature/item name, "—" fallback
    bonus: int           # +N bonus (better), −N penalty (worse)
    conditional: bool    # True when situational
    note: str            # condition note ("" when unconditional)


class AttackBreakdown(BaseModel):
    thac0: int           # base class headline (unchanged)
    attack_bonus: int    # 19 − thac0
    lines: list[AttackModLine]   # unconditional first, then conditional
    has_conditional: bool


def attack_modifiers_detail(spec, data) -> AttackBreakdown: ...
```

`attack_modifiers_detail`:

1. `base_thac0 = thac0(spec, data)`; `attack_bonus = 19 - base_thac0`. (These are
   the existing headline numbers — `thac0()` applies only `thac0`-target mods,
   not `attack`-target mods, so a global `attack +1` does *not* move the box.)
2. From `all_modifiers(spec, data)`, take `m.target == "attack" and m.op == "add"`.
3. **Unconditional** (`condition is None`) → `AttackModLine(conditional=False,
   note="")`. These explain why a weapon's to-hit exceeds the box number.
4. **Conditional**, where `condition not in _HEADLINE_ATTACK_CONDITIONS` →
   `AttackModLine(conditional=True, note=_attack_condition_note(condition))`.
5. `ranged`/`melee`-conditioned mods are **dropped** (handled per-weapon).
6. `lines` ordered unconditional-first; `has_conditional = any(l.conditional)`.

Use the same signed-effect convention as AC (`+N` / unicode-minus `−N`) for the
`bonus` display, applied in the template (the model stores a signed int, matching
`SaveModLine.bonus`).

## View design — `aose/sheet/view.py`

`CharacterSheet` gains:

- `attack_lines: list[AttackModLine]`
- `attack_has_conditional: bool`

Populated in `build_sheet` from `attack_modifiers_detail(spec, data)` (mirrors
how `ac_lines` / `ac_has_conditional` are populated from `armor_class_detail`).
The existing `thac0` / `attack_bonus` fields are unchanged.

## Template design — `aose/web/templates/sheet.html`

The Attack box currently opens `modal-matrix`. Keep that wiring; enrich it.

- **Box label** (`sheet.html:86–89`): append the conditional mark when
  `sheet.attack_has_conditional`, mirroring the AC box:
  `<span class="cond-mark" title="Has a conditional modifier — tap for details">★</span>`.
- **`modal-matrix`** (`sheet.html:866+`), retitled "Attack":
  - **Breakdown section (always):** base attack bonus / THAC0 (per `use_ascending`),
    then each `attack_lines` row: `source`, signed bonus (`+N` / `−N`),
    conditional rows flagged with their `note`. Reuse the AC modal's
    line markup/classes.
  - **To-hit matrix section:** wrap the existing matrix table in
    `{% if not sheet.use_ascending %}`. Under ascending AC there is no THAC0, so
    the matrix is meaningless; the modal then shows the breakdown only.

## Print sheet — `aose/web/templates/sheet_print.html`

Render the conditional `attack_lines` as footnotes near the attack section,
mirroring the existing conditional-AC footnotes (`.save-note`-style small text).

## Data changes

### Light Sensitivity attack penalty — race files only (3 files)

Each of `data/races/{drow,duergar,svirfneblin}.yaml` `light_sensitivity` feature
already has `granted_modifiers: - {target: ac, op: add, value: -1, condition:
bright_light}`. Add a second grant:

```yaml
  granted_modifiers:
  - {target: "ac", op: add, value: -1, condition: bright_light}
  - {target: "attack", op: add, value: -2, condition: bright_light}
```

**Race files only — do NOT touch the class files.** The race-as-class options
`data/classes/{drow,duergar,svirfneblin}.yaml` have `race_locked` set to their own
id, so the wizard assigns `race_id = cls.race_locked` ([wizard.py:794](../../../aose/web/wizard.py))
in race-as-class mode. A race-as-class drow therefore has `race_id='drow'`, and
`feature_modifiers` walks **both** the race and class feature lists. The grant on
the race file already reaches race-as-class characters (verified: `drow/drow`
already exposes the existing `ac -1` line once). Adding the same grant to the
class `light_sensitivity` feature would **double-apply** it (−2 AC / −4 attack).

This matches the established, documented pattern (CLAUDE.md: dwarf/halfling
resilience and the halfling missile bonus are "race-only ... to avoid
double-application"). The class `light_sensitivity` feature's text stays as-is; it
is functionally wired via the race file. Putting grants on the class files only
(and removing them from the race files) is rejected because it would break
separate-mode drow (`race_id='drow'`, `class_id='fighter'` — the class walk would
not fire).

### Knight Mounted Combat (+1 mounted)

`data/classes/knight.yaml` `mounted_combat` feature (`gained_at_level: 1`) gains:

```yaml
  granted_modifiers:
  - {target: "attack", op: add, value: 1, condition: mounted}
```

`source` for both flows automatically from `feature.name` ("Light Sensitivity",
"Mounted Combat") via `feature_modifiers` in `features.py`.

## Testing

- **Engine:** `attack_modifiers_detail` — unconditional global `attack` add
  appears as a non-conditional line; `bright_light`/`mounted` appear as
  conditional lines with correct notes; `ranged`/`melee` mods are excluded;
  `has_conditional` reflects only situational lines; empty when no `attack` mods.
  Headline `thac0`/`attack_bonus` and every weapon's to-hit are unchanged by the
  presence of a conditional attack modifier (regression-pins the no-behaviour-
  change claim).
- **Data:** a drow/duergar/svirfneblin character — **as a separate race and as a
  race-as-class** — exposes a `bright_light` −2 attack conditional line **exactly
  once** (regression-pins the no-double-application invariant via `race_locked`);
  a level-1 knight exposes a `mounted` +1 line; the unconditional headline is
  untouched.
- **View:** `CharacterSheet.attack_has_conditional` true for the above, false
  for a vanilla fighter; `attack_lines` populated correctly.
- **Template/print:** smoke-render coverage consistent with existing AC-modal and
  print-footnote tests.

## Files touched

| File | Change |
|---|---|
| `aose/engine/attacks.py` | `AttackModLine`, `AttackBreakdown`, `_ATTACK_CONDITION_NOTES`, `attack_modifiers_detail` |
| `aose/sheet/view.py` | `CharacterSheet.attack_lines` + `.attack_has_conditional`; populate in `build_sheet` |
| `aose/web/templates/sheet.html` | `★` on Attack box; merged breakdown + matrix in `modal-matrix`; matrix gated to descending |
| `aose/web/templates/sheet_print.html` | conditional-attack footnotes |
| `data/races/drow.yaml` | `attack -2 condition:bright_light` grant |
| `data/races/duergar.yaml` | `attack -2 condition:bright_light` grant |
| `data/races/svirfneblin.yaml` | `attack -2 condition:bright_light` grant |
| `data/classes/knight.yaml` | `attack +1 condition:mounted` grant |
| `tests/` | engine + data + view coverage |
