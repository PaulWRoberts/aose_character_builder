# Languages, Literacy & Wisdom Saves — Design

**Date:** 2026-06-07
**Status:** Approved (brainstorming)

## Goal

Make the ability-table-derived features we model faithful to the AOSE Advanced
Ability Scores and Languages rules. Two independent but related areas, shipped
under one spec:

- **A. Languages & Literacy** — proper display names for every language id, surface
  class/race-granted special languages (non-learnable), and a three-tier
  INT-derived literacy state with a class override (barbarian).
- **B. Wisdom magic saves, conditional racial resilience + saves-UI rethink** —
  apply the WIS modifier to saves versus magical effects (the one genuine modeling
  gap), introduce a conditional-modifier concept for saves, **make the demihuman
  resilience bonuses conditional where they only cover half an umbrella category
  (poison/paralysis, not death-ray/petrify)**, and rework the saves display into a
  base → modified headline with a click-through breakdown modal.

## Audit context (what is already correct — do not change)

Verified during brainstorming against the Ability Scores table:

- **HP (CON):** `hp.py` adds effective CON mod per HD-roll event, floor 1 HP/die. ✓
- **Prime-requisite XP:** `ability_mods.prime_requisite_xp_multiplier` matches the
  table exactly (−20 / −10 / 0 / +5 / +10 %). ✓
- **STR melee, DEX → AC, DEX → missile:** all correct. DEX → AC lowers descending /
  raises ascending; pure-ranged weapons take DEX to-hit and never to damage. ✓
- **INT spoken-language count:** `additional_language_count` matches the table. ✓

Out of scope (confirmed unmodeled, intentionally left alone): open doors,
initiative, NPC reactions, retainer max/loyalty.

---

## Part A — Languages & Literacy

### A1. Language registry (single source of truth for display names)

Problem: race languages are stored as lowercase ids (`common`, `deepcommon`,
`elvish`, `secret_language_of_burrowing_mammals`) and rendered raw, while the
learnable list is title-case display strings — two naming schemes, and special
languages print as ugly ids.

Unify on a canonical registry in `data/languages.yaml`:

```yaml
names:                       # id -> proper display name (single source of truth)
  common: Common
  deepcommon: Deepcommon
  elvish: Elvish
  dwarvish: Dwarvish
  gnomish: Gnomish
  goblin: Goblin
  kobold: Kobold
  # ... every d20-table language ...
  secret_language_of_burrowing_mammals: Secret language of burrowing mammals
  druidic: Druidic
additional:                  # now a list of IDS (the d20 learnable table)
  - bugbear
  - doppelganger
  - dragon
  - dwarvish
  - elvish
  - gargoyle
  - gnoll
  - gnomish
  - goblin
  - halfling
  - harpy
  - hobgoblin
  - kobold
  - lizard_man
  - medusa
  - minotaur
  - ogre
  - orcish
  - pixie
  - human_dialect
alignment: {law: Lawful, neutral: Neutral, chaos: Chaotic}
```

Model change (`aose/models/language.py`): `LanguageData` gains
`names: dict[str, str]`. `additional` stays `list[str]` but now holds **ids**.
`alignment` unchanged (alignment id → tongue display name).

**Display names are book-authoritative.** Every registered name matches the AOSE
text exactly, including casing and diacritics — e.g. `doppelganger: Doppelgänger`,
`lizard_man: Lizard man`, `human_dialect: Human dialect`, `gnoll: Gnoll`. The
title-case fallback is only a safety net for an unregistered id; all known
languages are registered explicitly so the book form is always used.

Engine (`aose/engine/languages.py`):
- `display_name(lang_id, lang_data) -> str` — registry lookup; **fallback** for an
  unregistered id title-cases it (underscores → spaces, preserving the flavourful
  "Secret language of…" form). Guarantees any data-discovered language renders
  with a proper name.
