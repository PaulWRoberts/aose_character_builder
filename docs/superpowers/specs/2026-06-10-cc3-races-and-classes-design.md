# Carcass Crawler 3 — races, classes & the *feature-choice* mechanic

**Date:** 2026-06-10
**Source:** Carcass Crawler Issue 3 (`source: carcass_crawler_3`, already in `data/sources.yaml`)
**Status:** Approved design — pending implementation plan

## Goal

Import the Carcass Crawler 3 content — Beast Master, Dragonborn, Mutoid,
Mycelian, Tiefling — as both demihuman **classes** (race-as-class, `race_locked`)
and split-mode **races**, and introduce the new cross-cutting concept these
entries rely on: **races/classes with choices made (or rolled) at creation**.

A *feature choice* is a "pick (or roll) N from this table" group. The chosen
option(s):

- are picked in the wizard with the secondary-skill interaction model (auto-roll,
  Strict-locked; free pick/reroll otherwise);
- show on the sheet as features — **only the chosen options appear**, never the
  picker or the unchosen rows;
- carry the same automation grammar as any feature: AC bonuses, synthetic
  "unarmed" attacks, situational `save:vs:*` bonuses, and **per-day use-limited
  innate abilities** (e.g. a Fiendish Gift that casts *magic missile* once/day).

## The mapping

Exactly the CC1 Gargantua/Goblin/Hephaestan shape. **A race and its race-as-class
are independent stat blocks that share only the concept and name** — each is
authored straight from the book and may freely diverge (different daily-use counts,
different feature sets, different ability handling). Nothing in the engine or data
links them beyond `race_locked`; do not assume one mirrors the other.

| Entry | Class file | Race file |
|---|---|---|
| Beast Master | `beast_master` (human class, no `race_locked`, no choices) | — |
| Dragonborn | `dragonborn` (`race_locked: dragonborn`) | `dragonborn` |
| Mutoid | `mutoid` (`race_locked: mutoid`) | `mutoid` |
| Mycelian | `mycelian` (`race_locked: mycelian`) | `mycelian` |
| Tiefling | `tiefling` (`race_locked: tiefling`) | `tiefling` |

**5 class files + 4 race files.** Each file is authored independently from
the book (see the independence note above); where a race and its race-as-class
happen to share a feature they are written out on both, but they are free to differ
and several do (see Content).

## 1. Data model — `FeatureChoice` / `ChoiceOption`

New module `aose/models/choice.py` (imported by both `race.py` and
`character_class.py`):

```python
class DailyUses(BaseModel):
    model_config = ConfigDict(extra="forbid")
    per_day: int = 1                 # flat uses/day (e.g. breath weapon = 3)
    scales_with_level: bool = False  # when True, max uses = class level
                                     # (Mycelian fungal spores: once/day per level)

class ChoiceOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    text: str = ""
    mechanical: dict[str, Any] | None = None
    granted_modifiers: list[GrantedModifier] = Field(default_factory=list)
    daily_uses: DailyUses | None = None   # use-limited chosen option (Fiendish Gift spell)
    spell_id: str | None = None           # references a real Spell — drives the modal expander

class FeatureChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str                 # group id, unique among a character's active sources
    name: str               # "Mutations", "Draconic Bloodline"
    text: str = ""          # group instructions
    pick: int = 1           # how many to choose
    roll_dice: str | None = None   # e.g. "d8"/"d10" for the Roll button
    cosmetic: bool = False  # purely flavor (Fiendish Appearance) — picked/shown, no mechanics
    options: list[ChoiceOption]
```

Notes:

- **No `allow_duplicates` field.** All CC3 pick-N tables re-roll duplicates;
  selection is always *distinct*. (YAGNI — nothing needs True.)
- A `ChoiceOption` is deliberately **feature-shaped** (`mechanical` +
  `granted_modifiers` + `daily_uses`), so chosen options reuse every existing
  automation path with no per-option-type code.
- `daily_uses` and `spell_id` are added to `ClassFeature` and `RaceFeature` too,
  because some daily/spell abilities are *fixed* features, not choices (Dragonborn
  breath weapon, Mycelian fungal spores).

`Race.feature_choices: list[FeatureChoice]` and
`CharClass.feature_choices: list[FeatureChoice]` (both default empty).

**Selection storage:** `CharacterSpec.feature_choices: dict[str, list[str]]` —
group id → chosen option ids (default `{}`; no migration per project policy).

## 2. Engine integration — `aose/engine/features.py`

`_reached_features` is the canonical "what applies" generator. Extend it (and the
parallel iteration in `feature_modifiers`) to also yield the **chosen options** of
each active group:

- race groups apply in split mode only (suppressed for race-as-class, like race
  features today);
- class groups apply for every class entry (race-as-class included), threading the
  granting class's **level** so level-scaling resolves.

