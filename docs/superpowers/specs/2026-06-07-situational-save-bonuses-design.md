# Situational ("vs X") save bonuses — design

**Date:** 2026-06-07

## Problem

Some classes and races grant *broad, cross-cutting* conditional save bonuses
that do not map to any single save category — e.g. the druid's "+2 to saving
throws against electricity (lightning) and fire" or the svirfneblin's "+2 vs
illusions". In OSE these apply whenever the relevant effect forces a save,
regardless of whether the underlying category is death/wands/paralysis/breath/
spells.

Today these live in the data only as *descriptive feature text*. They are not
mechanically encoded, not displayed as numbers, and there is no system for
adding more of them. The existing conditional-save machinery only handles
modifiers tied to a *single* category (poison→death, paralysis, magical),
rendered inside the per-save breakdown modal.

We want:

1. A data-driven representation for cross-cutting "vs X" save bonuses, attachable
   from race/class features **and** magic items.
2. Display of these bonuses directly **under** the saving-throws block, in a
   smaller font (always visible footnotes — not hidden behind the modal).
3. A sweep of all race/class data to encode every passive "vs X" save bonus that
   currently sits in text-only descriptions.

## What already exists

- `GrantedModifier` (YAML) → `feature_modifiers()` walks reached class features
  and all race features → emits `Modifier` objects carrying `condition`
  (open-ended free text) and `source` (the feature name).
- Magic items emit the same `Modifier` shape via `active_modifiers`.
- `all_modifiers(spec, data) = active_modifiers + feature_modifiers` is the
  single list every save derivation consumes.
- `saving_throws_detail()` computes per-category `base`/`modified`/`lines`;
  the sheet renders a clickable per-save breakdown modal with a ★ marker for
  category-specific conditionals.

The plumbing is ~80% there. The gap is a representation for *cross-cutting*
bonuses plus the under-block display.

## Decisions (from brainstorming)

- **Data scope:** full sweep of all races and classes — audit every YAML for
  passive "vs X" save bonuses in text-only feature descriptions and encode them.
- **Display form:** grouped by source. One feature granting two effects renders
  as a single line, e.g. `+2 vs fire & lightning (Energy Resistance)`.
- **Modal overlap:** cross-cutting bonuses appear **only** as the new under-block
  notes. Per-category breakdown modals are unchanged (they keep showing only
  category-specific conditionals: poison, paralysis, magical). Avoids rendering
  the same bonus five times.
- **Grammar:** a new `save:vs:<thing>` target family (chosen over overloading
  `save:all` + condition). `save:all` already has a live unconditional meaning
  (5 magic items use `save:all add 1` to bump all five headline saves); adding a
  condition to mean "don't fold into headlines, show as a footnote" would
  overload that target with two meanings. `save:vs:*` is unambiguous, never
  touches a headline, and reads clearly in YAML.

## Architecture

### 1. Data grammar

A cross-cutting save bonus is a `GrantedModifier` (features) or `Modifier`
(magic items) with target `save:vs:<thing>`. One feature with two effects emits
two grants:

```yaml
- id: energy_resistance
  name: Energy Resistance
  text: Druids gain a +2 bonus to saving throws against electricity (lightning) and fire.
  gained_at_level: 1
  granted_modifiers:
  - {target: "save:vs:fire", op: add, value: 2}
  - {target: "save:vs:lightning", op: add, value: 2}
```

`feature_modifiers()` already stamps `source=feat.name`, so no engine change is
needed to carry the source. Magic items get this for free — any catalog or
per-instance `Modifier(target="save:vs:fire", op="add", value=2,
source="…")` flows through `active_modifiers` into `all_modifiers`.

`op` is expected to be `add` for these (a bonus). Other ops are not meaningful
for situational bonuses and are simply not collected by the new function
(only `op == "add"` is gathered), keeping behaviour predictable.

### 2. Engine — `aose/engine/saves.py`

- `_VS_DISPLAY: dict[str, str]` — display-name registry for the `<thing>`
  suffix, mirroring the languages-registry pattern. Maps where the natural
  pluralisation/wording differs (e.g. `"illusion" → "illusions"`). Fallback for
  unregistered things: `thing.replace("_", " ")`.
- `class SituationalSaveBonus(BaseModel)`: `source: str`, `bonus: int`,
  `things: list[str]` (display names).
