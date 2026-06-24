# Retainer hiring follows the hiring PC's class/edition rules

**Date:** 2026-06-24
**Status:** Design approved, pending implementation plan
**Branch:** (tbd) `feat/retainer-hiring-rules`

## Problem

Hiring a retainer currently ignores most of the hiring character's ruleset and
content choices:

- `_retainer_class_options` ([view.py:1301](../../../aose/sheet/view.py)) filters
  only by `allowed_retainer_classes` (the AOSE per-class hiring-tier rule). It does
  **not** apply `content_enabled`, so classes from a source the player disabled
  (e.g. a turned-off *Carcass Crawler 1*) still appear, and it does **not** exclude
  race-as-class entries in Advanced mode.
- `generate_retainer` ([retainers.py:48](../../../aose/engine/retainers.py)) calls
  `apply_racial_modifiers` **without** `include_optional`, so the optional
  human-benefits rule (`human_racial_abilities`) is silently dropped for retainers.
- The hire form ([_companions.html:104](../../../aose/web/templates/_companions.html))
  hard-codes the retainer's `race_id` to the hiring PC's own race. There is no race
  picker in Advanced, and nothing distinguishes Basic (no separate race) from
  Advanced (race chosen).
- No server-side validation that a chosen class/race is actually permitted; the
  demihuman class-restriction and level-cap rules are never applied to a retainer.

## Goal

A hired retainer is built under the **same edition and content rules the hiring
character plays under**:

- **Basic** (`separate_race_class` off): may be any class **including** demihuman
  race-as-class entries; **no separate race** is chosen (a standard class is human;
  a race-as-class entry carries its own race via `race_locked`).
- **Advanced** (`separate_race_class` on): the player chooses **both a class and a
  race**; **race-as-class entries are not offered** (you build, e.g., an Elf Fighter,
  not the "Elf" race-as-class).
- **Demihuman restrictions** apply to the retainer's race+class combination in
  Advanced, governed by the same `lift_demihuman_restrictions` flag as the player:
  when the flag is off, `race.allowed_classes` and `race.class_level_caps` are
  enforced; when on, any race may take any class at any level.
- **Optional human benefits** (`human_racial_abilities`) are applied to human
  retainers exactly as for the player — i.e. only in Advanced/split mode.
- **Only content available to the player** is available to the retainer: classes and
  races from a source/category the player disabled (`disabled_content`) do not appear.
  *(Scope: classes and races only. The auto-rolled equipment kit and any spell content
  are out of scope for this change.)*
- **No multi-classing** for retainers, even when the `multiclassing` rule is on. (This
  already holds — the hire route builds a single class — and is pinned by a test.)

These gates are layered **on top of** the existing `allowed_retainer_classes` AOSE
hiring-tier rule (which class/level a PC may hire), which is unchanged and orthogonal.

## Non-goals / explicit decisions

- **Class and race demihuman matching is enforced at submit, not in the dropdown.**
  The hire form is a single no-JS POST. Per-race greying of class options would need
  client JS, so the class and race `<select>`s list all content/edition-available
  options and the route validates the chosen **combo** (and level vs. cap), returning
  a 400 with a clear message on an illegal pairing. This mirrors how the wizard
  validates on `post_class`/`post_race`. A two-step race-then-class filtered flow was
  considered and rejected as too large a change to the inline hire expander.
- Equipment kit and spell selection are **not** re-gated by `disabled_content` in this
  change (decided: classes & races only).
- Human benefits are **not** applied to Basic-mode human retainers (decided: mirror the
  player, who only receives them in Advanced).

## Design

### 1. Shared availability predicates — `engine/sources.py`

`sources.py` already owns `content_enabled` and imports only models. Add three pure
helpers there so the wizard and retainer code share one source of truth:

```python
def class_available(cls, ruleset) -> bool:
    """A class is offerable under this ruleset: its source/category is enabled
    AND it is not a race-as-class entry hidden by Advanced mode.
    In Basic (separate_race_class off) race-locked demihuman classes ARE offered."""
    if not content_enabled(cls.source, "classes", ruleset):
        return False
    if ruleset.separate_race_class and cls.race_locked:
        return False
    return True

def race_available(race, ruleset) -> bool:
    return content_enabled(race.source, "classes", ruleset)

def class_allowed_for_race(class_id, race, ruleset) -> bool:
    """Moved verbatim from wizard._class_allowed_for_race: lift_demihuman ->
    True; empty race.allowed_classes -> True; else membership test."""

def class_level_cap(race, class_id, ruleset) -> int | None:
    """The demihuman level cap for a race+class, or None when uncapped or when
    lift_demihuman_restrictions is on. Mirrors the wizard's inline computation."""
```

`class_available` does **not** special-case `normal_human` — callers decide.

### 2. Wizard refactor — `web/wizard.py`

- Delete `_class_allowed_for_race`; import `class_allowed_for_race` from
  `engine.sources` (keeping the call sites identical).
- In `get_class`, replace the two inline checks (`if separate_race_class and
  cls.race_locked: continue` plus the `content_enabled` guard) with
  `if cls.id == "normal_human" or not class_available(cls, ruleset): continue`.
