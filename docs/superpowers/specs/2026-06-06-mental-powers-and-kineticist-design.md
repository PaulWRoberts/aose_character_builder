# Mental Powers caster type + Kineticist class — design

**Date:** 2026-06-06
**Source:** Carcass Crawler Issue 1 (Necrotic Gnome) — the Kineticist class and its
"mental powers". A **non-core** source.

## Goal

Add the **Kineticist** class and, more importantly, build a generic **third
spellcasting type — "mental powers"** — that sits alongside the existing
`arcane` and `divine` caster types. Show mental powers correctly on the live
character sheet with play-state (a daily-use pool).

## Guiding principle — nothing keys on `"kineticist"`

Two reusable engine features are introduced; the Kineticist is merely their
first consumer:

1. **Level-based Armour Class** — a generic class-progression column (the
   classic Dwarf has this in the book too; not yet implemented). Engine code
   reads the data column, never the class id.
2. **Mental powers** — a generic `caster_type == "mental"`. All engine, view,
   route, and wizard logic branches on the caster type (exactly like arcane /
   divine do today), **never** on the class id.

If any code path references `"kineticist"` literally, the design is wrong.

## Out of scope (explicit non-goals)

- **Conditional feature-modifier framework** (features carrying `Modifier`s
  gated by level / ability bands — e.g. a flat AC bonus class, or races whose
  save bonus scales by CON). This is a separate work item; the Dwarf's
  level-based AC is *not* wired here either (only the generic engine support is
  added; populating Dwarf data is out of scope).
- **Mental Defence** (+2 to saves vs mental powers) — descriptive feature text
  only. There is no "vs mental powers" save sub-category.
- **Power sub-table math** (Accelerated Motion attacks/level, Kinetic Fist
  damage/level, Telekinetic Attack damage-by-weight) — lives in the power's
  description markdown (like thief-skill tables), not computed.
- **One-power-per-round** activation limit — descriptive text, not enforced.
- The 5% / 10% prime-requisite XP bonus needs **no** new code; `leveling.py`
  already derives the prime-req multiplier from `prime_requisites` (multi-prime
  uses the lowest score — DEX/WIS here).

## 1. New source

`data/sources.yaml` gains:

```yaml
- id: carcass_crawler_1
  name: Carcass Crawler Issue 1
  publisher: Necrotic Gnome
  core: false
```

Source gating is already generic (`engine/sources.py::source_enabled`). The
class, its spell list, and all powers carry `source: carcass_crawler_1`, so
disabling it in `/rules` or `/settings` hides every piece. No code change to
gating.

## 2. Level-based Armour Class — generic engine feature

- `ClassLevelData` (`aose/models/character_class.py`) gains:
  ```python
  armor_class: int | None = None  # descending AC the class grants at this level
  ```
  Sits beside `thac0` / `saves`.
- `engine/armor_class.py::armor_class()`: compute the best (lowest descending)
  class-granted AC across `spec.classes` that define `armor_class` at their
  level, and fold it into `base`:
  ```python
  base = min(base, class_granted_ac)   # when any class grants one
  ```
  Applied **outside** the `use_armor` block — it is not worn armour, so the
  unarmoured display reflects it too. DEX modifier and shield bonus still apply
  on top. `set` AC magic modifiers continue to compose via the existing
  `min(base, …)`.
- Resolution mirrors saves/THAC0 (best across classes). Keyed purely on the data
  column.

## 3. Mental powers — generic third caster type

### Models

- `SpellList.caster_type` literal and `engine/spells.py::CasterType` gain
  `"mental"`.
- `ClassLevelData` gains `powers_known: int | None = None` — the number of
  mental powers known at that level (the table's "Mental Powers" column).
- `ClassEntry` (`aose/models/character.py`) gains `powers_used: int = 0` — the
  daily-use pool counter. Pool size = `2 × level` (computed, not stored).
- **Known powers reuse `ClassEntry.spellbook`** — arcane and mental are both "a
  chosen known subset", so the field unifies them (docstring updated to
  "Known spells/powers"). Divine still knows its whole list and stores nothing.

### Data

- New `SpellList` in `data/spell_lists.yaml`:
  ```yaml
  - id: kineticist
    name: Mental Powers
    caster_type: mental
    source: carcass_crawler_1
    description: Mental powers fuelled by internal kinetic force.
  ```
  (The list id is class-named, mirroring `magic_user` / `cleric` / `druid`. This
  is data naming; no code keys on it.)