- `situational_save_bonuses(spec, data) -> list[SituationalSaveBonus]`:
  1. Take `all_modifiers(spec, data)`.
  2. Keep modifiers where `target.startswith("save:vs:")` and `op == "add"`.
  3. Group by `(source, value)`; within a group collect each target's `<thing>`
     suffix mapped through `_VS_DISPLAY`, de-duplicated.
  4. Return a list sorted deterministically (by `source`, then `bonus`
     descending). `things` within a group sorted alphabetically.
  - Empty source → `source` falls back to `"—"` (consistent with the existing
    modal's `m.source or "—"`).

**Headline math is untouched.** `saving_throws_detail` continues to match only
`save:all` and `save:{name}`; `save:vs:*` never folds into a headline and never
appears in a per-category modal. The existing `save:all add 1` magic items are
unaffected.

### 3. View — `aose/sheet/view.py`

- `class SheetSituationalSave(BaseModel)`: `bonus: int`, `vs: str` (joined
  display string, e.g. `"fire & lightning"`), `source: str`.
- `CharacterSheet` gains `situational_saves: list[SheetSituationalSave]`.
- `build_sheet` populates it from `saves.situational_save_bonuses(...)`, joining
  `things` for display: a single thing as-is; two joined with `" & "`; three or
  more joined with `", "` and the last with `" & "`.

### 4. Template — `sheet.html` (+ `sheet_print.html`)

A small block directly under the existing `.saves` grid:

```html
{% if sheet.situational_saves %}
<div class="save-notes">
  {% for sn in sheet.situational_saves %}
  <div class="save-note">+{{ sn.bonus }} vs {{ sn.vs }}
    <span class="muted">({{ sn.source }})</span></div>
  {% endfor %}
</div>
{% endif %}
```

CSS: a `.save-note` rule in `sheet.css` using the existing small-font / muted
tokens from `docs/STYLE-GUIDE.md` (read the guide before writing CSS). No new
overlay/modal — these are always-visible footnotes.

`sheet_print.html` gets the same block so situational bonuses appear on the
printed sheet. (Wizard `review.html` does not render the saves block; out of
scope.)

### 5. Data sweep (verify against the PDF per project practice)

Audit every race + class YAML for passive "vs X" save bonuses currently in
text-only feature descriptions and encode them as `save:vs:*` grants.

Confirmed so far:

- **Druid** `energy_resistance` → `save:vs:fire` +2, `save:vs:lightning` +2.
- **Svirfneblin** (race) → `save:vs:illusion` +2.

Flagged **out of scope** (not passive numeric save bonuses):

- Kineticist *Energy Control* activated power (a power-use effect, not a passive
  feature).
- Elf-style *immunities* (immunity is not a numeric save modifier).
- Dwarf/duergar/halfling resilience and gnome magic resistance: already encoded
  as category-specific conditionals (poison/spells/wands/paralysis) — unchanged.

Magic-item encoding is **not** part of this scope. The system supports magic
items emitting `save:vs:*` modifiers (they are collected automatically); actual
catalog encoding of items like "+2 vs fire attacks" is a follow-up.

### 6. Modifier docstring

Add the `save:vs:<thing>` family to the `target` grammar documentation in
`aose/models/modifier.py`.

## Testing

- **Engine** (`tests/test_situational_saves.py` or similar):
  - Grouping by source; a single feature with two `save:vs:*` grants collapses
    to one `SituationalSaveBonus` with two `things`.
  - Magic-item pickup: an equipped item with a `save:vs:*` modifier surfaces.
  - Display-name mapping (`illusion → illusions`); underscore fallback.
  - Empty case (no situational bonuses) → empty list.
- **Data:** druid → fire + lightning grouped under one source; svirfneblin →
  illusions.
- **Regression:** `save:all add 1` items still bump all five headlines; no
  `save:vs:*` modifier alters any headline or appears in a per-category modal.
- **View:** `CharacterSheet.situational_saves` populated end-to-end for a druid.

## Non-goals

- No magic-item catalog encoding (system-ready only).
- No conditions on `save:vs:*` modifiers (YAGNI).
- No changes to the per-category breakdown modal behaviour.
- No new overlay/interaction — footnotes are static.

## Coordination note

In-progress uncommitted work (ability-breakdown changes in `ability_mods.py`,
`view.py`, `sheet.css`, `sheet.html`) touches some of the same files. This work
edits different regions (the saves view model / saves template block / a new CSS
rule) and must not disturb that work.
