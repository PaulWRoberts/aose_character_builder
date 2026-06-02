# Energy Drain — Design

**Date:** 2026-06-02
**Status:** Approved (brainstorming)

## Summary

Add an **energy drain** action to the live character-sheet manager: a GM-applied,
permanent loss of one or more experience levels (or Hit Dice). It is available
only on the character sheet (not the wizard), with no `RuleSet` flag — energy
drain is an arbitrary effect the GM applies, always available.

When drained, the character loses the stated number of levels. Each lost level
strips:

- the corresponding **Hit Die of hit points** (the last `hp_rolls` entry of the
  drained class),
- **experience levels** (the class's `level` drops), and
- **all other benefits of that level** — saves, THAC0, and attack progression are
  derived from `level`, so they fall out automatically; spells are auto-trimmed
  (see below).

If the loss would take the character below level 1, they **immediately die**:
hit points 0, XP 0, level 1 (there is no level 0).

## Multi-class: LIFO level removal

Characters can be multi-class. Level, XP, and `hp_rolls` are tracked per class
(`ClassEntry`). Energy drain removes levels **LIFO** — the most recently gained
level is removed first — determined deterministically, with no stored
cross-class timeline:

- XP is split evenly across classes, and each class has its own XP table.
- A class's *current* level `L` was reached when it banked `xp_required(L)`. The
  shared/"global" XP point at which that happened is
  `xp_required(L) / prime_req_multiplier` (a class banks XP at the rate of its
  prime-requisite multiplier, so dividing converts a class threshold back to the
  global XP it represents).
- The **most recently leveled class** is the one (among classes with `level > 1`)
  that maximizes `xp_required(current_level) / prime_req_multiplier`.

Because level 1 requires 0 XP in every OSE table, a level-1 class always has a
global value of 0 and is never selected while another class is above level 1.
All classes therefore bottom out together at level 1 (character creation). When
every class is at level 1 and a level still must be removed, the drain is fatal.

The prime-requisite multiplier reuses `leveling._prime_req_multiplier`.

## Engine: `aose/engine/energy_drain.py`

A new cycle-free module (imports models + loader + the leveling/spells helpers it
uses). One public mutator:

```python
def energy_drain(
    spec: CharacterSpec,
    data: GameData,
    levels: int,
    xp_mode: Literal["midpoint", "new_min"],
) -> None
```

Mutates `spec` in place. `levels` must be `>= 1` (the route validates and maps a
bad value to HTTP 400).

### Algorithm

Remove one level at a time, `levels` times:

1. **Select** the most-recently-leveled class among those with `level > 1`
   (see above).
2. If **no class has `level > 1`** (all at level 1) and a level still must be
   removed → **death** (below); stop.
3. **Pop one level** from the selected class:
   - `entry.level -= 1`
   - drop the last `entry.hp_rolls` entry (the lost Hit Die)
   - record the class's *former* level (its level at the start of the drain) the
     first time it is touched
   - auto-trim its spells (below)

After the loop, for each class that lost at least one level, recompute `xp` from
its *former* level (pre-drain) and *new* level (post-drain):

- `midpoint` → `(xp_required(new_level) + xp_required(former_level)) // 2`
- `new_min`  → `xp_required(new_level)`

Classes that were not touched keep their XP unchanged.

**Midpoint is only valid for a single-level drain (`levels == 1`).** A
multi-level drain would put the midpoint between non-adjacent thresholds, which
can land *above* an intermediate level threshold and falsely offer an immediate
"Level Up". The engine therefore raises `ValueError` for
`xp_mode == "midpoint"` with `levels != 1` (route → HTTP 400), and the UI
disables the Midpoint option, forcing *New level minimum*, whenever **Levels**
> 1. With `levels == 1`, `former_level == new_level + 1`, so the midpoint is
unambiguously halfway into the new (reduced) level's band.

### Death

Triggered when `levels` exceeds the character's total remaining advancement
(every class is at level 1 and another level must still be removed). Set, for
every class:

- `level = 1`
- `hp_rolls = hp_rolls[:1]` (keep only the creation roll)
- `xp = 0`
- trim spells to the level-1 accessible set

Then set `spec.damage_taken = max_hp(spec, data)` so current HP is 0, which makes
`hp.is_dead(spec, data)` true and renders the dead state the sheet already
supports.

### Spell auto-trim (`_trim_to_accessible`)

Applied per affected class after its level drops:

- Drop prepared `slots` whose `level` is no longer in `accessible_levels`, or that
  exceed the now-smaller per-level cap from `memorizable_slots`.
- Trim the arcane `spellbook` to spells at accessible levels (and, under standard
  spell-book rules, the per-level book cap from `memorizable_slots`).
- Divine known-spells are derived from level, so only `slots` need trimming there.

## Route: `aose/web/routes.py`

```python
@router.post("/character/{character_id}/energy-drain")
async def energy_drain(request, character_id,
                       levels: int = Form(...),
                       xp_mode: str = Form("midpoint")):
```

Load the spec (404 if missing), call the engine, save, and redirect to
`/character/{character_id}` — mirroring the existing `grant_xp` /
`level_up_class` routes. The engine validates inputs (`levels >= 1`, known
`xp_mode`, and `midpoint` only when `levels == 1`); the route maps the engine's
`ValueError` to HTTP 400.

## UI: sheet advancement section

A small **Energy Drain** control in the same advancement area as the XP /
Level-Up buttons, styled as a danger action:

- a number input **Levels** (min 1, default 1),
- a two-option **XP reset** selector — *Midpoint (halfway into lost level)* /
  *New level minimum*. A small inline script disables the Midpoint radio and
  selects *New level minimum* whenever **Levels** > 1 (and re-enables it at
  Levels == 1),
- a **Drain** button with a JS `confirm()` ("Energy drain N level(s)? This is
  permanent.") because it is destructive and irreversible.

No class selector — LIFO chooses the class automatically. After submit, the page
reloads showing the reduced level / HP / XP, and on a lethal drain the dead state
the sheet already renders.

## Tests (TDD)

Engine (`tests/`):

- single-class drain: `level`, `hp_rolls` length, and both XP modes
  (`midpoint`, `new_min`);
- multi-class LIFO picks the correct (most-recently-leveled) class;
- cascade across classes when one drain spans multiple class levels;
- spell auto-trim drops now-inaccessible prepared/known spells;
- death on over-drain (single- and multi-class) sets HP 0 / level 1 / XP 0.

Route:

- happy path (drain reduces level and redirects 303);
- a validation case returning 400 (`levels < 1` or bad `xp_mode`).

## Out of scope

- No wizard integration and no `RuleSet` flag.
- No undo (the loss is permanent, per the rule); the GM can edit the saved JSON
  if a mistake is made.
- No drag-and-drop or other sheet UI beyond the single danger control.