- Replace the inline level-cap computation with `class_level_cap(race, cls.id, ruleset)`.
- In `get_race`, replace the inline `content_enabled(...)` guard with
  `race_available(race, ruleset)`.

This is duplication removal only; player-facing behaviour is unchanged (guarded by
existing wizard tests).

### 3. `generate_retainer` — `engine/retainers.py`

In the split-race branch, pass the optional-human flag through:

```python
elif hiring_spec.ruleset.separate_race_class and race_id in data.races:
    abilities = apply_racial_modifiers(
        abilities, data.races[race_id],
        include_optional=hiring_spec.ruleset.human_racial_abilities,
    )
```

Because this branch only runs in Advanced/split mode, human benefits remain
Advanced-only by construction — matching the player. No other change; the function
still accepts a single-element `class_ids`.

### 4. Sheet view — `sheet/view.py`

- `_retainer_class_options`: keep `normal_human` always; for every other class
  require `class_available(cls, ruleset)` **and** membership in the
  `allowed_retainer_classes` result.
- New `_retainer_race_options(spec, data) -> list[dict]`: when
  `ruleset.separate_race_class` is on, return `[{"id","name"}]` for every race with
  `race_available(race, ruleset)`; otherwise return `[]` (Basic shows no race picker).
- Add a `retainer_race_options: list[dict]` field to `CharacterSheet` and populate it
  alongside `retainer_class_options`.

### 5. Hire form — `web/templates/_companions.html`

In the "+ Hire a retainer…" form:

- If `sheet.retainer_race_options` is non-empty (Advanced), render a race
  `<select name="race_id">` listing those options (replacing the current
  `<input type="hidden" name="race_id" value="{{ sheet.race_id }}">`).
- If empty (Basic), omit the race control; the route's `race_id` parameter defaults to
  `"human"` so a standard class is human and a race-as-class entry overrides via its
  `race_locked`.

### 6. Hire route guard — `web/routes.py` `retainer_add`

Add server-side validation before generation (rejecting forged/stale posts and illegal
demihuman combos):

1. `class_id` must be in the allowed set (`normal_human`, or `class_available` ∩
   `allowed_retainer_classes`); else 400.
2. In Advanced (`separate_race_class`): `race_id` must satisfy `race_available`; else
   400. The combo must satisfy `class_allowed_for_race(class_id, race, ruleset)`; else
   400 with a message naming the race and class. If `class_level_cap(...)` is not None
   and `level` exceeds it, 400 with the cap.
3. Existing `level > pc_level` check unchanged.

The class/race availability is recomputed in the route from the spec's ruleset (not
trusted from the form), reusing the same predicates.

## Testing

New/updated tests (pytest, `tests/`):

- **Predicates** (`sources`): `class_available` hides race-locked classes in Advanced,
  shows them in Basic, and hides a class whose `source:classes` is in
  `disabled_content`; `race_available` hides a disabled race source;
  `class_allowed_for_race` / `class_level_cap` behave per `lift_demihuman_restrictions`
  (parametrized; the latter two are move-with-tests if wizard tests already cover them).
- **`_retainer_class_options`**: always includes `normal_human`; excludes a disabled
  CC class; excludes race-as-class entries in Advanced and includes them in Basic;
  still intersects `allowed_retainer_classes`.
- **`_retainer_race_options`**: empty in Basic; in Advanced lists content-enabled races
  and omits a disabled race source.
- **`generate_retainer`**: a human retainer gains `optional_ability_modifiers` when
  `human_racial_abilities` is on in Advanced, and does **not** in Basic; race-as-class
  and split-race ability paths unchanged.
- **Route `retainer_add`**: rejects a disabled/forbidden class (400); in Advanced
  rejects an illegal race+class combo when restrictions are on and accepts it when
  `lift_demihuman_restrictions` is on; rejects a level above the race/class cap.
- **Single-class invariant**: hiring with the `multiclassing` rule on still produces a
  one-class retainer.

## Docs

- Update the retainers section of `docs/ARCHITECTURE.md` in place (hiring now mirrors
  the player's edition/content/demihuman rules; human benefits Advanced-only; race
  picker in Advanced).
- Add a one-line row to the top of `docs/CHANGELOG.md`.

## Affected files

| File | Change |
|---|---|
| `aose/engine/sources.py` | + `class_available`, `race_available`, `class_allowed_for_race`, `class_level_cap` |
| `aose/web/wizard.py` | use shared predicates; delete local `_class_allowed_for_race` |
| `aose/engine/retainers.py` | pass `include_optional` to `apply_racial_modifiers` |
| `aose/sheet/view.py` | gate `_retainer_class_options`; add `_retainer_race_options` + sheet field |
| `aose/web/templates/_companions.html` | race `<select>` in Advanced; none in Basic |
| `aose/web/routes.py` | validate class/race/combo/level in `retainer_add` |
| `tests/` | predicate, option-builder, generation, and route tests |
| `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md` | keep current |
