# Unify Spells UX — design

**Date:** 2026-06-29
**Status:** approved (design)

## Problem

The live sheet renders castable spells in source-specific silos:

- `spellbook_view` emits one "Spells — Arcane/Divine" block **per casting
  class**. A multiclass illusionist + magic-user therefore shows two separate
  "Spells — Arcane" sections.
- Scroll spells are injected into the *first* block of each caster type, tagged
  with a bespoke `scroll-tag` label.
- Spell-backed innate abilities (e.g. a tiefling's once/day spell) render in a
  *separate* "Innate Abilities" section, never alongside the spells they cast.

Each silo has its own markup variations. We want one unified presentation:
**group by caster type, fold every spell-like source into that list with a
source label, and render every row through one common macro.**

## Goals

1. All arcane spells in a single list regardless of source, each with a label
   saying where it comes from (as scrolls have today).
2. Multiclass illusionist + magic-user → a single arcane list; each spell
   labelled with its class.
3. A spell-backed innate ability (tiefling once/day) appears in that same arcane
   list, labelled with its source (e.g. "Tiefling").
4. Casting both divine and arcane → separate lists (one block per caster type).
5. One set of styles + macros — no per-source visual variation.

## Decisions (from brainstorming)

- **Non-spell innate abilities** (breath weapon, fungal spores) keep their own
  "Innate Abilities" section. Only *spell-backed* innate abilities move into the
  arcane/divine lists. The spell lists only ever hold actual spells.
- **Source labels** show only when a block is ambiguous — i.e. it draws from
  **2+ distinct source labels**. A solo magic-user shows no tags; add a scroll
  or a second class and every row in that block gets labelled.
- **Mental powers** are out of scope. Their shared daily-use pool is a different
  model; they keep their own section.
- **`sheet_print.html`** is out of scope for this change.
- **The "Manage spells" drawer** stays grouped by class (memorization targets a
  specific class's slots). A multiclass caster with two arcane classes still
  gets two independent memorize sections — display unifies, management does not.

## Approach

Unify in the **view layer** (`aose/sheet/view.py`, which already assembles every
derivation). No engine changes — the data already exists in `engine/spells`,
`engine/spell_sources`, and `engine/innate`. Assembly stays unit-testable;
templates stay declarative.

Rejected alternatives: merging/sorting rows inside Jinja (untestable, fragile);
a generic engine "castable thing" abstraction (over-engineered — modals and
mechanics differ per source, mental excluded).

## Design

### 1. Unified row model — `SpellRow`

Replaces the parallel `SpellbookRow` and `ScrollSpellRow`, and absorbs
spell-backed innate rows:

- Display: `name`, `display_name`, `level`, `reversible`, `reversed`, `detail`
- Provenance: `source_label: str` (class name / scroll name / innate source),
  `source_kind: Literal["class", "scroll", "innate"]`
- Pips, unified: `ready: int` + `spent: int`
  - class: unspent memorised copies / spent copies
  - scroll: remaining charges / 0
  - innate: remaining daily uses / used
- `known: bool` — class arcane book spell, not memorised → renders a "known"
  tag instead of pips
- `castable: bool` + `block_reason: str | None` — scrolls (and any future
  gated source): "needs Read Magic", "can't read X", "not on your person"
- `modal_id: str` — the existing per-source modal to open (unchanged)

### 2. Block model — `SpellListBlock`

```
SpellListBlock {
  caster_type: str                 # "arcane" | "divine"
  show_labels: bool                # 2+ distinct source_labels in this block
  levels: list[SpellListLevel]
}
SpellListLevel {
  level: int                       # 0 == Cantrips
  cap: int                         # memorisable slots at this level (class)
  used: int                        # spent slots at this level (class)
  rows: list[SpellRow]
}
```

One block per caster type; multiple classes of the same type merge into it.
Blocks ordered arcane then divine. `cap`/`used` summarise the class slot
budget for the level header (today's behaviour); scroll/innate rows do not
contribute to them.

### 3. Assembly — `spell_lists_view(spec, data) -> list[SpellListBlock]`

- **Per class**: emit class rows (label = class name) into its caster-type
  block, preserving today's spellbook/slot semantics (known book spells, per
  `(spell, reversed)` memorised pip counts, divine memorised-only).
- **Per scroll**: emit rows (label = scroll name, current behaviour incl.
  `castable`/`block_reason`/charges) into the matching caster-type block.
- **Per spell-backed innate ability**: resolve the spell's caster type via its
  `spell_lists`; emit a row (label = innate source) into that block, pips =
  remaining/used daily. If the spell maps to no known list (no caster type),
  it stays in the Innate section (edge case — not routed).
- Sort rows within a level by name. Compute `show_labels` per block from the
  set of distinct `source_label`s.

This replaces `spellbook_view` and its `_scroll_rows_by_level` helper. The
`CharacterSheet.spellbook` field becomes `spell_lists: list[SpellListBlock]`.

### 4. One macro — `spell_row(row, show_labels)`

A macro (in a macros include) renders `.snm` + optional `.src-tag` source label
+ unified pips / "known" tag / locked state + the `data-modal` hook. Used for
every spell row in every block. The per-block cast legend stays.

### 5. Innate view split

`innate_view` continues to return non-spell innate abilities for the Innate
section. Spell-backed innate abilities (those whose `spell_id` resolves to a
spell with a caster type) are consumed by `spell_lists_view` instead. The
existing per-innate modals (`modal-innate-{id}`) are reused by the routed rows,
so spend/restore still works from the unified list.

### 6. Untouched

The "Manage spells" drawer (`sheet.spells` / `SpellClassView`), mental powers,
the non-spell Innate Abilities section, and all existing modals/routes. The
print sheet.

## Testing

Replace `spellbook_view` tests with `spell_lists_view` tests:

- multiclass same-type merge → one block, both classes' spells, labels shown
- scroll injection into the matching caster-type block, with label + charges
- spell-backed innate routed into the correct caster-type block, labelled by
  source, with remaining/used pips
- label suppression: single-source block (solo magic-user) → `show_labels`
  false, no tags
- arcane + divine → two separate blocks
- non-spell innate ability stays out of the spell lists (still in `innate_view`)

## Out of scope

- `sheet_print.html` unification
- Mental powers folding into the unified model
- Any change to memorization mechanics or the Manage drawer grouping
