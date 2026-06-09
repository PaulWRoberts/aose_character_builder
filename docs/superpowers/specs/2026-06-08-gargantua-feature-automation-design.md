# Gargantua feature automation — design

**Date:** 2026-06-08
**Status:** Approved (design)

## Problem

The gargantua race and the gargantua race-as-class each carry two features
whose mechanics are currently text-only:

- **Rock Throwing** — "Rocks thrown by a gargantua deal 1d6 damage … range
  5′–50′ / 51′–100′ / 101′–150′." Nothing puts a usable attack on the sheet.
- **Open Doors** — gargantuas are "treated as the next highest STR category"
  for the chance of opening (even barred) doors. The STR ability modal shows the
  raw banded Open Doors chance, ignoring the bump.

Both should be automated. Per project convention ("Data, not code"), **no engine
module may reference the gargantua id**; the engine reads generic `mechanical`
keys off whatever feature carries them. `is_race_as_class` already governs which
feature path (race vs class) contributes, so the race and race-as-class both work
and never double-count.

## Decisions (confirmed)

- **Rock attack math:** standard missile — DEX modifier to the attack roll, no
  ability modifier to damage, flat 1d6. Matches OSE RAW (thrown = missile
  attack) and the existing sling/bow path in `attacks.py`.
- **Implementation:** generic and data-driven. The weapon stats (damage, ranges,
  qualities) live in the feature's `mechanical` block; the engine reads a generic
  synthetic-weapon descriptor, not a hard-coded "rock".
- **Open Doors UI:** show the bumped (next-category) chance with an explanatory
  note so the difference from the raw score band is visible.

## Part A — Rock Throwing → synthetic always-on weapon

### Data

Restructure the `rock_throwing` feature's `mechanical` block in both
`data/races/gargantua.yaml` and `data/classes/gargantua.yaml` from loose
`damage`/`range` keys into a generic synthetic-weapon descriptor:

```yaml
mechanical:
  weapon:
    name: Rock
    damage: 1d6
    melee: false
    ranged: true
    range: [50, 100, 150]
    qualities: [blunt]
```

`mechanical` is a free `dict[str, Any]` already read directly by the engine
elsewhere (`languages.py` reads `feat.mechanical.get("languages")` /
`illiterate_below_level`), so a `weapon` key needs no new typed model. (No data
migrations — game YAML is edited in place.)

### Engine

- **`features.py`** — add a helper that collects `mechanical["weapon"]`
  descriptors from every *reached* feature: class features gated by
  `gained_at_level <= entry.level`; race features included only when **not**
  `is_race_as_class`. Mirrors `feature_modifiers`' iteration. This guarantees
  exactly one rock for a gargantua-race-with-a-class (race path) and for a
  gargantua-as-class (class path), with no duplication.

- **`attacks.py`** — add `_feature_weapon_profile(descriptor, spec, eff,
  base_thac0, g_atk, g_dmg)`, a sibling of `_unarmed_profile`, that builds an
  `AttackProfile` from a descriptor:
  - `melee = descriptor.get("melee", False)`; `ranged = descriptor.get("ranged",
    not melee)`.
  - melee ⇒ `atk_mod = dmg_mod = STR mod`; ranged ⇒ `atk_mod = DEX mod`,
    `dmg_mod = 0` (flat damage).
  - `base_damage` = the descriptor's `damage` verbatim (a fixed feature stat; the
    Variable Weapon Damage rule does not apply to it).
  - `range_ft` = the descriptor's `range` 3-tuple (ranged only).
  - `proficient = True` always — no weapon-proficiency penalty, like unarmed.
  - `manageable_item_id = None` — not a catalog item, so no click-to-manage link.
  - `weapon_id` = a stable synthetic id (the feature id, e.g. `rock_throwing`).
  - Global `attack`/`damage` mods flow through `_atk_dmg(mods, melee=…,
    ranged=…)` exactly as for catalog weapons.

  `attack_profiles()` builds one profile per collected descriptor and adds them
  to the catalog `weapon_profiles` list **before** the sort-by-name, so the rock
  sorts naturally among the other weapons. The synthetic **Unarmed** profile
  stays first.

### Rendering

No template change needed. The profile appears in the existing Equipped list as
`Rock · +N · 1d6 · 50/100/150′`, with no "non-prof" badge (proficient) and no
click target (no `manageable_item_id`).

### Out of scope

`blunt`/missile are recorded in the data. "Missile" is the `ranged` flag.
`blunt` is informational only: the weapon-qualities reference block scans
catalog inventory/equipped weapons, and the synthetic rock is in neither, so the
quality is not surfaced there. Surfacing synthetic-weapon qualities in that block
is deferred unless requested.

## Part B — Open Doors → bumped STR category + note

- **`features.py`** — add `open_doors_category_bonus(spec, data) -> int` summing
  `mechanical["str_category_bonus"]` over reached features (same race-as-class
  handling as Part A).

- **`ability_mods.ability_table_row(...)`** — add
  `open_doors_category_bonus: int = 0`. When non-zero, the **Open Doors** cell
  jumps that many bands up the `_OPEN_DOORS` table via band-index arithmetic
  (find the current band's index in the sorted thresholds, add the bonus, clamp
  to the last band) and carries a note (e.g. `+1 category (Gargantua)`). Per the
  rules this affects **only** Open Doors — the Melee column is untouched.

- **`AbilityTableCell`** (in `sheet/view.py`) — add `note: str = ""`.
  `build_sheet` passes `open_doors_category_bonus(spec, data)` into
  `ability_table_row` for STR and threads the note onto the cell.

- **Template** — the STR ability modal renders the note muted next to the value,
  e.g. `Open Doors … 3-in-6  +1 category (Gargantua)`.

Result: STR 12 gargantua → **3-in-6** (vs 2-in-6 raw) with the note; STR 16 →
5-in-6; STR 18 → 5-in-6 (clamped). Non-gargantua characters are unchanged
(`open_doors_category_bonus` is 0, no note).

## Tests

- **Rock:** present in `attack_profiles` for a gargantua-race character and for a
  gargantua race-as-class character; absent for a non-gargantua; never
  duplicated. DEX to hit, flat 1d6, range 50/100/150, `proficient` even with the
  `weapon_proficiency` rule on, `manageable_item_id is None`.
- **Open doors:** STR 12 gargantua → `3-in-6` with a note; STR 18 gargantua →
  `5-in-6` (clamped) with a note; non-gargantua STR 12 → `2-in-6`, no note;
  Melee column unchanged by the bonus.

## Files touched

- `data/races/gargantua.yaml`, `data/classes/gargantua.yaml` — restructure
  `rock_throwing` mechanical.
- `aose/engine/features.py` — feature-weapon collector + open-doors bonus.
- `aose/engine/attacks.py` — `_feature_weapon_profile` + wiring.
- `aose/engine/ability_mods.py` — Open Doors category bump + note.
- `aose/sheet/view.py` — `AbilityTableCell.note`, thread bonus/note.
- `aose/web/templates/sheet.html` — render the cell note.
- Tests under `tests/`.
- Docs: `docs/CHANGELOG.md` row; `docs/ARCHITECTURE.md` attacks/features topics.
