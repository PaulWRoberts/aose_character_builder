# On-Sheet Character State Management — Design

**Date:** 2026-06-02
**Status:** Approved (design)

## Goal

Let players manage short-term character state — current hit points, spell
memorization and casting, and rest recovery — directly from the live character
sheet during play, without editing the underlying build.

This is a "play state" layer added on top of the existing "build" model. It
covers three concerns: current HP, spell **slots** (memorize / cast / restore),
and **rest** (night's rest re-memorization + full-day natural healing).

## Scope

**Included:** track current HP; apply damage / healing / set-HP; track
memorized spells as individual slots; mark slots spent when cast; arcane
memorization from the spellbook; divine memorization from the class spell list;
duplicate memorization; reversed arcane spells (stored per slot); reversed
divine spells (chosen at cast time, not stored); spell recovery via rest;
full-day 1d3 natural healing.

**Excluded:** automating spell effects; tracking spell durations; party-level
time tracking; referee-only adjudication; target validity; deity disfavour.

## Key decisions

1. **One source of truth for slots.** Replace the flat `ClassEntry.prepared:
   list[str]` with `ClassEntry.slots: list[SpellSlot]`. Each slot tracks the
   memorized spell, its normal/reversed form (arcane only), and spent state.
2. **HP stored as a damage counter.** `CharacterSpec.damage_taken: int`. Current
   HP is always derived as `max(0, max_hp − damage_taken)`. Because `max_hp` is
   itself derived live (rolls + *effective* CON), the damage-taken counter tracks
   max shifts automatically — equipping/removing a CON item changes current HP
   without rewriting stored state.
3. **Dead is derived, not sticky.** `dead == (current_hp == 0)`. Healing or
   setting HP above 0 automatically revives — consistent with the damage-taken
   model and acceptable for this single-user tool. No stored flag.
4. **No migration.** The app isn't deployed (single-user, local). The `prepared`
   field is replaced outright; no backward-compat shim.
5. **Engine organization (Approach A).** Slot + rest logic extends
   `aose/engine/spells.py` (already owns the prepared mutators and `SpellError`);
   HP state logic extends `aose/engine/hp.py` (already owns HP derivation). Both
   are cycle-free cores. No new engine module.

## Data model (`aose/models/character.py`)

New value type, alongside the existing instance types:

```python
class SpellSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: int                    # spell level this slot occupies
    spell_id: str | None = None   # None = empty/unfilled
    reversed: bool = False        # arcane only; divine ignores
    spent: bool = False           # True = cast since last rest
```

- **`ClassEntry`**: replace `prepared: list[str]` with `slots: list[SpellSlot]`.
  One row per memorized spell; duplicates allowed (two slots, same `spell_id`).
  The per-level cap from `memorizable_slots` governs how many slots of a level
  may exist. Only filled/touched slots are stored as rows (mirrors the old
  capped `prepared` list); the UI renders empty pickers up to the cap rather than
  pre-materializing empty rows.
- **`CharacterSpec`**: add `damage_taken: int = 0`.

## HP state engine (`aose/engine/hp.py`)

Thin pure functions added to the existing derivation module. Mutators return the
new `damage_taken`; the route writes `spec.damage_taken` and saves.

```python
def current_hp(spec, data) -> int:        # max(0, max_hp − damage_taken)
def is_dead(spec, data) -> bool:          # current_hp == 0
def apply_damage(spec, data, amount: int) -> int:   # amount >= 0
def apply_healing(spec, data, amount: int) -> int:  # amount >= 0
def set_current_hp(spec, data, value: int) -> int:  # clamp value to [0, max]
```

- All arithmetic clamps `damage_taken` into `[0, max_hp]`, so current HP stays in
  `[0, max]`.
- Healing a 0-HP character revives them (dead is derived).
- `set_current_hp` **clamps** out-of-range values (friendlier than erroring; the
  spec permits either).
- Negative `amount` is rejected at the route (400); the engine assumes ≥ 0.
- There is **no** separate `natural_heal` — full-day rest rolls 1d3 and calls
  `apply_healing`.

Acceptance criteria all hold: 12/12 −5 → 7/12; 7/12 −10 → 0/12 dead; 9/12 +6 →
12/12 (capped); set above max → max; set below 0 → 0.

## Spell-slot engine (`aose/engine/spells.py`)

The flat `prepare`/`unprepare` mutators are removed and replaced by slot-aware
ones. Each returns a new `ClassEntry` and raises `SpellError` on violation.

```python
def assign_slot(entry, cls, data, level, spell_id, reversed=False) -> ClassEntry
def clear_slot(entry, slot_index) -> ClassEntry
def cast_slot(entry, slot_index) -> ClassEntry
def restore_slot(entry, slot_index) -> ClassEntry
```

- `assign_slot` enforces: spell is known (arcane spellbook / divine accessible
  list), `spell.level == level`, a free slot exists at that level (cap from
  `memorizable_slots`), and `reversed` may only be set for a reversible spell on
  an arcane caster. New slot starts `spent=False`.
- `cast_slot` sets `spent=True`; raises if already spent or empty. Per-index, so
  casting one of two `Sleep` slots leaves the other available.
- `restore_slot` sets `spent=False` (single slot) — undo / referee override.
- Arcane normal/reversed is fixed at `assign_slot` time and read back when
  casting. Divine slots always store `reversed=False`; the divine cast-time
  Normal/Reversed choice is purely informational (no effect tracking) and both
  paths call `cast_slot`.

## Rest engine (`aose/engine/spells.py` slot side; rolls via `engine/dice`)

Pure slot operations on a `ClassEntry`:

```python
def restore_all_slots(entry) -> ClassEntry   # every slot.spent = False
def clear_all_slots(entry) -> ClassEntry      # drop all slot rows
```

"Choose new loadout" = `clear_all_slots` then re-assign via the normal pickers
(not a distinct engine call). No "previous loadout" is stored separately — the
slot rows already hold last night's assignment until cleared.

**Two rest modes**, orchestrated in the route (they touch HP and all classes):

- **Night's Rest** — for each casting `ClassEntry`, apply the chosen spell option
  (restore / clear / keep). No HP change.
- **Full Day Rest** — same spell handling, **plus** 1d3 healing: roll via the
  `dice` engine or accept a manually-entered 1–3 result, then `apply_healing`.
  Confirmed before applying; "interrupted = don't confirm" satisfies the spec's
  no-healing-on-interruption rule.

**Dead guard:** Rest is blocked when current HP == 0 (a corpse gets no recovery).
Disabled control in the UI; the route also rejects (400) defensively.

## Routes (`aose/web/routes.py`)

Existing load→mutate-via-engine→save→303 pattern. Invalid input → 400.

**HP (character-level):**
- `POST /character/{id}/hp/damage` — `amount` → `apply_damage`
- `POST /character/{id}/hp/heal` — `amount` → `apply_healing`
- `POST /character/{id}/hp/set` — `value` → `set_current_hp`

**Spell slots (per class):**
- `POST /character/{id}/spells/assign` — `class_id`, `level`, `spell_id`, `reversed`
- `POST /character/{id}/spells/clear` — `class_id`, `slot_index`
- `POST /character/{id}/spells/cast` — `class_id`, `slot_index`
- `POST /character/{id}/spells/restore` — `class_id`, `slot_index`

The old `spells/prepare` and `spells/unprepare` routes are removed. `spells/learn`
and `spells/forget` (spellbook management) stay unchanged.

**Rest (character-level, spans all classes):**
- `POST /character/{id}/rest/night` — `mode` (`restore`/`clear`/`keep`)
- `POST /character/{id}/rest/full-day` — same spell handling + `heal_amount`
  (1–3, manual or pre-rolled); blocked (400) if dead.

V1 uses a single shared `mode` for the whole rest (applied to every casting
class); per-`class_id` divergence can be added later. Multiclass casters are
rare enough that a shared mode is acceptable for now.

## Sheet view + templates

**`aose/sheet/view.py`:**
- `CharacterSheet` gains `current_hp: int` and `is_dead: bool` (`max_hp` already
  present), populated from the HP engine.
- `spells_view` / `SpellLevelGroup` reworked around slots: each level group
  exposes its slot rows (`slot_index`, spell name, `reversed`, `spent`,
  reversible flag) plus the free-slot count (`cap − len(rows)`) for empty
  pickers. Picker options come from `known_spells` filtered to that level.
  `SpellEntryView.reversible` (already present) drives the Normal/Reversed
  selector.

**`aose/web/templates/sheet.html`** (plain server-rendered forms, no new JS, no
DnD — consistent with the magic-items / spells UI):
- **HP block:** `current_hp / max_hp`, alive/dead badge, three forms (Damage,
  Heal, Set). Dead state styles the badge and disables Rest.
- **Spells section:** per class, per level — slot rows. Available → **Cast**
  (arcane casts the stored form; divine reversible shows **Cast Normal** /
  **Cast Reversed**, both spending). Spent → "Spent" + **Restore**. Filled slot
  has **Clear**; free slot shows a spell picker (+ Normal/Reversed selector when
  the chosen spell is reversible, arcane only).
- **Rest controls:** "Rest and Memorize Spells" (night) and "Full Day Rest"
  (full-day, with an editable 1d3 field defaulting to a rolled value). Each
  offers Restore previous / Choose new / Clear all. Disabled when dead.

## Testing

Test-first (project TDD convention). New / updated files:

- **`tests/test_hp_state.py`** — the four HP acceptance criteria verbatim;
  `current_hp` / `is_dead` derivation; damage-taken clamping into `[0, max]`;
  max shifting under a CON-boosting magic item.
- **`tests/test_spell_slots.py`** — `assign_slot` enforcement (known, level
  match, cap, reversed-only-arcane-reversible; divine never stores reversed);
  `cast_slot` spends one duplicate without the other; double-cast raises;
  `restore_slot` undoes; `clear_slot` removes one row; `restore_all_slots` /
  `clear_all_slots`.
- **`tests/test_rest.py`** — night restore vs clear; full-day applies 1d3 and
  caps at max; dead character blocked.
- **Route test additions** — new HP / slot / rest routes return 303 and persist;
  invalid input returns 400; removed `prepare`/`unprepare` routes are gone.

Existing spell-route and sheet tests that reference `prepared` are updated to the
slot model. Run `pytest tests/ -q` to confirm no regressions.

## Non-goals

Resolve spell effects; track durations automatically; decide target validity;
enforce deity disfavour; replace referee judgement.
