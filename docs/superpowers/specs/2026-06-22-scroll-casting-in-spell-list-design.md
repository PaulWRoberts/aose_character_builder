# Scroll spells in the spell list — design

**Date:** 2026-06-22
**Status:** Approved (brainstorming) — pending implementation plan
**Branch:** `feat/scroll-casting-spell-list`

## Goal

Surface spells that can be cast from owned **scrolls** inside the character
sheet's existing per-caster-type spell list, so a player sees every spell they
can cast right now — memorized *and* scroll-borne — in one place, organized by
spell level.

Worked example (one caster who has Cure Wounds memorized twice, plus two
scrolls):

```
Level 1
Cure Wounds            ··        ← 2 memorized (existing behaviour)
Cure Wounds  scroll 1  ···       ← 3 charges on scroll 1
Cure Wounds  scroll 2  ·         ← 1 charge on scroll 2
```

Each scroll's spells show **separately per scroll** and **separately from
memorized copies**, at the spell's **true level**.

## Rules grounding (AOSE)

From `import/markdown/magic-items/advanced-fantasy_magic-scrolls-and-maps.md`:

- **Type gate.** "Only arcane spell casters can use scrolls of arcane spells.
  Only divine spell casters can use scrolls of divine spells."
- **Arcane scrolls** are "written in magical script that can only be read by
  magic" → require Read Magic to decipher.
- **Divine scrolls** are "written in normal languages (usually Common), but can
  only be used by divine spell casters" → require knowing the scroll's language.
- **No caster-level requirement** to cast from a scroll — any caster of the
  right type can use any spell on it, regardless of the spell's level.
- **One use.** "If a scroll contains multiple spells, only the spell cast
  disappears from the scroll." Casting expends one charge.
- A referee may place the **same spell multiple times** on a scroll (nothing
  forbids it); the builder's current one-each restriction is a convenience, not a
  rule.

## Design decisions (settled in brainstorming)

1. **Duplicate spells per scroll are allowed** (e.g. 3× Cure Wounds), modeled as
   repeated entries. Spellbooks keep no-duplicates.
2. **Casting is inline** from the spell list.
3. **Arcane scrolls are unlocked by casting Read Magic on the specific scroll.**
   A single casting unlocks the whole scroll, permanently. Reading requires Read
   Magic to be *memorized* at the time and **burns** that memorized cast.
4. **Divine scrolls** carry a language (picked from `languages.yaml`, default
   Common); a divine scroll is castable only if the character knows that language.
5. **Read action lives on the scroll** in the Documents tab; the spell-list rows
   only reflect locked/unlocked (and unreadable-language) state.

## Components

### 1. Data model — `aose/models/character.py`

`SpellSource` gains:

| field | type | meaning |
|---|---|---|
| `language` | `str = "Common"` | language a **divine** scroll is written in; ignored for arcane scrolls and spellbooks |
| `unlocked` | `bool = False` | whether an **arcane** scroll has been deciphered (Read Magic cast on it); permanent once true; ignored for divine/spellbooks |

`SpellSourceEntry` is unchanged — multiple charges of one spell are multiple
entries with the same `spell_id`.

Old saves: missing `language` → `"Common"`, missing `unlocked` → `False`.
Existing arcane scrolls therefore start **locked** (consistent with the new
gate). No migration code required per project convention; field defaults handle
it.

### 2. Engine — `aose/engine/spell_sources.py`

**Document creation.**
- `new_spell_source` (and `add_spell_source`) accept duplicate `spell_id`s **only
  when `kind == "scroll"`**; spellbooks still reject duplicates.
- The `MAX_SCROLL_SPELLS` (7) cap counts **total entries** (so 3× Cure Wounds
  uses 3 of 7).
- A `language` argument is accepted and stored (divine scrolls); coerced/ignored
  otherwise. Default `"Common"`.

**Cast gating.** Replace the single `can_cast_scroll` type check with a richer
result so the view can show a reason. Proposed shape: a function returning either
castable or a human reason string, e.g.

```python
def scroll_cast_block_reason(source, spec, data) -> str | None:
    # None => castable; else a short reason
```

Rules:
- wrong caster type → "not an arcane/divine caster" (or simply not shown — see
  view).
- arcane scroll, not `unlocked` → `"needs Read Magic"`.
- divine scroll, `language` not in known languages → `"can't read {language}"`.
- otherwise `None` (castable).

`can_cast_scroll` is kept (or reimplemented as `reason is None`) and used by the
existing `/spell-sources/cast` route as a hard guard.