- `known_languages(...)` returns **ids** internally; the sheet maps to display
  names via `display_name`. (Alternatively `known_languages` returns display
  names directly — implementation detail; the registry + fallback is the
  contract.) De-dup stays case-insensitive on ids.
- `available_additional(...)` compares on ids and excludes native + alignment +
  **granted** languages (see A2).

Flavourful special tongues (e.g. the gnome's "Secret language of burrowing
mammals", druid's "Druidic") keep their full descriptive names — they are valid,
shown as known, and never appear in the learnable INT-pick list.

### A2. Surface class/race-granted special languages (non-learnable)

New `granted_languages(spec, data) -> list[str]` (in `languages.py`, still pure —
model traversal only):
- Walk **race** features (all) + **class** features (gated by
  `gained_at_level <= class entry level`), collecting
  `feature.mechanical.languages` (list of ids).
- The gnome race feature already carries `mechanical.languages:
  [secret_language_of_burrowing_mammals]`. Add `mechanical: {languages: [druidic]}`
  to the druid Languages feature for the secret sect tongue.

Granted languages are:
- added to **known** languages, and
- **excluded** from `available_additional` (not learnable via INT).

**Out of scope (V1):** the druid's per-level Sylvan languages ("a language used by
creatures of Sylvan forests, at each level above 2nd") stay as descriptive
feature text — open-ended, GM-chosen, not a fixed enumerable list.

### A3. Three-tier literacy (derived, with class override)

From **final** INT (post-racial, post-adjustment — the same score used for the
language count):

| INT | Literacy |
|---|---|
| ≤ 5 | Illiterate |
| 6–8 | Basic |
| ≥ 9 | Literate |

Class override (data-driven, no class id in engine): add
`mechanical: {illiterate_below_level: 2}` to the barbarian Literacy feature. The
restriction is **1st-level-only** — a barbarian learns to read/write on early
adventures, so at level 2+ they fall back to the INT table.

Engine: `literacy(spec, data) -> str` returns `"illiterate" | "basic" | "literate"`.
It computes the INT-derived tier, then forces `"illiterate"` if **any** class
entry has `entry.level < feature.mechanical.illiterate_below_level` for a feature
that declares it.

Sheet: a `Literacy: <state>` line in the "Languages, Notes & Skills" group, next
to the existing INT-3 broken-speech note.

---

## Part B — Wisdom magic saves, conditional racial resilience + saves-UI rethink

### B1. WIS modifier as synthetic conditional modifiers

The WIS "Magic Saves" modifier (versus magical effects, never breath) is currently
not applied anywhere. Model it by reusing the existing `Modifier` model
(`condition` + `source` fields already present).

New `wisdom_save_modifiers(spec, data) -> list[Modifier]` built from **effective**
WIS modifier (`value`):

| Target | Condition | In headline? | Rationale |
|---|---|---|---|
| `save:spells` | none | **yes** | Spells/rods/staves are magical by definition |
| `save:wands`  | none | **yes** | Wands are magical by definition |
| `save:death`  | `"magical"` | no | Death-ray half is magical; poison is not |
| `save:paralysis` | `"magical"` | no | Magical paralysis/petrify only |

`source="Wisdom"`, `op="add"`. A negative WIS mod correctly worsens the save
(`saves.py` does `target -= sum(add values)`; `add` of −1 raises the target).
WIS never targets `breath`.

These are computed per-derivation, not persisted. They are local to the saves
derivation (not added to `features.all_modifiers`).

### B1a. Racial resilience must become conditional (correcting an existing bug)

The demihuman resilience / magic-resistance features (recently encoded as
CON-scaled `GrantedModifier`s) currently apply **unconditionally** to whole
umbrella save categories. That is wrong for the categories the bonus only half
covers. The book bonus is versus **poison, spells, and magic wands/rods/staves**
(duergar adds **paralysis**) — notably **not** death magic or petrification. But
our save categories are OSE umbrellas:

- `death` = death-ray **or** poison
- `paralysis` = paralysis **or** petrify (turn to stone)
- `spells` = rods, staves, **or** spells (fully covered → unconditional)
- `wands` = magic wands (fully covered → unconditional)

So each `save:death` resilience modifier must gain `condition: poison`, and the
duergar `save:paralysis` modifier must gain `condition: paralysis`. The
`spells`/`wands` modifiers stay unconditional. Gnome magic resistance only ever
targeted `spells` + `wands`, so it needs **no** change.

Data changes (`data/races/*.yaml`, on the existing `granted_modifiers`):

| Race | Feature | Modifier | Change |
|---|---|---|---|
| dwarf | Resilience | `save:death` | add `condition: poison` |
| dwarf | Resilience | `save:spells`, `save:wands` | unchanged (unconditional) |
| halfling | Resilience | `save:death` | add `condition: poison` |
| halfling | Resilience | `save:spells`, `save:wands` | unchanged |
| duergar | Resilience | `save:death` | add `condition: poison` |
| duergar | Resilience | `save:paralysis` | add `condition: paralysis` |
| duergar | Resilience | `save:spells`, `save:wands` | unchanged |
| gnome | Magic Resistance | `save:spells`, `save:wands` | unchanged |

The descriptive `mechanical.save_categories` blocks already name `poison`
(not `death`); they stay as-is — they are not engine-load-bearing.

**Behaviour / test impact:** a dwarf/halfling/duergar's **death** save *headline*
will no longer include the resilience bonus (it moves to a conditional "vs poison"
line in the modal). The recent `test: update dwarf save expectations to include
resilience bonus` expectation must be reverted for the `death` headline and
re-asserted as a conditional breakdown line. `spells`/`wands` headlines are
unchanged.

### B2. Headline vs. breakdown split

`saves.py` already excludes conditioned modifiers from the headline number
(`m.condition is None`). The split therefore falls out naturally:

- **Base** — best class-progression value across all classes, no modifiers.
- **Modified (headline)** — base + all **unconditional** modifiers: class best,
  magic items, feature-granted unconditional parts (resilience on `spells`/`wands`),
  and WIS on `spells`/`wands`. Floor at `SAVE_FLOOR` (2).
- **Conditional** modifiers — WIS on death/paralysis (`magical`), resilience on
  death (`poison`) and duergar paralysis (`paralysis`) — are computed but
  **excluded** from the headline; shown only in the modal.

### B3. Breakdown view model

New `saving_throws_detail(spec, data)` returns, per category:

```
SaveBreakdown(
    category: str,            # id: death / wands / paralysis / breath / spells
    base: int,
    modified: int,            # headline (after unconditional mods, floored)
    lines: list[SaveModLine], # one per contributing modifier
)
SaveModLine(
    source: str,              # modifier.source (feature/item name, or "Wisdom")
    bonus: int,               # signed save adjustment: +N = bonus (better), -N = penalty (worse)
    conditional: bool,        # True when modifier.condition is not None
    note: str,                # e.g. "vs magical effects" / category real-world half
)
```

`bonus` is framed from the **player's** point of view, not the raw target number:
a +N improves the save, a −N worsens it. The modal renders it literally as
`+N bonus` / `−N penalty` so there is no ambiguity (OSE saves are roll-high
internally, but the player never sees the target delta).

The existing `saving_throws()` dict becomes a thin derivation of `.modified`.
Each line reads `modifier.source` and `modifier.condition` (that is what `source`
was added for). Conditional lines are rendered distinctly and excluded from the
headline arithmetic.

### B4. Category + condition labelling (resolves the poison/petrification nuance)

Our data categories are OSE umbrellas. The modal shows the umbrella label, and
each conditional line shows *which sub-cause within that umbrella* it applies to.
Two small id → label mappings (engine constants — these are fixed game terms):

**Category labels:**

| id | Modal label | WIS applies? |
|---|---|---|
| `death` | Death / Poison | yes — death-ray (magical) half only |
| `wands` | Wands | yes — wholly magical |
| `paralysis` | Paralysis / Petrify | yes — magical half only |
| `breath` | Breath Attacks | never |
| `spells` | Spells / Rods / Staves | yes — wholly magical |

**Condition labels** (`modifier.condition` → modal note):

| condition | Modal note |
|---|---|
| `magical` | magical effects only |
| `poison` | poison only (not death magic) |
| `paralysis` | paralysis only (not petrification) |

So a dwarf's **Death / Poison** modal shows: base; a conditional Wisdom line
"*+1 bonus — magical effects only*" (death-ray); and a conditional Resilience line
"*+3 bonus — poison only*". Neither is in the headline; they cover complementary
halves and never stack on one actual save. Unconditional lines (e.g. resilience on
`spells`/`wands`) appear in both the headline and the modal, sourced by feature
name.

### B5. UI

The saves block on the sheet:
- Each row shows **base → modified**, with the modified value prominent.
- Each row is clickable → a **breakdown modal** (reuse the existing single-open
  overlay controller in `sheet_overlays.js`).
- The modal lists: base, every contributing `SaveModLine` rendered as
  `<source>: +N bonus` / `−N penalty`, conditional lines flagged distinctly
  ("conditional — magical sources only"), and the umbrella / real-world category
  labels.

---

## Components & boundaries

| Unit | Responsibility | Depends on |
|---|---|---|
| `models/language.py` | `LanguageData` gains `names`; `additional` holds ids | pydantic |
| `engine/languages.py` | `display_name`, `granted_languages`, `literacy`, updated `known_languages`/`available_additional` | models only (pure) |
| `engine/saves.py` | `wisdom_save_modifiers`, `saving_throws_detail`, `SaveBreakdown`/`SaveModLine`; `saving_throws` derived from detail | models, features, magic |
| `sheet/view.py` | feed literacy + language display names + save breakdowns into `CharacterSheet` | engine |
| `data/languages.yaml` | registry (`names`), id-based `additional` | — |
| `data/classes/barbarian.yaml` | `illiterate_below_level: 2` on Literacy feature | — |
| `data/classes/druid.yaml` | `mechanical.languages: [druidic]` on Languages feature | — |
| `data/races/{dwarf,halfling,duergar}.yaml` | `condition: poison` on `save:death` (+ `condition: paralysis` on duergar `save:paralysis`) resilience modifiers | — |
| `web/templates/sheet.html` | literacy line; clickable saves rows + breakdown modal | — |

## Testing

- **Languages:** display-name registry + unregistered-id fallback; granted
  languages surfaced and excluded from learnable list (gnome, druid); native +
  alignment + granted all non-learnable; INT count unchanged.
- **Literacy:** INT tiers (5/6/8/9 boundaries); barbarian L1 forced Illiterate,
  L2 falls back to INT table; multi-class with one illiterate-below-level class.
- **WIS saves:** positive/negative/zero WIS on spells & wands headline; death &
  paralysis conditional WIS excluded from headline but present in breakdown;
  breath never affected; `SAVE_FLOOR` respected; interaction with magic-item
  save mods.
- **Conditional resilience:** dwarf/halfling death-save headline excludes the
  `poison` resilience bonus (present as a conditional breakdown line); their
  `spells`/`wands` headlines still include it; duergar paralysis headline excludes
  the `paralysis` resilience bonus; gnome `spells`/`wands` unchanged. Update the
  existing dwarf save-expectation test accordingly.
- **Breakdown view model:** base vs modified correctness; line sources; category
  + condition labels; conditional flagging.

## Non-goals

- Druid per-level Sylvan languages (descriptive only).
- Open doors, initiative, NPC reactions, retainers.
- Making spells/wands WIS conditional (treated as always magical).
- Any change to the verified-correct HP / XP / STR / DEX / INT-count derivations.
