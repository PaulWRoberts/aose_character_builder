# CC5 Cantrips (optional rule) — design

**Date:** 2026-06-12
**Status:** approved (brainstorming)
**Source:** Carcass Crawler Issue 5, "Cantrips" by Gavin Norman

## Summary

Implement Carcass Crawler 5's optional **Cantrips** rule and its dependent
**Read Magic Cantrip** rule. Cantrips are modelled as **level-0 arcane spells**
that ride the existing spellbook / slot machinery — a level-0 group appears
alongside spell levels 1+ on the sheet, and a separate "choose your cantrips"
picker appears in the wizard. The optional rule (not a content checkbox) brings
the cantrip spells into play; they apply only to **dedicated arcane spell
casters**.

## Rule text

### Cantrips (the table)

Dedicated arcane spell casters know a number of cantrips by level. The table
gives **both** the spellbook count and the memorisable count:

| Character level | Cantrips |
|---|---:|
| 1–2 | 2 |
| 3–4 | 3 |
| 5+ | 4 |

> **Adding cantrips:** An arcane spell caster can add new cantrips to their
> spell book in the same way as other arcane spells. See *Spell Books* in
> Old-School Essentials.

### Read Magic Cantrip (optional, depends on Cantrips)

> Groups wishing to make scrolls easier to use can demote *read magic* from a
> 1st level spell to a cantrip that is automatically known by all arcane casters,
> in addition to the normal number of cantrips known. This does not alter the
> number of cantrips a character can memorise, however.

## Key interpretations / decisions

These were settled during brainstorming:

1. **"Dedicated arcane spell caster"** = a class whose caster type is `arcane`
   **and** whose level-1 progression row grants a 1st-level spell slot
   (i.e. casts arcane spells with access to spells at character level 1). This
   includes magic-user, illusionist, and arcane race-as-class entries (elf,
   goblin/hephaestan magic-user, etc.); it excludes scroll-only **Mage** and
   **Acolyte** (no slots) and the L2-casting **Arcane Bard**.

2. **Cantrips are level-0 spells, reusing everything.** Stored in the existing
   `ClassEntry.spellbook` (known) and `ClassEntry.slots` (memorised, level 0).
   No new storage shape.

3. **The cantrip table caps follow whichever spellbook rule is active**, exactly
   as level-1+ spells do — there is **no level-0 special-casing in `learn`**:
   - **Standard spell books:** the "learn" button (a mentor) adds cantrips
     freely; the spellbook (known) cap = the memorisable cap = the cantrip table
     value (2/3/4).
   - **Advanced spell books:** cantrips are **copy-only** — added by copying from
     a spell book or scroll (1d100 vs INT), and the spellbook count is uncapped.
     Cantrips can be authored into spell books and scrolls like any arcane spell.
   - In **both** modes the **memorisable** cap is the cantrip table value (2/3/4),
     enforced by injecting `{0: cantrip_count(level)}` into `memorizable_slots`.

4. **Read Magic Cantrip behaviour** (when the dependent rule is on, for dedicated
   arcane casters only):
   - **Demote:** the level-1 `magic_user_read_magic` / `illusionist_read_magic`
     are hidden from every arcane spell listing (known / learnable / wizard
     candidate / copyable).
   - **Auto-grant:** a level-0 `read_magic_cantrip` is injected into the *known*
     list — **beyond** the 2/3/4 cap (it is not stored in `spellbook`, so it
     consumes no cantrip slot) but memorisable like any cantrip.
   - Scoped to dedicated arcane casters only. The rule text says "all arcane
     casters", but non-dedicated casters (Mage, Arcane Bard) have no cantrip
     mechanism in which to hold/memorise it.

5. **Cantrips come from the rule, not a content option.** They are gated solely
   by `RuleSet.cantrips`, independent of whether CC5 *content* is enabled. (They
   ride the `magic_user` / `illusionist` lists, which are enabled whenever the
   casting class is playable, so no per-spell source gate is involved.)

## Architecture

### 1. RuleSet flags (`aose/models/ruleset.py`)

Two new bool fields:

```python
cantrips: bool = False
read_magic_cantrip: bool = False   # depends on cantrips
```

### 2. Settings / wizard rules UI (`aose/web/settings_routes.py`)

- `RULE_LABELS`: `cantrips` → "Cantrips", `read_magic_cantrip` → "Read Magic
  Cantrip".
- `RULE_DESCRIPTIONS`: short copy for each (cantrip table summary; read-magic
  demotion summary).
- `IMPLEMENTED_RULES`: add both.
- `SOURCE_RULES`: new `carcass_crawler_5` entry expressing the dependency:
  ```python
  "carcass_crawler_5": [
      _rule("cantrips", _rule("read_magic_cantrip")),
  ],
  ```
  The existing `_enforce_rule_tree` (server) and `data-parent` greying (JS)
  force `read_magic_cantrip` off whenever `cantrips` is off — no new UI code.

The CC5 panel already renders (the source exists); it currently has no Optional
Rules subsection, which this adds. No content checkbox is involved.

### 3. Cantrip data (`data/spells/carcass_crawler_5_cantrips.yaml`)

13 new `Spell` entries, all `level: 0`, `source: carcass_crawler_5`,
`spell_lists: [magic_user, illusionist]`, with the article's range/duration/
description:

`cantrip_book_leaf`, `cantrip_cleaning_brush`, `cantrip_coloured_flame`,
`cantrip_floating_trinket`, `cantrip_magic_quill`, `cantrip_open_close_portal`,
`cantrip_rune`, `cantrip_sense_magic`, `cantrip_smoke_rings`, `cantrip_spark`,
`cantrip_vanish`, `cantrip_wizard_flame`, and `read_magic_cantrip` (the
demoted Read Magic).