**Known languages.** Compute via `engine/languages.known_languages(...)` using
the character's chosen/native/alignment/granted languages, matched
case-insensitively.

**Reading an arcane scroll.**
- `ready_read_magic_slot(spec, data) -> (class_idx, slot_idx) | None` — finds a
  memorized, **not-spent** slot whose `spell_id ∈ {magic_user_read_magic,
  illusionist_read_magic, read_magic_cantrip}` in any arcane class entry.
- `read_scroll(spec, data, instance_id) -> (classes, sources)` (or route
  orchestration): requires the scroll to be an **arcane scroll not already
  unlocked** and a ready Read Magic slot to exist; **spends that slot**
  (`cast_slot`) and sets `source.unlocked = True`. Raises `SpellSourceError`
  otherwise.

### 3. Sheet view — `aose/sheet/view.py`

New view model:

```python
class ScrollSpellRow(BaseModel):
    scroll_instance_id: str
    label: str            # custom name, else "scroll N"
    spell_id: str
    name: str
    level: int
    charges: int          # remaining entries of this spell on this scroll
    castable: bool
    block_reason: str | None  # why cast is disabled, if any
    detail: DetailCard | None = None
```

`SpellbookLevelGroup` gains `scroll_rows: list[ScrollSpellRow] = []`.

`spellbook_view` changes:
- For each caster-type **block**, gather castable-type scrolls (arcane scrolls →
  arcane block, divine → divine block).
- To avoid double-listing when a character has two classes of one caster type,
  attach scroll rows to the **first** block of each caster type only.
- Build scroll rows grouped by the spell's true `level`. Per (scroll, spell),
  `charges` = count of matching entries on that scroll.
- Level groups now iterate `sorted(set(caps) | set(scroll_levels))`; a level that
  exists only because of a scroll has `cap = used = 0` and only scroll rows.
- `label`: `source.name` if set, else `"scroll N"` where N is the scroll's
  1-based position among that caster type's scrolls (display-only; may shift as
  scrolls are added/emptied).
- `castable` / `block_reason` from `scroll_cast_block_reason`.

`spell_sources_view` gains, per source: `unlocked`, `language`,
`can_read` (arcane scroll, not unlocked, and a ready Read Magic slot exists), and
per-entry `can_cast` recomputed via the new gate.

`spell_source_add_options` gains a `languages` list (from `languages.yaml`) for
the divine-scroll language picker.

### 4. Web — routes + templates

**Routes (`aose/web/routes.py`).**
- `/spell-sources/add` — accept repeated `spell_ids` and a `language` field.
- `/spell-sources/cast` — enforce the full gate (`scroll_cast_block_reason`).
- **New** `/spell-sources/read` — POST `instance_id`; runs `read_scroll`
  (spends a memorized Read Magic slot, sets `unlocked`).

**Sheet spell list (`sheet.html`).** In each spellbook block's level groups,
render `scroll_rows` after the memorized rows: italic/dim scroll label, pips =
`charges`, a cast control posting to `/spell-sources/cast` when `castable`, else
the pips with a short `block_reason` and no control.

**Documents tab (`_equipment_ui.html`, `spell_source_add.js`).**
- Per arcane scroll: a **Read** button (enabled only when `can_read`); once
  `unlocked`, show "deciphered" and per-spell cast. Divine scrolls show their
  `language` and cast directly when known.
- Add-scroll form reworked: pick a spell + quantity, add to a staged,
  repeatable list (same spell allowed); a **language dropdown** (default Common)
  shown when the divine type is selected; 7-charge cap enforced across the staged
  list.

### 5. Tests

- **Engine:** duplicate-entry scroll creation (allowed for scrolls, rejected for
  spellbooks); 7-cap counts dupes; arcane gate (locked vs unlocked); divine gate
  (language known vs not); `read_scroll` requires & burns a memorized Read Magic
  slot and sets `unlocked`; reading a divine scroll or an already-unlocked scroll
  errors; reading with no Read Magic memorized errors.
- **View:** scroll rows grouped at the correct (true) levels including levels the
  caster can't otherwise cast; correct `charges`; `castable`/`block_reason` for
  locked/unreadable scrolls; scroll rows attach to the first block per caster
  type only; label falls back to "scroll N".

## Out of scope / non-goals

- Cursed scrolls, protection scrolls, treasure maps (not spell scrolls).
- Surfacing a Read affordance inside the spell list (Read stays in Documents).
- Copying from scrolls (existing Advanced-rule path is untouched).
- Any caster-level restriction on scroll casting (rules impose none).