Because all feature-derived data funnels through this generator,
`feature_modifiers`, `feature_weapons`, `open_doors_category_bonus`, and
`all_modifiers` pick up chosen options automatically. The existing race-as-class
guard prevents double-counting. A small refactor threads `level | None` through the
shared iteration so `feature_weapons` can resolve level-scaled damage (see §4).

Validation: at resolution, a stored option id that isn't in any active group is
ignored; group ids are expected unique among a character's active race+class
sources (only race-as-class demihuman entries carry choices, and multiclassing
excludes race-as-class, so collisions can't occur in practice).

## 3. Daily-use innate abilities (the "granted spells" automation)

New cycle-free `aose/engine/innate.py` (imports models + loader only):

- collects every reached feature/option carrying `daily_uses`;
- resolves `max_uses` (`per_day`, or class level when `scales_with_level`);
- exposes `spend` / `restore` / `reset` mirroring the mental-power pool.

Storage: `CharacterSpec.innate_uses: dict[str, int]` (feature/option id → uses
spent today). The existing `/rest/night` and `/rest/full-day` routes reset it
alongside `reset_powers`.

Sheet: new `InnateAbilitiesBlock` (in `view.py`) rendered as pips in the same
column as Mental Powers — each entry shows name, description, uses remaining, and
(when `spell_id` is set) the **spell expander** from §6. Routes
`/innate/{spend,restore,reset}`.

Covers: Fiendish-Gift spell options (chosen, use-limited, 1/day), Dragonborn breath
weapon (fixed, 3/day), Mycelian fungal spores (fixed, per-level), Mutoid pincer
lock (descriptive — no counter needed).

Other Fiendish-Gift options map to existing patterns instead of pips:

- `+2 vs paralysis` → `GrantedModifier(save:paralysis, add, 2)`
- `+2 vs poison` → `GrantedModifier(save:death, add, 2, condition: poison)`
- Draconic Resistance (`+2 vs <breath type>`) → `save:vs:<type> +2` on each
  bloodline option (the druid Energy-Resistance pattern)
- Cold/fire "half damage" → descriptive text only.

## 4. Mycelian level-scaling

- **Natural AC** (6[13] → 3[16]): a level-scaled `ac set` `GrantedModifier`, table
  `{1:6, 2:5, 3:4, 4:3}` (descending AC) — **no condition**. This mirrors the
  Kineticist level-AC precedent exactly. The engine already handles shields the way
  we want: `_has_worn_armor` (`armor_class.py`) excludes shields, so `unarmored` only
  ever means "no *body* armour," and an `ac set` is a base candidate evaluated
  outside the armour gate with its condition ignored — so a Mycelian's natural AC
  stands as the base and a carried shield's bonus simply adds on top. No new
  "unarmored-but-allow-shield" condition is introduced; Kineticist stays as-is.
- **Fist damage** (1d4 per level): extend the `feature_weapons` descriptor with an
  optional per-level die (`damage_per_level_die: d4`). `features.py` resolves it
  against the granting class level so the synthetic melee profile deals `Ld4` at
  level L; `attacks.py`/`_feature_weapon_profile` consume the resolved damage
  string. Flat-damage descriptors (gargantua rock) are unchanged.

## 5. Wizard — a "Features" section in `class_setup`

Runs after both race and class are chosen, so one section covers split-mode race
choices and race-as-class class choices. Interaction mirrors secondary skills:

- `_feature_choices_context(draft, data)` gathers the active groups (race when
  split & not race-as-class; each class otherwise) with pick count, options,
  current selection, and `roll_dice`.
- On first GET, **auto-roll** each group (distinct picks), store on the draft, and
  **lock under Strict Mode**. Non-strict renders a checklist + Roll/reroll button.
- `POST /wizard/{id}/feature-choices` validates pick counts, valid option ids, and
  distinctness; cosmetic groups validate identically.
- `_class_setup_complete` additionally requires choices done when any active group
  exists. `_clear_after_race` / `_clear_after_class` also drop `feature_choices`
  from the draft. `_draft_to_spec` carries `feature_choices` onto the spec.

## 6. Sheet rendering

- `_class_features` / `_race_features` append the **chosen options** as
  `SheetFeature`s (source-labelled, e.g. "Mutation"), and never render the picker
  or unchosen rows. Always-on `features:` render as today.
- **Feature detail modal**: features become clickable, opening a modal with the
  feature text. When the feature/option has a `spell_id`, the modal includes an
  **expander** rendering that spell's full card (reusing the shop
  `detail_card` / `row-detail` expander pattern). The same expander appears on the
  innate-ability pip entry for spell-granting daily abilities.

## 7. Content (`source: carcass_crawler_3`)

All numbers/text taken from the provided CC3 extract. Class progressions
(XP/THAC0/saves/HD) transcribed per the book tables.

**Classes**

- `beast_master` — human; prime STR+WIS; HD 1d6; max 14; leather/chainmail/shields;
  any weapons; no choices. Features (text): Animal Companions, Companions' Behaviour,
  Clairvoyance (L5), Identify Tracks, Reaction Modifier, Speak with Animals (L2/L4),
  9th-level stronghold.
