# Wizard Overhaul — Slice 6b: Languages Subsystem

**Date:** 2026-05-31
**Status:** Design approved, pending written-spec review

## Context

Second half of the split Slice 6 (see 6a for the Identity page it builds on).
Implements the **languages** portion of the target spec's **P7 — Identity &
Background**: native languages, the auto alignment language, and the INT-based
additional-language selection. This is a net-new subsystem — there is no
`CharacterSpec.languages` field, no language data, and no engine today.

## The rules

- **Native languages:** from the character's race (`race.languages`, which
  already includes Common + racial tongues). In Basic (race-as-class) the race
  is the derived race-as-class, so the same source applies.
- **Alignment language:** auto-determined by the chosen alignment (each of
  Law / Neutral / Chaos has its own tongue). Never chosen manually.
- **Additional languages from INT** (uses **final** INT, after racial mods and
  P5 adjustment), per the table:

  | Final INT | Additional |
  |---|---|
  | ≤ 12 | 0 |
  | 13–15 | 1 |
  | 16–17 | 2 |
  | 18 | 3 |

  INT 3 grants 0 additional **and** flags "broken speech" (a display note).
- Additional languages are **optional** (the player may choose 0..N); choosing
  fewer than N is allowed and surfaces only as a **non-blocking warning** (the
  warning is aggregated at Final Review in Slice 8; the Identity page may hint
  at it).
- The selectable additional list is the spec's default, **campaign-configurable
  later** — for now it comes from a data file and the picker enforces it
  (no free-text).

## Design

### 1. Data + model

**`data/languages.yaml`** (auto-loaded like other data):

```yaml
alignment:
  law: Lawful
  neutral: Neutral
  chaos: Chaotic
additional:
  [Bugbear, Doppelgänger, Dragon, Dwarvish, Elvish, Gargoyle, Gnoll, Gnomish,
   Goblin, Halfling, Harpy, Hobgoblin, Kobold, Lizard man, Medusa, Minotaur,
   Ogre, Orcish, Pixie, Human dialect]
```

**`aose/models/language.py`** — a small typed `LanguageData`
(`alignment: dict[str, str]`, `additional: list[str]`), loaded by
`GameData.load` into `data.languages`.

**`aose/models/character.py`** — add
`languages: list[str] = Field(default_factory=list)` to `CharacterSpec`,
storing **only the chosen additional** languages. Native and alignment
languages are derived, never stored.

### 2. Engine (`aose/engine/languages.py`, pure/cycle-free)

```python
def additional_language_count(int_score: int) -> int      # table above
def broken_speech(int_score: int) -> bool                  # int_score == 3
def native_languages(race) -> list[str]                    # race.languages
def alignment_language(alignment: str, lang_data) -> str
def available_additional(lang_data, already_known: set[str]) -> list[str]
    # additional list minus already-known (native + alignment + chosen)
def known_languages(chosen, race, alignment, lang_data) -> list[str]
    # native + alignment + chosen, order-stable + deduped
def validate_languages(chosen, race, alignment, final_int, lang_data) -> None
    # raises LanguageError unless: len(chosen) <= count(final_int),
    # chosen ⊆ available_additional, no dups, none already native/alignment
```

`LanguageError(ValueError)` mirrors the existing error types.

### 3. Identity page — Languages section (extends 6a)

Add a Languages section to the Identity page:

- **Native** languages (read-only list from race).
- **Alignment** language (read-only; derived from the alignment selected on the
  same page — computed server-side on submit, shown for the current draft
  alignment on GET).
- **Additional** pickers: up to `additional_language_count(final_int)` choices
  from `available_additional(...)`. If `broken_speech`, show the note.
- It is **valid to leave additional slots empty**; the Identity step's
  completion is unchanged from 6a (name + alignment, + skill if the rule is on)
  — languages never block it.

`POST /{draft_id}/identity` (extends 6a's handler): parse chosen languages,
`validate_languages(...)` (400 on failure), store `draft["languages"]`.

Final INT is `_creation_abilities(draft, data)["INT"]` (post racial + P5
adjustment — Slices 3/4).

### 4. Sheet integration

`sheet/view.py`: replace `languages=race.languages` with
`known_languages(spec.languages, race, spec.alignment, data.languages)` so the
sheet shows native + alignment + chosen. Surface the broken-speech note when
final INT is 3. `build_sheet` already has `data`, so `data.languages` is
available.

### 5. Downstream clears

Clear `draft["languages"]` whenever final INT could change or its dependencies
shift: add it to `_clear_after_abilities`, `_clear_after_race`,
`_clear_after_class`, and clear it when `ability_adjustments` is resubmitted and
when the `human_racial_abilities` flag toggles (both move INT). Alignment
changes don't require clearing (alignment tongues aren't in the additional
list), but re-validation on the Identity POST covers any edge case.

### 6. Tests

- `languages.yaml` loads into `LanguageData` (alignment tongues + additional
  list); `CharacterSpec.languages` defaults empty.
- `additional_language_count`: 12→0, 13→1, 15→1, 16→2, 17→2, 18→3;
  `broken_speech(3)` True, else False.
- `native_languages(elf)` includes elvish; `alignment_language("law")` =
  "Lawful".
- `available_additional` excludes native + alignment + chosen; no dups.
- `validate_languages`: ≤N passes; >N fails; choosing a native/alignment tongue
  fails; duplicate fails; unknown fails.
- `known_languages` composes + dedupes in stable order.
- Final INT drives N: an elf whose INT is raised by P5 to 13 gets 1 slot.
- Identity page renders N pickers; storing fewer than N is allowed; sheet shows
  the composed list and the broken-speech note at INT 3.
- `languages` cleared on abilities/race/class/adjustment/human-flag changes.

## Risks / notes

- The additional list overlaps racial native tongues (Dwarvish, Elvish, …);
  `available_additional` must exclude already-known so a player can't pick a
  language they already speak.
- Diacritic in "Doppelgänger" — keep the YAML UTF-8; ensure the loader/test
  handle it.
- Free-text / campaign-custom languages are explicitly deferred; the picker is
  closed to the data-file list for now.
- No migration (nothing deployed).
