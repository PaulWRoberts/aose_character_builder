# Fixed HP at name level (no roll, no CON) — design

**Date:** 2026-06-03
**Status:** Approved, pending implementation plan

## Problem

In AOSE, every class reaches a **name level** (the level at which Hit Dice
stop accumulating — level 9 for nearly every class). Beyond name level a
character no longer rolls Hit Dice: each level grants a **fixed number of hit
points** with **no Constitution modifier applied**.

The current builder does not model this:

- `aose/engine/leveling.py` `level_up` always calls `roll_hp(cls.hit_die)` and
  appends the roll to `entry.hp_rolls`, *every* level.
- `aose/engine/hp.py` `_hp_total` adds the effective CON modifier to *every*
  HP-gain event, with no level cutoff.

The progression data already encodes the correct rule in the
`progression[L].hit_dice` string (e.g. fighter L9 = `9d8`, L10 = `9d8+2`,
L14 = `9d8+10`), but **no engine code ever reads that field** — it is loaded
and ignored. Net effect: a character past name level gets too much HP, in two
compounding ways (an extra rolled die per level *and* a spurious CON addition).

## The rule (verified against AOSE text)

- **Name level**: the last level at which a die is rolled. Level 9 for almost
  every class; level 8 for the four capped race-as-class options (gnome,
  half_orc, halfling, svirfneblin), whose `max_level` is also 8.
- **Beyond name level**: gain a fixed HP step per level, **no CON modifier**.
- **Multi-class HP** (per the AOSE text): *"When determining hit points at
  character creation or upon gaining a level, any hit points gained are divided
  by the number of classes. Fractions are tracked and may add up to a whole
  number later on."* The fixed step is treated exactly like a rolled value:
  divided by N classes, no CON, with fractions accumulated across level-ups.

## Design

### 1. Data model — typed fields as the single source of truth

- **`CharClass`** (`aose/models/character_class.py`) gains two fields:
  - `name_level: int = 9` — the last level that rolls a Hit Die.
  - `hp_after_name_level: int` — flat HP gained per level beyond name level.
- **`ClassLevelData.hit_dice: str` is removed** entirely, and the field is
  deleted from every progression row in all 22 `data/classes/*.yaml` files.
  Nothing in the engine or templates reads it. (The identifiers named
  `hit_dice` in `aose/engine/dice.py` and `aose/web/wizard.py` are unrelated
  local variables / parameters — lists of `hit_die` strings — and stay.)

Per-class values (extracted from the current `hit_dice` constants *before*
deleting them):

| step (`hp_after_name_level`) | classes |
|---|---|
| 1 | cleric, druid, illusionist, magic_user |
| 2 | acrobat, assassin, bard, drow, elf, fighter, half_elf, knight, paladin, ranger, thief |
| 3 | barbarian, duergar, dwarf |
| inert (name_level 8, max_level 8) | gnome, half_orc, halfling, svirfneblin |

All classes use `name_level: 9` except the four capped race-as-class options,
which use `name_level: 8`. Those four can never exceed `max_level` 8, so their
fixed step never fires; record a faithful value anyway for completeness.

### 2. Engine — HP derivation (`aose/engine/hp.py`)

`_hp_total` keeps its existing rolled-events loop unchanged and **adds one new
term** for the fixed post-name-level HP:

```
fixed = Fraction(
    sum(max(0, entry.level - cls.name_level) * cls.hp_after_name_level
        for entry, cls in classes),
    N,
)
```

- **No CON** is added to the fixed term.
- **No `max(1, …)` floor** on the fixed term — it is a flat bonus, not a Hit
  Die, so the per-Hit-Die minimum does not apply.
- The fixed term is summed into the same exact-`Fraction` total and floored
  once. `max_hp` and `hp_remainder` are otherwise unchanged; fractional
  remainders accumulate naturally across level-ups.
- **Defensive cap:** the rolled-events computation counts only the first
  `name_level` rolls per class, so HP stays correct even if a stored
  `hp_rolls` list ever runs longer than name level.

### 3. Engine — leveling (`aose/engine/leveling.py`)

In `level_up`, when `entry.level >= cls.name_level`, advance the level but **do
not roll a Hit Die and do not append to `hp_rolls`**. (The route ignores
`level_up`'s return value — HP is recomputed on the sheet — so the no-roll
branch's return value is unconstrained.)

### 4. Engine — energy drain (`aose/engine/energy_drain.py`)

When removing a level LIFO, only `pop()` a `hp_roll` when the removed level is
`<= name_level`. Levels above name level were never given a roll, so popping
one would incorrectly destroy a real Hit Die. Draining back across the name-
level boundary must restore the character's prior HP exactly.

## Testing (TDD)

- **Single-class:** fighter at L9 → L10 gains exactly +2 max HP — no die rolled,
  no CON, independent of CON score; L14 fighter = sum of 9 rolls + 10.
  Magic-user L10 = 9 rolls + 1.
- **CON independence past name level:** changing effective CON does not change
  the fixed portion of max HP.
- **Multi-class:** a fighter/thief past name level in one or both classes
  accumulates `step / 2` fractions that combine across classes; assert
  `max_hp` and `hp_remainder`.
- **Round-trip:** `level_up` past name level leaves `hp_rolls` capped at
  `name_level` entries; `energy_drain` back across the boundary restores max HP
  exactly and does not consume a real die.
- **Data:** every class loads with the new `name_level` / `hp_after_name_level`
  fields; `hit_dice` is gone from `ClassLevelData` and all YAML. Update the one
  test that constructs `ClassLevelData(hit_dice=…)`
  (`tests/test_demihuman_rules.py:118`) plus the `import/cribs/class.md` crib.

## Assumptions / non-goals

- **No data migration** for characters already leveled past name level under the
  old engine (project policy: local, undeployed). The defensive cap in §2
  covers stale `hp_rolls` regardless.
- Multi-class XP splitting and the existing averaging model are **out of scope** —
  they were reviewed during design and confirmed correct against the AOSE text.
