# Spell Books & Scrolls — Design Spec

Date: 2026-06-03
Status: Approved (pending implementation plan)

## Goal

Fully support **magic scrolls** and **spell books** as owned documents, and make
the **Advanced Spell Book** optional rule behave by the book: post-creation
arcane spells are no longer free picks — they must be **copied from a source**
(another spell book or a scroll) with an INT-based check.

Source rules: `import/markdown/advanced-fantasy_spell-books.md`,
`import/markdown/magic-items/advanced-fantasy_magic-scrolls-and-maps.md`.

## What already exists (not changing)

- **Standard Spell Book rule** is implemented: `spells.learn()` caps the book at
  the memorizable count per spell level; the wizard/sheet surface "learnable"
  spells (accessible level, not yet known) for free selection (mentoring on
  level-up). This stays as the standard-rule behaviour.
- Beginning-spell selection in the wizard (`post_spells`) writes the starting
  book directly into `draft["spellbooks"][class_id]` — it does **not** call
  `learn()`. Advanced beginning-spell count already uses the INT table
  (`beginning_spell_count`). Creation-time free pick is unaffected by this work.
- Per-instance ownership patterns to mirror: `ContainerInstance`, `AmmoStack`,
  `MagicItemInstance` — all live on `CharacterSpec` as lists separate from
  `inventory`, with their own engine module and shared sheet/route surface.

## Rule summary (the two regimes)

| | Standard Spell Book | Advanced Spell Book (optional rule on) |
|---|---|---|
| Book size | Capped at memorizable count per level | Uncapped |
| Beginning spells | = memorizable total | INT-table count |
| **Adding spells post-creation** | **Free "learn" on level-up** (mentoring), up to the per-level cap | **Copy from a source only** (spell book / scroll), INT-based % check |
| Copy failure | n/a | Burns **that (source, spell) pair**; the same spell may still be copied from a *different* source |

Scroll **casting** is independent of which regime is active and available to both.

## Decisions (confirmed)

1. **Copying check** — the app rolls the INT-based `d100` check. On failure the
   spell is marked failed **on that source only**; it can still be attempted from
   a different source. (Prevents "spam Learn on one book until it succeeds.")
2. **Scroll casting** — supported on the live sheet. Usability is gated by
   caster-type match: an arcane caster can cast arcane scrolls, a divine caster
   divine scrolls. **No Read Magic check.** No spell-level check (the point of a
   scroll is casting above your level). Casting consumes that one spell; a
   multi-spell scroll keeps the rest; an emptied scroll instance is removed.
3. **Creation of spell books / scrolls** — sheet-only, **Add-only** (no gold),
   matching the magic-item acquisition pattern. The wizard equipment step stays
   mundane-only.
4. **Scrolls of Protection** — plain catalog `MagicItem` entries with full rules
   text and **no special Use action** (consistent with how potions are modelled
   today — they are inventory items the player removes manually on use).
5. **Cursed scrolls and treasure maps** — out of scope.

## Where failures are stored (design invariant)

A failed copy is recorded **on the source document, never on the character.**
`copy_failed` is a field on `SpellSourceEntry` (inside the `SpellSource`
instance). There is **no** per-character "spells I can never learn" list, and
nothing is written to `ClassEntry`/`CharacterSpec` on a failure beyond the
source entry's flag. This is what makes a failure burn *that source for that
spell* while leaving the same spell copyable from any other source.

## Architecture

Unified per-instance `SpellSource` model (one shape for both spell books and
scrolls, distinguished by `kind`), a new cycle-free engine module
`aose/engine/spell_sources.py`, a new sheet section + routes, and a small data
file for the protection scrolls. No catalog item is used for the custom-content
documents (their contents are chosen per instance).

### Data model — `aose/models/character.py`

```python
class SpellSourceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spell_id: str
    copy_failed: bool = False     # advanced rule: a failed copy from THIS source

class SpellSource(BaseModel):
    """A physical document the character owns — an arcane spell book or a magic
    scroll — with custom contents chosen at acquisition (Add-only, sheet).
    Not stored in `inventory`; carries its own existence like ContainerInstance.
    Scroll spells are expended (removed) when cast; spell books are never
    expended. `copy_failed` entries are arcane-copy attempts that failed from
    this specific source."""
    model_config = ConfigDict(extra="forbid")
    instance_id: str                              # uuid4 hex
    kind: Literal["spellbook", "scroll"]
    caster_type: Literal["arcane", "divine"]      # spellbook is always arcane
    name: str = ""                                # optional label; display falls back to a default
    entries: list[SpellSourceEntry] = Field(default_factory=list)
```

`CharacterSpec` gains:

```python
spell_sources: list[SpellSource] = Field(default_factory=list)
```

No migration needed (app is not deployed; new optional field defaults empty).

### Engine — `aose/engine/spell_sources.py` (new, cycle-free)

Imports only models + `data.loader` + `engine.dice` + `engine.spells` +
`engine.magic` (for effective INT). Nothing imports it back.