- New file `data/spells/carcass_crawler_kineticist_powers.yaml` — the 9 powers as
  `Spell` entries: Accelerated Motion, Control Density, Crush Life, Kinetic Fist,
  Kinetic Leap, Kinetic Shield, Kinetic Wave, Telekinetic Attack, Throw Weapon.
  Each: `level: 1` (uniform; cosmetic — mental ignores level), `spell_lists:
  [kineticist]`, `source: carcass_crawler_1`, `range`, `duration`,
  `description` (full book text; per-level sub-tables as markdown),
  `reversible: false`. Verify text against the Carcass Crawler source markdown.

### Engine (`aose/engine/spells.py`) — all branch on caster type, never class id

- `caster_type_of` — returns `"mental"` for mental lists (literal change only).
- `known_spells` — mental resolves `entry.spellbook` to `Spell`s (identical to
  the arcane branch; fold `arcane`/`mental` together).
- `powers_known_cap(entry, cls) -> int` — `progression[level].powers_known or 0`.
- `learnable_spells` — mental: every on-list power not yet known (no level /
  accessible filter).
- `learn` — mental branch: allow when the power is on the list, not already
  known, and `len(entry.spellbook) < powers_known_cap`. No `advanced_spell_books`
  restriction. `forget` is already generic — reused.
- `beginning_spell_count` — mental: `powers_known_cap` at the entry's level
  (3 at L1).
- Daily-pool helpers (new, return an updated `ClassEntry`, raise `SpellError`):
  - `power_pool(entry) -> int` = `2 * entry.level`
  - `spend_power(entry)` — `powers_used += 1`; raise if already at pool.
  - `restore_power(entry)` — `powers_used -= 1`; raise if already 0.
  - `reset_powers(entry)` — `powers_used = 0`.
- `accessible_levels` / `memorizable_slots` — mental has no `spell_slots`, so
  these return empty naturally; no change needed.

### Sheet view (`aose/sheet/view.py`)

- `spells_view` and `spellbook_view` **skip** mental entries
  (`if ctype == "mental": continue`) — mental is rendered by its own block.
- New models + `mental_powers_view(spec, data) -> list[MentalPowersBlock]`:
  - `MentalPowerRow`: `power_id`, `name`, `detail: DetailCard`.
  - `MentalPowersBlock`: `class_id`, `class_name`, `cap` (`powers_known`),
    `known: list[MentalPowerRow]`, `can_add` (`len(known) < cap`),
    `addable: list[MentalPowerRow]` (on-list, not known),
    `uses_total` (`2×level`), `uses_used`, `uses_remaining`.
- `CharacterSheet` gains `mental_powers: list[MentalPowersBlock] =
  Field(default_factory=list)`; `build_sheet` populates it.

### Routes (`aose/web/routes.py`) — keyed by `class_id`, branch on caster type

- `/{id}/powers/learn` (`class_id`, `power_id`), `/powers/forget`
  (`class_id`, `power_id`), `/powers/spend` (`class_id`), `/powers/restore`
  (`class_id`), `/powers/reset` (`class_id`). Each resolves the `ClassEntry`,
  applies the matching `spells.py` helper, persists. Errors → HTTP 400.
- `/rest/night` and `/rest/full-day`: additionally `reset_powers` for every
  mental class entry (alongside the existing `restore_all_slots`). Rest is still
  blocked when dead.

### Wizard (`aose/web/wizard.py`)

- The "casts at L1" predicate (`_class_casts_at_l1` / `_set_spellcasting_flag`):
  treat a class as a L1 caster when it has `spell_lists` **and** either a L1
  `spell_slots` entry **or** a L1 `powers_known`. This makes the existing
  `spells` step fire for mental classes.
- `_caster_entries`: mental branch — `required = powers_known` at L1 (3);
  options = all on-list powers (source-gated via `source_enabled`); reuse the
  `spell_<class_id>` form field; label "Mental Powers".
- `post_spells`: mental branch — require exactly `powers_known` chosen, each a
  valid on-list power; store into `books[cid]` → `spellbook`.
- Wizard review surfaces chosen mental powers (via the same mental view data).

### Sheet template (`aose/web/templates/sheet.html` + partial)

A distinct **Mental Powers** section (parallel to Spells / Spell Books), only
shown when `mental_powers` is non-empty:
- Known powers with collapsible detail cards; add/remove controls gated by
  `can_add` / cap (Add picks from `addable`).
- A daily-use pool: `uses_remaining / uses_total` with spend / restore / reset
  controls (pip style consistent with the existing slot UI).
