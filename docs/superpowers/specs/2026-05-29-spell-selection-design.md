# Spell selection & sheet spell management — design

**Date:** 2026-05-29
**Status:** Approved (brainstorming) — pending implementation plan

## Goal

Let the character builder handle spells faithfully to Advanced Old-School
Essentials:

1. **Wizard:** when a chosen class (or race-as-class) can cast at level 1, add a
   spell step that lets the caster choose their starting *known* spells from the
   appropriate spell list.
2. **Sheet viewer:** let the player manage spells after creation — grow the known
   set (arcane only) and pick a daily *prepared* loadout — restricted to spells
   the character actually has access to.

This builds on scaffolding that already exists but was never wired:
`Spell` model, `CharClass.spell_lists`, `ClassLevelData.spell_slots`, and an
unused `ClassEntry.chosen_spells` field. There is currently **no spell data**
(`data/spells/` does not exist).

## AOSE model: known vs prepared

AOSE separates two layers, and the builder models both faithfully:

- **Known** — what a caster can potentially prepare.
  - *Arcane* (magic-user, elf, illusionist): a **spellbook** — a limited,
    selected set. Grows via leveling, scrolls, and research.
  - *Divine* (cleric, druid): the **entire** class list at accessible levels, known
    automatically. Nothing to select.
- **Prepared** — the daily memorised loadout, chosen from known spells, **hard-capped**
  per spell level by `spell_slots`. Duplicates allowed (memorise the same spell
  twice if you have two slots).

The arcane/divine distinction is a property of the **spell list / tradition**, not
the class — every class casting from the magic-user list is arcane by definition.
So caster type lives on the list (see registry below), and a class derives its
behavior from the list(s) it references.

## Decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Model | Faithful known-vs-prepared, both layers tracked |
| Prepared cap | Hard cap by `spell_slots` per spell level |
| Read Magic | Optional rule `free_read_magic`, wired end-to-end like other rules |
| Wizard vs sheet | Wizard sets *known*; sheet manages *both* known and prepared |
| Caster type home | On the spell list (a new `SpellList` registry), not the class |
| Seed data | `read_magic` + a few L1 magic-user and druid spells |
| Starting spellbook (RAW) | Read Magic + one 1st-level spell of choice (choose-count = L1 slot total) |
| Wizard step placement | After HP, before Equipment |

## Architecture

Mirrors the magic-items feature: a pure, cycle-free engine core; per-instance
state on the spec; shared wizard/sheet route pairs; a `*_view` helper feeding both
the live sheet and the wizard review.

### 1. Spell-list registry (new)

`aose/models/spell_list.py`:

```python
class SpellList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    caster_type: Literal["arcane", "divine"]
    description: str | None = None
```

- Loaded from a single file `data/spell_lists.yaml` (a YAML list of mappings,
  following the `secondary_skills.yaml` single-file pattern) into
  `GameData.spell_lists: dict[str, SpellList]`.
- Seed: `magic_user` (arcane), `druid` (divine).

`GameData.load` gains a `_load_spell_lists(data_dir)` helper that returns an empty
dict when the file is absent (keeps minimal test fixtures working).

### 2. Data-model changes

**`CharClass`** — no new field. Casting behavior is derived from the existing
`spell_lists`. (`magic_user.yaml` gains `spell_lists: [magic_user]`; `druid.yaml`
already has `spell_lists: [druid]`.)

**`ClassEntry`** — replace the unused `chosen_spells` with two lists:

```python
class ClassEntry(BaseModel):
    class_id: str
    level: int = 1
    hp_rolls: list[int] = Field(default_factory=list)
    spellbook: list[str] = Field(default_factory=list)   # known (arcane); empty for divine
    prepared: list[str] = Field(default_factory=list)     # daily loadout; duplicates allowed
```

`examples/thorin.json` updated to drop `chosen_spells` (non-caster → both lists
omitted/empty).

### 3. Engine — `aose/engine/spells.py` (pure, cycle-free)

Imports only models + loader (no derivation modules), exactly like `magic.py`.

Query / derivation:
- `caster_type_of(cls, data) -> Literal["arcane","divine"] | None` — common
  `caster_type` of the class's referenced lists; `None` if the class has no lists.
  **Rejects** a class whose lists mix arcane and divine (`ValueError`).
- `accessible_levels(entry, cls) -> set[int]` — spell levels with ≥1 slot at the
  entry's level (from `progression[level].spell_slots`).
- `slot_counts(entry, cls) -> dict[int, int]` — spell-level → slot count at the
  entry's level.
- `known_spells(entry, cls, data, ruleset) -> list[Spell]`:
  - *arcane*: resolve `entry.spellbook` to `Spell`s, plus `read_magic` if
    `free_read_magic` is on, that spell exists in data, and it is on one of the
    class's lists (no-ops gracefully if absent).
  - *divine*: every spell whose `spell_lists` intersect `cls.spell_lists` and whose
    `level` is in `accessible_levels`.
- `learnable_spells(entry, cls, data) -> list[Spell]` — *arcane only*:
  accessible-level spells on the class's lists not already in the spellbook.
- `starting_spellbook_size(entry, cls) -> int` — RAW: the class's L1 slot total
  (1 for a magic-user). Used by the wizard to enforce the exact choose-count.

Mutators (return new lists, raise `ValueError` on violation):
- `learn(entry, cls, data, spell_id)` — arcane only; spell must be on a class list
  and at an accessible level; not already known.
- `forget(entry, spell_id)` — arcane only; removes a spellbook entry.
- `prepare(entry, cls, data, ruleset, spell_id)` — spell must be **known**; a free
  slot must exist at its level (hard cap); appends to `prepared`.
- `unprepare(entry, spell_id)` — removes one matching entry from `prepared`.