```python
class SpellSourceError(ValueError): ...

def new_spell_source(kind, caster_type, spell_ids, data, name="") -> SpellSource
    # validate each spell exists and sits on a list of caster_type; spellbook
    # forces caster_type="arcane"; reject duplicates within the document;
    # uuid4 instance_id. No spell-level filter (a document may hold any level).

def add_spell_source(sources, kind, caster_type, spell_ids, data, name="") -> list[SpellSource]
    # Add-only append (GM grant / loot); no gold.

def remove_spell_source(sources, instance_id) -> list[SpellSource]

def cast_from_scroll(sources, instance_id, spell_id) -> list[SpellSource]
    # kind must be "scroll" and contain spell_id (not already expended); remove
    # that entry; if the scroll has no entries left, drop the instance.
    # (Caster-type usability is enforced by the caller against the character's
    # classes — the engine fn validates only the scroll/entry integrity.)

def copy_spell(entry, cls, data, ruleset, eff_int, sources, instance_id,
               spell_id, rng=None) -> tuple[ClassEntry, list[SpellSource], bool]
    # ADVANCED RULE ONLY (raises otherwise). Validates: character is arcane;
    # source is arcane; spell on the class's list; spell.level in accessible
    # levels; spell not already known; entry exists and not copy_failed.
    # Rolls d100 vs spells.copy_chance_for_int(eff_int):
    #   success -> append spell_id to entry.spellbook; return (entry', sources, True)
    #   failure -> set copy_failed=True on that source entry; return (entry, sources', False)

# View helpers (for spells_view / the new section):
def castable_scroll_entries(source, spec, data) -> list[...]   # entries the char may cast
def copyable_entries(source, entry, cls, data, ruleset) -> list[...]  # advanced-rule copy targets
```

`copy_spell` appends to the spellbook directly (it performs its own validation);
it does **not** route through `learn()` because `learn()` is the standard-rule
mutator and will refuse under the advanced rule (see below).

### `aose/engine/spells.py` changes

- **Add `copy_chance_for_int(int_score: int) -> int`** — the "Chance of Copying"
  column (20/30/35/40/50/70/75/85/90) of the same INT table that already drives
  `beginning_spells_for_int`. Extend the existing `_INT_*` table data so both
  functions read one source of truth.
- **Guard `learn()`**: when `ruleset.advanced_spell_books` is true, raise
  `SpellError("under advanced rules, spells must be copied from a source")`.
  Standard-rule behaviour is unchanged. The wizard does not call `learn()`, so
  beginning-spell selection is unaffected; this only closes the sheet's
  free-add path under the advanced rule.
- **`spells_view`**: under the advanced rule, return `learnable=[]` (the sheet's
  free pick is hidden; the Spell Books & Scrolls section's per-entry **Copy**
  actions replace it). Under the standard rule, `learnable` is unchanged.

### UI — sheet section + routes

New sheet section **"Spell Books & Scrolls"** (collapsible, mirroring the Magic
Items / Ammo sections). For each `SpellSource`:

- Header: derived/edited name, kind, caster type, spell count.
- Per spell entry, context-sensitive actions:
  - **Scroll + a character class whose caster_type matches** → **Cast**
    (consumes the spell; confirms the result; removes the scroll if emptied).
  - **Advanced rule + arcane character + arcane source + spell is
    castable-level, on the class's list, not yet known, not `copy_failed`** →
    **Copy to spellbook** (rolls; shows success/failure). `copy_failed` entries
    render struck-through and inert.
- A **Remove** action for the whole document.

**Add flow** (sheet only, Add-only):

- Choose **Spellbook** → choose an **arcane** spell list → pick one or more
  unique spells from that list → optional name → Add.
- Choose **Scroll** → choose **arcane** or **divine** → pick one or more spells
  from all lists of that type → optional name → Add.
- No spell-level filter at creation.

Routes (sheet; follow the existing `/character/{id}/...` POST pattern, keyed by
instance and — for copy — by `class_id`):

- `POST /spell-sources/add`
- `POST /spell-sources/remove`
- `POST /spell-sources/cast`
- `POST /spell-sources/copy`

### Data — `data/equipment/scrolls.yaml` (new)

Four `MagicItem` entries, auto-loaded by the equipment glob:

- `scroll_of_protection_from_elementals`
- `scroll_of_protection_from_lycanthropes`
- `scroll_of_protection_from_magic`
- `scroll_of_protection_from_undead`

Each: `item_type: magic`, `magic: true`, `cost_gp: 0`, `equippable: false`,
`category: scrolls`, full rules text in `description` (radius, effect,
ranged-attack caveat, breaking, duration — verbatim from the source markdown).
No charges / no Use action (matches potions).

## Testing (TDD)

- **Engine** (`tests/test_spell_sources.py`, injectable `rng`):
  add/remove; `cast_from_scroll` (consume one, multi keeps rest, empty scroll
  removed, non-scroll/missing-spell errors); `copy_spell` success appends to
  book, failure sets `copy_failed`, second attempt on a failed entry rejected,
  same spell copyable from a second source, all the guard conditions
  (non-arcane char, divine source, off-list, above castable level, already
  known, advanced-rule-off rejection).
- **`tests/test_spells.py`**: `copy_chance_for_int` table; `learn()` raises under
  the advanced rule; `spells_view` hides `learnable` under the advanced rule.
- **Routes** (`tests/test_spell_routes.py` or a new module): add/remove/cast/copy
  happy paths + caster-type-mismatch cast rejection + advanced-only copy.
- **Data**: a load test asserting the four protection scrolls parse as
  `MagicItem` and appear under `category: scrolls`.

## Out of scope

- Cursed scrolls; treasure maps.
- Random scroll-generation tables (the player picks exact spell contents).
- "Lost spell book" rewriting, mentoring time/cost, and magical research (p114) —
  narrative/referee bookkeeping, not modelled.
- Captured-book readability (only-owner-can-read) — flavour, not enforced.