No loader change — the spell glob auto-discovers new YAML files.

### 4. Spell engine (`aose/engine/spells.py`)

All cantrip logic lives here (a separate module would create an import cycle —
it would need `caster_type_of`, which is in `spells.py`, the bottom of the
spell DAG). New helpers:

```python
def cantrip_count(level: int) -> int:          # 2 / 3 / 4 banded
def is_dedicated_arcane(cls, data) -> bool:    # arcane + L1 spell slot
```

Cantrip identifiers (module constants): `READ_MAGIC_CANTRIP_ID`,
`DEMOTED_READ_MAGIC_IDS = {"magic_user_read_magic", "illusionist_read_magic"}`.

**Optional cantrip-aware params, defaulting to off** (so existing callers —
`energy_drain.py`, tests — are unchanged):

- `accessible_levels(entry, cls, data=None, ruleset=None)` — when both supplied
  and cantrips apply, adds `0`.
- `memorizable_slots(entry, cls, data=None, ruleset=None)` — adds
  `{0: cantrip_count(level)}`. This is the single injection point that makes the
  sheet's level-0 spellbook group, `assign_slot`, `_free_slots_at`, and cast
  pips all work for cantrips with no further change.
- `known_spells(entry, cls, data, ruleset=None)` — when cantrips + read-magic-
  cantrip apply: inject the auto-granted `read_magic_cantrip` (beyond cap) and
  filter out demoted L1 read magic.
- `learnable_spells(entry, cls, data, ruleset=None)` — passes `ruleset` to
  `accessible_levels` so level-0 cantrips become learnable/copyable; filters out
  demoted L1 read magic.
- `learn(...)` and `assign_slot(...)` pass `data`/`ruleset` into the cap/level
  lookups (so cantrips obey the standard book cap and the level-0 memorise cap).
  `assign_slot` gains a `ruleset` parameter; its route passes it.
- New `beginning_cantrip_count(entry, cls, data, ruleset)` =
  `cantrip_count(level)` for a dedicated arcane caster with the rule on, else 0.
  (`beginning_spell_count` stays spells-only; the wizard renders cantrips as a
  separate picker — see §6.)

### 5. Spell books & scrolls (`aose/engine/spell_sources.py`)

`new_spell_source` already has **no spell-level filter**, so cantrips can be
authored into spell books and scrolls today (they are arcane spells). The only
change: `copyable_spell_ids` / `copy_spell` pass `ruleset` through to
`learnable_spells` so a level-0 cantrip in a source registers as copyable under
the Advanced rule (uncapped). No other change.

### 6. Wizard (`aose/web/wizard.py`)

- `_caster_entries` gains, per dedicated arcane caster, a **separate cantrip
  block**: `cantrip_required = beginning_cantrip_count(...)` (= 2 at L1) plus its
  own candidate list (the level-0 cantrip spells on the class's lists; demoted
  read magic excluded when the rule is on). Rendered as a distinct
  "Cantrips — choose N" sub-section beside the existing spell picker.
- `_apply_spells` validates the cantrip selection count + eligibility
  independently and writes the chosen level-0 ids into the same
  `entry.spellbook` list.
- `_apply_rule_changes` cascading clear: when `cantrips` is toggled off
  mid-wizard, strip every level-0 spell id from each `draft["spellbooks"][cid]`.
  (`read_magic_cantrip` stores nothing — it is auto-granted — so toggling it
  needs no clear.)

### 7. Sheet rendering (`aose/sheet/view.py`, templates)

- `spells_view` / `spellbook_view` call `memorizable_slots` / `known_spells` /
  `learnable_spells` with `data` + `spec.ruleset`, so the level-0 group, its
  learnable list, and the auto-granted read-magic cantrip all appear.
- The spellbook template labels the level-0 group **"Cantrips"** instead of
  "Level 0" (small conditional in the level header). `sheet_print.html` mirrors.
- `OPTIONAL_RULE_LABELS` (the sheet's active-rules summary) gains `cantrips` and
  `read_magic_cantrip`.

## Testing

**Engine (`tests/test_spells.py` / new `tests/test_cantrips.py`):**
- `cantrip_count` banding (1→2, 2→2, 3→3, 4→3, 5→4, 9→4).
- `is_dedicated_arcane`: true for magic-user/illusionist; false for Mage,
  Acolyte, Arcane Bard.
- Level-0 injection: `memorizable_slots`/`accessible_levels` include level 0
  only when `data`+`ruleset` (cantrips on) supplied for a dedicated arcane
  caster; unchanged otherwise.
- Standard rules: `learn` allows cantrips up to the table cap and blocks over it.
- Advanced rules: `learn` blocks cantrips (copy-only); a cantrip in a spell
  book/scroll is copyable via `copy_spell` and lands uncapped.
- Read-magic demotion: L1 read magic hidden from known/learnable when the rule
  is on; `read_magic_cantrip` auto-known beyond the cantrip cap and memorisable.

**Settings (`tests/test_settings.py` / `test_combat_talents_settings.py`
pattern):**
- CC5 panel renders the nested `cantrips` → `read_magic_cantrip` rule.
- `read_magic_cantrip` forced off when `cantrips` unchecked (server + parse).
- No "pending"/unimplemented badge for either rule (the existing regression
  guard).

**Wizard (`tests/test_wizard*.py` pattern):**
- A magic-user draft shows a "choose 2 cantrips" picker; selecting 2 stores them
  in the spellbook; wrong count is rejected.
- Toggling `cantrips` off clears level-0 ids from the draft spellbook.

## Out of scope

- No cantrip "roll" affordance (the article lets the referee allow choose **or**
  roll; the app mirrors spell selection, which is choose-only).
- No new encumbrance/AC/attack interactions — cantrips are utility-only flavour.