- `dragonborn` — `race_locked`; prime STR; HD 1d8; max 10; any armour/weapons;
  langs Alignment/Common/Dragon. Fixed: Breath Weapon (`daily_uses {per_day:3}`),
  Scales (`ac +1`), Dragon-Affecting Magic, Dragon Affinity (text). Choice:
  **Draconic Bloodline** (`pick 1`, d10) — each option sets breath shape/damage in
  text and grants `save:vs:<type> +2`.
- `mutoid` — `race_locked`; prime DEX; HD 1d6; max 8; leather/shields; one-handed
  melee + all missile. Fixed: Back-Stab, skills (text). Choice: **Mutations**
  (`pick 2`, d8) — options include Clawed hand (`feature_weapons` 1d6 melee),
  Pincer (1d3 + lock text), Sticky tongue (1d3 bite), Scales (`ac +2`), Beast eyes
  (infravision text), etc.
- `mycelian` — `race_locked`; prime STR; HD 1d8; max 6; shields only; any weapons;
  langs +Deepcommon. Fixed: Natural AC (level-scaled `ac set`, §4), Fist
  (`feature_weapons` `damage_per_level_die: d4`, §4), Fungal Spores
  (`daily_uses {scales_with_level:true}`; Hallucinogenic from L4 — text), Light
  Sensitivity (`ac -1 bright_light`, `attack -2 bright_light`), Infravision,
  Telepathy, Growth (text). No pickable choice group.
- `tiefling` — `race_locked`; prime CHA+DEX; HD 1d6; max 10; leather/chainmail/
  shields; any weapons. Fixed: Holy Water Vulnerability, Infravision, skills (text).
  Choices: **Fiendish Gifts** (`pick 2`, d10) — spell options carry
  `daily_uses {per_day:1}` + `spell_id` (`magic_user_magic_missile`,
  `magic_user_mirror_image`, `magic_user_detect_magic`,
  `magic_user_detect_invisible`, `magic_user_ventriloquism`, darkness via the
  reversible `magic_user_light`); resistance options map to save modifiers per §3.
  **Fiendish Appearance** (`pick 2`, d10, `cosmetic: true`).

**Races** (independent split-mode stat blocks — authored from the book, not copied
from the class files; each carries its own `feature_choices`, `allowed_classes`, and
`class_level_caps` from the extract, and may differ from its race-as-class):

- `dragonborn` — ability mods none; reqs CON 9/INT 9; Breath Weapon `per_day:1`
  (race differs from class's 3/day); Draconic Bloodline + Resistance + Dragon-
  Affecting Magic.
- `mutoid` — ability mods none; no reqs; Mutations choice.
- `mycelian` — −1 DEX / +1 WIS; req CON 9; Fungal Spores from L3 once/day
  (`daily_uses {per_day:1}`, gated by feature level — race version differs from the
  class's per-level scaling); Infravision, Light Sensitivity, Telepathy.
- `tiefling` — +1 DEX / −1 WIS; req INT 9; Fiendish Gifts + Appearance, Holy Water
  Vulnerability, Infravision.

No new languages needed (`dragon`, `deepcommon` already in `data/languages.yaml`).

**Out of scope:** the per-level percentage skill tables (Mutoid/Tiefling skills,
Beast Master Identify Tracks) are **feature text only** — no new skills engine.
Cold/fire "half damage" resistances are descriptive. Breath-weapon damage
("half current HP") is descriptive.

## 8. Tests (`tests/test_cc3_*`)

- **Loader/model**: all 5 class + 4 race files load; `FeatureChoice`/`ChoiceOption`
  validate; `spell_id`s resolve to real spells.
- **Choice resolution**: chosen options emit expected modifiers, feature-weapons,
  and `save:vs:*`; unchosen options contribute nothing; race-as-class suppression
  holds (no double-count).
- **Innate abilities**: max-use resolution (flat + per-level), spend/restore/reset,
  rest reset; spell expander data present for spell options.
- **Mycelian scaling**: Natural-AC by level; fist profile `Ld4` by level.
- **Sheet**: only chosen options render as features; feature modal exposes the
  spell expander.
- **Wizard**: full flow through the Features section — auto-roll, Strict lock,
  non-strict pick/reroll, validation (count/distinct/valid ids), downstream clears
  on race/class change, `_draft_to_spec` carries selections.

## Docs to update on landing

- `docs/CHANGELOG.md` — one-line row.
- `docs/ARCHITECTURE.md` — extend the `GrantedModifier`/features section with the
  feature-choice mechanic; add an innate-abilities note alongside Mental Powers;
  add a "Carcass Crawler 3 content" subsection mirroring the CC1 one.
- `CLAUDE.md` — add `feature_choices` + `innate_uses` to the Storage-shapes list.
