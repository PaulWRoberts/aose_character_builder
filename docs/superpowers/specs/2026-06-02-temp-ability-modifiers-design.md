# Temporary ability-score modifiers (sheet manager) — design

**Date:** 2026-06-02
**Scope:** Live character sheet only (not the wizard).

## Goal

Let the GM/player apply a temporary adjustment to any ability score directly on
the character sheet. Temporary modifiers:

- never alter the real underlying score (`CharacterSpec.abilities`);
- stack additively with ability modifiers from equipped magic items;
- keep the **final effective score clamped to [3, 18]**;
- come with on-sheet feedback making it obvious what composes the final score
  (base + equipment + temporary).

One signed net modifier per ability (no per-effect list, no free-text label).

## Data model

Add to `CharacterSpec` (`aose/models/character.py`):

```python
temp_ability_modifiers: dict[Ability, int] = Field(default_factory=dict)
```

- One signed integer per ability.
- Only non-zero entries are stored; setting a value of 0 removes the key.
- Real `abilities` are never modified.
- No migration needed — the app isn't deployed; the new field defaults empty
  on existing saves.

## Engine

`effective_abilities(spec, data)` in `aose/engine/magic.py` becomes the single
clamp point. For **every** ability it computes:

```
base = spec.abilities[ab]
after_equip = apply magic ability:* modifiers to base   # unclamped (as today)
final = clamp(after_equip + temp_ability_modifiers.get(ab, 0), 3, 18)
```

Because the shared derivation path already routes through `effective_abilities`
(HP via effective CON, attacks via effective STR/DEX, AC via effective DEX),
temporary modifiers automatically propagate into derived stats — consistent
with how magic-item ability modifiers already behave.

Clamping is now applied to **all** abilities (previously `effective_abilities`
only rewrote an ability when a magic modifier targeted it). This is a
deliberate, correct behaviour change: an effective score can never sit outside
[3, 18]. The only ability modifier in seed magic data is the Girdle of Giant
Strength's `set STR=18`, which is already in range, so no existing magic
behaviour changes.

A tiny pure helper handles set/clear for testability:

```python
def set_temp_ability_modifier(temp: dict[Ability, int], ability: Ability,
                              value: int) -> dict[Ability, int]:
    """Return a new dict with `ability` set to `value`, or the key removed
    when value == 0. Single modifier per ability (replaces any prior)."""
```

## Sheet view

`AbilityRow` (`aose/sheet/view.py`) gains breakdown fields:

- `base_score: int` — the real underlying score.
- `equip_delta: int` — `after_equip − base` (works for both `add` and `set`
  magic ops; a `set STR=18` over base 13 reads as `+5`).
- `temp_delta: int` — the stored temporary modifier (0 when none).
- `score` stays the **final clamped** value; `modifier` derives from it.
- `modified = score != base_score`.

## Feedback (UI)

In the Abilities section of `sheet.html`:

- The existing `*` marker stays on any modified score.
- The footnote becomes a per-modified-ability breakdown. **Only non-zero
  adjustments are shown.** Examples:
  - temp only: `STR: base 13, temporary −2 → 11`
  - equipment only: `STR: base 13, equipment +5 → 18`
  - both: `STR: base 13, equipment +5, temporary −2 → 16`

  Base and final are always shown; an adjustment line (equipment / temporary)
  appears only when its delta is non-zero.

## Route / control

- New route `POST /character/{character_id}/abilities/temp-modifier`
  (form fields: `ability`, `value: int`). Follows the existing
  mutate → `save_character` → 303 redirect pattern (cf. `/hp/set`).
- Each ability row in `sheet.html` gets a compact numeric input pre-filled with
  its current temp value plus a "Set" button. Entering 0 clears the modifier.

## Testing

Engine (`tests/`):

- temp stacks additively with a magic `set` (Girdle 18 + temp −2 = 16);
- clamps high (push above 18 → 18) and low (push below 3 → 3);
- single modifier per ability — a second set replaces the first;
- `set_temp_ability_modifier` removes the key on value 0;
- propagation into a derived stat (e.g. CON change shifts max HP, or STR change
  shifts to-hit).

View:

- `AbilityRow.base_score / equip_delta / temp_delta` populated correctly,
  including the equipment-`set` case.

Route:

- setting a modifier persists and clears on 0.

## Out of scope

- Wizard (creation) — sheet manager only.
- Per-effect named modifier lists / free-text labels.
- Temp modifiers to anything other than ability scores.