- A short note on the activation rules (one power per round; takes effect at the
  start of the combat sequence) as static text.

## 4. Kineticist class data

`data/classes/kineticist.yaml`:

- `id: kineticist`, `name: Kineticist`, `source: carcass_crawler_1`.
- `prime_requisites: [DEX, WIS]`, `max_level: 14`, `hit_die: 1d6`,
  `name_level: 9`, `hp_after_name_level: 2`.
- `weapons_allowed: all`, `armor_allowed: []`, `shields_allowed: false`.
- `spell_lists: [kineticist]`.
- `progression` L1-14, each row: `xp_required`, `thac0`, `saves`
  (`death/wands/paralysis/breath/spells`), `armor_class` (descending AC column),
  `powers_known`. No `spell_slots`. Values transcribed from the Carcass Crawler
  table:

  | Lvl | XP | THAC0 | AC | D | W | P | B | S | Powers |
  |--|--|--|--|--|--|--|--|--|--|
  | 1 | 0 | 19 | 9 | 13 | 14 | 13 | 16 | 15 | 3 |
  | 2 | 2000 | 19 | 8 | 13 | 14 | 13 | 16 | 15 | 3 |
  | 3 | 4000 | 19 | 7 | 13 | 14 | 13 | 16 | 15 | 4 |
  | 4 | 8000 | 19 | 6 | 13 | 14 | 13 | 16 | 15 | 4 |
  | 5 | 16000 | 17 | 5 | 12 | 13 | 11 | 14 | 13 | 5 |
  | 6 | 32000 | 17 | 4 | 12 | 13 | 11 | 14 | 13 | 5 |
  | 7 | 64000 | 17 | 3 | 12 | 13 | 11 | 14 | 13 | 6 |
  | 8 | 120000 | 17 | 2 | 12 | 13 | 11 | 14 | 13 | 6 |
  | 9 | 240000 | 14 | 1 | 10 | 11 | 9 | 12 | 10 | 7 |
  | 10 | 360000 | 14 | 0 | 10 | 11 | 9 | 12 | 10 | 7 |
  | 11 | 480000 | 14 | -1 | 10 | 11 | 9 | 12 | 10 | 8 |
  | 12 | 600000 | 14 | -2 | 10 | 11 | 9 | 12 | 10 | 8 |
  | 13 | 720000 | 12 | -3 | 8 | 9 | 7 | 10 | 8 | 9 |
  | 14 | 840000 | 12 | -3 | 8 | 9 | 7 | 10 | 8 | 9 |

  (HD: 1d6 through L9; L10+ flat `9d6 + 2/level`, handled by
  `name_level: 9` + `hp_after_name_level: 2`. The `*` "CON no longer applies"
  past name level is the existing flat-HP behaviour.)
- `features`: Combat (no armour/shields; any weapon), Mental Defence (+2 vs
  mental powers — text), Mental Powers (frequency: 2/day/level; activation /
  one-per-round / combat-sequence rules — text), After Reaching 9th Level
  (academy; 1d6 apprentices of level 1d4).

## Testing

- **AC engine (generic):** a class defining `armor_class` per level → sheet AC
  reflects it; best across multiple classes; DEX still applied; unarmoured
  display reflects it. No reference to `"kineticist"` in the test's assertions
  about mechanism (use the kineticist data as the fixture, but assert on the
  generic behaviour).
- **Mental caster type:** `caster_type_of` → `"mental"`; `known_spells`,
  `learnable_spells`, `learn` cap enforcement, `forget`, `beginning_spell_count`;
  pool helpers `spend/restore/reset` incl. boundary errors; `power_pool == 2×level`.
- **View:** `spells_view` / `spellbook_view` skip mental; `mental_powers_view`
  shape (cap, known, addable, uses_total/used/remaining).
- **Routes:** learn/forget/spend/restore/reset happy paths + 400s; rest resets
  the pool.
- **Wizard:** a mental class triggers the spells step; requires exactly
  `powers_known` powers; rejects wrong counts / off-list powers; source gating
  hides it when the source is disabled.
- **Source gating:** disabling `carcass_crawler_1` removes the class from the
  wizard and the powers from candidates.
- **Sheet template:** renders the Mental Powers section for a kineticist.

## Verification against the source

Per project practice, transcribe the class table and every power's
range/duration/description faithfully from the Carcass Crawler Issue 1 markdown
(`C:\Users\paulw\Downloads\carcass-crawler-1_kineticist.md`). No fabricated values.