**Access rule** ("would have access"): a spell is accessible to a class when it is
on one of the class's `spell_lists` **and** its `level` is in `accessible_levels`
(i.e. the class has a slot of that level at its current level). Learning and
preparing both enforce this; preparing additionally enforces known-membership and
the per-level slot cap.

### 4. Optional rule — `free_read_magic`

`RuleSet.free_read_magic: bool = False`, wired through the full methodology:
- `RULE_LABELS["free_read_magic"] = "Free Read Magic"`
- a new **"Magic"** group in `RULE_GROUPS` with a one-line description
- added to `IMPLEMENTED_RULES`
- consumed by `known_spells` (auto-grants `read_magic` to arcane casters)

The rule governs only whether Read Magic is **auto-known**. It does not make Read
Magic slot-free when prepared — that stays an ordinary slotted spell.

A regression test asserts `free_read_magic` is in `IMPLEMENTED_RULES` (the
existing "no pending badge on the settings page" guard).

### 5. Wizard step — `spells` (selects *known* only)

- Position: after `hp`, before `equipment`.
- **Gating without game_data:** `_wizard_steps`, `_next_incomplete_step`, and
  `_gate` only see the draft, so `post_class` caches a derived
  `draft["spellcasting"]` boolean (true when any picked class casts at L1). It is
  cleared by the existing downstream-clear helpers (`_clear_after_*`) the same way
  `class_ids` is. The `spells` step is included only when `draft["spellcasting"]`.
- **Arcane:** choose exactly `starting_spellbook_size` spells from the accessible
  list; Read Magic shown as an auto-known badge when `free_read_magic` is on.
  Exact-count validation, like the proficiencies step.
- **Divine:** read-only — "You know all level-1 <list> spells", list shown; the
  step auto-completes (nothing to submit).
- `_draft_to_spec` carries `spellbook` into each `ClassEntry`; `prepared` starts
  empty (managed on the sheet).
- Multi-class (elf Fighter/Magic-User): the step operates per casting
  `ClassEntry`; non-casting entries contribute nothing.

### 6. Sheet section — Spells (manages *both*)

`spells_view(spec, data) -> list[SpellClassView]` (one block per casting class),
shared by the live sheet and the wizard review, mirroring `magic_items_view`.
Each block:
- **Known** list (spellbook for arcane / full accessible list for divine), each
  with level, a collapsible description, and a Prepare button.
- **Prepared** list grouped by spell level with usage counts (e.g. "Level 1 — 1/1"),
  each with an Unprepare button.
- *Arcane only:* a **Learn** control (from `learnable_spells`) and a **Forget**
  control. Divine has neither (knows all).

New view models on `CharacterSheet` (e.g. `SpellEntryView`, `SpellLevelGroup`,
`SpellClassView`). `build_sheet` calls `spells_view`.

Routes mirror the equipment/magic pattern as wizard+sheet pairs:
- Sheet: `POST /character/{id}/spells/learn|forget|prepare|unprepare`
- Wizard: `POST /wizard/{id}/spells` (submit the known selection). Prepared is
  sheet-only, per the wizard=known / sheet=both split.

Each route loads spec/draft, calls the matching `engine/spells.py` mutator inside
a `try/except ValueError -> HTTPException(400)`, saves, and redirects — identical
shape to the existing magic-item routes.

### 7. Import pipeline

- **New crib** `import/cribs/spell-list.md` documenting `SpellList` and the single
  judgment call, with heuristics: *spellbook / "learns spells" → arcane*;
  *"prays for" / "access to the whole list" → divine*.
- **New prompt** `import/prompts/phase2-spell-list.md`.
- **`import/cribs/class.md` updated:** a casting class references the right
  `spell_lists`; if a referenced list is new, define it in `spell_lists.yaml`
  first. Remove any per-class caster-type guidance.
- **`import/cribs/spell.md` updated:** note that `spell_lists` references must
  resolve to a defined `SpellList`.
- **`tools/validate_import.py` updated:** every `spell_lists` id referenced by a
  class or spell must resolve to a defined `SpellList` id (referential integrity).

### 8. Seed data

- `data/spell_lists.yaml`: `magic_user` (arcane), `druid` (divine).
- `data/spells/`: `read_magic` plus a handful of L1 spells per list — e.g.
  magic-user: Magic Missile, Sleep, Charm Person, Detect Magic; druid: Faerie Fire,
  Entangle, Detect Magic (Detect Magic tagged on both lists where appropriate).
- `data/classes/magic_user.yaml`: add `spell_lists: [magic_user]`.

## Testing

- **Engine:** access rules (on-list + accessible-level), slot caps (hard),
  `free_read_magic` on/off, `learn`/`forget`/`prepare`/`unprepare` happy + error
  paths, mixed-list class rejection, divine full-list derivation.
- **Wizard:** step gating (non-caster omits step; arcane vs divine behavior),
  exact-count validation, `_draft_to_spec` spellbook round-trip, `spellcasting`
  flag cleared on upstream changes.
- **Sheet:** `spells_view` shape for arcane vs divine; route happy/error paths.
- **Settings regression:** `free_read_magic` in `IMPLEMENTED_RULES`.
- **Loader:** `spell_lists.yaml` parsed; absent file → empty dict.
- **Validator:** unresolved `spell_lists` reference fails.

## Out of scope (V1)

- Spell drag-and-drop (buttons/forms only, like magic items V1).
- Spontaneous / spell-point casters (a third mode beyond arcane/divine).
- Spellcasting that begins above level 1 in the wizard (builder is L1-only; later
  levels are gained on the sheet, where prepared/known management already applies).
- Casting-time slot mechanics during play beyond prepare/unprepare bookkeeping.
